"""Paso 4: LightGBM contra la logística y la tabla de la app.

Mismas 16 variables que la logística con rayos, misma evaluación día por día.
Dos configuraciones fijadas de antemano (no se ajustan mirando la prueba):
  - lgbm_chico:   árboles chicos y hojas grandes, pensado para pocos casos independientes
  - lgbm_defecto: los valores por defecto de la librería, para ver cuánto sobreajusta

Uso:  uv run --with pandas --with numpy --with scikit-learn --with lightgbm python paso4_lightgbm.py
"""

import pandas as pd
from lightgbm import LGBMClassifier

from paso2_referencia import MIN_DIAS_TRAIN, SEPARACION, cargar, intervalo, metricas, predecir
from paso3_logistica import VARIABLES, agregar_variables
from paso3b_avisos import tablero, umbral_para_pod
from paso5_rayos import RAYOS, agregar_rayos, entrenar

TODAS = VARIABLES + RAYOS
CONFIG = {
    "lgbm_chico": dict(n_estimators=150, learning_rate=0.03, num_leaves=4, min_child_samples=500,
                       subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=5.0),
    "lgbm_defecto": dict(),
}
MODELOS = ("tabla_app", "logistica", "lgbm_chico", "lgbm_defecto")


def main() -> None:
    d = agregar_rayos(agregar_variables(cargar()))
    dias = sorted(d.dia.unique())

    partes = []
    for i in range(MIN_DIAS_TRAIN + SEPARACION, len(dias)):
        tr, te = d[d.dia.isin(dias[: i - SEPARACION])], d[d.dia == dias[i]]
        te = predecir(tr, te)
        te["logistica"] = entrenar(tr, TODAS).predict_proba(te[TODAS])[:, 1]
        for nombre, params in CONFIG.items():
            m = LGBMClassifier(random_state=42, verbose=-1, n_jobs=2, **params)
            m.fit(tr[TODAS], tr.y, sample_weight=tr.peso)
            te[nombre] = m.predict_proba(te[TODAS])[:, 1]
        partes.append(te)
    te = pd.concat(partes)
    casos = te.groupby("caso").y.max()
    print(f"\nPrueba: {te.dia.nunique()} días, {len(casos)} casos, {casos.sum()} con lluvia")

    print(f"\n{'modelo':<14}{'Brier':>8}{'IC 90 %':>18}")
    for col in MODELOS:
        lo, hi = intervalo(te, lambda x: metricas(x, col)["brier"], n=1000)
        print(f"{col:<14}{metricas(te, col)['brier']:>8.4f}{f'{lo:.3f} a {hi:.3f}':>18}")
    for a, b in (("lgbm_chico", "logistica"), ("lgbm_chico", "tabla_app"), ("lgbm_defecto", "logistica")):
        dif = lambda x: metricas(x, a)["brier"] - metricas(x, b)["brier"]
        lo, hi = intervalo(te, dif, n=1000)
        print(f"Brier {a} menos {b}: {dif(te):+.4f} (IC 90 %: {lo:+.4f} a {hi:+.4f})")

    for votos, nombre in ((1, "«posible» (1 voto o más)"), (2, "«probable» (2 votos o más)")):
        te["a_tabla_app"] = te.votos >= votos
        pod = tablero(te, "a_tabla_app")["pod"]
        print(f"\nAviso {nombre}, todos a POD {pod:.2f}")
        print(f"{'modelo':<14}{'FAR':>6}{'CSI':>6}{'% con aviso':>13}")
        for col in MODELOS:
            if col != "tabla_app":
                u = umbral_para_pod(te[col].to_numpy(), te.y.to_numpy(), te.peso.to_numpy(), pod)
                te["a_" + col] = te[col] >= u
            t = tablero(te, "a_" + col)
            print(f"{col:<14}{t['far']:>6.2f}{t['csi']:>6.2f}{100 * t['avisa']:>12.1f}%")
        dif = lambda x: tablero(x, "a_lgbm_chico")["far"] - tablero(x, "a_tabla_app")["far"]
        lo, hi = intervalo(te, dif, n=1000)
        print(f"FAR lgbm_chico menos app: {dif(te):+.3f} (IC 90 %: {lo:+.3f} a {hi:+.3f})")

    m = LGBMClassifier(random_state=42, verbose=-1, n_jobs=2, importance_type="gain", **CONFIG["lgbm_chico"])
    m.fit(d[TODAS], d.y, sample_weight=d.peso)
    imp = pd.Series(m.feature_importances_, index=TODAS)
    print("\nImportancia de las variables en lgbm_chico (% de la ganancia, todos los días):")
    print((100 * imp / imp.sum()).sort_values(ascending=False).round(1).head(8).to_string())


if __name__ == "__main__":
    main()
