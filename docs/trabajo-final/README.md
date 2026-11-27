# Trabajo Final — fuentes del informe

Lo que cita el informe del Trabajo Final (*Clima Rutero: probabilidad de lluvia por tramo de ruta*) y no es código del
servicio. El despliegue reproducible está en [`../trabajo-final.md`](../trabajo-final.md); el código, en `lluvia/`,
`helm/charts/`, `observability/lluvia/`, `loadtest/` y `terraform/`.

| Carpeta | Qué hay | Dónde lo cita el informe |
|---|---|---|
| [`pruebas/`](pruebas/) | Resultados crudos y notas de cada sesión: `grilla-gke-2026-11-13.csv` (48 corridas: réplicas × usuarios × tamaño de lote), `hpa-lotes-grandes-gke-2026-11-13.txt`, las dos sesiones de GKE, la latencia desde el VPS (H12), el ensayo en k3d, los probes bajo carga y la cobertura de los METAR | 5.2 a 5.5, 7.2 |
| [`graficos/`](graficos/) | `versiones.csv` (una fila por versión entrenada, sacada de los `metadata.json` del bucket) y los scripts que arman los gráficos del informe (`versiones.py`, `graficos_gke1.py`) | 5.2, 5.3, 5.6 |
| [`poc/`](poc/) | Bitácora de la prueba de concepto del modelo (`README.md`), sus scripts y la salida de cada paso (`salidas/`) | 5.7 |
| [`dataset/`](dataset/) | `armar_dataset.py`: arma la copia publicada del dataset a partir de los exports diarios | 7.3 |
| [`capturas/`](capturas/) | Las capturas numeradas que respaldan cada parte (el PDF incluye solo algunas) | tabla de la sección 3 |

## Datos

- **Dataset publicado:** release
  [`dataset-2026-11`](https://github.com/neptunonet/infra-cloud-template/releases/tag/dataset-2026-11). No trae la
  columna `es_api` porque se le quitaron las filas de pedidos de usuarios; `lluvia/variables.py` la completa si falta, y
  `lluvia/tests/test_train.py` entrena con una muestra de ese archivo.
- **Lo que no se publica:** `poc/datos/casos.csv` y la carga inicial del bucket, que usaron los scripts de la PoC, incluyen
  filas de pedidos de usuarios. Por eso los scripts de `poc/` no corren tal cual (leen `datos/casos.csv`): quedan como
  registro de cómo se obtuvo cada número, junto con la salida de cada paso en `poc/salidas/`.

## Regenerar

```bash
cd docs/trabajo-final/graficos
uv run --with pandas --with matplotlib python graficos_gke1.py   # grilla-gke1.png y hpa-gke1.png, desde ../pruebas/
uv run --with pandas --with matplotlib python versiones.py       # versiones.csv y versiones.png (pide acceso al bucket)
```
