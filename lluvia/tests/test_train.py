import json
import re

import joblib
import pandas as pd
import pytest
from conftest import datos_sinteticos

import evaluacion as ev
import train
from variables import TODAS, preparar


@pytest.fixture()
def csv(tmp_path):
    def _csv(escenario, **kw):
        ruta = tmp_path / f"{escenario}.csv"
        datos_sinteticos(escenario, **kw).to_csv(ruta, index=False)
        return str(ruta)

    return _csv


def test_brier_y_calibracion():
    x = pd.DataFrame({"y": [1, 0, 1, 0], "p": [1.0, 0.0, 0.5, 0.5], "peso": 1.0})
    assert ev.brier(x, "p") == pytest.approx((0 + 0 + 0.25 + 0.25) / 4)
    assert ev.ece(x, "p") == pytest.approx(0.0)  # en cada tramo dice lo que pasa


def test_ventana_ultimos_14_dias():
    d = preparar(datos_sinteticos("aprende"))
    v = ev.ventana(d)
    assert v["n_dias"] == 14 and v["evidencia_suficiente"]


def test_promueve_un_modelo_que_le_gana_a_la_tabla(csv, tmp_path):
    destino = tmp_path / "artefactos"
    m = train.correr(csv("aprende"), str(destino), candidatas=("logistica_rayos",))

    assert re.fullmatch(r"v\d{8}_\d{6}", m["version"])
    assert m["decision"]["promovida"] and m["receta"] == "logistica_rayos"
    carpeta = destino / "versiones" / m["version"]
    meta = json.loads((carpeta / "metadata.json").read_text())
    assert meta["datos"]["archivos"][0]["sha256"]
    assert set(meta["evaluacion"]["recetas"]) == {"tabla_app", "logistica_rayos"}
    assert meta["tiempos_s"]["entrenamiento_final"] > 0 and meta["tiempos_s"]["evaluacion"] > 0
    assert set(meta["evaluacion"]["en_entrenamiento"]) == {"modelo", "tabla_app"}
    puntero = json.loads((destino / "activa.json").read_text())
    assert puntero == {**puntero, "receta": "logistica_rayos", "version": m["version"]}

    art = joblib.load(carpeta / "modelo.joblib")
    p = art["modelo"].predict_proba(preparar(datos_sinteticos("aprende", dias=2))[TODAS])[:, 1]
    assert ((p >= 0) & (p <= 1)).all()


def test_vuelta_atras_a_la_tabla(csv, tmp_path):
    destino = tmp_path / "artefactos"
    destino.mkdir()
    (destino / "activa.json").write_text(json.dumps({"receta": "logistica_rayos", "version": "v20260101_000000"}))

    m = train.correr(csv("tabla"), str(destino), candidatas=("logistica_rayos",))

    assert m["decision"]["receta_elegida"] == "tabla_app"
    assert "vuelta atrás" in m["decision"]["motivo"]
    assert not m["decision"]["promovida"]
    assert json.loads((destino / "activa.json").read_text())["receta"] == "tabla_app"
    assert (destino / "versiones" / m["version"] / "modelo.joblib").exists()  # queda en sombra


def test_sin_evidencia_no_cambia(csv, tmp_path):
    destino = tmp_path / "artefactos"
    m = train.correr(csv("aprende", estaciones=1, tasa_lluvia=0.05), str(destino), candidatas=("logistica_rayos",))

    assert not m["evaluacion"]["ventana"]["evidencia_suficiente"]
    assert m["decision"]["receta_elegida"] == "tabla_app" and not m["decision"]["promovida"]
    assert not (destino / "activa.json").exists()


def test_main_por_linea_de_comandos(csv, tmp_path, capsys):
    assert train.main(["--datos", csv("aprende"), "--destino", str(tmp_path / "a"), "--candidatas", "logistica_rayos"]) == 0
    log = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert log["evento"] == "entrenamiento" and log["promovida"]
