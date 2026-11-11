# lluvia — servicio de probabilidad de lluvia por tramo (Trabajo Final)

Servicio de modelo para Clima Rutero: dado lo que prevén GFS, ECMWF IFS y WRF-SMN para una franja de 3 h, y los
rayos cercanos, devuelve la probabilidad de lluvia. El umbral de aviso no lo fija el servicio: lo elige quien usa
la app (decisiones 25 y 26 del TF).

## Entrenamiento (`train.py`)

```bash
uv run --python 3.12 --with-requirements requirements.txt python train.py \
  --datos ruta/a/casos.csv --destino ./artefactos
# en GKE, con el bucket:
python train.py --datos 'gs://BUCKET/datasets/*.parquet' --destino gs://BUCKET/modelos
```

Cada corrida entrena, evalúa, versiona y decide:

1. **Datos:** el export de Clima Rutero (una fila por estación METAR × franja de 3 h × emisión). Filtros: tramos a
   ≤ 10 km de la estación, sin pedidos de usuarios, anticipación de 0 a 6 h, los 3 modelos disponibles.
2. **Evaluación:** día por día sobre los últimos 14 días (se estira hasta tener ≥ 30 casos con lluvia en ≥ 5 días),
   entrenando cada día con los datos hasta dos días antes. Cada caso pesa 1. Intervalos del 90 % remuestreando días.
3. **Recetas:** `tabla_app` (referencia fija: la tabla de votos de la app), `logistica_rayos` y `lgbm_chico`.
4. **Decisión:**
   - una receta aprendida es **apta** si le gana a la tabla en Brier con el intervalo debajo de cero y su error de
     calibración es ≤ 0,05;
   - si la activa deja de ser apta, **vuelve sola a la tabla** (vuelta atrás automática);
   - una candidata reemplaza a la activa solo si le gana a ella con el intervalo debajo de cero;
   - sin evidencia mínima no cambia de receta;
   - POD, FAR y CSI de cada sensibilidad se guardan pero no deciden.
5. **Salida:** `versiones/vAAAAMMDD_HHMMSS/modelo.joblib` + `metadata.json` (datos con sha256, filtros, ventana,
   métricas de cada receta, comparaciones, decisión y versiones de librerías) y el puntero `activa.json`. Si queda
   la tabla, igual se guarda la mejor receta aprendida, en sombra. Al final imprime una línea JSON para los logs.

Lee y escribe igual en disco local o en `gs://` (fsspec + gcsfs).

## API (`serve.py`)

```bash
DESTINO=./artefactos uv run --python 3.12 --with-requirements requirements.txt python serve.py   # puerto 8083
```

| Endpoint | Qué hace |
|---|---|
| `POST /predict` | Lote de hasta 5.000 tramos (413 si se pasa) → probabilidad, zona y fuente de cada uno |
| `GET /version` | Versión y receta servidas |
| `GET /healthz` | 200 cuando ya leyó el puntero; 503 antes |
| `GET /metrics` | Pedidos, tramos por fuente y zona, latencia, tamaño del lote, probabilidades devueltas, versión |

Cada tramo lleva `lat`, `lon`, `hora_paso_utc`, `emision_utc`, `votos`, `lluvia_mm_3h` y `ciclos` por modelo
(`gfs`, `ifs`, `wrf`), y opcionalmente `tormenta_nivel` y `tormenta_dist_km`. La respuesta por tramo:

| Caso | `fuente` | `motivo` |
|---|---|---|
| Estación entrenada a ≤ 10 km (`verificada`) o a ≤ 150 km (`region_entrenada`) | `modelo` | — |
| Zona no vista (decisiones 23 y 24) | `tabla_app` | `zona_no_vista` |
| Anticipación mayor a 6 h | `tabla_app` | `anticipacion_mayor_6h` |
| 2 de 3 modelos (`degradado: true`) | `tabla_app` | `dos_modelos` |
| Menos de 2 modelos | `sin_dato` (`p: null`) | `menos_de_dos_modelos` |
| La receta activa es la tabla | `tabla_app` | `receta_activa_tabla` |

Lee el puntero `activa.json` al arrancar y cada `RECARGA_SEG` (300 s): una promoción del Job se toma sola, sin
reiniciar pods. Con `CLAVES=consumidor:clave,...` pide `X-API-Key`. Logs: una línea JSON por pedido con consumidor,
cantidad de tramos, fuentes y milisegundos; **sin coordenadas**.

Medido en la notebook con el modelo real (11/11, 5 pedidos por tamaño): 1 tramo 7–19 ms · 156 tramos 12–14 ms ·
4.810 tramos 100–160 ms · 5.000 tramos 90–150 ms.

## Tests

```bash
uv run --python 3.12 --with-requirements requirements.txt --with pytest --with httpx pytest -q
```

Con datos sintéticos: promoción, vuelta atrás a la tabla, falta de evidencia y línea de comandos (`test_train.py`);
zonas, fuentes, tope del lote, claves, sin versión activa, sin destino y métricas (`test_serve.py`). 15 en total.

## Archivos

| Archivo | Qué hace |
|---|---|
| `variables.py` | Filtros y variables; lo van a usar también la API, para calcular igual en los dos lados |
| `recetas.py` | Cómo entrena y predice cada receta |
| `evaluacion.py` | Ventana, evaluación día por día, Brier, calibración, avisos por sensibilidad, intervalos |
| `train.py` | El ciclo completo |
| `serve.py` | La API |
| `estaciones.csv` | Coordenadas de las estaciones METAR argentinas (aviationweather.gov, 09/11) |

## Pendiente

- Probar contra el bucket real (`gs://`).
- Registrar cada entrenamiento en Postgres (hoy queda en `metadata.json`).
- Entrenar ocultando un modelo, para que con 2 de 3 responda el modelo y no la tabla (decisión 16).
- Dockerfile multi-arch, Job de Kubernetes y CI.
