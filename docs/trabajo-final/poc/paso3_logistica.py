"""Paso 3 de la prueba de concepto: regresión logística contra las tablas de votos.

Misma evaluación que el paso 2 (mismos filtros, mismos días, cada caso pesa 1).
Variables: solo pronósticos y contexto de la emisión. Los rayos quedan para el paso 5 (ablación).

Uso:  uv run --with pandas --with numpy --with scikit-learn python paso3_logistica.py
"""

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from paso2_referencia import MIN_DIAS_TRAIN, SEPARACION, cargar, intervalo, metricas, predecir

MODELOS = ("gfs", "ifs", "wrf")
VARIABLES = (
    [f"{m}_{a}_log" for m in MODELOS for a in ("media", "max")]  # lluvia prevista por modelo (mm/3 h)
    + [f"{m}_edad_h" for m in MODELOS]  # antigüedad de la corrida usada
    + ["votos_media", "anticip_h", "hora_sin", "hora_cos"]
)


def agregar_variables(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    for m in MODELOS:
        for a in ("media", "max"):
            d[f"{m}_{a}_log"] = np.log1p(d[f"{m}_{a}"])
        ciclo = pd.to_datetime(d[f"ciclo_{m}"], utc=True).dt.tz_localize(None)
        d[f"{m}_edad_h"] = (d.emision_utc - ciclo).dt.total_seconds() / 3600
    hora = (d.franja_utc - pd.Timedelta(hours=3)).dt.hour  # hora argentina de la franja
    d["hora_sin"], d["hora_cos"] = np.sin(2 * np.pi * hora / 24), np.cos(2 * np.pi * hora / 24)
    return d


def entrenar(tr: pd.DataFrame):
    m = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=1000))
    m.fit(tr[VARIABLES], tr.y, logisticregression__sample_weight=tr.peso)
    return m


def predecir_todo(tr: pd.DataFrame, te: pd.DataFrame) -> pd.DataFrame:
    te = predecir(tr, te)  # climatología y las dos tablas
    te["logistica"] = entrenar(tr).predict_proba(te[VARIABLES])[:, 1]
    return te


def informe(te: pd.DataFrame, titulo: str) -> None:
    casos = te.groupby("caso").y.max()
    print(f"\n== {titulo} ==")
    print(f"Prueba: {te.dia.nunique()} días, {len(casos)} casos, {casos.sum()} con lluvia, "
          f"{te[te.y == 1].dia.nunique()} días con lluvia")
    print(f"{'modelo':<14}{'Brier':>8}{'IC 90 %':>18}{'POD':>7}{'FAR':>7}{'CSI':>7}")
    for col in ("tabla_app", "tabla_recal", "logistica"):
        m = metricas(te, col)
        lo, hi = intervalo(te, lambda x: metricas(x, col)["brier"])
        print(f"{col:<14}{m['brier']:>8.4f}{f'{lo:.3f} a {hi:.3f}':>18}{m['pod']:>7.2f}{m['far']:>7.2f}{m['csi']:>7.2f}")
    for ref in ("tabla_app", "tabla_recal"):
        dif = lambda x: metricas(x, "logistica")["brier"] - metricas(x, ref)["brier"]
        lo, hi = intervalo(te, dif)
        print(f"Brier logística menos {ref}: {dif(te):+.4f} (IC 90 %: {lo:+.4f} a {hi:+.4f}); negativa = gana la logística")
    gana = [metricas(g, "logistica")["brier"] < metricas(g, "tabla_app")["brier"] for _, g in te.groupby("dia")]
    print(f"Días en que la logística le gana a la tabla de la app: {sum(gana)} de {len(gana)}")


def main() -> None:
    d = agregar_variables(cargar())
    dias = sorted(d.dia.unique())

    corte = int(len(dias) * 2 / 3)
    tr = d[d.dia.isin(dias[:corte])]
    informe(predecir_todo(tr, d[d.dia.isin(dias[corte + SEPARACION:])]), "A) Un solo corte")

    partes = []
    for i in range(MIN_DIAS_TRAIN + SEPARACION, len(dias)):
        partes.append(predecir_todo(d[d.dia.isin(dias[: i - SEPARACION])], d[d.dia == dias[i]]))
    te = pd.concat(partes)
    informe(te, "B) Día por día (reentrenando cada día)")

    # Qué aprendió: coeficientes del modelo entrenado con todos los días (variables estandarizadas).
    m = entrenar(d)
    coef = pd.Series(m[-1].coef_[0], index=VARIABLES).sort_values(key=abs, ascending=False)
    print("\nCoeficientes (todos los días, variables estandarizadas):")
    print(coef.round(2).to_string())

    # Calibración en la prueba B: probabilidad dicha contra frecuencia observada.
    te["tramo"] = pd.cut(te.logistica, [0, 0.05, 0.1, 0.2, 0.4, 0.6, 1.0], include_lowest=True)
    cal = te.groupby("tramo", observed=True).apply(
        lambda g: pd.Series({"casos": g.peso.sum(), "dicho": np.average(g.logistica, weights=g.peso),
                             "observado": np.average(g.y, weights=g.peso)}), include_groups=False)
    print("\nCalibración de la logística (prueba B):")
    print(cal.round(2).to_string())


if __name__ == "__main__":
    main()
