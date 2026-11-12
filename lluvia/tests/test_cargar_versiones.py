"""Carga de los metadata.json en Postgres: lectura del bucket (en disco), filas y la carga contra una base real."""

import os

import pytest
from conftest import datos_sinteticos

import cargar_versiones as cv
import train


@pytest.fixture(scope="module")
def destino(tmp_path_factory):
    base = tmp_path_factory.mktemp("versiones")
    datos = base / "casos.csv"
    datos_sinteticos("aprende").to_csv(datos, index=False)
    train.correr(str(datos), str(base / "modelos"), candidatas=("logistica_rayos",))
    return str(base / "modelos")


def test_lee_las_versiones_y_arma_las_filas(destino):
    ms = cv.leer_metadatas(destino)
    assert len(ms) == 1
    v = cv.fila_version(ms[0])
    assert v[0].startswith("v") and v[3] == "logistica_rayos" and v[4] is True
    assert v[11] > 0 and v[12] > 0  # casos y casos con lluvia
    ev = cv.filas_evaluacion(ms[0])
    assert {e[1] for e in ev} == {"tabla_app", "logistica_rayos"}
    assert all(e[3] <= e[2] <= e[4] for e in ev)  # el Brier cae dentro de su intervalo


def test_tolera_metadata_viejo_sin_tiempos():
    m = {"version": "v20261111_174359", "creada_utc": "2026-11-11T17:43:59+00:00", "receta": "logistica_rayos",
         "decision": {"receta_elegida": "logistica_rayos", "promovida": True, "motivo": "x"},
         "evaluacion": {"recetas": {"tabla_app": {"brier": 0.08, "ece": 0.01}}}}
    v = cv.fila_version(m)
    assert v[7] is None and v[8] is None and v[6] is None  # sin tiempos ni git_sha
    assert cv.filas_evaluacion(m)[0][3:5] == (None, None)


def test_sin_database_url_no_hace_nada(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert cv.main() == 0
    assert "sin DATABASE_URL" in capsys.readouterr().out


@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="sin TEST_DATABASE_URL (Postgres con el esquema)")
def test_carga_idempotente_en_postgres_real(destino):
    ms = cv.leer_metadatas(destino)
    version = ms[0]["version"]
    with cv.conectar(os.environ["TEST_DATABASE_URL"]) as con:
        con.execute("DELETE FROM versiones WHERE version = %s", (version,))
        try:
            assert cv.cargar(ms, con)["nuevas"] == 1
            assert cv.cargar(ms, con) == {"en_bucket": 1, "nuevas": 0, "ya_estaban": 1}  # segunda vez: nada
            n = con.execute("SELECT count(*) FROM evaluaciones WHERE version = %s", (version,)).fetchone()[0]
            receta = con.execute("SELECT metadata->>'receta' FROM versiones WHERE version = %s", (version,)).fetchone()
            assert n == 2 and receta[0] == "logistica_rayos"
        finally:
            con.execute("DELETE FROM versiones WHERE version = %s", (version,))
            con.commit()
