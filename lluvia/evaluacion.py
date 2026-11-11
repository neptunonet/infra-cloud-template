"""Evaluación fuera de muestra, como en la prueba de concepto.

- Día por día: cada día se predice con un modelo entrenado hasta dos días antes (un día de separación).
- Cada caso (estación x franja) pesa 1, aunque tenga muchas emisiones.
- Margen de error: intervalo del 90 % remuestreando días enteros; las comparaciones son apareadas por día.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import recetas

SEPARACION = 1  # días que se saltean entre entrenamiento y prueba
MIN_DIAS_TRAIN = 7
VENTANA_DIAS = 14  # decisión 15: ventana mínima, se estira hasta tener evidencia
MIN_CASOS_LLUVIA = 30
MIN_DIAS_LLUVIA = 5
SENSIBILIDADES = {"avisame_todo": 0.10, "equilibrado": 0.20, "solo_probable": 0.40}  # decisión 26
BORDES_CALIBRACION = (0, 0.05, 0.1, 0.2, 0.4, 0.6, 1.0)
N_BOOTSTRAP = 1000


def ventana(d: pd.DataFrame) -> dict:
    """Últimos 14 días; si no alcanzan la evidencia mínima, se estira hacia atrás mientras queden días para entrenar."""
    dias = sorted(d.dia.unique())
    primero_posible = MIN_DIAS_TRAIN + SEPARACION
    n = VENTANA_DIAS
    while True:
        desde = max(len(dias) - n, primero_posible)
        v = d[d.dia.isin(dias[desde:])]
        casos = v.groupby("caso").y.max()
        dias_lluvia = v[v.y == 1].dia.nunique()
        suficiente = casos.sum() >= MIN_CASOS_LLUVIA and dias_lluvia >= MIN_DIAS_LLUVIA
        if suficiente or desde == primero_posible or desde >= len(dias):
            break
        n += 1
    return {
        "dias": dias[desde:],
        "desde": str(dias[desde]) if desde < len(dias) else None,
        "hasta": str(dias[-1]) if dias else None,
        "n_dias": len(dias) - desde,
        "casos": int(len(casos)),
        "casos_con_lluvia": int(casos.sum()),
        "dias_con_lluvia": int(dias_lluvia),
        "evidencia_suficiente": bool(suficiente),
    }


def predicciones_rodantes(d: pd.DataFrame, dias_prueba: list, lista_recetas: list[str]) -> pd.DataFrame:
    dias = sorted(d.dia.unique())
    partes = []
    for dia in dias_prueba:
        i = dias.index(dia)
        tr, te = d[d.dia.isin(dias[: i - SEPARACION])], d[d.dia == dia].copy()
        for r in lista_recetas:
            te[r] = recetas.predecir(r, recetas.entrenar(r, tr), te)
        partes.append(te)
    return pd.concat(partes, ignore_index=True)


def brier(x: pd.DataFrame, col: str) -> float:
    return float((x.peso * (x[col] - x.y) ** 2).sum() / x.peso.sum())


def ece(x: pd.DataFrame, col: str) -> float:
    """Error de calibración: diferencia media entre lo que dice y lo que pasa, por tramos de probabilidad."""
    tramo = pd.cut(x[col], BORDES_CALIBRACION, include_lowest=True)
    total = 0.0
    for _, g in x.groupby(tramo, observed=True):
        total += g.peso.sum() * abs(np.average(g[col], weights=g.peso) - np.average(g.y, weights=g.peso))
    return float(total / x.peso.sum())


def avisos(x: pd.DataFrame, col: str, umbral: float) -> dict:
    w, y, a = x.peso.to_numpy(), x.y.to_numpy() == 1, x[col].to_numpy() >= umbral
    acierto, falsa, perdida = (w * (a & y)).sum(), (w * (a & ~y)).sum(), (w * (~a & y)).sum()
    div = lambda n, m: float(n / m) if m else None
    return {"pod": div(acierto, acierto + perdida), "far": div(falsa, acierto + falsa),
            "csi": div(acierto, acierto + falsa + perdida), "franjas_con_aviso": div((w * a).sum(), w.sum())}


def _bootstrap(x: pd.DataFrame, f, semilla: int = 42) -> tuple[float, float]:
    rng = np.random.default_rng(semilla)
    por_dia = [g for _, g in x.groupby("dia")]
    vals = [f(pd.concat([por_dia[j] for j in rng.integers(0, len(por_dia), len(por_dia))])) for _ in range(N_BOOTSTRAP)]
    lo, hi = np.percentile(vals, [5, 95])
    return float(lo), float(hi)


def resumen(x: pd.DataFrame, col: str) -> dict:
    return {
        "brier": brier(x, col),
        "brier_ic90": list(_bootstrap(x, lambda z: brier(z, col))),
        "ece": ece(x, col),
        "sensibilidades": {k: avisos(x, col, u) for k, u in SENSIBILIDADES.items()},
    }


def comparar(x: pd.DataFrame, a: str, b: str) -> dict:
    """Brier de `a` menos el de `b`, apareado por día. Negativo = `a` es mejor."""
    f = lambda z: brier(z, a) - brier(z, b)
    lo, hi = _bootstrap(x, f)
    return {"a": a, "b": b, "dif_brier": f(x), "ic90": [lo, hi], "a_mejor": hi < 0, "a_peor": lo > 0}
