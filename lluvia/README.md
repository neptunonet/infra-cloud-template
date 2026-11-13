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

El `metadata.json` también guarda los **tiempos** (`tiempos_s`: evaluación y entrenamiento final), las métricas **sobre
los datos de entrenamiento** (`evaluacion.en_entrenamiento`, del modelo y de la tabla, para compararlas con las de la
evaluación día por día) y el **commit del código** (`entorno.git_sha`, que el CI mete en la imagen al publicar).

**Dónde corre (decisión 30 del TF):** todos los días en el VPS de Clima Rutero (`scripts/entrenar_lluvia.sh`, cron
07:30, cuenta `lluvia-entrena`, 1 CPU y 1 GB); en GKE, como CronJob durante las sesiones de prueba. Misma imagen,
mismo bucket, misma regla.

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
| 2 de 3 modelos, falta WRF | modelo activo (sin WRF el Brier no cambia: H10) | — |
| 2 de 3 modelos, falta GFS o IFS (`degradado: true`) | `tabla_app` | `dos_modelos` |
| Menos de 2 modelos | `sin_dato` (`p: null`) | `menos_de_dos_modelos` |
| La receta activa es la tabla | `tabla_app` | `receta_activa_tabla` |

Lee el puntero `activa.json` al arrancar y cada `RECARGA_SEG` (300 s): una promoción del Job se toma sola, sin
reiniciar pods. Con `CLAVES=consumidor:clave,...` pide `X-API-Key`. Logs: una línea JSON por pedido con consumidor,
cantidad de tramos, fuentes y milisegundos; **sin coordenadas**.

Cierra cada conexión después de `CONEXION_MAX_PEDIDOS` pedidos (100) o `CONEXION_MAX_SEG` segundos (30) con
`Connection: close`. Kubernetes reparte conexiones, no pedidos: sin esto, un cliente con conexiones persistentes sigue en
los pods viejos y las réplicas nuevas del HPA no reciben nada (prueba en k3d del 12/11: 7.036 pedidos contra 23.750
con el cierre). Contador en `lluvia_conexiones_cerradas_total{motivo}`.

Con `DATABASE_URL` (chart `postgres`) registra cada pedido, también los rechazados, en `pedidos` y cada tramo en
`predicciones` (p, fuente, zona, degradado, motivo, votos y anticipación; sin coordenadas). Lo hace `registro.py` **en
segundo plano**: `/predict` deja el pedido en una cola y responde; un hilo escribe en lotes de hasta 50 (un INSERT por
pedido y COPY para los tramos). Si la base falla o no da abasto, la API sigue respondiendo y solo se pierde el registro,
contado en `lluvia_registro_total{resultado=ok|error|descartado}`. Sin `DATABASE_URL` no registra nada.

Cada pedido guarda siempre su **resumen** (`pedidos.resumen`: tramos por fuente, zona y motivo, degradados, sin dato,
probabilidad media y máxima). El **detalle tramo por tramo** va a `predicciones` solo en uno de cada `MUESTRA_TRAMOS`
pedidos (por defecto 20; `pedidos.con_detalle` dice cuáles). Guardando todos, el ensayo de carga del 12/11 llevó la base a
4,6 GB con 40 millones de filas; con la muestra, ~5 % de eso (esquema `002_resumen_y_muestra.sql`).

Medido en la notebook con el modelo real (11/11, 5 pedidos por tamaño): 1 tramo 7–19 ms · 156 tramos 12–14 ms ·
4.810 tramos 100–160 ms · 5.000 tramos 90–150 ms.

## Export diario (`exportar.py`)

Lo corre el VPS de Clima Rutero cada día (`scripts/export_lluvia.sh` y `scripts/export_lluvia.sql` en ese repo), con
la cuenta `lluvia-export`, que solo puede **crear** objetos en `datasets/`:

```bash
psql ... -v dia=2026-11-10 < export_lluvia.sql | python exportar.py --dia 2026-11-10 --destino gs://BUCKET/datasets
```

Valida antes de subir (columnas, al menos una fila, todas las franjas del día pedido) y sube `datasets/AAAA-MM-DD.parquet`
en una sola escritura. Si algo no cierra, no sube nada y sale con código 2. Como la cuenta no puede pisar, un día ya
subido no se puede reemplazar por error.

Si un día aparece en dos archivos (por ejemplo, la carga inicial y el export de ese día), `variables.filtrar` se queda
con la fila de más tramos.

## Imagen

Una sola imagen para la API y el entrenamiento, **multi-arch** (amd64 para GKE, arm64 para el VPS):

```bash
docker build -t lluvia:local lluvia/
docker run --rm -v "$PWD/datos:/datos:ro" -v "$PWD/artefactos:/artefactos" lluvia:local \
  python train.py --datos /datos/casos.csv --destino /artefactos          # entrenamiento (Job)
docker run -d -e DESTINO=/artefactos -v "$PWD/artefactos:/artefactos:ro" -p 8083:8083 lluvia:local   # API
```

El modelo no va dentro de la imagen: lo lee de `DESTINO`. Base `python:3.12.15-slim-trixie` + `libgomp1` (LightGBM),
usuario sin privilegios (uid 1000). Pesa ~1 GB sin comprimir (pyarrow 131 MB, scipy 153 MB, pandas 75 MB).
Probado el 11/11 en la notebook (amd64): entrena dentro del contenedor y la API queda `healthy`.

**CI:** tests y smoke test de `/healthz` como los otros servicios; en los pull requests además construye la versión
arm64 bajo QEMU y prueba que importe todo; al publicar sube un solo manifiesto con las dos arquitecturas.

## Registro de entrenamientos en Postgres (`cargar_versiones.py`)

El registro de cada entrenamiento es su `metadata.json` en el bucket (lo escribe `train.py`, hoy en el cron del VPS).
`cargar_versiones.py` lo pasa a `versiones` (una fila por versión, con el metadata completo en `jsonb`) y a
`evaluaciones` (una fila por receta evaluada: Brier con su IC 90 %, ECE y POD/FAR/CSI por sensibilidad). El chart lo
corre como Job después de cada `helm install`/`upgrade`, o sea, al prender el clúster (decisión 30). Idempotente: una
versión que ya está no se vuelve a escribir. Sin `DATABASE_URL` no hace nada.

## Tests

```bash
uv run --python 3.12 --with-requirements requirements.txt --with pytest --with httpx pytest -q
```

Con datos sintéticos: promoción, vuelta atrás a la tabla, falta de evidencia y línea de comandos (`test_train.py`);
zonas, fuentes, tope del lote, claves, sin versión activa, sin destino y métricas (`test_serve.py`); export válido,
vacío, de otro día o con otras columnas, y días repetidos (`test_exportar.py`); registro de pedidos y tramos, rechazados,
base caída, lotes, cola llena, sin base, resumen y muestra (`test_registro.py`); lectura de versiones, metadata viejo y sin base
(`test_cargar_versiones.py`); cierre de conexiones (`test_serve.py`). 35 en total, más dos contra Postgres real que corren solo con
`TEST_DATABASE_URL` (por ejemplo, el Postgres del k3d con `kubectl port-forward svc/postgres 15432:5432`).

## Archivos

| Archivo | Qué hace |
|---|---|
| `variables.py` | Filtros y variables; lo van a usar también la API, para calcular igual en los dos lados |
| `recetas.py` | Cómo entrena y predice cada receta |
| `evaluacion.py` | Ventana, evaluación día por día, Brier, calibración, avisos por sensibilidad, intervalos |
| `train.py` | El ciclo completo |
| `serve.py` | La API |
| `registro.py` | Registro de pedidos y predicciones en Postgres, en segundo plano |
| `cargar_versiones.py` | Pasa los `metadata.json` del bucket a `versiones` y `evaluaciones` (Job del chart) |
| `exportar.py` | Export diario desde el VPS: valida el CSV del día y lo sube como Parquet |
| `estaciones.csv` | Coordenadas de las estaciones METAR argentinas (aviationweather.gov, 09/11) |

## Pendiente

- Entrenar ocultando un modelo al azar, para que también responda el modelo cuando falta GFS o IFS (decisión 16). Medido
  el 13/11 (`TRABAJO FINAL/poc/paso8_modelo_oculto.py`): así queda empatado con la tabla; hoy solo falta WRF (0,2 %).
