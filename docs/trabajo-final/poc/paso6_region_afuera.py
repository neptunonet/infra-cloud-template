"""Paso 6: dejar una región afuera. ¿Sirve el modelo en una región que nunca vio?

Para cada región y cada día de prueba se comparan, sobre los casos de ESA región:
  - tabla_app:  la tabla de votos de la app (no aprende, sirve igual en cualquier lado)
  - vista:      logística con rayos entrenada con todas las regiones (días anteriores)
  - no_vista:   la misma logística entrenada SIN esa región (mismos días anteriores)

Se mantiene la separación en el tiempo: siempre se entrena hasta dos días antes del día evaluado.

Uso:  uv run --with pandas --with numpy --with scikit-learn python paso6_region_afuera.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

from paso2_referencia import MIN_DIAS_TRAIN, SEPARACION, cargar, intervalo, metricas, predecir
from paso3_logistica import VARIABLES, agregar_variables
from paso5_rayos import RAYOS, agregar_rayos, entrenar

TODAS = VARIABLES + RAYOS
CENTROS = {"AMBA": (-34.7, -58.4), "Litoral": (-32.3, -60.7), "Córdoba": (-31.4, -64.3), "Mendoza": (-35.0, -68.9)}


def region_de(lat: float, lon: float) -> str:
    """Región más cercana; «otra» si la estación queda a más de ~150 km de todos los centros."""
    d = {r: np.hypot((lat - la) * 111, (lon - lo) * 92) for r, (la, lo) in CENTROS.items()}
    r = min(d, key=d.get)
    return r if d[r] <= 150 else "otra"


def main() -> None:
    d = agregar_rayos(agregar_variables(cargar()))
    est = pd.read_csv(Path(__file__).parent / "datos" / "estaciones.csv").set_index("estacion")
    d["region"] = [region_de(est.lat[e], est.lon[e]) for e in d.estacion]
    resumen = d.groupby(["region", "estacion"]).apply(
        lambda g: pd.Series({"casos": g.caso.nunique(), "con_lluvia": g.groupby("caso").y.max().sum()}),
        include_groups=False)
    print("\nEstaciones por región:")
    print(resumen.to_string())
    d = d[d.region != "otra"]
    dias = sorted(d.dia.unique())

    partes = []
    for i in range(MIN_DIAS_TRAIN + SEPARACION, len(dias)):
        tr, te = d[d.dia.isin(dias[: i - SEPARACION])], d[d.dia == dias[i]]
        te = predecir(tr, te)
        te["vista"] = entrenar(tr, TODAS).predict_proba(te[TODAS])[:, 1]
        te["no_vista"] = np.nan
        for r in CENTROS:
            fuera = te.region == r
            if fuera.any():
                m = entrenar(tr[tr.region != r], TODAS)
                te.loc[fuera, "no_vista"] = m.predict_proba(te.loc[fuera, TODAS])[:, 1]
        partes.append(te)
    te = pd.concat(partes)

    # Córdoba no tiene tramos a <= 10 km de su estación (SACO): con el radio decidido no entra a entrenar.
    # Sirve entonces como región no vista de verdad, evaluada con su etiqueta de 10 a 30 km (más débil).
    lejos = agregar_rayos(agregar_variables(cargar(cerca=False)))
    cba = lejos[lejos.estacion == "SACO"]
    partes_cba = []
    for i in range(MIN_DIAS_TRAIN + SEPARACION, len(dias)):
        tr, x = d[d.dia.isin(dias[: i - SEPARACION])], cba[cba.dia == dias[i]]
        if len(x):
            x = predecir(tr, x)
            x["no_vista"] = entrenar(tr, TODAS).predict_proba(x[TODAS])[:, 1]
            partes_cba.append(x)
    cba = pd.concat(partes_cba)

    def bloque(x: pd.DataFrame, nombre: str, modelos=("tabla_app", "vista", "no_vista")) -> None:
        casos = x.groupby("caso").y.max()
        print(f"\n== {nombre}: {len(casos)} casos, {casos.sum()} con lluvia, {x[x.y == 1].dia.nunique()} días con lluvia ==")
        print("Brier  " + " · ".join(f"{c} {metricas(x, c)['brier']:.4f}" for c in modelos))
        for ref in modelos[:-1]:
            dif = lambda z: metricas(z, "no_vista")["brier"] - metricas(z, ref)["brier"]
            lo, hi = intervalo(x, dif, n=1000)
            print(f"  no_vista menos {ref}: {dif(x):+.4f} (IC 90 %: {lo:+.4f} a {hi:+.4f})")

    for r in CENTROS:
        if (te.region == r).any():
            bloque(te[te.region == r], r)
    bloque(te, "Las tres regiones juntas")
    bloque(cba, "Córdoba (nunca vista; etiqueta de 10 a 30 km)", modelos=("climatologia", "tabla_app", "no_vista"))


if __name__ == "__main__":
    main()
