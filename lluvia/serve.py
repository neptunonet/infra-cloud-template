"""API del servicio de probabilidad de lluvia (Trabajo Final).

Endpoints:
  POST /predict   lote de hasta 5.000 tramos -> probabilidad de lluvia de cada uno, con la zona y la fuente
  GET  /version   versión y receta que se están sirviendo
  GET  /healthz   200 cuando ya se leyó el puntero de la versión activa; 503 antes o si falla
  GET  /metrics   Prometheus

Qué responde cada tramo (decisiones 16, 23 y 24 del TF):
  - zona «verificada» (estación entrenada a <= 10 km) o «region_entrenada» (a <= 150 km): el modelo activo;
  - zona «no_vista»: la tabla de votos de la app;
  - anticipación mayor a 6 h: la tabla de votos;
  - 2 de los 3 modelos numéricos: si falta WRF, el modelo (sin WRF el Brier no cambia: H10, 13/11); si falta GFS o IFS,
    la tabla de votos, marcado como degradado;
  - menos de 2 modelos: sin dato.
Si la receta activa es la tabla (todavía no hay un modelo que le gane), todo sale de la tabla.

El umbral de aviso no está acá: lo elige quien usa la app (decisión 25).
Logs: una línea JSON por pedido, sin coordenadas ni datos de usuarios (decisión 20).
Registro: cada pedido (también los rechazados) va a Postgres en segundo plano (ver registro.py).

Variables de entorno:
  DESTINO      carpeta o gs://bucket/prefijo donde train.py deja `activa.json` y `versiones/`
  CLAVES       opcional, «consumidor:clave,...»; si está, /predict pide el encabezado X-API-Key
  RECARGA_SEG  cada cuánto se relee el puntero (por defecto 300)
  PORT         por defecto 8083
  DATABASE_URL opcional, postgresql://...; si está, cada pedido y sus predicciones se guardan en Postgres
  MUESTRA_TRAMOS  con base: guarda los tramos de uno de cada N pedidos (por defecto 20; 1 = todos, 0 = ninguno)
  CONEXION_MAX_PEDIDOS  cierra cada conexión después de N pedidos (por defecto 100; 0 = sin límite)
  CONEXION_MAX_SEG      cierra cada conexión después de N segundos (por defecto 30; 0 = sin límite)
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import threading
import time
from collections import Counter as Conteo
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import fsspec
import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, Header, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Gauge, Histogram, generate_latest
from pydantic import BaseModel, Field

import recetas
from registro import Pedido as PedidoRegistrado, Registro
from variables import MODELOS, agregar_variables

MAX_FILAS = 5000  # decisión 18
VERIFICADA_KM = 10.0  # decisión 17
REGION_KM = 150.0
ANTICIPACION_MAX_H = 6.0  # decisión 16
ESTACIONES = pd.read_csv(Path(__file__).with_name("estaciones.csv")).set_index("estacion")

REGISTRO = CollectorRegistry()
PEDIDOS = Counter("lluvia_pedidos_total", "Pedidos a /predict", ["resultado"], registry=REGISTRO)
FILAS = Counter("lluvia_filas_total", "Tramos respondidos, por fuente y zona", ["fuente", "zona"], registry=REGISTRO)
LATENCIA = Histogram("lluvia_predict_seconds", "Tiempo de /predict", registry=REGISTRO,
                     buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5))
TAMANO = Histogram("lluvia_lote_filas", "Tramos por pedido", registry=REGISTRO,
                   buckets=(1, 10, 50, 150, 500, 1000, 2500, 5000))
PROBABILIDAD = Histogram("lluvia_probabilidad", "Probabilidad devuelta (para la alerta de deriva)", registry=REGISTRO,
                         buckets=(0.05, 0.1, 0.2, 0.3, 0.4, 0.6, 0.8, 1.0))
REGISTRADOS = Counter("lluvia_registro_total", "Pedidos llevados a Postgres, por resultado", ["resultado"],
                      registry=REGISTRO)
CONEXIONES_CERRADAS = Counter("lluvia_conexiones_cerradas_total", "Conexiones que la API pidió cerrar (para repartir)",
                              ["motivo"], registry=REGISTRO)
VERSION = Gauge("lluvia_version_info", "Versión servida (valor 1)", ["version", "receta"], registry=REGISTRO)


class Fila(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    hora_paso_utc: datetime
    emision_utc: datetime
    votos: int = Field(ge=0, le=3)
    lluvia_mm_3h: dict[str, float | None] = Field(description="lluvia prevista por modelo: gfs, ifs, wrf")
    ciclos: dict[str, datetime | None] = Field(description="corrida usada de cada modelo")
    tormenta_nivel: int | None = Field(default=None, ge=0, le=2)
    tormenta_dist_km: float | None = Field(default=None, ge=0)


class Pedido(BaseModel):
    filas: list[Fila] = Field(min_length=1)


def _distancia_km(lat, lon, lat2, lon2):
    la1, lo1, la2, lo2 = map(np.radians, (lat[:, None], lon[:, None], lat2[None, :], lon2[None, :]))
    a = np.sin((la2 - la1) / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(a))


def _utc(s: pd.Series) -> pd.Series:
    s = pd.to_datetime(s, utc=True)
    return s.dt.tz_localize(None)


class Estado:
    """Lo que se está sirviendo. Se relee del puntero cada RECARGA_SEG segundos."""

    def __init__(self, destino: str | None):
        self.destino = (destino or "").rstrip("/")
        self.lock = threading.Lock()
        self.receta, self.version, self.modelo = recetas.REFERENCIA, None, None
        self.estaciones = np.empty((0, 2))
        self.listo, self.error, self.cargado_utc = False, None, None

    def _leer(self, ruta: str) -> bytes:
        fs, p = fsspec.core.url_to_fs(f"{self.destino}/{ruta}")
        return fs.cat_file(p)

    def cargar(self) -> None:
        try:
            if not self.destino:
                raise RuntimeError("falta la variable DESTINO")
            fs, p = fsspec.core.url_to_fs(f"{self.destino}/activa.json")
            puntero = json.loads(fs.cat_file(p)) if fs.exists(p) else {"receta": recetas.REFERENCIA, "version": None}
            version = puntero.get("version")
            if version == self.version and self.listo:
                return
            if version:
                art = joblib.load(io.BytesIO(self._leer(f"versiones/{version}/modelo.joblib")))
                meta = json.loads(self._leer(f"versiones/{version}/metadata.json"))
                codigos = [e for e in meta["datos"].get("estaciones", []) if e in ESTACIONES.index]
                coords = ESTACIONES.loc[codigos, ["lat", "lon"]].to_numpy(dtype=float)
                receta, modelo = art["receta"], art["modelo"]
            else:
                receta, modelo, coords = recetas.REFERENCIA, None, np.empty((0, 2))
            with self.lock:
                self.receta, self.version, self.modelo, self.estaciones = receta, version, modelo, coords
                self.listo, self.error = True, None
                self.cargado_utc = datetime.now(timezone.utc).isoformat()
            VERSION.clear()
            VERSION.labels(version=version or "ninguna", receta=receta).set(1)
            print(json.dumps({"evento": "version_cargada", "version": version, "receta": receta}), flush=True)
        except Exception as exc:  # se sigue sirviendo lo que había; /healthz muestra la causa si nunca cargó
            self.error = f"{type(exc).__name__}: {exc}"
            print(json.dumps({"evento": "error_carga", "error": self.error}), flush=True)

    def predecir(self, filas: list[Fila]) -> list[dict]:
        with self.lock:
            receta, modelo, estaciones = self.receta, self.modelo, self.estaciones
        n = len(filas)
        d = pd.DataFrame({
            "lat": [f.lat for f in filas], "lon": [f.lon for f in filas],
            "hora_paso": _utc(pd.Series([f.hora_paso_utc for f in filas])),
            "emision_utc": _utc(pd.Series([f.emision_utc for f in filas])),
            "votos": [f.votos for f in filas],
            "tormenta_nivel_max": [f.tormenta_nivel for f in filas],
            "tormenta_dist_min": [f.tormenta_dist_km for f in filas],
        })
        for m in MODELOS:
            mm = pd.Series([f.lluvia_mm_3h.get(m) for f in filas], dtype=float)
            d[f"{m}_media"], d[f"{m}_max"] = mm, mm
            # Sin pronóstico del modelo, tampoco su corrida: la edad queda en 0, como se evaluó en H10.
            d[f"ciclo_{m}"] = pd.Series([f.ciclos.get(m) if f.lluvia_mm_3h.get(m) is not None else None for f in filas],
                                        dtype=object)
        d["tormenta_nivel_max"] = d.tormenta_nivel_max.astype(float)
        d["tormenta_dist_min"] = d.tormenta_dist_min.astype(float)
        d["franja_utc"] = d.hora_paso.dt.floor("3h")
        d["anticip_h"] = (d.hora_paso - d.emision_utc).dt.total_seconds() / 3600
        d["votos_media"] = d.votos.astype(float)
        disponibles = d[[f"{m}_media" for m in MODELOS]].notna().sum(axis=1).to_numpy()
        # H10 (13/11): sin WRF el modelo no pierde nada y le gana a la tabla; sin GFS o IFS empata con ella.
        degradado = (disponibles == 2) & d.wrf_media.notna().to_numpy()

        if len(estaciones):
            dist = _distancia_km(d.lat.to_numpy(), d.lon.to_numpy(), estaciones[:, 0], estaciones[:, 1]).min(axis=1)
        else:
            dist = np.full(n, np.inf)
        zona = np.where(dist <= VERIFICADA_KM, "verificada", np.where(dist <= REGION_KM, "region_entrenada", "no_vista"))

        motivo = np.full(n, None, dtype=object)
        motivo[zona == "no_vista"] = "zona_no_vista"
        motivo[d.anticip_h.to_numpy() > ANTICIPACION_MAX_H] = "anticipacion_mayor_6h"
        motivo[d.anticip_h.to_numpy() < 0] = "emision_posterior_al_paso"
        if receta == recetas.REFERENCIA:  # no hay modelo activo: todo sale de la tabla, sea cual sea la zona
            motivo[:] = "receta_activa_tabla"
        motivo[degradado] = "dos_modelos"
        motivo[disponibles < 2] = "menos_de_dos_modelos"

        p = d.votos.map(recetas.TABLA_APP).to_numpy(dtype=float)
        usa_modelo = pd.isna(motivo)
        if usa_modelo.any():
            x = agregar_variables(d.loc[usa_modelo].copy())
            p[usa_modelo] = recetas.predecir(receta, modelo, x)
        fuente = np.where(usa_modelo, "modelo", "tabla_app")
        sin_dato = disponibles < 2
        fuente[sin_dato] = "sin_dato"

        salida = []
        for i in range(n):
            salida.append({
                "p": None if sin_dato[i] else round(float(p[i]), 4),
                "fuente": str(fuente[i]),
                "zona": str(zona[i]),
                "degradado": bool(degradado[i]),
                "motivo": motivo[i],
            })
            FILAS.labels(fuente=str(fuente[i]), zona=str(zona[i])).inc()
            if not sin_dato[i]:
                PROBABILIDAD.observe(float(p[i]))
        return salida


def _resumen(filas: list[dict]) -> dict:
    """Lo que se guarda de cada pedido aunque no entre en la muestra: conteos y probabilidad, sin coordenadas."""
    ps = [f["p"] for f in filas if f["p"] is not None]
    contar = lambda clave: dict(Conteo(f[clave] for f in filas if f[clave] is not None))
    return {"fuente": contar("fuente"), "zona": contar("zona"), "motivo": contar("motivo"),
            "degradados": sum(f["degradado"] for f in filas), "sin_dato": len(filas) - len(ps),
            "p_media": round(sum(ps) / len(ps), 4) if ps else None, "p_max": max(ps) if ps else None}


class CierreDeConexiones:
    """Pide cerrar cada conexión después de `max_pedidos` pedidos o `max_seg` segundos (`Connection: close`).

    Kubernetes reparte CONEXIONES entre los pods, no pedidos: un cliente con conexiones persistentes (keep-alive) sigue
    mandando todo a los pods que había cuando se conectó. En el k3d, el HPA escaló de 1 a 5 réplicas y los 7.036 pedidos
    los atendió el pod original. Cerrando cada tanto, el cliente reconecta y kube-proxy vuelve a elegir pod, así las
    réplicas nuevas reciben trabajo. Reconectar cuesta unos ms cada `max_pedidos` pedidos.

    Middleware ASGI puro: la conexión se identifica por la IP y el puerto del cliente (cada conexión TCP tiene el suyo).
    """

    def __init__(self, app, max_pedidos: int = 100, max_seg: float = 30.0):
        self.app, self.max_pedidos, self.max_seg = app, max_pedidos, max_seg
        self.conexiones: dict[tuple, list] = {}  # (ip, puerto) -> [pedidos, abierta_desde]

    def _cerrar(self, cliente) -> str | None:
        ahora = time.monotonic()
        if len(self.conexiones) > 1000:  # conexiones que se cerraron solas: no crecer sin tope
            viejas = 2 * self.max_seg if self.max_seg else 600
            self.conexiones = {k: v for k, v in self.conexiones.items() if ahora - v[1] < viejas}
        dato = self.conexiones.setdefault(cliente, [0, ahora])
        dato[0] += 1
        if self.max_pedidos and dato[0] >= self.max_pedidos:
            motivo = "pedidos"
        elif self.max_seg and ahora - dato[1] >= self.max_seg:
            motivo = "tiempo"
        else:
            return None
        del self.conexiones[cliente]
        return motivo

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("client") or not (self.max_pedidos or self.max_seg):
            return await self.app(scope, receive, send)
        motivo = self._cerrar(tuple(scope["client"]))
        if motivo is None:
            return await self.app(scope, receive, send)

        async def enviar(mensaje):
            if mensaje["type"] == "http.response.start":
                mensaje["headers"] = [*mensaje.get("headers", []), (b"connection", b"close")]
                CONEXIONES_CERRADAS.labels(motivo=motivo).inc()
            await send(mensaje)

        return await self.app(scope, receive, enviar)


def _claves() -> dict[str, str]:
    """«consumidor:clave,...» -> {clave: consumidor}."""
    out = {}
    for par in filter(None, os.environ.get("CLAVES", "").split(",")):
        nombre, _, clave = par.partition(":")
        out[clave.strip()] = nombre.strip()
    return out


def crear_app(destino: str | None = None, registro: Registro | None = None) -> FastAPI:
    estado = Estado(destino if destino is not None else os.environ.get("DESTINO"))
    registro = registro or Registro(os.environ.get("DATABASE_URL"), contador=REGISTRADOS,
                                    muestra=int(os.environ.get("MUESTRA_TRAMOS", "20")))
    recarga = float(os.environ.get("RECARGA_SEG", "300"))
    claves = _claves()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        registro.iniciar()
        await asyncio.to_thread(estado.cargar)

        async def bucle():
            while True:
                await asyncio.sleep(recarga)
                await asyncio.to_thread(estado.cargar)

        tarea = asyncio.create_task(bucle())
        yield
        tarea.cancel()
        await asyncio.to_thread(registro.cerrar)

    app = FastAPI(title="lluvia", version="1.0.0", lifespan=lifespan)
    app.add_middleware(CierreDeConexiones, max_pedidos=int(os.environ.get("CONEXION_MAX_PEDIDOS", "100")),
                       max_seg=float(os.environ.get("CONEXION_MAX_SEG", "30")))
    app.state.estado = estado
    app.state.registro = registro

    @app.get("/")
    def indice() -> dict:
        return {"servicio": "lluvia", "endpoints": ["POST /predict", "GET /version", "GET /healthz", "GET /metrics"]}

    @app.get("/healthz")
    def healthz(response: Response) -> dict:
        if not estado.listo:
            response.status_code = 503
            return {"estado": "cargando", "error": estado.error}
        return {"estado": "ok", "version": estado.version, "receta": estado.receta}

    @app.get("/version")
    def version() -> dict:
        return {"version": estado.version, "receta": estado.receta, "cargado_utc": estado.cargado_utc,
                "error_ultima_recarga": estado.error}

    @app.get("/metrics")
    def metrics() -> Response:
        return Response(generate_latest(REGISTRO), media_type=CONTENT_TYPE_LATEST)

    def anotar(pedido: Pedido, t0: float, recibido: datetime, resultado: str, consumidor: str | None,
               filas: list[dict] | None = None) -> float:
        """Deja el pedido en la cola del registro y devuelve la latencia en segundos."""
        dt = time.perf_counter() - t0
        predicciones, resumen = [], (_resumen(filas) if filas else None)
        if filas and registro.detalle():
            anticip = ((_utc(pd.Series([f.hora_paso_utc for f in pedido.filas]))
                        - _utc(pd.Series([f.emision_utc for f in pedido.filas]))).dt.total_seconds() / 3600).tolist()
            predicciones = [(f["p"], f["fuente"], f["zona"], f["degradado"], f["motivo"], e.votos, round(a, 2))
                            for f, e, a in zip(filas, pedido.filas, anticip)]
        registro.anotar(PedidoRegistrado(recibido_utc=recibido, consumidor=consumidor, filas=len(pedido.filas),
                                         version=estado.version, receta=estado.receta,
                                         latencia_ms=round(dt * 1000, 2), resultado=resultado,
                                         resumen=resumen, predicciones=predicciones))
        return dt

    @app.post("/predict")
    def predict(pedido: Pedido, x_api_key: str | None = Header(default=None)) -> dict:
        t0, recibido = time.perf_counter(), datetime.now(timezone.utc)
        consumidor = "anonimo"
        if claves:
            if x_api_key not in claves:
                PEDIDOS.labels(resultado="sin_clave").inc()
                anotar(pedido, t0, recibido, "sin_clave", None)
                raise HTTPException(status_code=401, detail="falta X-API-Key o no es válida")
            consumidor = claves[x_api_key]
        if len(pedido.filas) > MAX_FILAS:
            PEDIDOS.labels(resultado="lote_grande").inc()
            anotar(pedido, t0, recibido, "lote_grande", consumidor)
            raise HTTPException(status_code=413, detail=f"máximo {MAX_FILAS} tramos por pedido")
        if not estado.listo:
            PEDIDOS.labels(resultado="no_listo").inc()
            anotar(pedido, t0, recibido, "no_listo", consumidor)
            raise HTTPException(status_code=503, detail="el servicio todavía no cargó la versión activa")
        filas = estado.predecir(pedido.filas)
        dt = time.perf_counter() - t0
        LATENCIA.observe(dt)
        TAMANO.observe(len(filas))
        PEDIDOS.labels(resultado="ok").inc()
        anotar(pedido, t0, recibido, "ok", consumidor, filas)
        fuentes = pd.Series([f["fuente"] for f in filas]).value_counts().to_dict()
        print(json.dumps({"evento": "predict", "consumidor": consumidor, "filas": len(filas), "fuentes": fuentes,
                          "version": estado.version, "ms": round(dt * 1000, 1)}), flush=True)
        return {"version": estado.version, "receta": estado.receta, "filas": filas}

    return app


app = crear_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8083")))
