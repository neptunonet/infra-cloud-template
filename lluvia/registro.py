"""Registro de pedidos y predicciones en Postgres, en segundo plano (Trabajo Final, consigna 2.4).

/predict no espera a la base: deja el pedido en una cola y responde. Un hilo saca de la cola, junta hasta LOTE pedidos
(o lo que haya al pasar ESPERA_SEG) y los escribe en una sola transacción: `pedidos` con INSERT y `predicciones` con
COPY. Así el registro no suma latencia a las pruebas de carga.

Si la base no está o falla, la API sigue prediciendo y solo se pierde el registro de ese lote (no se reintenta: un
reintento sin tope llenaría la memoria del pod). Todo queda contado en `lluvia_registro_total{resultado=...}`:
  ok          pedidos escritos
  error       pedidos perdidos porque la escritura falló
  descartado  pedidos perdidos porque la cola estaba llena (la base no da abasto)
Sin DATABASE_URL no registra nada (como antes de tener base).

Resumen siempre, detalle por muestra: cada pedido guarda su resumen (cuántos tramos por fuente, zona y motivo, y la
probabilidad media y máxima); el detalle tramo por tramo va a `predicciones` solo en uno de cada MUESTRA pedidos (por
defecto 20; 1 = todos, 0 = ninguno). En el ensayo de carga del 12/11 guardar todos los tramos llevó la base a 4,6 GB.

Sin coordenadas (decisión 20): de cada tramo se guardan p, fuente, zona, degradado, motivo, votos y anticipación.
"""

from __future__ import annotations

import itertools
import json
import queue
import socket
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime

LOTE = 50
ESPERA_SEG = 1.0
MAX_COLA = 2000
_FIN = object()


@dataclass
class Pedido:
    recibido_utc: datetime
    consumidor: str | None
    filas: int
    version: str | None
    receta: str
    latencia_ms: float
    resultado: str
    pod: str = field(default_factory=socket.gethostname)
    resumen: dict | None = None  # None si el pedido falló
    # Una tupla por tramo: (p, fuente, zona, degradado, motivo, votos, anticipacion_h). Vacía si el pedido falló o no
    # entró en la muestra.
    predicciones: list[tuple] = field(default_factory=list)


class EscritorPostgres:
    """Escribe lotes de pedidos. Una conexión propia del hilo, que se rehace si se corta."""

    def __init__(self, url: str):
        self.url = url
        self.conexion = None

    def escribir(self, lote: list[Pedido]) -> None:
        import psycopg  # acá y no arriba: sin DATABASE_URL la API ni lo carga
        from psycopg.types.json import Jsonb

        if self.conexion is None or self.conexion.closed:
            self.conexion = psycopg.connect(self.url, connect_timeout=5, application_name="lluvia-api")
        try:
            with self.conexion.transaction(), self.conexion.cursor() as cur:
                for p in lote:
                    cur.execute(
                        "INSERT INTO pedidos (recibido_utc, consumidor, filas, version, receta, latencia_ms, resultado,"
                        " pod, resumen, con_detalle) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                        (p.recibido_utc, p.consumidor, p.filas, p.version, p.receta, p.latencia_ms, p.resultado, p.pod,
                         Jsonb(p.resumen) if p.resumen is not None else None, bool(p.predicciones)))
                    pedido_id = cur.fetchone()[0]
                    if p.predicciones:
                        with cur.copy("COPY predicciones (pedido_id, idx, p, fuente, zona, degradado, motivo, votos,"
                                      " anticipacion_h) FROM STDIN") as copia:
                            for i, fila in enumerate(p.predicciones):
                                copia.write_row((pedido_id, i, *fila))
        except Exception:
            self.conexion.close()  # la próxima vez se conecta de nuevo
            raise


class Registro:
    def __init__(self, url: str | None, contador=None, escritor=None, lote: int = LOTE,
                 espera_seg: float = ESPERA_SEG, max_cola: int = MAX_COLA, muestra: int = 1):
        self.muestra = max(0, int(muestra))
        self._numero = itertools.count()  # next() es atómico con el GIL: sirve entre los hilos de FastAPI
        self.activo = bool(url) or escritor is not None
        self.escritor = escritor or (EscritorPostgres(url) if url else None)
        self.contador = contador
        self.lote, self.espera_seg = lote, espera_seg
        self.cola: queue.Queue = queue.Queue(maxsize=max_cola)
        self.hilo: threading.Thread | None = None

    def _contar(self, resultado: str, n: int = 1) -> None:
        if self.contador is not None and n:
            self.contador.labels(resultado=resultado).inc(n)

    def detalle(self) -> bool:
        """¿Este pedido guarda sus tramos? Uno de cada `muestra` (contado en el pod, así la muestra es pareja)."""
        if not self.activo or self.muestra == 0:
            return False
        return next(self._numero) % self.muestra == 0

    def anotar(self, pedido: Pedido) -> None:
        """Nunca bloquea ni falla: si la cola está llena, el pedido se descarta y se cuenta."""
        if not self.activo:
            return
        try:
            self.cola.put_nowait(pedido)
        except queue.Full:
            self._contar("descartado")

    def iniciar(self) -> None:
        if self.activo and self.hilo is None:
            self.hilo = threading.Thread(target=self._bucle, name="registro", daemon=True)
            self.hilo.start()

    def cerrar(self, espera_seg: float = 10.0) -> None:
        """Al apagar el pod: escribe lo que quedó en la cola (hasta espera_seg)."""
        if self.hilo is None:
            return
        try:
            self.cola.put(_FIN, timeout=espera_seg)
        except queue.Full:
            pass
        self.hilo.join(timeout=espera_seg)
        self.hilo = None

    def _bucle(self) -> None:
        fin = False
        while not fin:
            lote = []
            try:
                primero = self.cola.get()
            except Exception:  # pragma: no cover
                continue
            if primero is _FIN:
                break
            lote.append(primero)
            limite = time.monotonic() + self.espera_seg
            while len(lote) < self.lote:
                resto = limite - time.monotonic()
                if resto <= 0:
                    break
                try:
                    item = self.cola.get(timeout=resto)
                except queue.Empty:
                    break
                if item is _FIN:
                    fin = True
                    break
                lote.append(item)
            self._escribir(lote)

    def _escribir(self, lote: list[Pedido]) -> None:
        try:
            self.escritor.escribir(lote)
            self._contar("ok", len(lote))
        except Exception as exc:
            self._contar("error", len(lote))
            # Sin datos del pedido en el log: solo la causa y cuántos se perdieron.
            print(json.dumps({"evento": "error_registro", "pedidos": len(lote),
                              "error": f"{type(exc).__name__}: {exc}"[:300]}), flush=True)
            time.sleep(min(self.espera_seg * 5, 5))  # no martillar una base caída
