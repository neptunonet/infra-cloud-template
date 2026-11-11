import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def datos_sinteticos(escenario: str, dias: int = 22, estaciones: int = 6, tasa_lluvia: float = 1.0,
                     semilla: int = 0) -> pd.DataFrame:
    """Dataset con las columnas del export de Clima Rutero.

    - "aprende": la lluvia depende de cuánto prevé GFS y los votos casi no ayudan (un modelo le gana a la tabla).
    - "tabla":   la lluvia sale exactamente de la tabla de votos (ningún modelo le puede ganar).
    `tasa_lluvia` < 1 achica la lluvia para probar la falta de evidencia.
    """
    from recetas import TABLA_APP

    rng = np.random.default_rng(semilla)
    filas = []
    inicio = pd.Timestamp("2026-10-01 03:00")
    for dia in range(dias):
        for est in range(estaciones):
            for f in range(8):
                franja = inicio + pd.Timedelta(days=dia, hours=3 * f)
                gfs = rng.exponential(1.0) * rng.integers(0, 2)
                votos = int(rng.integers(0, 4))
                if escenario == "aprende":
                    p = 1 / (1 + np.exp(-(-2.5 + 2.5 * np.log1p(gfs))))
                else:
                    p = TABLA_APP[votos]
                llovio = rng.random() < p * tasa_lluvia
                for e in range(3):
                    emision = franja - pd.Timedelta(minutes=15 * (e + 2))
                    filas.append({
                        "estacion": f"SA{est:02d}", "franja_utc": franja, "emision_utc": emision,
                        "es_api": "f", "cerca_10km": "t", "n_filas": 10, "n_tramos": 3, "dist_km_media": 5.0,
                        "anticip_h": (franja - emision).total_seconds() / 3600, "votos_media": votos,
                        "votos_max": votos, "disponibles_min": 3, "mm3h_media": gfs, "mm3h_max": gfs,
                        "gfs_media": gfs, "gfs_max": gfs, "ifs_media": rng.exponential(0.5),
                        "ifs_max": rng.exponential(0.5), "wrf_media": rng.exponential(0.5),
                        "wrf_max": rng.exponential(0.5),
                        "ciclo_gfs": (franja - pd.Timedelta(hours=6)).isoformat() + "+00:00",
                        "ciclo_ifs": (franja - pd.Timedelta(hours=12)).isoformat() + "+00:00",
                        "ciclo_wrf": (franja - pd.Timedelta(hours=6)).isoformat() + "+00:00",
                        "viento_media": 3.0, "rafaga_max": 6.0, "tormenta_calculada": 0,
                        "tormenta_nivel_max": np.nan, "tormenta_dist_min": np.nan, "tormenta_minutos_min": np.nan,
                        "obs_lluvia": "t" if llovio else "f", "obs_rayos": "f", "obs_rayos_n": 0,
                    })
    return pd.DataFrame(filas)
