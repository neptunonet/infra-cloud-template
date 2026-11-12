"""Registro de pedidos en Postgres: la API nunca espera a la base ni falla por ella."""

import os
import threading
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from prometheus_client import CollectorRegistry, Counter
from test_serve import CORDOBA, PALOMAR, destino, fila  # noqa: F401 (destino es un fixture)

import serve
from registro import EscritorPostgres, Pedido, Registro


class EscritorFalso:
    def __init__(self, falla: bool = False):
        self.falla, self.pedidos, self.lotes = falla, [], 0
        self.lock = threading.Lock()

    def escribir(self, lote):
        if self.falla:
            raise ConnectionError("la base no responde")
        with self.lock:
            self.pedidos += lote
            self.lotes += 1


def contador():
    reg = CollectorRegistry()
    return reg, Counter("t_registro_total", "prueba", ["resultado"], registry=reg)


def valor(reg, resultado):
    return reg.get_sample_value("t_registro_total", {"resultado": resultado}) or 0


def test_predict_registra_el_pedido_y_cada_tramo(destino):
    esc = EscritorFalso()
    reg, c = contador()
    registro = Registro(None, contador=c, escritor=esc, espera_seg=0.05)
    with TestClient(serve.crear_app(destino, registro=registro)) as cli:
        r = cli.post("/predict", json={"filas": [fila(PALOMAR), fila(CORDOBA, anticip_h=3, votos=2)]})
        assert r.status_code == 200
    # al cerrar la app se escribe lo que quedó en la cola
    assert len(esc.pedidos) == 1 and valor(reg, "ok") == 1
    p = esc.pedidos[0]
    assert (p.resultado, p.filas, p.consumidor, p.receta) == ("ok", 2, "anonimo", "logistica_rayos")
    assert p.version.startswith("v") and p.latencia_ms > 0 and p.pod
    # (p, fuente, zona, degradado, motivo, votos, anticipacion_h): sin coordenadas
    assert len(p.predicciones) == 2 and all(len(t) == 7 for t in p.predicciones)
    assert p.predicciones[1][1:] == ("tabla_app", "no_vista", False, "zona_no_vista", 2, 3.0)
    assert p.predicciones[1][0] == r.json()["filas"][1]["p"]


def test_los_rechazados_tambien_se_registran(destino, monkeypatch):
    monkeypatch.setenv("CLAVES", "climarutero:abc123")
    esc = EscritorFalso()
    with TestClient(serve.crear_app(destino, registro=Registro(None, escritor=esc, espera_seg=0.05))) as cli:
        assert cli.post("/predict", json={"filas": [fila(PALOMAR)]}).status_code == 401
        assert cli.post("/predict", json={"filas": [fila(PALOMAR)]}, headers={"X-API-Key": "abc123"}).status_code == 200
    assert [(p.resultado, p.consumidor, len(p.predicciones)) for p in esc.pedidos] == [
        ("sin_clave", None, 0), ("ok", "climarutero", 1)]


def test_si_la_base_falla_la_api_sigue_respondiendo(destino):
    reg, c = contador()
    registro = Registro(None, contador=c, escritor=EscritorFalso(falla=True), espera_seg=0.01)
    with TestClient(serve.crear_app(destino, registro=registro)) as cli:
        assert cli.post("/predict", json={"filas": [fila(PALOMAR)]}).status_code == 200
    assert valor(reg, "error") == 1 and valor(reg, "ok") == 0


def test_agrupa_en_lotes():
    esc = EscritorFalso()
    registro = Registro(None, escritor=esc, lote=10, espera_seg=5)
    for _ in range(25):  # se encolan antes de arrancar el hilo: tiene que armar lotes de 10, 10 y 5
        registro.anotar(Pedido(datetime.now(timezone.utc), None, 1, None, "tabla_app", 1.0, "ok"))
    registro.iniciar()
    registro.cerrar()
    assert len(esc.pedidos) == 25 and esc.lotes == 3


def test_cola_llena_descarta_sin_bloquear():
    reg, c = contador()
    registro = Registro(None, contador=c, escritor=EscritorFalso(), max_cola=2)
    for _ in range(5):  # el hilo no arrancó: la cola se llena
        registro.anotar(Pedido(datetime.now(timezone.utc), None, 1, None, "tabla_app", 1.0, "ok"))
    assert valor(reg, "descartado") == 3


def test_sin_database_url_no_registra():
    registro = Registro(None)
    assert not registro.activo
    registro.anotar(Pedido(datetime.now(timezone.utc), None, 1, None, "tabla_app", 1.0, "ok"))
    registro.iniciar()
    assert registro.hilo is None and registro.cola.empty()


@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="sin TEST_DATABASE_URL (Postgres con el esquema)")
def test_escribe_en_postgres_real():
    import psycopg

    url = os.environ["TEST_DATABASE_URL"]
    marca = f"test-{datetime.now(timezone.utc).timestamp()}"
    pedido = Pedido(datetime.now(timezone.utc), marca, 2, "v20261112_073004", "logistica_rayos", 12.3, "ok",
                    predicciones=[(0.27, "modelo", "verificada", False, None, 2, 2.0),
                                  (None, "sin_dato", "verificada", False, "menos_de_dos_modelos", 1, 1.5)])
    EscritorPostgres(url).escribir([pedido])
    with psycopg.connect(url) as con:
        filas = con.execute("SELECT pr.idx, pr.p, pr.fuente, pr.motivo FROM pedidos pe JOIN predicciones pr"
                            " ON pr.pedido_id = pe.id WHERE pe.consumidor = %s ORDER BY pr.idx", (marca,)).fetchall()
        con.execute("DELETE FROM pedidos WHERE consumidor = %s", (marca,))
    assert [(i, f, m) for i, _, f, m in filas] == [(0, "modelo", None), (1, "sin_dato", "menos_de_dos_modelos")]
    assert filas[0][1] == pytest.approx(0.27) and filas[1][1] is None
