"""Paso 8 (13/11, para H10): ¿cuánto empeora el modelo si falta uno de los tres modelos numéricos?

H10 (escrita el 11/11, antes de medir): con un modelo oculto el Brier empeora poco (menos de 0,005). Si empeora más que
la ventaja sobre la tabla (~0,006), con 2 modelos conviene responder la tabla. Hoy la API responde la tabla con 2 de 3
(«dos_modelos», degradado); la decisión 16 decía «predice, entrenado ocultando un modelo al azar».

Cómo se simula que falta el modelo m en una fila (igual que llega a la API):
  - m_media, m_max y ciclo_m vacíos -> agregar_variables() los pone en 0 (lluvia 0 y edad 0);
  - el voto de m se resta del conteo: m votaba si su media era >= 0,2 mm/3 h (umbral de Clima Rutero,
    `UMBRAL_MM_3H`). Reconstruir los votos así coincide con los de la app en el 96,5 % de las filas.

Se compara, día por día y con la misma ventana que train.py (evaluacion.ventana):
  completo      logística con rayos, 3 modelos (lo de siempre)
  tabla_3       tabla de votos de la app, 3 modelos
  y, ocultando cada modelo (gfs, ifs, wrf) en el día de prueba:
  log_normal    la misma logística, entrenada con los 3 (lo que pasaría si la API la usara sin más)
  log_masc      logística entrenada con los datos + una copia con un modelo oculto al azar (decisión 16)
  tabla_2       tabla con el conteo de votos sin el modelo oculto

Uso (desde infra-cloud-template/lluvia, que tiene los módulos y requirements.txt):
  uv run --with-requirements requirements.txt python ../docs/trabajo-final/poc/paso8_modelo_oculto.py '<datasets>/*.parquet'
"""

import json
import sys

import numpy as np
import pandas as pd

import evaluacion as E
import recetas
import train
import variables as V

UMBRAL_VOTO = 0.2
RECETA = "logistica_rayos"


def ocultar(d: pd.DataFrame, modelo) -> pd.DataFrame:
    """Oculta `modelo` en todas las filas (str) o uno distinto por fila (array de nombres)."""
    d = d.copy()
    por_fila = np.broadcast_to(np.asarray(modelo, dtype=object), len(d))
    for m in V.MODELOS:
        sel = por_fila == m
        if not sel.any():
            continue
        voto = (d.loc[sel, f"{m}_media"] >= UMBRAL_VOTO).astype(float)
        d.loc[sel, "votos_media"] = (d.loc[sel, "votos_media"] - voto).clip(lower=0)
        d.loc[sel, [f"{m}_media", f"{m}_max"]] = np.nan
        d.loc[sel, f"ciclo_{m}"] = None
    d["votos"] = d.votos_media.round().astype(int).clip(0, 3)
    return d


def main(datos: str) -> dict:
    crudo, _ = train.leer_datos(datos)
    d = V.filtrar(crudo)
    v = E.ventana(d)
    dias = sorted(d.dia.unique())
    rng = np.random.default_rng(42)
    partes = []
    for dia in v["dias"]:
        i = dias.index(dia)
        tr, te = d[d.dia.isin(dias[: i - E.SEPARACION])], d[d.dia == dia]
        normal = recetas.entrenar(RECETA, V.agregar_variables(tr))
        masc_tr = pd.concat([tr, ocultar(tr, rng.choice(V.MODELOS, len(tr)))], ignore_index=True)
        masc = recetas.entrenar(RECETA, V.agregar_variables(masc_tr))
        x = V.agregar_variables(te).copy()
        x["completo"] = recetas.predecir(RECETA, normal, x)
        x["tabla_3"] = recetas.predecir("tabla_app", None, x)
        for m in V.MODELOS:
            xo = V.agregar_variables(ocultar(te, m))
            x[f"log_normal_sin_{m}"] = recetas.predecir(RECETA, normal, xo)
            x[f"log_masc_sin_{m}"] = recetas.predecir(RECETA, masc, xo)
            x[f"tabla_2_sin_{m}"] = recetas.predecir("tabla_app", None, xo)
        partes.append(x)
    x = pd.concat(partes, ignore_index=True)

    res = {"ventana": v, "brier": {}, "comparaciones": []}
    cols = [c for c in x.columns if c in ("completo", "tabla_3") or "_sin_" in c]
    for c in cols:
        res["brier"][c] = round(E.brier(x, c), 4)
    comp = [("tabla_3", "completo")]
    for m in V.MODELOS:
        comp += [(f"log_normal_sin_{m}", "completo"), (f"log_masc_sin_{m}", "completo"),
                 (f"log_masc_sin_{m}", f"tabla_2_sin_{m}"), (f"log_normal_sin_{m}", f"tabla_2_sin_{m}"),
                 (f"log_masc_sin_{m}", f"log_normal_sin_{m}")]
    for a, b in comp:
        c = E.comparar(x, a, b)
        res["comparaciones"].append({k: (round(v_, 4) if isinstance(v_, float) else
                                         [round(z, 4) for z in v_] if isinstance(v_, list) else v_)
                                     for k, v_ in c.items()})
    return res


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1]), ensure_ascii=False, indent=1, default=str))
