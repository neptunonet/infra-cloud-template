"""Paso 7: curva de umbrales de la logística con rayos, para decidir quién fija el umbral de aviso.

Misma prueba día por día (14 días). Para cada umbral de probabilidad: qué parte de las lluvias se avisa (POD),
qué parte de los avisos no se cumple (FAR) y en qué parte de las franjas se avisa. Como referencia, los dos
puntos de la app (1 voto o más, 2 votos o más). También mide qué tan estable es el umbral si se lo recalcula
cada día para un POD objetivo.

Uso:  uv run --with pandas --with numpy --with scikit-learn python paso7_umbral.py
"""

import numpy as np
import pandas as pd

from paso2_referencia import MIN_DIAS_TRAIN, SEPARACION, cargar, predecir
from paso3_logistica import VARIABLES, agregar_variables
from paso3b_avisos import tablero, umbral_para_pod
from paso5_rayos import RAYOS, agregar_rayos, entrenar

TODAS = VARIABLES + RAYOS
UMBRALES = (0.05, 0.08, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50)


def main() -> None:
    d = agregar_rayos(agregar_variables(cargar()))
    dias = sorted(d.dia.unique())
    partes, umbrales_dia = [], []
    for i in range(MIN_DIAS_TRAIN + SEPARACION, len(dias)):
        tr, te = d[d.dia.isin(dias[: i - SEPARACION])], d[d.dia == dias[i]]
        te = predecir(tr, te)
        m = entrenar(tr, TODAS)
        te["p"] = m.predict_proba(te[TODAS])[:, 1]
        p_tr = m.predict_proba(tr[TODAS])[:, 1]
        umbrales_dia.append({pod: umbral_para_pod(p_tr, tr.y.to_numpy(), tr.peso.to_numpy(), pod) for pod in (0.8, 0.9)})
        partes.append(te)
    te = pd.concat(partes)
    print(f"Prueba: {te.dia.nunique()} días, {te.caso.nunique()} casos, {te.groupby('caso').y.max().sum()} con lluvia")

    print(f"\n{'aviso si':<22}{'POD':>6}{'FAR':>6}{'falsas por acierto':>20}{'% franjas con aviso':>21}")
    filas = [("App: 1 voto o más", te.votos >= 1), ("App: 2 votos o más", te.votos >= 2)]
    filas += [(f"Modelo: P >= {u:.2f}", te.p >= u) for u in UMBRALES]
    for nombre, aviso in filas:
        te["a"] = aviso
        t = tablero(te, "a")
        print(f"{nombre:<22}{t['pod']:>6.2f}{t['far']:>6.2f}{t['far'] / (1 - t['far']):>20.1f}{100 * t['avisa']:>20.1f}%")

    u = pd.DataFrame(umbrales_dia)
    print("\nUmbral recalculado cada día para un POD objetivo (con los días de entrenamiento):")
    for pod in u.columns:
        print(f"  POD {pod:.0%}: entre {u[pod].min():.2f} y {u[pod].max():.2f} (mediana {u[pod].median():.2f})")


if __name__ == "__main__":
    main()
