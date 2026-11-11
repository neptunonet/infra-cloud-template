"""Recetas de modelo: cómo se entrena y cómo predice cada una.

`tabla_app` es la referencia fija: la tabla de votos que usa hoy Clima Rutero. No aprende, así que sirve igual en
cualquier región (decisión 23: responde en zona no vista).
"""

from __future__ import annotations

import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from variables import TODAS

TABLA_APP = {0: 0.05, 1: 0.21, 2: 0.47, 3: 0.78}
REFERENCIA = "tabla_app"

HIPERPARAMETROS = {
    "tabla_app": {"tabla": TABLA_APP},
    "logistica_rayos": {"C": 1.0, "max_iter": 1000},
    "lgbm_chico": dict(n_estimators=150, learning_rate=0.03, num_leaves=4, min_child_samples=500, subsample=0.8,
                       subsample_freq=1, colsample_bytree=0.8, reg_lambda=5.0, random_state=42),
}
RECETAS = tuple(HIPERPARAMETROS)
VARIABLES_DE = {"tabla_app": ["votos"], "logistica_rayos": TODAS, "lgbm_chico": TODAS}


def entrenar(receta: str, d: pd.DataFrame):
    if receta == "tabla_app":
        return None
    p = HIPERPARAMETROS[receta]
    if receta == "logistica_rayos":
        m = make_pipeline(StandardScaler(), LogisticRegression(**p))
        m.fit(d[TODAS], d.y, logisticregression__sample_weight=d.peso)
    elif receta == "lgbm_chico":
        m = LGBMClassifier(verbose=-1, n_jobs=2, **p)
        m.fit(d[TODAS], d.y, sample_weight=d.peso)
    else:
        raise ValueError(f"receta desconocida: {receta}")
    return m


def predecir(receta: str, modelo, d: pd.DataFrame):
    if receta == "tabla_app":
        return d.votos.map(TABLA_APP).to_numpy()
    return modelo.predict_proba(d[VARIABLES_DE[receta]])[:, 1]
