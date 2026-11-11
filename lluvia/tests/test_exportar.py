import json

import pandas as pd
import pytest
from conftest import datos_sinteticos

import exportar
from variables import filtrar


def _csv_de_un_dia(dia="2026-10-02"):
    d = datos_sinteticos("aprende", dias=3)
    d = d[d.franja_utc.dt.date.astype(str) == dia]
    return d[exportar.COLUMNAS].to_csv(index=False).encode()


def test_sube_el_dia_como_parquet(tmp_path, capsys):
    entrada = tmp_path / "dia.csv"
    entrada.write_bytes(_csv_de_un_dia())
    assert exportar.main(["--dia", "2026-10-02", "--destino", str(tmp_path / "datasets"), "--entrada", str(entrada)]) == 0
    d = pd.read_parquet(tmp_path / "datasets" / "2026-10-02.parquet")
    assert d.obs_lluvia.dtype == bool and len(d) > 0
    log = json.loads(capsys.readouterr().out)
    assert log["ok"] and log["filas"] == len(d)


@pytest.mark.parametrize("caso", ["vacio", "otro_dia", "columnas"])
def test_no_sube_si_algo_esta_mal(tmp_path, capsys, caso):
    crudo = _csv_de_un_dia()
    if caso == "vacio":
        crudo = crudo.split(b"\n")[0] + b"\n"
    elif caso == "columnas":
        crudo = crudo.replace(b"obs_lluvia", b"lluvia", 1)
    dia = "2026-10-03" if caso == "otro_dia" else "2026-10-02"
    entrada = tmp_path / "dia.csv"
    entrada.write_bytes(crudo)
    assert exportar.main(["--dia", dia, "--destino", str(tmp_path / "datasets"), "--entrada", str(entrada)]) == 2
    assert not (tmp_path / "datasets").exists()
    assert not json.loads(capsys.readouterr().out)["ok"]


def test_un_dia_repetido_en_dos_archivos_cuenta_una_vez():
    d = datos_sinteticos("aprende", dias=2)
    repetido = d.copy()
    repetido["n_filas"] = 20  # el export diario, con más tramos verificados
    assert len(filtrar(pd.concat([d, repetido]))) == len(filtrar(d))
