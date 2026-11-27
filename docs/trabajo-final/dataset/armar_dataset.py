"""Arma la copia publicable del dataset del TF (decisión 20): un parquet + un CSV comprimido + sha256 + README.

Lee los `datasets/*.parquet` del bucket (o de una carpeta), y:
  - saca las filas de pedidos de usuarios (`es_api`): son pocas por estación y dejan ver por dónde y cuándo viajó
    alguien; el modelo tampoco las usa;
  - deduplica los días que aparecen en dos archivos (queda la fila con más tramos, igual que variables.filtrar);
  - no agrega nada que no esté en el export: sin coordenadas de tramos, sin rutas, sin usuarios.

Uso (desde infra-cloud-template/lluvia, que tiene los módulos y requirements.txt):
  PYTHONPATH=. uv run --with-requirements requirements.txt python ../docs/trabajo-final/dataset/armar_dataset.py \
      'gs://unlu-ia-armas-lluvia/datasets/*.parquet' /tmp/dataset-salida
"""

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

import train

CLAVE = ["estacion", "franja_utc", "emision_utc", "es_api", "cerca_10km"]


def main(datos: str, salida: str) -> dict:
    crudo, archivos = train.leer_datos(datos)
    d = crudo.copy()
    d["es_api"] = d.es_api.astype(str).str.lower().isin(["true", "t"])
    n_api = int(d.es_api.sum())
    d = d[~d.es_api].drop(columns=["es_api"])
    d = d.sort_values("n_filas").drop_duplicates([c for c in CLAVE if c != "es_api"], keep="last")
    d = d.sort_values(["franja_utc", "estacion", "emision_utc", "cerca_10km"]).reset_index(drop=True)

    desde, hasta = d.franja_utc.min().date(), d.franja_utc.max().date()
    base = f"clima-rutero-lluvia_{desde}_{hasta}"
    out = Path(salida)
    out.mkdir(parents=True, exist_ok=True)
    pq, csv = out / f"{base}.parquet", out / f"{base}.csv.gz"
    d.to_parquet(pq, index=False)
    d.to_csv(csv, index=False, compression="gzip")
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (pq, csv)}
    (out / "SHA256SUMS").write_text("".join(f"{h}  {n}\n" for n, h in hashes.items()))

    casos = d[d.cerca_10km].groupby(["estacion", "franja_utc"]).obs_lluvia.max()
    resumen = {
        "origen": [{"archivo": Path(a["archivo"]).name, "sha256": a["sha256"]} for a in archivos],
        "filas_de_usuarios_quitadas": n_api,
        "filas": len(d),
        "desde": str(desde), "hasta": str(hasta),
        "dias": int(d.franja_utc.dt.date.nunique()),
        "estaciones": sorted(d.estacion.unique().tolist()),
        "casos_a_10km": int(len(casos)), "casos_a_10km_con_lluvia": int(casos.sum()),
        "columnas": list(d.columns),
        "sha256": hashes,
    }
    (out / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1))
    actualizar_readme(out, resumen, base)
    # Los archivos de una corrida anterior (otro período) no se publican.
    for viejo in out.glob("clima-rutero-lluvia_*"):
        if not viejo.name.startswith(base):
            viejo.unlink()
    return resumen


def actualizar_readme(out: Path, r: dict, base: str) -> None:
    """Pone las cifras del resumen en la tabla del README (el resto del README se escribe a mano)."""
    import re
    p = out / "README.md"
    if not p.exists():
        return
    miles = lambda n: f"{n:,}".replace(",", ".")
    fecha = lambda d: f"{d[8:10]}/{d[5:7]}/{d[:4]}"
    filas = {
        "Período": f"{fecha(r['desde'])} – {fecha(r['hasta'])} ({r['dias']} días, franjas en UTC)",
        "Filas": miles(r["filas"]),
        "Estaciones METAR": ", ".join(r["estaciones"]),
        "Casos a ≤ 10 km (estación × franja)": f"{miles(r['casos_a_10km'])}, {r['casos_a_10km_con_lluvia']} con lluvia observada",
        "Archivos": f"`{base}.parquet` y el mismo contenido en `.csv.gz`",
    }
    s = p.read_text()
    for k, v in filas.items():
        s = re.sub(rf"^\| {re.escape(k)} \| .* \|$", f"| {k} | {v} |", s, flags=re.M)
    p.write_text(s)


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1], sys.argv[2]), ensure_ascii=False, indent=1))
