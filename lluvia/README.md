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

## Tests

```bash
uv run --python 3.12 --with-requirements requirements.txt --with pytest pytest -q
```

Con datos sintéticos: promoción, vuelta atrás a la tabla, falta de evidencia y la línea de comandos.

## Archivos

| Archivo | Qué hace |
|---|---|
| `variables.py` | Filtros y variables; lo van a usar también la API, para calcular igual en los dos lados |
| `recetas.py` | Cómo entrena y predice cada receta |
| `evaluacion.py` | Ventana, evaluación día por día, Brier, calibración, avisos por sensibilidad, intervalos |
| `train.py` | El ciclo completo |

## Pendiente

- Probar contra el bucket real (`gs://`).
- Registrar cada entrenamiento en Postgres (hoy queda en `metadata.json`).
- API (`serve.py`), Dockerfile multi-arch, Job de Kubernetes y CI.
