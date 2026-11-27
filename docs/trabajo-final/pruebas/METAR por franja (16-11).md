# ¿Las estaciones informan en cada franja? («no llovió» contra «no informó») — 16/11/2026

Pendiente desde la decisión 17. Período 19/10–15/11 (28 días, 224 bloques de 3 h por estación), las 9 estaciones del
dataset.

## Cómo arma la etiqueta Clima Rutero (`src/clima_rutero/verificacion.py`)

- Toma el METAR más cercano (≤ 30 km) y mira todos sus reportes (METAR y SPECI) dentro del bloque de 3 h del paso.
- «Llovió» si **alguno** tiene precipitación presente o reciente (RA, DZ, SH, TS, también con `RE`).
- **Si la estación no mandó ningún reporte en el bloque, la etiqueta queda vacía (`NULL`)** y el export del TF la
  descarta (`WHERE obs_lluvia IS NOT NULL`). Así que «no informó» **no** se confunde con «no llovió».
- El riesgo que queda: una estación que informa **poco** dentro del bloque (1 reporte en 3 h) puede perderse una lluvia
  corta entre reportes; el código `RE` (precipitación reciente) lo cubre en parte.

## Medido

Reportes por bloque, del archivo público de METAR de Iowa State (IEM), con la misma regla de precipitación:

| Estación | METAR por día | Bloques sin reporte | Con 1 | Con 2 | Con 3 o más | Bloques con lluvia |
|---|---|---|---|---|---|---|
| SAAR | 25,5 | 0 | 0 | 1 | 223 | 40 |
| SAAV | 24,9 | 0 | 1 | 3 | 220 | 37 |
| SACO | 25,5 | 0 | 0 | 0 | 224 | 31 |
| **SADJ** | **14,3** | **57** | **56** | 2 | 109 | 24 |
| SADL | 24,6 | 0 | 1 | 7 | 216 | 25 |
| SADM | 24,0 | 0 | 2 | 10 | 212 | 22 |
| SADP | 24,9 | 0 | 0 | 1 | 223 | 32 |
| **SAMM** | 20,5 | **26** | **14** | 0 | 184 | 21 |
| SAMR | 24,6 | 0 | 0 | 3 | 221 | 35 |

En la base de Clima Rutero (consulta de solo lectura): los bloques sin dato son el 0,1–0,4 % de las predicciones en 7
estaciones, **24,9 % en SADJ** y **11,2 % en SAMM**, y caen casi todos en los bloques de 03 y 06 UTC (de 0 a 6, hora
argentina): **esas dos estaciones no informan de noche** (SADJ, 27 de 28 noches; SAMM, 12).

## Lectura

- **Siete de nueve estaciones informan cada hora** (≥ 3 reportes en el 97–100 % de los bloques): ahí la etiqueta es
  confiable.
- **SADJ (Mariano Moreno) y SAMM (Malargüe) cierran de noche.** Los bloques sin reporte se descartan solos, así que no
  hay «no llovió» inventados; pero el modelo **no ve lluvias nocturnas** en esas dos estaciones.
- **El riesgo real son los bloques con un solo reporte** (5,2 % de los bloques con dato en total; casi todos en SADJ, 56,
  y SAMM, 14): son los de apertura y cierre. Ahí una lluvia corta puede quedar como «no llovió».
- Mejora posible, fuera del TF: descartar también los bloques con menos de 2 reportes, o marcar la cobertura en el
  export para pesarla.
