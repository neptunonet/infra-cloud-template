"""Paso 2 de la prueba de concepto: referencias sin aprendizaje, evaluadas fuera de muestra.

Compara tres formas de dar la probabilidad de lluvia de una franja:
  - climatologia: siempre la frecuencia de lluvia vista en entrenamiento
  - tabla_app:    la tabla que usa hoy la app, {0: 0.05, 1: 0.21, 2: 0.47, 3: 0.78}
  - tabla_recal:  la misma tabla, con los valores ajustados con los días de entrenamiento

Uso:  uv run --with pandas --with numpy python paso2_referencia.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).parent
TABLA_APP = {0: 0.05, 1: 0.21, 2: 0.47, 3: 0.78}
UMBRAL = 0.20  # a partir de qué probabilidad se avisa (el de moto hoy)
MIN_DIAS_TRAIN = 7
SEPARACION = 1  # días que se saltean entre entrenamiento y prueba
rng = np.random.default_rng(42)


def cargar(cerca: bool = True) -> pd.DataFrame:
    """cerca=True: tramos a <= 10 km de la estación (lo decidido). cerca=False: los de 10 a 30 km."""
    d = pd.read_csv(
        AQUI / "datos" / "casos.csv",
        parse_dates=["franja_utc", "emision_utc"],
        true_values=["t"],
        false_values=["f"],
    )
    n0 = len(d)
    d = d[(d.cerca_10km == cerca) & ~d.es_api]  # etiqueta a <= 10 km, sin pedidos de usuarios
    d = d[(d.anticip_h >= 0) & (d.anticip_h <= 6)]  # emitido antes del paso, hasta 6 h
    d = d[d.disponibles_min == 3].copy()  # la tabla está definida para 3 modelos
    d["votos"] = d.votos_media.round().astype(int).clip(0, 3)
    d["y"] = d.obs_lluvia.astype(int)
    d["dia"] = (d.franja_utc - pd.Timedelta(hours=3)).dt.date  # día en hora argentina
    d["caso"] = d.estacion + " " + d.franja_utc.astype(str)
    d["peso"] = 1.0 / d.groupby("caso").caso.transform("size")  # cada caso pesa 1
    print(f"Filas: {n0} -> {len(d)} tras los filtros; casos: {d.caso.nunique()}, "
          f"con lluvia: {d.groupby('caso').y.max().sum()}, días: {d.dia.nunique()}")
    return d


def ajustar_tabla(tr: pd.DataFrame) -> dict[int, float]:
    """Frecuencia observada por cantidad de votos, con suavizado y sin dejarla bajar al subir los votos."""
    t, previo = {}, 0.0
    for v in range(4):
        g = tr[tr.votos == v]
        n, k = g.peso.sum(), (g.peso * g.y).sum()
        p = (k + 1) / (n + 2) if n > 0 else TABLA_APP[v]
        previo = t[v] = max(p, previo)
    return t


def predecir(tr: pd.DataFrame, te: pd.DataFrame) -> pd.DataFrame:
    te = te.copy()
    te["climatologia"] = (tr.peso * tr.y).sum() / tr.peso.sum()
    te["tabla_app"] = te.votos.map(TABLA_APP)
    te["tabla_recal"] = te.votos.map(ajustar_tabla(tr))
    return te


def metricas(te: pd.DataFrame, col: str) -> dict:
    w, y, p = te.peso.to_numpy(), te.y.to_numpy(), te[col].to_numpy()
    aviso = p >= UMBRAL
    a, b, c = (w * (aviso & (y == 1))).sum(), (w * (aviso & (y == 0))).sum(), (w * (~aviso & (y == 1))).sum()
    return {
        "brier": (w * (p - y) ** 2).sum() / w.sum(),
        "pod": a / (a + c) if a + c else np.nan,
        "far": b / (a + b) if a + b else np.nan,
        "csi": a / (a + b + c) if a + b + c else np.nan,
    }


def intervalo(te: pd.DataFrame, f, n=2000) -> tuple[float, float]:
    """Intervalo del 90 % remuestreando días enteros."""
    por_dia = {dia: g for dia, g in te.groupby("dia")}
    dias = list(por_dia)
    vals = [f(pd.concat([por_dia[x] for x in rng.choice(dias, len(dias))])) for _ in range(n)]
    return tuple(np.nanpercentile(vals, [5, 95]))


def informe(te: pd.DataFrame, titulo: str) -> None:
    casos = te.groupby("caso").y.max()
    print(f"\n== {titulo} ==")
    print(f"Prueba: {te.dia.nunique()} días ({te.dia.min()} a {te.dia.max()}), {len(casos)} casos, "
          f"{casos.sum()} con lluvia, {te[te.y == 1].dia.nunique()} días con lluvia")
    print(f"{'referencia':<14}{'Brier':>8}{'IC 90 %':>18}{'POD':>7}{'FAR':>7}{'CSI':>7}")
    for col in ("climatologia", "tabla_app", "tabla_recal"):
        m = metricas(te, col)
        lo, hi = intervalo(te, lambda x: metricas(x, col)["brier"])
        print(f"{col:<14}{m['brier']:>8.4f}{f'{lo:.3f} a {hi:.3f}':>18}{m['pod']:>7.2f}{m['far']:>7.2f}{m['csi']:>7.2f}")
    dif = lambda x: metricas(x, "tabla_recal")["brier"] - metricas(x, "tabla_app")["brier"]
    lo, hi = intervalo(te, dif)
    print(f"Diferencia de Brier, recalibrada menos app: {dif(te):+.4f} (IC 90 %: {lo:+.4f} a {hi:+.4f}); "
          "negativa = gana la recalibrada")


def main() -> None:
    d = cargar()
    dias = sorted(d.dia.unique())

    # A) Un solo corte: primeros dos tercios de los días para ajustar, un día de separación, el resto de prueba.
    corte = int(len(dias) * 2 / 3)
    tr = d[d.dia.isin(dias[:corte])]
    te = predecir(tr, d[d.dia.isin(dias[corte + SEPARACION:])])
    print(f"\nTabla ajustada con {corte} días ({dias[0]} a {dias[corte - 1]}): "
          + ", ".join(f"{v} votos = {p:.2f}" for v, p in ajustar_tabla(tr).items()))
    informe(te, "A) Un solo corte")

    # B) Como va a funcionar en la realidad: cada día se predice con una tabla ajustada hasta dos días antes.
    partes = []
    for i in range(MIN_DIAS_TRAIN + SEPARACION, len(dias)):
        tr = d[d.dia.isin(dias[: i - SEPARACION])]
        partes.append(predecir(tr, d[d.dia == dias[i]]))
    informe(pd.concat(partes), "B) Día por día (reentrenando cada día)")


if __name__ == "__main__":
    main()
