"""Gráficos de la sesión de GKE 1 (13/11/2026) para el informe del TF.

Lee ../pruebas/grilla-gke-2026-11-13.csv y ../pruebas/hpa-lotes-grandes-gke-2026-11-13.txt y deja PNG en esta
carpeta. Uso:  uv run --with pandas --with matplotlib python graficos_gke1.py
"""

import re
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

AQUI = Path(__file__).parent
PRUEBAS = AQUI.parent / "pruebas"
COLOR = {1: "#2a78d6", 3: "#eb6834", 5: "#1baf7a"}  # paleta categórica de referencia, slots 1-3, orden fijo
TINTA, TINTA2, GRILLA, FONDO = "#1f1f1e", "#5f5f5c", "#e4e4e1", "#fcfcfb"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": GRILLA, "axes.labelcolor": TINTA2,
                     "xtick.color": TINTA2, "ytick.color": TINTA2, "axes.titlecolor": TINTA, "figure.facecolor": FONDO,
                     "axes.facecolor": FONDO, "savefig.facecolor": FONDO})


def ejes(ax):
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    ax.grid(axis="y", color=GRILLA, linewidth=0.8)
    ax.set_axisbelow(True)


def grilla():
    d = pd.read_csv(PRUEBAS / "grilla-gke-2026-11-13.csv")
    d["pasada"] = [1] * 24 + [2] * 24
    vus = [1, 2, 5, 10]
    x = {v: i for i, v in enumerate(vus)}
    fig, axs = plt.subplots(2, 2, figsize=(9, 6.4))
    for fila, filas in enumerate((156, 4810)):
        for col, (met, titulo, unidad) in enumerate((("pedidos_s", "Pedidos por segundo", "pedidos/s"),
                                                     ("ms_p95", "Latencia p95", "ms"))):
            ax = axs[fila, col]
            ejes(ax)
            finales = {}
            for rep in (1, 3, 5):
                s = d[(d.filas == filas) & (d.replicas == rep)]
                g = s.groupby("vus")[met].agg(["mean", "min", "max"]).reindex(vus)
                xs = [x[v] + (rep - 3) * 0.05 for v in vus]
                ax.vlines(xs, g["min"], g["max"], color=COLOR[rep], linewidth=2, alpha=0.45)
                ax.plot(xs, g["mean"], color=COLOR[rep], linewidth=2, marker="o", markersize=5,
                        markeredgecolor=FONDO, markeredgewidth=1.5, label=f"{rep} réplica{'s' if rep > 1 else ''}")
                finales[rep] = (xs[-1], g["mean"].iloc[-1])
            # Etiqueta directa al final de cada línea; si dos quedan muy cerca, se separan en vertical.
            orden = sorted(finales, key=lambda r: finales[r][1])
            alto = ax.get_ylim()[1] if ax.get_ylim()[1] > 0 else 1
            previo, dy = None, {}
            for rep in orden:
                y = finales[rep][1]
                dy[rep] = 5 if previo is not None and abs(y - previo) < 0.04 * alto else 0
                if dy[rep]:
                    dy[previo_rep] = -5  # la más alta arriba, la más baja abajo
                previo, previo_rep = y, rep
            for rep, (xf, yf) in finales.items():
                ax.annotate(f"{rep}", (xf, yf), xytext=(8, dy.get(rep, 0)), textcoords="offset points",
                            va="center", color=TINTA2, fontsize=8)
            ax.set_xticks(range(len(vus)), [str(v) for v in vus])
            ax.set_xlim(-0.3, len(vus) - 0.6)
            ax.set_ylim(bottom=0)
            ax.set_title(f"{titulo} · lote de {filas:,} tramos".replace(",", "."), loc="left", fontsize=10)
            ax.set_ylabel(unidad)
            if fila == 1:
                ax.set_xlabel("pedidos simultáneos (usuarios de k6)")
            if met == "ms_p95" and filas == 4810:
                r = d[(d.filas == 4810) & (d.replicas == 1) & (d.vus == 10) & (d.pasada == 1)].iloc[0]
                ax.annotate("pasada 1: 36 % de errores\n(reinicios por la liveness)", (x[10] - 0.1, r.ms_p95),
                            xytext=(-175, -18), textcoords="offset points", fontsize=7.5, color=TINTA2,
                            arrowprops=dict(arrowstyle="-", color=TINTA2, linewidth=0.8))
    h, l = axs[0, 0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper center", ncol=3, frameon=False, bbox_to_anchor=(0.5, 1.0))
    fig.text(0.01, 0.005, "GKE us-central1-a, 2 × e2-standard-2. Punto = promedio de 2 pasadas de 60 s; barra = rango entre "
             "pasadas. HPA apagado (réplicas fijas).", fontsize=7.5, color=TINTA2)
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    fig.savefig(AQUI / "grilla-gke1.png", dpi=200)


def hpa():
    filas = []
    for linea in (PRUEBAS / "hpa-lotes-grandes-gke-2026-11-13.txt").read_text().splitlines():
        m = re.match(r"t=(\d+)s \S+ cpu: (\d+)%/60% actuales=(\d+) listas=(\d+)", linea)
        if m:
            filas.append([int(g) for g in m.groups()])
    d = pd.DataFrame(filas, columns=["t", "cpu", "actuales", "listas"])
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(9, 4.6), sharex=True, gridspec_kw={"height_ratios": [1, 1.2]})
    for ax in (a1, a2):
        ejes(ax)
        ax.axvspan(0, 248, color="#2a78d6", alpha=0.06, linewidth=0)
    a1.step(d.t, d.cpu, where="post", color="#eb6834", linewidth=2)
    a1.axhline(60, color=TINTA2, linewidth=1, linestyle=(0, (4, 3)))
    a1.annotate("objetivo 60 %", (560, 60), xytext=(0, 4), textcoords="offset points", ha="right", fontsize=7.5,
                color=TINTA2)
    a1.set_ylabel("CPU / request (%)")
    a1.set_title("CPU de la API (promedio de los pods, % del request de 250m)", loc="left", fontsize=10)
    a2.step(d.t, d.listas, where="post", color="#2a78d6", linewidth=2, label="réplicas listas")
    a2.step(d.t, d.actuales, where="post", color="#1baf7a", linewidth=2, linestyle=(0, (4, 2)), label="réplicas pedidas")
    a2.set_ylim(0, 5.6)
    a2.set_yticks(range(0, 6))
    a2.set_ylabel("réplicas")
    a2.set_xlabel("segundos desde que arranca k6")
    a2.set_title("Réplicas del HPA (1–5)", loc="left", fontsize=10)
    a2.legend(loc="center right", frameon=False)
    a2.annotate("5 listas a los ~95 s", (94, 5), xytext=(20, -22), textcoords="offset points", fontsize=7.5,
                color=TINTA2, arrowprops=dict(arrowstyle="-", color=TINTA2, linewidth=0.8))
    a2.annotate("carga de k6 (248 s)", (124, 0.3), ha="center", fontsize=7.5, color=TINTA2)
    a2.annotate("se queda en 5 aunque la carga terminó: baja a 4 y a 1 recién\na los ~10 min (ventana de "
                "estabilización de 5 min; fuera del registro)", (585, 5), xytext=(-5, -34),
                textcoords="offset points", ha="right", fontsize=7.5, color=TINTA2)
    a1.annotate("metrics-server\ntodavía no midió\nla carga", (36, 0), xytext=(0, 52), textcoords="offset points",
                ha="center", fontsize=7.5, color=TINTA2)
    a1.annotate("la métrica llega con\n~60 s de retraso", (300, 110), xytext=(12, 30), textcoords="offset points",
                fontsize=7.5, color=TINTA2, arrowprops=dict(arrowstyle="-", color=TINTA2, linewidth=0.8))
    fig.text(0.01, 0.005, "Lotes de 4.810 tramos, 5 usuarios, HPA prendido. Muestreo cada ~19 s con kubectl.",
             fontsize=7.5, color=TINTA2)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(AQUI / "hpa-gke1.png", dpi=200)


if __name__ == "__main__":
    grilla()
    hpa()
