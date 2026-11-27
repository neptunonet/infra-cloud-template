"""Paso 3b: comparar los avisos de la logística y de la app a igual detección de lluvias.

La app avisa por votos (1 o más = «posible»; 2 o más = «probable»). Para comparar parejo, a la logística se le
busca el umbral que avisa la misma proporción de lluvias (POD) y se mira cuántas falsas alarmas tiene ahí.

Dos formas de elegir ese umbral:
  - "en prueba":  mirando los mismos días que se evalúan (optimista, sirve como techo)
  - "operativo":  cada día, con los días de entrenamiento solamente (como funcionaría de verdad)

Uso:  uv run --with pandas --with numpy --with scikit-learn python paso3b_avisos.py
"""

import numpy as np
import pandas as pd

from paso2_referencia import MIN_DIAS_TRAIN, SEPARACION, cargar, intervalo, predecir
from paso3_logistica import VARIABLES, agregar_variables, entrenar


def umbral_para_pod(p, y, w, pod: float) -> float:
    """Umbral más alto con el que se avisa al menos la proporción `pod` de las lluvias."""
    p, w = p[y == 1], w[y == 1]
    orden = np.argsort(-p)
    acumulado = np.cumsum(w[orden]) / w.sum()
    return p[orden][np.searchsorted(acumulado, pod - 1e-9)]


def tablero(te: pd.DataFrame, aviso: str) -> dict:
    w, y, a = te.peso.to_numpy(), te.y.to_numpy() == 1, te[aviso].to_numpy()
    acierto, falsa, perdida = (w * (a & y)).sum(), (w * (a & ~y)).sum(), (w * (~a & y)).sum()
    return {"pod": acierto / (acierto + perdida), "far": falsa / (acierto + falsa),
            "csi": acierto / (acierto + falsa + perdida), "avisa": (w * a).sum() / w.sum()}


def main() -> None:
    d = agregar_variables(cargar())
    dias = sorted(d.dia.unique())

    partes = []
    for i in range(MIN_DIAS_TRAIN + SEPARACION, len(dias)):
        tr, te = d[d.dia.isin(dias[: i - SEPARACION])], d[d.dia == dias[i]]
        te = predecir(tr, te)
        m = entrenar(tr)
        te["logistica"] = m.predict_proba(te[VARIABLES])[:, 1]
        p_tr, y_tr, w_tr = m.predict_proba(tr[VARIABLES])[:, 1], tr.y.to_numpy(), tr.peso.to_numpy()
        for votos in (1, 2):  # umbral operativo: iguala el POD que tuvo la app en entrenamiento
            pod_app = (w_tr * ((tr.votos >= votos) & (tr.y == 1))).sum() / (w_tr * y_tr).sum()
            te[f"umbral_op_{votos}"] = umbral_para_pod(p_tr, y_tr, w_tr, pod_app)
        partes.append(te)
    te = pd.concat(partes)
    print(f"Prueba: {te.dia.nunique()} días, {te.caso.nunique()} casos, {te.groupby('caso').y.max().sum()} con lluvia")

    for votos, nombre in ((1, "«posible» (1 voto o más)"), (2, "«probable» (2 votos o más)")):
        te["app"] = te.votos >= votos
        pod_app = tablero(te, "app")["pod"]
        u = umbral_para_pod(te.logistica.to_numpy(), te.y.to_numpy(), te.peso.to_numpy(), pod_app)
        te["log_prueba"] = te.logistica >= u
        te["log_operativo"] = te.logistica >= te[f"umbral_op_{votos}"]
        print(f"\n== Aviso {nombre} ==")
        print(f"{'quién avisa':<34}{'POD':>6}{'FAR':>6}{'CSI':>6}{'% franjas con aviso':>21}")
        filas = (("app", "App (votos)"), ("log_prueba", f"Logística, umbral en prueba {u:.2f}"),
                 ("log_operativo", "Logística, umbral operativo"))
        for col, etiqueta in filas:
            t = tablero(te, col)
            print(f"{etiqueta:<34}{t['pod']:>6.2f}{t['far']:>6.2f}{t['csi']:>6.2f}{100 * t['avisa']:>20.1f}%")
        op = te[f"umbral_op_{votos}"]
        print(f"Umbral operativo: entre {op.min():.2f} y {op.max():.2f} según el día (mediana {op.median():.2f})")
        for col in ("log_prueba", "log_operativo"):
            for met in ("pod", "far"):
                dif = lambda x: tablero(x, col)[met] - tablero(x, "app")[met]
                lo, hi = intervalo(te, dif, n=1000)
                print(f"  {met.upper()} {col} menos app: {dif(te):+.3f} (IC 90 %: {lo:+.3f} a {hi:+.3f})")


if __name__ == "__main__":
    main()
