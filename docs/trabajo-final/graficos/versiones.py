"""Historial de versiones del modelo (sección 5.6 del informe): tabla y gráfico del Brier por versión.

Lee todos los `modelos/versiones/*/metadata.json` del bucket con `gcloud storage` (la cuenta de gcloud de Juan) y deja
en esta carpeta:
  versiones.csv        una fila por versión: fecha, dónde corrió, ventana, casos, Brier de cada receta, receta activa,
                       motivo, tiempos
  versiones.html       la misma tabla, lista para pegar en el informe
  versiones.png        el Brier día por día de cada receta en cada versión, con la receta activa marcada

Uso:  uv run --with pandas --with matplotlib python versiones.py      (volver a correr antes de la entrega;
      también reemplaza la tabla en el HTML del informe, entre las marcas VERSIONES_INI y VERSIONES_FIN)
"""

import json
import subprocess
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

AQUI = Path(__file__).parent
BASE = "gs://unlu-ia-armas-lluvia/modelos/versiones"
RECETAS = {"tabla_app": "Tabla de votos (referencia)", "logistica_rayos": "Logística con rayos", "lgbm_chico": "LightGBM chico"}
COLOR = {"tabla_app": "#8a8a86", "logistica_rayos": "#2a78d6", "lgbm_chico": "#eb6834"}
TINTA, TINTA2, GRILLA, FONDO = "#1f1f1e", "#5f5f5c", "#e4e4e1", "#fcfcfb"


def gcloud(*args: str) -> str:
    return subprocess.run(["gcloud", "storage", *args], check=True, capture_output=True, text=True).stdout


def leer() -> pd.DataFrame:
    rutas = [l.strip() for l in gcloud("ls", f"{BASE}/*/metadata.json").splitlines() if l.strip()]
    filas = []
    for r in sorted(rutas):
        d = json.loads(gcloud("cat", r))
        ev, dec = d["evaluacion"], d["decision"]
        fila = {
            "version": d["version"],
            "fecha": pd.to_datetime(d["version"][1:], format="%Y%m%d_%H%M%S"),
            "desde": ev["ventana"].get("desde"), "hasta": ev["ventana"].get("hasta"),
            "casos": ev["ventana"].get("casos"), "casos_con_lluvia": ev["ventana"].get("casos_con_lluvia"),
            "activa": dec.get("receta_elegida") or d.get("receta"),
            "motivo": dec.get("motivo", ""),
            "eval_s": (d.get("tiempos_s") or {}).get("evaluacion"),
            "git_sha": (d.get("entorno") or {}).get("git_sha") or "",
        }
        for k, v in ev["recetas"].items():
            fila[f"brier_{k}"] = v.get("brier")
            fila[f"ece_{k}"] = v.get("ece")
        for c in ev.get("comparaciones", []):
            if c["b"] == "tabla_app":
                fila[f"dif_{c['a']}"] = c["dif_brier"]
                fila[f"dif_{c['a']}_lo"], fila[f"dif_{c['a']}_hi"] = c["ic90"]
        filas.append(fila)
    return pd.DataFrame(filas).sort_values("fecha").reset_index(drop=True)


def tabla_html(d: pd.DataFrame) -> str:
    c = lambda x, n=4: "" if pd.isna(x) else f"{x:.{n}f}".replace(".", ",")
    out = ['<table class="avoid">',
           "<tr><th>Versión</th><th>Ventana de prueba</th><th>Casos (con lluvia)</th><th>Brier tabla</th>"
           "<th>Brier logística</th><th>Brier LightGBM</th><th>Activa</th><th>Evaluación</th></tr>"]
    for _, r in d.iterrows():
        b = {k: c(r.get(f"brier_{k}")) for k in RECETAS}
        b[r.activa] = f"<b>{b[r.activa]}</b>"
        ventana = f"{r.desde[8:10]}/{r.desde[5:7]}–{r.hasta[8:10]}/{r.hasta[5:7]}" if r.desde else ""
        out.append(f"<tr><td><code>{r.version}</code></td><td>{ventana}</td>"
                   f'<td class="n">{r.casos} ({r.casos_con_lluvia})</td><td class="n">{b["tabla_app"]}</td>'
                   f'<td class="n">{b["logistica_rayos"]}</td><td class="n">{b["lgbm_chico"]}</td>'
                   f"<td>{'logística' if r.activa == 'logistica_rayos' else 'LightGBM' if r.activa == 'lgbm_chico' else 'tabla'}</td>"
                   f'<td class="n">{"" if pd.isna(r.eval_s) else c(r.eval_s, 1) + " s"}</td></tr>')
    out.append("</table>")
    return "\n".join(out)


def grafico(d: pd.DataFrame) -> None:
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": GRILLA,
                         "axes.labelcolor": TINTA2, "xtick.color": TINTA2, "ytick.color": TINTA2,
                         "figure.facecolor": FONDO, "axes.facecolor": FONDO, "savefig.facecolor": FONDO})
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(9, 6.4), sharex=True, gridspec_kw={"height_ratios": [1.1, 1]})
    for a_ in (ax, ax2):
        for lado in ("top", "right"):
            a_.spines[lado].set_visible(False)
        a_.grid(axis="y", color=GRILLA, linewidth=0.8)
        a_.set_axisbelow(True)
    for k, nombre in RECETAS.items():
        col = f"brier_{k}"
        if col not in d:
            continue
        estilo = (0, (4, 3)) if k == "tabla_app" else "-"
        ax.plot(d.fecha, d[col], color=COLOR[k], linewidth=2, linestyle=estilo, marker="o", markersize=4,
                label=nombre)
        act = d[d.activa == k]
        ax.scatter(act.fecha, act[col], s=90, facecolors="none", edgecolors=COLOR[k], linewidths=2, zorder=5)
    ax.scatter([], [], s=90, facecolors="none", edgecolors=TINTA2, linewidths=2, label="receta activa en esa versión")
    cambios = d[d.activa != d.activa.shift()].iloc[1:]
    # Panel 2: lo que decide la regla: diferencia contra la tabla y su intervalo del 90 % (apta si queda debajo de 0)
    for i, k in enumerate(("logistica_rayos", "lgbm_chico")):
        if f"dif_{k}" not in d:
            continue
        x = d.fecha + pd.Timedelta(hours=(-2 if i == 0 else 2))
        err = [d[f"dif_{k}"] - d[f"dif_{k}_lo"], d[f"dif_{k}_hi"] - d[f"dif_{k}"]]
        ax2.errorbar(x, d[f"dif_{k}"], yerr=err, fmt="o", color=COLOR[k], markersize=5, elinewidth=2, capsize=0,
                     label=RECETAS[k])
    ax2.axhline(0, color=TINTA2, linewidth=1)
    ax2.annotate("apta = todo el intervalo debajo de 0 (le gana a la tabla con evidencia)",
                 (0.01, 0.03), xycoords="axes fraction", fontsize=7.5, color=TINTA2)
    ax2.set_ylabel("Brier − Brier de la tabla")
    ax2.set_title("Diferencia contra la tabla e intervalo del 90 % (lo que decide la promoción)", loc="left",
                  fontsize=10, color=TINTA)
    ax2.legend(loc="upper left", bbox_to_anchor=(1.01, 1), frameon=False, fontsize=8)
    for _, r in cambios.iterrows():
        ax.axvline(r.fecha, color=TINTA2, linewidth=0.8, linestyle=(0, (2, 2)))
        ax2.axvline(r.fecha, color=TINTA2, linewidth=0.8, linestyle=(0, (2, 2)))
        ax.annotate(f"{r.fecha:%d/%m}: pasa a {'LightGBM' if r.activa == 'lgbm_chico' else 'logística' if r.activa == 'logistica_rayos' else 'la tabla'}",
                    (r.fecha, ax.get_ylim()[1]), xytext=(4, -12), textcoords="offset points", fontsize=7.5, color=TINTA2)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
    ax.set_ylabel("Brier día por día (menor = mejor)")
    ax.set_title("Brier de cada receta en cada versión (cada una evaluada en sus últimos 14 días)", loc="left",
                 fontsize=10, color=TINTA)
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1), frameon=False, fontsize=8)
    fig.text(0.01, 0.01, f"{len(d)} versiones, {d.fecha.min():%d/%m} al {d.fecha.max():%d/%m}. La primera se entrenó en la "
             "notebook; las demás, en el VPS. Datos: metadata.json de cada versión.", fontsize=7.5, color=TINTA2)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(AQUI / "versiones.png", dpi=200)


def actualizar_informe(tabla: str) -> bool:
    """Reemplaza la tabla de versiones del informe (entre las marcas VERSIONES_INI y VERSIONES_FIN)."""
    import re
    p = AQUI.parent / "Informe TF - Juan Ignacio Armas.html"
    if not p.exists():  # en el repo no está el HTML del informe: solo se generan el CSV, la tabla y el gráfico
        return False
    s = p.read_text()
    m = re.search(r"(<!--VERSIONES_INI.*?)(<table class=\"avoid\">.*?</table>)(.*?<!--VERSIONES_FIN-->)", s, re.S)
    if not m:
        return False
    p.write_text(s[:m.start(2)] + tabla + s[m.end(2):])
    return True


if __name__ == "__main__":
    d = leer()
    d.to_csv(AQUI / "versiones.csv", index=False)
    (AQUI / "versiones.html").write_text(tabla_html(d))
    print("informe actualizado:", actualizar_informe(tabla_html(d)))
    grafico(d)
    print(d[["version", "activa", "brier_tabla_app", "brier_logistica_rayos", "brier_lgbm_chico"]].to_string(index=False))
