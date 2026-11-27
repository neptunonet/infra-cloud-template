"""Paso 5 (se hizo antes que el 4): ¿los rayos suman por encima de los pronósticos?

El aviso de rayos (nowcast GLM) solo se calcula cuando el paso por el tramo cae dentro de los 60 minutos
siguientes a la emisión. Por eso se evalúa en tres conjuntos:
  - todo:        todas las emisiones (la mayoría sin aviso calculado)
  - con_aviso:   solo emisiones con el aviso calculado
  - limpio:      con aviso calculado y emitidas ANTES de que empiece la franja de 3 h
                 (así el rayo no puede ser consecuencia de una lluvia que ya empezó en esa franja)

Se comparan dos logísticas iguales, una sin y otra con las variables de rayos (ablación).

Uso:  uv run --with pandas --with numpy --with scikit-learn python paso5_rayos.py
"""

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from paso2_referencia import MIN_DIAS_TRAIN, SEPARACION, cargar, intervalo, metricas, predecir
from paso3_logistica import VARIABLES, agregar_variables
from paso3b_avisos import tablero, umbral_para_pod

RAYOS = ["ray_calculado", "ray_nivel", "ray_cercania"]


def agregar_rayos(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    d["ray_calculado"] = d.tormenta_nivel_max.notna().astype(int)
    d["ray_nivel"] = d.tormenta_nivel_max.fillna(0)  # 0 nada, 1 atención, 2 llegando
    d["ray_cercania"] = np.exp(-d.tormenta_dist_min / 20).fillna(0)  # 1 = encima, 0 = lejos o sin rayos
    d["antes_de_franja"] = d.emision_utc < d.franja_utc
    return d


def entrenar(tr: pd.DataFrame, variables: list[str]):
    m = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=1000))
    m.fit(tr[variables], tr.y, logisticregression__sample_weight=tr.peso)
    return m


def repesar(te: pd.DataFrame) -> pd.DataFrame:
    te = te.copy()
    te["peso"] = 1.0 / te.groupby("caso").caso.transform("size")
    return te


def informe(te: pd.DataFrame, titulo: str) -> None:
    te = repesar(te)
    casos = te.groupby("caso").y.max()
    print(f"\n== {titulo} ==")
    print(f"{len(te)} emisiones, {len(casos)} casos, {casos.sum()} con lluvia, {te[te.y == 1].dia.nunique()} días con lluvia")
    print(f"{'modelo':<14}{'Brier':>8}{'IC 90 %':>18}")
    for col in ("tabla_app", "sin_rayos", "con_rayos"):
        lo, hi = intervalo(te, lambda x: metricas(x, col)["brier"], n=1000)
        print(f"{col:<14}{metricas(te, col)['brier']:>8.4f}{f'{lo:.3f} a {hi:.3f}':>18}")
    dif = lambda x: metricas(x, "con_rayos")["brier"] - metricas(x, "sin_rayos")["brier"]
    lo, hi = intervalo(te, dif, n=1000)
    print(f"Brier con rayos menos sin rayos: {dif(te):+.4f} (IC 90 %: {lo:+.4f} a {hi:+.4f}); negativa = los rayos suman")

    # Avisos a igual detección que la app («posible» = 1 voto o más), umbral buscado en la misma prueba.
    te["a_app"] = te.votos >= 1
    pod = tablero(te, "a_app")["pod"]
    print(f"{'aviso «posible»':<22}{'POD':>6}{'FAR':>6}{'% con aviso':>13}")
    for col, nombre in (("a_app", "App (votos)"), ("sin_rayos", "Logística sin rayos"), ("con_rayos", "Logística con rayos")):
        if col != "a_app":
            u = umbral_para_pod(te[col].to_numpy(), te.y.to_numpy(), te.peso.to_numpy(), pod)
            te["a_" + col], col = te[col] >= u, "a_" + col
        t = tablero(te, col)
        print(f"{nombre:<22}{t['pod']:>6.2f}{t['far']:>6.2f}{100 * t['avisa']:>12.1f}%")
    dif = lambda x: tablero(x, "a_con_rayos")["far"] - tablero(x, "a_sin_rayos")["far"]
    lo, hi = intervalo(te, dif, n=1000)
    print(f"FAR con rayos menos sin rayos: {dif(te):+.3f} (IC 90 %: {lo:+.3f} a {hi:+.3f})")


def main() -> None:
    d = agregar_rayos(agregar_variables(cargar()))
    dias = sorted(d.dia.unique())

    partes = []
    for i in range(MIN_DIAS_TRAIN + SEPARACION, len(dias)):
        tr, te = d[d.dia.isin(dias[: i - SEPARACION])], d[d.dia == dias[i]]
        te = predecir(tr, te)
        te["sin_rayos"] = entrenar(tr, VARIABLES).predict_proba(te[VARIABLES])[:, 1]
        te["con_rayos"] = entrenar(tr, VARIABLES + RAYOS).predict_proba(te[VARIABLES + RAYOS])[:, 1]
        partes.append(te)
    te = pd.concat(partes)

    # Dato crudo: frecuencia de lluvia según el nivel del aviso, en el conjunto limpio.
    limpio = repesar(te[(te.ray_calculado == 1) & te.antes_de_franja])
    print("\nConjunto limpio: frecuencia de lluvia según pronóstico y aviso de rayos (cada caso pesa 1)")
    limpio["pronostico"] = np.where(limpio.votos >= 1, "dice lluvia", "no dice lluvia")
    limpio["aviso"] = limpio.ray_nivel.map({0: "0 nada", 1: "1 atención", 2: "2 llegando"})
    crudo = limpio.groupby(["pronostico", "aviso"]).apply(
        lambda g: pd.Series({"casos": g.peso.sum(), "llovio": np.average(g.y, weights=g.peso)}), include_groups=False)
    print(crudo.round(2).to_string())

    informe(te, "Todo (14 días de prueba)")
    informe(te[te.ray_calculado == 1], "Solo emisiones con aviso calculado")
    informe(te[(te.ray_calculado == 1) & te.antes_de_franja], "Limpio: aviso calculado y emitido antes de la franja")

    m = entrenar(d, VARIABLES + RAYOS)
    coef = pd.Series(m[-1].coef_[0], index=VARIABLES + RAYOS)
    print("\nCoeficientes de las variables de rayos (todos los días, estandarizadas):")
    print(coef[RAYOS].round(2).to_string())


if __name__ == "__main__":
    main()
