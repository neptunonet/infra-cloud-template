"""Carga en Postgres las versiones entrenadas (Trabajo Final, consigna 2.4 y decisión 30).

El registro de entrenamientos es el `metadata.json` de cada versión en el bucket: lo escribe train.py, corra donde
corra (hoy, el cron del VPS). Este script los pasa a las tablas `versiones` y `evaluaciones` para poder consultarlos
con SQL junto con los pedidos. Corre como Job de Kubernetes cada vez que se instala o actualiza el chart (o sea, al
prender el clúster) y se puede correr a mano.

Idempotente: una versión que ya está en la base no se vuelve a escribir (el metadata de una versión no cambia).
Sin DATABASE_URL termina sin hacer nada (código 0), para no trabar un despliegue sin Postgres.

Uso:
  DESTINO=gs://BUCKET/modelos DATABASE_URL=postgresql://... python cargar_versiones.py
"""

from __future__ import annotations

import json
import os
import sys
import time

import fsspec
from psycopg.types.json import Jsonb


def leer_metadatas(destino: str) -> list[dict]:
    fs, raiz = fsspec.core.url_to_fs(destino.rstrip("/"))
    rutas = sorted(fs.glob(f"{raiz}/versiones/*/metadata.json"))
    return [json.loads(fs.cat_file(r)) for r in rutas]


def fila_version(m: dict) -> tuple:
    datos, decision, tiempos = m.get("datos", {}), m.get("decision", {}), m.get("tiempos_s") or {}
    return (m["version"], m["creada_utc"], m.get("receta"), decision.get("receta_elegida") or m.get("receta"),
            bool(decision.get("promovida")), decision.get("motivo"), (m.get("entorno") or {}).get("git_sha"),
            tiempos.get("evaluacion"), tiempos.get("entrenamiento_final"), datos.get("desde"), datos.get("hasta"),
            datos.get("casos"), datos.get("casos_con_lluvia"), Jsonb(m))


def filas_evaluacion(m: dict) -> list[tuple]:
    out = []
    for receta, r in ((m.get("evaluacion") or {}).get("recetas") or {}).items():
        ic = r.get("brier_ic90") or [None, None]
        out.append((m["version"], receta, r["brier"], ic[0], ic[1], r.get("ece"), Jsonb(r.get("sensibilidades"))))
    return out


def conectar(url: str, intentos: int = 12, espera_seg: float = 5):
    """Postgres puede estar arrancando cuando corre el Job (se instalan juntos): reintenta ~1 minuto."""
    import psycopg

    for i in range(intentos):
        try:
            return psycopg.connect(url, connect_timeout=5, application_name="lluvia-cargar-versiones")
        except psycopg.OperationalError:
            if i == intentos - 1:
                raise
            time.sleep(espera_seg)


def cargar(metadatas: list[dict], conexion) -> dict:
    nuevas = 0
    with conexion.transaction(), conexion.cursor() as cur:
        for m in metadatas:
            cur.execute(
                "INSERT INTO versiones (version, creada_utc, receta, receta_elegida, promovida, motivo, git_sha,"
                " t_evaluacion_s, t_entrenamiento_s, datos_desde, datos_hasta, casos, casos_con_lluvia, metadata)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                " ON CONFLICT (version) DO NOTHING", fila_version(m))
            if cur.rowcount == 0:  # ya estaba
                continue
            nuevas += 1
            cur.executemany(
                "INSERT INTO evaluaciones (version, receta, brier, brier_ic90_bajo, brier_ic90_alto, ece,"
                " sensibilidades) VALUES (%s, %s, %s, %s, %s, %s, %s)", filas_evaluacion(m))
    return {"en_bucket": len(metadatas), "nuevas": nuevas, "ya_estaban": len(metadatas) - nuevas}


def main() -> int:
    destino, url = os.environ.get("DESTINO"), os.environ.get("DATABASE_URL")
    if not url:
        print(json.dumps({"evento": "cargar_versiones", "omitido": "sin DATABASE_URL"}), flush=True)
        return 0
    if not destino:
        print("falta la variable DESTINO", file=sys.stderr)
        return 2
    metadatas = leer_metadatas(destino)
    with conectar(url) as con:
        res = cargar(metadatas, con)
    print(json.dumps({"evento": "cargar_versiones", **res}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
