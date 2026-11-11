"""Export diario: recibe las filas de un día de Clima Rutero (CSV) y las sube como Parquet al bucket.

Lo corre el cron del VPS de Clima Rutero (`scripts/export_lluvia.sh` en ese repo), con la cuenta `lluvia-export`,
que solo puede CREAR objetos en `datasets/`: no puede leer, borrar ni pisar. Por eso un día ya subido no se puede
volver a subir por error.

  psql ... -v dia=2026-11-10 < export_lluvia.sql | python exportar.py --dia 2026-11-10 --destino gs://BUCKET/datasets

Valida antes de subir: columnas esperadas, al menos una fila y que todas las franjas sean de ese día (UTC).
Salida: una línea JSON. Código 0 si subió, 2 si los datos no validan, 3 si la subida falla (p. ej. el día ya existe).
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from datetime import date

import fsspec
import pandas as pd

COLUMNAS = [
    "estacion", "franja_utc", "emision_utc", "es_api", "cerca_10km", "n_filas", "n_tramos", "dist_km_media",
    "anticip_h", "votos_media", "votos_max", "disponibles_min", "mm3h_media", "mm3h_max", "gfs_media", "gfs_max",
    "ifs_media", "ifs_max", "wrf_media", "wrf_max", "ciclo_gfs", "ciclo_ifs", "ciclo_wrf", "viento_media",
    "rafaga_max", "tormenta_calculada", "tormenta_nivel_max", "tormenta_dist_min", "tormenta_minutos_min",
    "obs_lluvia", "obs_rayos", "obs_rayos_n",
]
BOOLEANAS = ("es_api", "cerca_10km", "obs_lluvia", "obs_rayos")


class ExportInvalido(ValueError):
    pass


def preparar(crudo: bytes, dia: date) -> pd.DataFrame:
    d = pd.read_csv(io.BytesIO(crudo), parse_dates=["franja_utc", "emision_utc"])
    if list(d.columns) != COLUMNAS:
        faltan, sobran = set(COLUMNAS) - set(d.columns), set(d.columns) - set(COLUMNAS)
        raise ExportInvalido(f"columnas distintas a las esperadas (faltan {sorted(faltan)}, sobran {sorted(sobran)})")
    if d.empty:
        raise ExportInvalido(f"sin filas para {dia}: ¿ya se verificó ese día?")
    otros = sorted({str(x) for x in d.franja_utc.dt.date.unique()} - {str(dia)})
    if otros:
        raise ExportInvalido(f"hay franjas de otros días: {otros}")
    for c in BOOLEANAS:
        d[c] = d[c].map({"t": True, "f": False, True: True, False: False}).astype(bool)
    return d


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--dia", required=True, type=date.fromisoformat, help="día UTC de las franjas, AAAA-MM-DD")
    p.add_argument("--destino", required=True, help="carpeta local o gs://bucket/datasets")
    p.add_argument("--entrada", default="-", help="CSV de entrada; '-' = stdin")
    a = p.parse_args(argv)

    crudo = sys.stdin.buffer.read() if a.entrada == "-" else open(a.entrada, "rb").read()
    try:
        d = preparar(crudo, a.dia)
    except ExportInvalido as e:
        print(json.dumps({"evento": "export_lluvia", "dia": str(a.dia), "ok": False, "error": str(e)},
                         ensure_ascii=False), flush=True)
        return 2

    buf = io.BytesIO()
    d.to_parquet(buf, index=False)
    url = f"{a.destino.rstrip('/')}/{a.dia}.parquet"
    try:
        fs, ruta = fsspec.core.url_to_fs(url)
        if ruta.startswith("/"):  # destino local: crear la carpeta
            fs.makedirs(ruta.rsplit("/", 1)[0], exist_ok=True)
        fs.pipe_file(ruta, buf.getvalue())  # una sola subida: alcanza con permiso de crear objetos
    except OSError as e:
        # El caso esperable es «Forbidden»: el día ya está subido y la cuenta no puede pisarlo.
        motivo = str(e).strip().splitlines()[-1]
        print(json.dumps({"evento": "export_lluvia", "dia": str(a.dia), "ok": False, "destino": url,
                          "error": f"no se pudo subir: {motivo}"}, ensure_ascii=False), flush=True)
        return 3

    casos = d.groupby(["estacion", "franja_utc"]).obs_lluvia.max()
    print(json.dumps({
        "evento": "export_lluvia", "dia": str(a.dia), "ok": True, "destino": url, "filas": len(d),
        "casos": len(casos), "casos_con_lluvia": int(casos.sum()), "estaciones": int(d.estacion.nunique()),
        "bytes": buf.getbuffer().nbytes,
    }, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
