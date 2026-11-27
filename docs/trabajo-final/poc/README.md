# Prueba de concepto del modelo — bitácora

Se hace en la notebook, sin GCP. Objetivo: saber si un modelo aprendido le gana a la tabla de votos corregida
(Brier 0,127, medido sobre los mismos datos) antes de armar la infraestructura.

## Paso 1 — Export de los casos desde el VPS (09/11/2026, hecho)

- **Consulta:** `export_casos.sql` (solo lectura, `COPY ... TO STDOUT`). La corrió Juan desde `ubuntunote007`:
  ```bash
  ssh vps-oracle "cd ~/clima-rutero && docker compose exec -T db psql -U clima_rutero -d clima_rutero" < export_casos.sql > datos/casos.csv
  ```
- **Salida:** `datos/casos.csv` (12,9 MB, 57.524 filas, 32 columnas). `datos/estaciones.csv`: las 93 estaciones METAR
  argentinas con lat/lon (aviationweather.gov, 09/11), que la base no guarda.
- **Grano:** una fila por estación METAR × franja de 3 h (UTC) × emisión (cada 15 min) × `es_api` × `cerca_10km`.
  Es más fino que el caso (estación × franja) a propósito: deja elegir en la notebook cómo agrupar por anticipación
  sin volver al VPS. Las variables se agregan entre los tramos que comparten estación (media y máximo).
- **Privacidad:** no sale ninguna coordenada de viaje, solo el código de la estación. Las filas de pedidos reales
  quedan marcadas con `es_api` para poder excluirlas.
- **Columnas:** `estacion, franja_utc, emision_utc, es_api, cerca_10km, n_filas, n_tramos, dist_km_media, anticip_h,
  votos_media, votos_max, disponibles_min, mm3h_media, mm3h_max, {gfs,ifs,wrf}_{media,max}, ciclo_{gfs,ifs,wrf},
  viento_media, rafaga_max, tormenta_calculada, tormenta_nivel_max, tormenta_dist_min, tormenta_minutos_min,
  obs_lluvia, obs_rayos, obs_rayos_n`. Los booleanos salen como `t`/`f`
  (`pd.read_csv(..., true_values=["t"], false_values=["f"])`).

### Verificación del archivo

| Conjunto | Casos (estación × franja) | Con lluvia |
|---|---|---|
| Todo (≤ 30 km) | 1.536 | 241 |
| ≤ 10 km | 1.362 | 218 |
| ≤ 10 km, sin pedidos de usuarios | 1.293 | 204 |

- Coincide con lo medido a la tarde (1.527 casos y 241 lluvias; a 10 km, 1.336 y 216 con 12 estaciones): la
  diferencia son las horas que pasaron y que ahora entran las 20 estaciones con datos (19 a ≤ 10 km).
- Período: 19/10 18:00 a 09/11 21:00 UTC (22 días). Filas de origen resumidas: 2.001.390 (875.462 a ≤ 10 km).
- Ningún caso tiene etiqueta contradictoria entre emisiones.
- Emisiones por caso (≤ 10 km): mediana 25.
- Modelos disponibles: 3 en 57.350 filas, 2 en 173, 1 en 1. `wrf_*` vacío en el 0,3 %.
- Aviso de rayos: `tormenta_nivel_max` vacío en el 60 % de las filas (sin nowcast calculado para ese plazo).

### A tener en cuenta en el paso siguiente

- **`anticip_h` va de −5,2 a 25,9 h** (mediana 2,5). Hay emisiones posteriores a la hora de paso: hay que filtrar
  `anticip_h >= 0` (y ≤ 6 h, que es el alcance decidido) antes de entrenar, o sería fuga.
- Una fila es una emisión, no un caso: para evaluar hay que agrupar por caso o ponderar, y el corte train/test va
  por días completos.

## Paso 2 — Referencias sin aprendizaje, fuera de muestra (09/11/2026, hecho)

- **Script:** `paso2_referencia.py` (`uv run --with pandas --with numpy python paso2_referencia.py`). Salida guardada
  en `salidas/paso2_salida.txt`.
- **Filtros:** etiqueta a ≤ 10 km, sin pedidos de usuarios, anticipación entre 0 y 6 h, los 3 modelos disponibles.
  Quedan 31.618 filas = **1.293 casos, 204 con lluvia, 22 días**.
- **Unidad:** se evalúa cada emisión, pero pesada para que **cada caso pese 1** (un caso tiene ~25 emisiones).
  Votos = promedio entre tramos, redondeado. Día = fecha en hora argentina.
- **Tres referencias:** climatología (frecuencia de entrenamiento), tabla de la app (5/21/47/78 %) y la misma tabla
  ajustada con los días de entrenamiento (suavizada y sin dejarla bajar al subir los votos).
- **Dos evaluaciones:** (A) un corte: 14 días para ajustar, 1 de separación, 7 de prueba; (B) día por día: cada día
  se predice con la tabla ajustada hasta dos días antes (mínimo 7 días), que es como va a funcionar el ciclo real.
- Aviso a partir de probabilidad 0,20. Intervalos del 90 % remuestreando días enteros (2.000 veces).

| Evaluación | Referencia | Brier | IC 90 % | POD | FAR | CSI |
|---|---|---|---|---|---|---|
| A (7 días, 426 casos, 46 con lluvia, 3 días con lluvia) | Climatología | 0,103 | 0,052 a 0,161 | 0,00 | — | 0,00 |
| | Tabla de la app | 0,064 | 0,026 a 0,103 | 0,94 | 0,61 | 0,39 |
| | Tabla recalibrada | 0,063 | 0,023 a 0,105 | 0,65 | 0,51 | 0,38 |
| B (14 días, 850 casos, 102 con lluvia, 10 días con lluvia) | Climatología | 0,113 | 0,078 a 0,149 | 0,11 | 0,94 | 0,04 |
| | Tabla de la app | 0,077 | 0,052 a 0,103 | 0,92 | 0,68 | 0,31 |
| | **Tabla recalibrada** | **0,075** | 0,049 a 0,101 | 0,66 | 0,61 | 0,33 |

Tabla ajustada con los primeros 14 días: 0 votos = 0,05 · 1 voto = 0,17 · 2 votos = 0,38 · 3 votos = 0,71.

### Lectura

- **La vara es Brier ≈ 0,075** (evaluación B). No se compara con el 0,127 de la devolución: aquel era por caso ×
  votos, a 30 km, con todas las anticipaciones y sobre los mismos datos del ajuste.
- **La recalibración casi no mejora el Brier fuera de muestra:** −0,0014, con intervalo de −0,0045 a +0,0017. No
  alcanza para decir que la tabla recalibrada es mejor que la de la app.
- **Sí cambia los avisos:** con 1 voto la probabilidad baja de 0,21 a 0,17 y queda debajo del umbral de 0,20, así
  que deja de avisar. El POD cae de 0,92 a 0,66 y las falsas alarmas bajan poco (0,68 a 0,61). Confirma la decisión
  de mirar POD y FAR como resguardo y no solo el Brier, y que **el umbral hay que elegirlo junto con la tabla**.
- Los intervalos son anchos: 10 días con lluvia en la prueba. Para que un modelo «gane», la diferencia tiene que
  medirse apareada, día por día, como acá.
- Las dos tablas le ganan claro a la climatología (0,113).

## Paso 3 — Regresión logística (09/11/2026, hecho)

- **Script:** `paso3_logistica.py` (`uv run --with pandas --with numpy --with scikit-learn python paso3_logistica.py`).
  Salida en `salidas/paso3_salida.txt`. Reutiliza la carga, los filtros y las métricas del paso 2.
- **Modelo:** `StandardScaler` + `LogisticRegression(C=1.0)`, con el peso por caso como `sample_weight`.
- **13 variables, sin rayos y sin lat/lon:** lluvia prevista por modelo (media y máximo entre tramos, en `log1p`),
  antigüedad de la corrida de cada modelo, votos, anticipación y hora de la franja (seno y coseno, hora argentina).
  Los rayos quedan para el paso 5.

| Evaluación | Modelo | Brier | IC 90 % | POD | FAR | CSI |
|---|---|---|---|---|---|---|
| A (7 días, 3 con lluvia) | Tabla de la app | 0,064 | 0,026 a 0,105 | 0,94 | 0,61 | 0,39 |
| | Tabla recalibrada | 0,063 | 0,023 a 0,104 | 0,65 | 0,51 | 0,38 |
| | Logística | 0,062 | 0,023 a 0,104 | 0,70 | 0,53 | 0,39 |
| B (14 días, 10 con lluvia) | Tabla de la app | 0,077 | 0,052 a 0,102 | 0,92 | 0,68 | 0,31 |
| | Tabla recalibrada | 0,075 | 0,050 a 0,101 | 0,66 | 0,61 | 0,33 |
| | **Logística** | **0,073** | 0,045 a 0,100 | 0,68 | 0,59 | 0,34 |

Diferencias apareadas de Brier (negativa = gana la logística):

| Evaluación | Contra la tabla de la app | Contra la tabla recalibrada | Días que le gana a la app |
|---|---|---|---|
| A | −0,0022 (−0,0071 a +0,0028) | −0,0011 (−0,0032 a +0,0007) | 5 de 7 |
| B | **−0,0042 (−0,0078 a −0,0004)** | **−0,0028 (−0,0054 a −0,0005)** | 9 de 14 |

Calibración en la prueba B (probabilidad dicha → frecuencia observada): 0,03 → 0,01 · 0,07 → 0,04 · 0,14 → 0,17 ·
0,28 → 0,18 · 0,50 → 0,48 · 0,77 → 0,71.

Coeficientes más grandes (variables estandarizadas, modelo con todos los días): votos 1,01 · GFS máximo 0,84 ·
GFS media −0,55 · hora (cos 0,29, sin 0,23) · WRF media 0,27 · IFS media 0,24. Anticipación y antigüedad, cerca de 0.

### Lectura

- **La logística le gana a las dos tablas en la evaluación día por día**, y el intervalo no incluye el cero. La
  mejora es chica: 5 % de Brier contra la tabla de la app. En el corte único (3 días con lluvia) no se distingue.
- **Los votos siguen siendo la variable que más pesa.** Lo que agrega la logística es la cantidad de lluvia de cada
  modelo y la hora del día. Los signos opuestos de «media» y «máximo» del mismo modelo son por colinealidad: no se
  interpretan uno por uno.
- **Anticipación y antigüedad no aportan** dentro de las 6 h. Coincide con el punto 6 de la devolución.
- **Calibración razonable**, con un tramo flojo: cuando dice ~28 % se observa 18 %. Justo alrededor del umbral.
- Con umbral 0,20 avisa menos que la app (POD 0,68 contra 0,92). No es que detecte peor: es otro punto de la misma
  curva. **Pendiente: comparar a igual POD** (elegir el umbral de la logística que dé el POD de la app y mirar el FAR).

## Paso 3b — Avisos a igual detección (09/11/2026, hecho)

- **Script:** `paso3b_avisos.py`; salida en `salidas/paso3b_salida.txt`. Misma prueba B (14 días, 850 casos, 102 con
  lluvia).
- La app avisa por votos: 1 o más («posible») y 2 o más («probable»). A la logística se le busca el umbral que da
  el mismo POD, de dos formas: **en prueba** (mirando los días evaluados; es el techo) y **operativo** (cada día,
  con el umbral que igualaba el POD de la app en los días de entrenamiento).

| Aviso | Quién avisa | POD | FAR | CSI | Franjas con aviso |
|---|---|---|---|---|---|
| «Posible» | App (1 voto o más) | 0,92 | 0,68 | 0,31 | 35,0 % |
| | Logística, umbral en prueba (0,08) | 0,92 | 0,73 | 0,26 | 41,1 % |
| | Logística, umbral operativo (mediana 0,11) | 0,86 | 0,63 | 0,35 | 27,8 % |
| «Probable» | App (2 votos o más) | 0,65 | 0,55 | 0,36 | 17,5 % |
| | Logística, umbral en prueba (0,23) | 0,65 | 0,56 | 0,36 | 17,7 % |
| | Logística, umbral operativo (mediana 0,26) | 0,62 | 0,51 | 0,37 | 15,3 % |

Diferencias contra la app (IC 90 % por día): a igual POD 0,92, FAR **+0,047** (+0,014 a +0,072); a igual POD 0,65,
FAR +0,004 (−0,013 a +0,020). Con el umbral operativo: «posible» POD −0,058 y FAR −0,056; «probable» POD −0,034 y
FAR −0,039.

### Lectura

- **A igual detección, la logística no avisa mejor que los votos.** Para llegar al 92 % de las lluvias necesita
  avisar en más franjas (41 % contra 35 %) y tiene más falsas alarmas. En «probable» empata.
- **La mejora de Brier del paso 3 es de calibración, no de separación:** dice mejor el número (36 % en vez de
  47 %), pero no ordena las franjas mejor que contar votos. Con estas 13 variables, la información que separa
  lluvia de no lluvia ya está casi toda en los votos.
- El umbral operativo no es una mejora: es otro punto de la misma curva (menos lluvias avisadas, menos falsas
  alarmas). Además se mueve entre 0,09 y 0,18 según el día: con tres semanas de datos el umbral es inestable.
- **Consecuencia para el TF:** el argumento a favor del modelo aprendido, hoy, es «da una probabilidad honesta», no
  «avisa mejor». Para avisar mejor hace falta información nueva (rayos, paso 5) o un modelo que capture
  combinaciones (LightGBM, paso 4). Si ninguno separa mejor, eso es un resultado válido y se informa así.

## Paso 5 — Rayos: ¿suman sobre los pronósticos? (09/11/2026, hecho antes que el 4)

- **Script:** `paso5_rayos.py`; salida en `salidas/paso5_salida.txt`. Ablación: dos logísticas iguales, una con las 13
  variables del paso 3 y otra con 3 más de rayos (`ray_calculado`, `ray_nivel` 0/1/2, `ray_cercania` =
  exp(−distancia/20)). Misma prueba día por día.
- **Dato de diseño:** el aviso de rayos solo se calcula si el paso cae en los 60 minutos siguientes a la emisión
  (60 % de las filas no lo tienen). Se evalúa en tres conjuntos: todo, solo con aviso calculado, y **limpio**
  (con aviso calculado y emitido **antes** de que empiece la franja de 3 h). El limpio responde el pendiente de la
  devolución: ahí el rayo no puede ser consecuencia de una lluvia que ya empezó en esa franja.

Dato crudo en el conjunto limpio (622 casos, 77 con lluvia, 8 días con lluvia):

| Pronóstico | Aviso de rayos | Casos | Llovió |
|---|---|---|---|
| Dice lluvia | Nada | 206 | 30 % |
| Dice lluvia | Atención | 3,6 | 63 % |
| Dice lluvia | Llegando | 11,4 | 93 % |
| No dice lluvia | Nada | 400 | 1 % |

| Conjunto | Brier app | Brier sin rayos | Brier con rayos | Diferencia con − sin (IC 90 %) |
|---|---|---|---|---|
| Todo (850 casos) | 0,077 | 0,073 | 0,071 | −0,0018 (−0,0043 a +0,0001) |
| Con aviso calculado (628 casos) | 0,074 | 0,068 | 0,064 | −0,0046 (−0,0099 a −0,0002) |
| **Limpio (622 casos)** | 0,073 | 0,070 | **0,062** | **−0,0084 (−0,0173 a −0,0013)** |

Avisos «posible» a igual POD que la app (conjunto limpio, POD 0,96): app FAR 0,67 · logística sin rayos 0,73 ·
con rayos 0,70 (con − sin: −0,026, IC 90 % −0,047 a −0,008).

### Lectura

- **Los rayos suman, y el efecto sobrevive a la prueba limpia:** con el aviso emitido antes de la franja, el Brier
  baja 12 % respecto de la logística sin rayos y el intervalo no incluye el cero. Responde la pregunta del docente
  («¿cómo comprobás que suman por encima de los pronósticos?»).
- **Pero el aviso es raro:** hay rayos en unos 15 de 622 casos (2,4 %). Cuando aparece «llegando» con pronóstico de
  lluvia, llovió el 93 % de las veces, pero son 11 casos de muy pocos días: el intervalo real es ancho.
- **Mejoran la parte alta de la probabilidad, no el aviso «posible».** A igual detección la logística con rayos
  sigue teniendo más falsas alarmas que los votos (0,70 contra 0,67). Los rayos sirven para decir «viene seguro»,
  no para descartar falsas alarmas.
- Sobre todas las emisiones el efecto se diluye (−0,0018, el intervalo roza el cero), porque la mayoría no tiene
  aviso calculado.
- De las tres variables pesa la cercanía (0,29); el nivel y el indicador de «calculado» casi no (0,03).
- **Decisión que sale de acá:** los rayos quedan como variable del modelo. Límite a declarar: solo actúan en la
  última hora antes del paso.

## Paso 4 — LightGBM (09/11/2026, hecho)

- **Script:** `paso4_lightgbm.py`; salida en `salidas/paso4_salida.txt`. Mismas 16 variables que la logística con
  rayos, misma prueba día por día (14 días, 850 casos, 102 con lluvia).
- **Dos configuraciones fijadas de antemano, sin ajustar mirando la prueba:** `lgbm_chico` (150 árboles, 4 hojas,
  `min_child_samples=500`, tasa 0,03, submuestreo 0,8, `reg_lambda=5`) y `lgbm_defecto` (valores de la librería).

| Modelo | Brier | IC 90 % | FAR a POD 0,92 («posible») | FAR a POD 0,65 («probable») |
|---|---|---|---|---|
| Tabla de la app | 0,077 | 0,052 a 0,104 | 0,68 | 0,55 |
| **Logística con rayos** | **0,071** | 0,046 a 0,099 | 0,73 | 0,53 |
| LightGBM chico | 0,073 | 0,047 a 0,097 | 0,71 | 0,52 |
| LightGBM por defecto | 0,088 | 0,061 a 0,121 | 0,76 | 0,59 |

Diferencias apareadas (IC 90 %): Brier LightGBM chico − logística **+0,0027** (−0,0011 a +0,0062); − tabla de la
app −0,0033 (−0,0061 a −0,0008); LightGBM por defecto − logística +0,0175 (+0,0101 a +0,0247). FAR LightGBM chico −
app: «posible» +0,020 (−0,002 a +0,041); «probable» **−0,034 (−0,058 a −0,007)**.

Importancia en LightGBM chico (% de la ganancia): votos 31,7 · GFS media 20,3 · IFS media 20,1 · WRF máximo 9,2 ·
IFS máximo 5,5 · hora 5,0 · GFS máximo 4,2 · cercanía de rayos 1,8.

### Lectura

- **LightGBM no le gana a la logística.** El chico queda apenas peor en Brier (la diferencia no se distingue del
  cero) y el de valores por defecto sobreajusta claro: es peor que la tabla de la app.
- **Con ~200 lluvias en 22 días no hay datos para un modelo más flexible.** La logística es el mejor modelo hoy. El
  ciclo de promoción automática queda igual: LightGBM entra como candidato y se promueve solo cuando gane.
- **En el aviso «probable» los modelos sí bajan un poco las falsas alarmas** a igual detección (0,52–0,53 contra
  0,55; para LightGBM chico el intervalo no incluye el cero). En «posible» ninguno le gana a los votos.
- Los votos siguen siendo la variable principal en los dos modelos.

## Resumen de la prueba de concepto (al 09/11)

| Pregunta | Respuesta |
|---|---|
| ¿Un modelo aprendido da mejor probabilidad que la tabla de la app? | Sí, por poco: Brier 0,071 contra 0,077 (logística con rayos) |
| ¿Avisa mejor? | En «posible» no; en «probable» apenas |
| ¿Los rayos suman? | Sí, en la última hora y en pocos casos |
| ¿LightGBM le gana a la logística? | No, con estos datos |
| ¿Qué limita todo? | 22 días, ~200 lluvias, 10 días con lluvia en la prueba |

## Paso 6 — Dejar una región afuera (09/11/2026, hecho)

- **Script:** `paso6_region_afuera.py`; salida en `salidas/paso6_salida.txt`. Logística con rayos, misma prueba día por
  día. Para cada región se compara, sobre sus casos: la tabla de la app, el modelo entrenado con todas las regiones
  («vista») y el mismo modelo entrenado sin esa región («no vista»), siempre con días anteriores.
- Regiones por cercanía de la estación: AMBA (SADJ, SADL, SADM, SADP), Litoral (SAAR, SAAV), Mendoza (SAMM, SAMR).
- **Hallazgo: Córdoba se queda sin datos con el radio de 10 km.** Su estación (SACO) tiene 170 casos del monitor,
  todos de tramos a más de 10 km (el más cercano, a 11,5 km de media). Lo de «se conservan las 12 estaciones» de la
  devolución contaba 5 casos de pedidos de usuarios. Con lo decidido, Córdoba no entra a entrenar ni a evaluar.
- Se la usó entonces como **región nunca vista de verdad**: modelo entrenado con las otras tres, evaluado en
  Córdoba con la etiqueta de 10 a 30 km (más débil). `cargar(cerca=False)` en `paso2_referencia.py`.

| Región | Casos | Con lluvia | Brier tabla app | Brier vista | Brier no vista | No vista − vista (IC 90 %) | No vista − tabla app (IC 90 %) |
|---|---|---|---|---|---|---|---|
| AMBA | 416 | 56 | 0,073 | 0,069 | 0,069 | +0,0001 (−0,0046 a +0,0054) | −0,0045 (−0,0176 a +0,0085) |
| Litoral | 222 | 32 | 0,094 | 0,082 | 0,082 | −0,0001 (−0,0031 a +0,0032) | −0,0123 (−0,0220 a −0,0028) |
| **Mendoza** | 212 | 14 | 0,065 | 0,063 | **0,078** | **+0,0153 (+0,0066 a +0,0243)** | **+0,0130 (+0,0004 a +0,0263)** |
| Las tres juntas | 850 | 102 | 0,077 | 0,071 | 0,075 | +0,0038 (+0,0005 a +0,0073) | −0,0022 (−0,0084 a +0,0044) |
| Córdoba (nunca vista, 10–30 km) | 111 | 14 | 0,076 | — | 0,062 | — | −0,0142 (−0,0251 a −0,0043) |

### Lectura

- **En la llanura el modelo se traslada sin pérdida:** en AMBA y el Litoral da lo mismo haber visto la región o
  no, y en Córdoba, que nunca vio, le gana a la tabla de la app.
- **En Mendoza no:** sin haberla visto es peor que el modelo que sí la vio y peor que la tabla de la app, y los dos
  intervalos excluyen el cero. Es la región más distinta (cordillera, clima seco) y la de menos lluvias (14).
- **Para la zona no vista la respuesta depende de a qué se parece.** La regla decidida («responde el modelo solo
  si la prueba lo respalda») da: sí en llanura pampeana, no en zonas distintas. Opción que aparece acá y no estaba:
  en zona no vista responder con **la tabla de votos** (no aprende, así que no depende de la región) en vez de
  «sin dato». **Decidido por Juan el 09/11: en zona no vista responde la tabla de votos** (decisión 23).
- **Pendiente de decisión de Juan: Córdoba y el radio.** O se acepta que Córdoba no entrena (queda como «no
  vista»), o se usa un radio mayor solo ahí (p. ej. 15 km), o se agrega al monitor una ruta que pase cerca de SACO.
- Límite: son 3 regiones, 22 días y pocas lluvias por región. Alcanza para decidir el comportamiento inicial, no
  para afirmar que el modelo sirve en todo el país.

## Paso 7 — Curva de umbrales (11/11/2026, hecho)

- **Script:** `paso7_umbral.py`; salida en `salidas/paso7_salida.txt`. Logística con rayos, misma prueba día por día
  (14 días, 850 casos, 102 con lluvia). Responde a la pregunta del docente «¿quién fija el umbral?».

| Aviso si | POD | FAR | Falsas alarmas por acierto | Franjas con aviso |
|---|---|---|---|---|
| App: 1 voto o más | 0,92 | 0,68 | 2,2 | 35,0 % |
| App: 2 votos o más | 0,65 | 0,55 | 1,2 | 17,5 % |
| Modelo: P ≥ 0,05 | 0,98 | 0,82 | 4,5 | 64,3 % |
| Modelo: P ≥ 0,08 | 0,92 | 0,73 | 2,7 | 40,7 % |
| Modelo: P ≥ 0,10 | 0,88 | 0,69 | 2,2 | 34,3 % |
| Modelo: P ≥ 0,15 | 0,78 | 0,63 | 1,7 | 25,5 % |
| Modelo: P ≥ 0,20 | 0,70 | 0,59 | 1,4 | 20,4 % |
| Modelo: P ≥ 0,25 | 0,65 | 0,53 | 1,1 | 16,6 % |
| Modelo: P ≥ 0,30 | 0,62 | 0,48 | 0,9 | 14,2 % |
| Modelo: P ≥ 0,40 | 0,55 | 0,38 | 0,6 | 10,7 % |
| Modelo: P ≥ 0,50 | 0,47 | 0,32 | 0,5 | 8,3 % |

Umbral recalculado cada día para un POD objetivo, con los días de entrenamiento: POD 80 % → entre 0,14 y 0,24
(mediana 0,16); POD 90 % → entre 0,08 y 0,13 (mediana 0,08).

### Lectura

- **No hay un umbral que baje las falsas alarmas sin perder lluvias:** es una curva. Pasar de 2,2 a 1,1 falsas
  alarmas por acierto cuesta avisar 65 % de las lluvias en vez de 88–92 %.
- Los dos puntos de la app caen sobre la curva del modelo: «1 voto» ≈ P ≥ 0,10 (algo mejor la app en POD) y
  «2 votos» ≈ P ≥ 0,25.
- **Si el umbral lo recalcula el modelo cada día, salta** (0,08 a 0,13 para el mismo objetivo): el aviso cambiaría de
  un día para otro sin que cambie el tiempo.
- Elegir el punto de la curva no sale de los datos: depende de cuánto molesta una falsa alarma contra una lluvia
  no avisada, y eso es distinto en moto y en auto.
- **Decidido por Juan el 11/11 (decisión 25): el umbral lo elige quien usa la app**, entre sensibilidades
  definidas sobre esta curva. El servicio devuelve solo la probabilidad.
- **Sensibilidades (decisión 26):** «Avisame todo» P ≥ 0,10 · «Equilibrado» P ≥ 0,20, por defecto en moto y auto ·
  «Solo si es probable» P ≥ 0,40.

## Paso 8 — Un modelo numérico oculto (13/11/2026, hecho; H10)

- **Script:** `paso8_modelo_oculto.py` (usa los módulos de `infra-cloud-template/lluvia/` y los datasets del bucket);
  salida en `paso8_resultado.json`. Misma prueba día por día y misma ventana que `train.py` (30/10–12/11: 14 días, 856
  casos, 104 con lluvia).
- **Cómo se oculta un modelo:** su lluvia y su corrida quedan vacías (la API las pone en 0) y su voto se resta del
  conteo. Un modelo vota si su media es ≥ 0,2 mm/3 h, el umbral de Clima Rutero; reconstruidos así, los votos coinciden
  con los de la app en el 96,5 % de las filas.
- Se comparan la logística con rayos entrenada normal, la misma entrenada con una copia de los datos con un modelo
  oculto al azar («enmascarada», como decía la decisión 16) y la tabla con el conteo de votos sin el modelo oculto.

| Falta | Logística normal | Logística enmascarada | Tabla (2 votos) | Enmascarada − tabla (IC 90 %) |
|---|---|---|---|---|
| — (los 3) | 0,0679 | — | 0,0728 | — |
| WRF | 0,0690 | 0,0679 | 0,0750 | **−0,0071** (−0,0125 a −0,0023) |
| GFS | 0,0785 | 0,0763 | 0,0804 | −0,0041 (−0,0098 a +0,0003) |
| IFS | 0,0839 | 0,0765 | 0,0779 | −0,0014 (−0,0053 a +0,0024) |

### Lectura

- **WRF casi no aporta:** sin él, el Brier no cambia (+0,0011 la normal, IC −0,0018 a +0,0042) y el modelo le sigue
  ganando a la tabla con evidencia.
- **Sin GFS o sin IFS empeora ~0,0085** (con evidencia) y queda empatado con la tabla.
- **La logística normal sin IFS es peor que la tabla** (+0,0060): si se usa el modelo con cualquier 2 de 3, hay que
  entrenarlo enmascarado (sin IFS mejora 0,0074, con evidencia).
- **En los datos solo faltó WRF:** 141 filas (0,2 %), todas del 19/10. GFS e IFS no faltaron nunca.
- Decidido (Juan, 13/11; decisión 38): si falta WRF responde el modelo; si falta GFS o IFS, la tabla (degradado).

## Pasos siguientes

- Decidido el 09/11: en zona no vista responde la tabla de votos (decisión 23) y Córdoba queda como zona no vista
  (decisión 24).
- Pasar lo que quedó firme a `train.py` del servicio: logística con rayos como modelo, tabla de la app como
  referencia fija, LightGBM como candidato.

4. LightGBM.
5. Ablación de rayos y prueba dejando una región afuera.
