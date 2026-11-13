from datetime import datetime, timedelta, timezone

import pytest
from conftest import datos_sinteticos
from fastapi.testclient import TestClient

import serve
import train
from variables import MODELOS

PALOMAR = (-34.61, -58.613)  # estación entrenada: zona verificada
LUJAN = (-34.57, -59.10)  # a ~30 km de Moreno: región entrenada
CORDOBA = (-31.32, -64.21)  # sin estaciones entrenadas cerca: no vista


def fila(lugar, anticip_h=2.0, modelos=MODELOS, votos=1, mm=2.0):
    hp = datetime(2026, 11, 1, 15, 30, tzinfo=timezone.utc)
    return {
        "lat": lugar[0], "lon": lugar[1],
        "hora_paso_utc": hp.isoformat(), "emision_utc": (hp - timedelta(hours=anticip_h)).isoformat(),
        "votos": votos,
        "lluvia_mm_3h": {m: (mm if m in modelos else None) for m in MODELOS},
        "ciclos": {m: (hp - timedelta(hours=8)).isoformat() for m in MODELOS},
    }


@pytest.fixture(scope="module")
def destino(tmp_path_factory):
    base = tmp_path_factory.mktemp("lluvia")
    datos = base / "casos.csv"
    datos_sinteticos("aprende").to_csv(datos, index=False)
    m = train.correr(str(datos), str(base / "artefactos"), candidatas=("logistica_rayos",))
    assert m["decision"]["promovida"]
    return str(base / "artefactos")


@pytest.fixture()
def cliente(destino):
    with TestClient(serve.crear_app(destino)) as c:
        yield c


def test_healthz_y_version(cliente):
    r = cliente.get("/healthz")
    assert r.status_code == 200 and r.json()["receta"] == "logistica_rayos"
    assert cliente.get("/version").json()["version"].startswith("v")


def test_zonas_y_fuentes(cliente):
    r = cliente.post("/predict", json={"filas": [fila(PALOMAR), fila(LUJAN), fila(CORDOBA)]})
    assert r.status_code == 200
    f = r.json()["filas"]
    assert [x["zona"] for x in f] == ["verificada", "region_entrenada", "no_vista"]
    assert [x["fuente"] for x in f] == ["modelo", "modelo", "tabla_app"]
    assert f[2]["p"] == 0.21 and f[2]["motivo"] == "zona_no_vista"
    assert all(0 <= x["p"] <= 1 for x in f)


def test_casos_que_no_usan_el_modelo(cliente):
    filas = [fila(PALOMAR, anticip_h=8), fila(PALOMAR, modelos=("gfs", "wrf")), fila(PALOMAR, modelos=("gfs",))]
    f = cliente.post("/predict", json={"filas": filas}).json()["filas"]
    assert f[0]["fuente"] == "tabla_app" and f[0]["motivo"] == "anticipacion_mayor_6h"
    assert f[1]["fuente"] == "tabla_app" and f[1]["degradado"] and f[1]["motivo"] == "dos_modelos"
    assert f[2]["fuente"] == "sin_dato" and f[2]["p"] is None


def test_sin_wrf_responde_el_modelo(cliente):
    # H10 (13/11): sin WRF el Brier no cambia; sin GFS o IFS sigue la tabla.
    filas = [fila(PALOMAR, modelos=("gfs", "ifs")), fila(PALOMAR, modelos=("ifs", "wrf"))]
    f = cliente.post("/predict", json={"filas": filas}).json()["filas"]
    assert f[0]["fuente"] == "modelo" and not f[0]["degradado"] and f[0]["motivo"] is None
    assert f[1]["fuente"] == "tabla_app" and f[1]["degradado"]


def test_mas_lluvia_prevista_da_mas_probabilidad(cliente):
    f = cliente.post("/predict", json={"filas": [fila(PALOMAR, mm=0.0), fila(PALOMAR, mm=8.0)]}).json()["filas"]
    assert f[1]["p"] > f[0]["p"]


def test_tope_del_lote(cliente):
    r = cliente.post("/predict", json={"filas": [fila(PALOMAR)] * (serve.MAX_FILAS + 1)})
    assert r.status_code == 413


def test_clave_por_consumidor(destino, monkeypatch):
    monkeypatch.setenv("CLAVES", "climarutero:abc123")
    with TestClient(serve.crear_app(destino)) as c:
        assert c.post("/predict", json={"filas": [fila(PALOMAR)]}).status_code == 401
        r = c.post("/predict", json={"filas": [fila(PALOMAR)]}, headers={"X-API-Key": "abc123"})
        assert r.status_code == 200


def test_sin_version_activa_responde_la_tabla(tmp_path):
    with TestClient(serve.crear_app(str(tmp_path))) as c:
        assert c.get("/healthz").json()["receta"] == "tabla_app"
        f = c.post("/predict", json={"filas": [fila(PALOMAR, votos=2)]}).json()["filas"][0]
        assert f["p"] == 0.47 and f["motivo"] == "receta_activa_tabla"


def test_sin_destino_no_esta_listo():
    with TestClient(serve.crear_app("")) as c:
        assert c.get("/healthz").status_code == 503


def test_metricas(cliente):
    cliente.post("/predict", json={"filas": [fila(PALOMAR)]})
    texto = cliente.get("/metrics").text
    assert "lluvia_filas_total" in texto and "lluvia_version_info" in texto


def test_cierra_la_conexion_cada_n_pedidos(destino, monkeypatch):
    monkeypatch.setenv("CONEXION_MAX_PEDIDOS", "3")
    with TestClient(serve.crear_app(destino)) as c:  # TestClient usa siempre el mismo cliente: una sola «conexión»
        cierres = [c.get("/healthz").headers.get("connection") for _ in range(7)]
    assert cierres == [None, None, "close", None, None, "close", None]


def test_sin_limite_no_cierra(destino, monkeypatch):
    monkeypatch.setenv("CONEXION_MAX_PEDIDOS", "0")
    monkeypatch.setenv("CONEXION_MAX_SEG", "0")
    with TestClient(serve.crear_app(destino)) as c:
        assert all(c.get("/healthz").headers.get("connection") is None for _ in range(5))


def test_cierra_por_tiempo(destino, monkeypatch):
    monkeypatch.setenv("CONEXION_MAX_PEDIDOS", "0")
    monkeypatch.setenv("CONEXION_MAX_SEG", "30")
    reloj = [1000.0]
    monkeypatch.setattr(serve.time, "monotonic", lambda: reloj[0])
    with TestClient(serve.crear_app(destino)) as c:
        assert c.get("/healthz").headers.get("connection") is None
        reloj[0] += 31
        assert c.get("/healthz").headers.get("connection") == "close"
