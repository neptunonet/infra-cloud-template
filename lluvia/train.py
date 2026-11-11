"""Entrenamiento diario del servicio de probabilidad de lluvia (Trabajo Final).

Entrena -> evalúa -> versiona -> decide si promueve. Cada corrida:

1. Lee el dataset exportado por Clima Rutero (CSV o Parquet; un archivo, una carpeta o un patrón; local o gs://).
2. Lee qué receta está activa (`<destino>/activa.json`; si no hay, la tabla de votos de la app).
3. Evalúa día por día, sobre los últimos 14 días (o más, hasta tener evidencia mínima), la tabla de la app, la
   receta activa y las candidatas.
4. Decide (decisiones 15, 23 y 27 del TF):
   - una receta aprendida es «apta» si le gana a la tabla de la app en Brier (intervalo del 90 % debajo de cero)
     y está calibrada (error de calibración <= 0,05);
   - si la activa deja de ser apta, vuelve sola a la tabla de la app (vuelta atrás automática);
   - una candidata reemplaza a la activa solo si también le gana a ella con el intervalo debajo de cero;
   - sin evidencia mínima no cambia de receta.
   POD y FAR de cada sensibilidad se calculan y se guardan, pero no deciden (decisión 27).
5. Reentrena la receta elegida (o, si quedó la tabla, la mejor candidata, como versión en sombra) con todos los
   días y guarda `<destino>/versiones/vAAAAMMDD_HHMMSS/{modelo.joblib, metadata.json}`.
6. Si hay promoción, mueve el puntero `<destino>/activa.json`.

Uso:
  python train.py --datos datos/casos.csv --destino ./artefactos
  python train.py --datos 'gs://BUCKET/datasets/*.parquet' --destino gs://BUCKET/modelos
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import platform
import sys
from datetime import datetime, timezone

import fsspec
import joblib
import lightgbm
import numpy as np
import pandas as pd
import sklearn

import evaluacion as ev
import recetas
from variables import FILTROS, preparar

ECE_MAX = 0.05
CANDIDATAS = ("logistica_rayos", "lgbm_chico")


# ---------- almacenamiento (local o gs:// con la misma API) ----------
def _archivos(url: str) -> tuple[fsspec.AbstractFileSystem, list[str]]:
    fs, ruta = fsspec.core.url_to_fs(url)
    if any(c in ruta for c in "*?["):
        rutas = sorted(fs.glob(ruta))
    elif fs.isdir(ruta):
        rutas = sorted(p for p in fs.find(ruta) if p.endswith((".csv", ".parquet")))
    else:
        rutas = [ruta]
    if not rutas:
        raise FileNotFoundError(f"no hay archivos de datos en {url}")
    return fs, rutas


def leer_datos(url: str) -> tuple[pd.DataFrame, list[dict]]:
    fs, rutas = _archivos(url)
    partes, info = [], []
    for r in rutas:
        crudo = fs.cat_file(r)
        info.append({"archivo": r, "bytes": len(crudo), "sha256": hashlib.sha256(crudo).hexdigest()})
        lector = pd.read_parquet if r.endswith(".parquet") else pd.read_csv
        partes.append(lector(io.BytesIO(crudo)))
    return pd.concat(partes, ignore_index=True), info


def _unir(base: str, *partes: str) -> str:
    return "/".join([base.rstrip("/"), *partes])


def leer_json(url: str) -> dict | None:
    fs, ruta = fsspec.core.url_to_fs(url)
    if not fs.exists(ruta):
        return None
    return json.loads(fs.cat_file(ruta))


def escribir(url: str, contenido: bytes) -> None:
    fs, ruta = fsspec.core.url_to_fs(url)
    padre = ruta.rsplit("/", 1)[0]
    if padre:
        fs.makedirs(padre, exist_ok=True)
    with fs.open(ruta, "wb") as f:
        f.write(contenido)


# ---------- decisión ----------
def decidir(res: dict, comps: dict, activa: str, evidencia: bool) -> tuple[str, str]:
    ref = recetas.REFERENCIA
    apta = lambda r: r != ref and res[r]["ece"] <= ECE_MAX and comps[(r, ref)]["a_mejor"]
    if not evidencia:
        return activa, "sin evidencia mínima en la ventana: se mantiene la receta activa"
    motivo = ""
    if activa != ref and not apta(activa):
        motivo = f"vuelta atrás: {activa} ya no le gana a la tabla de la app o perdió calibración. "
        activa = ref
    aptas = [r for r in res if apta(r)]
    if activa == ref:
        if not aptas:
            return ref, motivo + "ninguna receta aprendida le gana a la tabla de la app con evidencia"
        mejor = min(aptas, key=lambda r: res[r]["brier"])
        return mejor, motivo + f"{mejor} le gana a la tabla de la app y está calibrada"
    mejores = [r for r in aptas if r != activa and comps[(r, activa)]["a_mejor"]]
    if mejores:
        mejor = min(mejores, key=lambda r: res[r]["brier"])
        return mejor, f"{mejor} le gana a la activa ({activa}) con evidencia"
    return activa, f"{activa} sigue siendo apta y ninguna candidata le gana con evidencia: se reentrena"


def _limpio(x):
    """Convierte numpy y fechas a tipos que entiende json."""
    if isinstance(x, dict):
        return {str(k): _limpio(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_limpio(v) for v in x]
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating,)):
        return None if np.isnan(x) else float(x)
    if isinstance(x, (np.bool_,)):
        return bool(x)
    return x


def correr(datos: str, destino: str, candidatas: tuple[str, ...] = CANDIDATAS, ahora: datetime | None = None) -> dict:
    ahora = ahora or datetime.now(timezone.utc)
    version = ahora.strftime("v%Y%m%d_%H%M%S")
    crudo, archivos = leer_datos(datos)
    d = preparar(crudo)
    casos = d.groupby("caso").y.max()

    puntero_url = _unir(destino, "activa.json")
    puntero = leer_json(puntero_url) or {"receta": recetas.REFERENCIA, "version": None}
    activa = puntero["receta"]

    v = ev.ventana(d)
    evaluadas = list(dict.fromkeys([recetas.REFERENCIA, activa, *candidatas]))
    pred = ev.predicciones_rodantes(d, v["dias"], evaluadas)
    res = {r: ev.resumen(pred, r) for r in evaluadas}
    aprendidas = [r for r in evaluadas if r != recetas.REFERENCIA]
    pares = [(r, recetas.REFERENCIA) for r in aprendidas]
    pares += [(r, activa) for r in aprendidas if activa != recetas.REFERENCIA and r != activa]
    comps = {p: ev.comparar(pred, *p) for p in pares}

    elegida, motivo = decidir(res, comps, activa, v["evidencia_suficiente"])
    if elegida != recetas.REFERENCIA:
        receta_version = elegida
    else:  # queda la tabla: se guarda igual la mejor receta aprendida, en sombra
        receta_version = min(aprendidas, key=lambda r: res[r]["brier"]) if aprendidas else None
    promovida = elegida == receta_version and elegida != recetas.REFERENCIA

    base = _unir(destino, "versiones", version)
    if receta_version:
        modelo = recetas.entrenar(receta_version, d)
        buf = io.BytesIO()
        joblib.dump({"version": version, "receta": receta_version, "modelo": modelo,
                     "variables": recetas.VARIABLES_DE[receta_version]}, buf)
        escribir(_unir(base, "modelo.joblib"), buf.getvalue())

    metadata = _limpio({
        "version": version,
        "creada_utc": ahora.isoformat(),
        "receta": receta_version,
        "hiperparametros": recetas.HIPERPARAMETROS.get(receta_version),
        "variables": recetas.VARIABLES_DE.get(receta_version),
        "datos": {
            "origen": datos,
            "archivos": archivos,
            "filtros": FILTROS,
            "filas": len(d),
            "casos": len(casos),
            "casos_con_lluvia": int(casos.sum()),
            "dias": d.dia.nunique(),
            "desde": str(d.dia.min()),
            "hasta": str(d.dia.max()),
        },
        "evaluacion": {
            "metodo": "día por día, entrenando hasta dos días antes; cada caso pesa 1; IC 90 % por días",
            "ventana": {k: val for k, val in v.items() if k != "dias"},
            "recetas": res,
            "comparaciones": list(comps.values()),
            "ece_max": ECE_MAX,
        },
        "decision": {
            "activa_antes": puntero,
            "receta_elegida": elegida,
            "promovida": promovida,
            "motivo": motivo,
        },
        "entorno": {
            "git_sha": os.environ.get("GIT_SHA"),
            "python": platform.python_version(),
            "scikit_learn": sklearn.__version__,
            "lightgbm": lightgbm.__version__,
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
    })
    escribir(_unir(base, "metadata.json"), json.dumps(metadata, ensure_ascii=False, indent=2).encode())

    nuevo = {"receta": elegida, "version": version if promovida else None,
             "actualizado_utc": ahora.isoformat(), "motivo": motivo}
    if promovida or elegida != activa or (elegida == recetas.REFERENCIA and puntero.get("version")):
        escribir(puntero_url, json.dumps(nuevo, ensure_ascii=False, indent=2).encode())
    return metadata


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--datos", default=os.environ.get("DATOS"), help="CSV/Parquet, carpeta o patrón; local o gs://")
    p.add_argument("--destino", default=os.environ.get("DESTINO"), help="carpeta local o gs://bucket/prefijo")
    p.add_argument("--candidatas", default=os.environ.get("CANDIDATAS", ",".join(CANDIDATAS)))
    a = p.parse_args(argv)
    if not a.datos or not a.destino:
        p.error("faltan --datos y --destino (o las variables DATOS y DESTINO)")
    m = correr(a.datos, a.destino, tuple(c for c in a.candidatas.split(",") if c))
    ev_r = m["evaluacion"]["recetas"]
    # Una línea JSON para los logs (Loki): sin coordenadas ni datos de usuarios.
    print(json.dumps({
        "evento": "entrenamiento",
        "version": m["version"],
        "receta": m["receta"],
        "elegida": m["decision"]["receta_elegida"],
        "promovida": m["decision"]["promovida"],
        "motivo": m["decision"]["motivo"],
        "brier": {r: round(x["brier"], 4) for r, x in ev_r.items()},
        "ventana": m["evaluacion"]["ventana"],
    }, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
