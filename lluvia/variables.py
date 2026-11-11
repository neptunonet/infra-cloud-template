"""Carga del dataset exportado por Clima Rutero y armado de las variables del modelo.

Lo usan el entrenamiento (train.py) y, más adelante, la API, para que las variables se calculen igual en los dos
lados. El dataset tiene una fila por estación METAR x franja de 3 h x emisión (ver TRABAJO FINAL/poc/README.md).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

MODELOS = ("gfs", "ifs", "wrf")
VARIABLES = (
    [f"{m}_{a}_log" for m in MODELOS for a in ("media", "max")]  # lluvia prevista por modelo (mm/3 h, log1p)
    + [f"{m}_edad_h" for m in MODELOS]  # antigüedad de la corrida usada
    + ["votos_media", "anticip_h", "hora_sin", "hora_cos"]
)
RAYOS = ["ray_calculado", "ray_nivel", "ray_cercania"]
TODAS = VARIABLES + RAYOS

# Filtros decididos en la prueba de concepto (decisiones 16 y 17 del TF).
FILTROS = {
    "solo_tramos_a_10km": True,
    "sin_pedidos_de_usuarios": True,
    "anticipacion_h": [0, 6],
    "modelos_disponibles": 3,
}

BOOLEANAS = ("es_api", "cerca_10km", "obs_lluvia", "obs_rayos")


def _a_bool(s: pd.Series) -> pd.Series:
    if s.dtype == bool:
        return s
    return s.map({"t": True, "f": False, True: True, False: False, "true": True, "false": False}).astype(bool)


def filtrar(d: pd.DataFrame) -> pd.DataFrame:
    """Aplica los filtros y agrega la etiqueta, el día (hora argentina), el caso y el peso por caso."""
    d = d.copy()
    for c in BOOLEANAS:
        if c in d:
            d[c] = _a_bool(d[c])
    for c in ("franja_utc", "emision_utc"):
        d[c] = pd.to_datetime(d[c])
        if d[c].dt.tz is not None:
            d[c] = d[c].dt.tz_convert("UTC").dt.tz_localize(None)
    # Un día puede aparecer en dos archivos (la carga inicial y el export diario de ese día): queda la fila con más
    # tramos, que es la del export hecho cuando ya estaba todo verificado.
    clave = ["estacion", "franja_utc", "emision_utc", "es_api", "cerca_10km"]
    d = d.sort_values("n_filas").drop_duplicates(clave, keep="last")
    lo, hi = FILTROS["anticipacion_h"]
    d = d[d.cerca_10km & ~d.es_api & d.anticip_h.between(lo, hi) & (d.disponibles_min == FILTROS["modelos_disponibles"])]
    d = d.copy()
    d["votos"] = d.votos_media.round().astype(int).clip(0, 3)
    d["y"] = d.obs_lluvia.astype(int)
    d["dia"] = (d.franja_utc - pd.Timedelta(hours=3)).dt.date
    d["caso"] = d.estacion + " " + d.franja_utc.astype(str)
    d["peso"] = 1.0 / d.groupby("caso").caso.transform("size")  # cada caso pesa 1 aunque tenga ~25 emisiones
    return d.reset_index(drop=True)


def agregar_variables(d: pd.DataFrame) -> pd.DataFrame:
    """Variables de entrada. No usa la etiqueta ni nada observado después de la emisión."""
    d = d.copy()
    for m in MODELOS:
        for a in ("media", "max"):
            d[f"{m}_{a}_log"] = np.log1p(d[f"{m}_{a}"].fillna(0))
        ciclo = pd.to_datetime(d[f"ciclo_{m}"], utc=True).dt.tz_localize(None)
        d[f"{m}_edad_h"] = ((d.emision_utc - ciclo).dt.total_seconds() / 3600).fillna(0)
    hora = (d.franja_utc - pd.Timedelta(hours=3)).dt.hour
    d["hora_sin"], d["hora_cos"] = np.sin(2 * np.pi * hora / 24), np.cos(2 * np.pi * hora / 24)
    d["ray_calculado"] = d.tormenta_nivel_max.notna().astype(int)
    d["ray_nivel"] = d.tormenta_nivel_max.fillna(0)
    d["ray_cercania"] = np.exp(-d.tormenta_dist_min / 20).fillna(0)  # 1 = encima, 0 = lejos o sin rayos
    return d


def preparar(d: pd.DataFrame) -> pd.DataFrame:
    return agregar_variables(filtrar(d))
