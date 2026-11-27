# Ensayo de la prueba de carga en k3d (12/11/2026)

**Para qué:** probar la herramienta (`loadtest/lluvia.js` + `loadtest/lluvia-grilla.sh`) y encontrar problemas antes de
pagar GKE. **Los números no van al informe como resultado**: los 3 nodos de k3d comparten los 20 núcleos y los 14 GB de
«la mini» (`noteubuntu001`) con k6 y Postgres. Sirven para comparar con GKE y para anticipar qué mirar.

- Clúster: k3d `tf-lluvia` (k3s 1.35.5, 1 server + 2 agentes). API `lluvia:local` (commit `9fb5522`), modelo
  `v20261112_073004` (logística con rayos). Pod: requests 100m / 256Mi, **limits 1 CPU / 512Mi**.
- Carga: k6 2.3.0 como Job dentro del clúster, contra el Service. Modelo cerrado (cada usuario virtual manda el pedido
  siguiente al recibir la respuesta, sin pausa), 60 s por corrida, 5 pedidos de calentamiento.
- Lotes sintéticos con semilla fija: 55 % de tramos en zona verificada, 28 % en región entrenada, 8 % no vista, el resto
  con anticipación > 6 h o un modelo faltante (83 % los responde el modelo, 17 % la tabla).
- Datos crudos: `ensayo-k3d-2026-11-12.csv` (24 corridas, de 16:25 a 17:05 UTC).

## Resultados

| Réplicas | Tramos | Simult. | Pedidos/s | Tramos/s | p50 ms | p95 ms | API ms | CPU m | Mem MiB |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 156 | 1 | 55,3 | 8.630 | 17 | 21 | 11 | 968 | 313 |
| 1 | 156 | 2 | 45,5 | 7.091 | 42 | 63 | 24 | 1.001 | 312 |
| 1 | 156 | 5 | 36,6 | 5.702 | 127 | 229 | 70 | 1.000 | 330 |
| 1 | 156 | 10 | 31,1 | 4.844 | 308 | 505 | 157 | 1.000 | 360 |
| 1 | 4.810 | 1 | 4,6 | 22.006 | 212 | 260 | 119 | 979 | 377 |
| 1 | 4.810 | 2 | 4,1 | 19.526 | 482 | 625 | 318 | 995 | 381 |
| 1 | 4.810 | 5 | 3,3 | 15.715 | 1.519 | 2.048 | 1.079 | 1.001 | 428 |
| 1 | 4.810 | 10 | 3,0 | 14.506 | 3.256 | 4.220 | 2.062 | 1.000 | 383 |
| 3 | 156 | 1 | 56,3 | 8.783 | 17 | 21 | 11 | 972 | 718 |
| 3 | 156 | 2 | 110,7 | 17.268 | 17 | 22 | 11 | 1.943 | 650 |
| 3 | 156 | 5 | 150,9 | 23.543 | 18 | 93 | 20 | 2.958 | 662 |
| 3 | 156 | 10 | 134,5 | 20.974 | 56 | 211 | 41 | 2.980 | 670 |
| 3 | 4.810 | 1 | 4,7 | 22.633 | 207 | 252 | 117 | 982 | 690 |
| 3 | 4.810 | 2 | 9,1 | 43.559 | 212 | 264 | 121 | 1.966 | 690 |
| 3 | 4.810 | 5 | 7,9 | 38.208 | 242 | 1.415 | 421 | 1.986 | 737 |
| 3 | 4.810 | 10 | 10,8 | 51.993 | 787 | 1.766 | 631 | 3.000 | 801 |
| 5 | 156 | 1 | 56,7 | 8.850 | 17 | 20 | 11 | 981 | 1.062 |
| 5 | 156 | 2 | 110,9 | 17.296 | 17 | 21 | 11 | 1.966 | 1.051 |
| 5 | 156 | 5 | 146,9 | 22.916 | 35 | 60 | 20 | 2.987 | 1.042 |
| 5 | 156 | 10 | 258,3 | 40.289 | 17 | 106 | 23 | 4.970 | 1.057 |
| 5 | 4.810 | 1 | 4,7 | 22.524 | 209 | 257 | 117 | 986 | 1.064 |
| 5 | 4.810 | 2 | 9,1 | 43.656 | 212 | 264 | 120 | 1.975 | 1.089 |
| 5 | 4.810 | 5 | 16,8 | 80.752 | 233 | 571 | 176 | 3.966 | 1.119 |
| 5 | 4.810 | 10 | 18,9 | 90.712 | 513 | 905 | 351 | 4.990 | 1.146 |

«API ms» es el promedio que mide la propia API (de Postgres); «p50» lo mide k6 desde afuera. CPU y memoria: suma de los
pods de la API, a los ~50 s de cada corrida. **0 errores, 0 reinicios y el 100 % de los pedidos registrados en
Postgres** (79.180 pedidos en total).

## Lo que muestra

1. **El servicio está limitado por CPU.** Cada pod ocupado está en su límite de 1 CPU (968–1.001 m). Con tantos pedidos
   simultáneos como réplicas o menos, la latencia queda en el piso: **17 ms para 156 tramos y ~210 ms para 4.810**, y el
   throughput crece casi lineal con las réplicas (156 tramos con 2 simultáneos: 45 pedidos/s con 1 réplica, 111 con 3).
2. **Con 1 réplica, más concurrencia da *menos* throughput** (55 → 31 pedidos/s con 156 tramos; 4,6 → 3,0 con 4.810).
   FastAPI atiende cada pedido en un hilo; con 1 CPU de límite los hilos compiten (GIL de Python y *throttling* del
   límite) y se pierde tiempo en esa competencia. Además la mitad de la latencia es espera antes de que la API empiece
   (con 10 simultáneos: 157 ms adentro contra 308 ms afuera). Más pedidos simultáneos por pod no ayudan: hacen falta
   más réplicas.
3. **El lote grande abarata cada tramo:** 4.810 tramos son 31 veces 156, pero tardan 12 veces más (212 contra 17 ms).
   Por tramo: ~0,044 ms en lote grande contra ~0,11 ms en el lote de 156.
4. **El reparto entre réplicas no es parejo.** Hay corridas que rinden menos de lo esperado (3 réplicas y 5
   simultáneos: 151 pedidos/s, pero con 10 bajan a 134; 3 réplicas, 4.810 tramos y 5 simultáneos: 7,9, menos que con
   2). k6 mantiene la conexión abierta (*keep-alive*) y kube-proxy asigna cada conexión a un pod al azar: con 5
   conexiones y 3 pods, algún pod se lleva 3 y otro 1. Un cliente real con conexiones persistentes (el VPS de Clima
   Rutero) tendría el mismo efecto. **Hay que explicarlo en el informe** y, en GKE, mirar el reparto por pod.
   Confirmado con la columna `pod` de Postgres en las dos últimas corridas (5 réplicas, 4.810 tramos, 5 y 10
   simultáneos): un pod atendió 1.048 pedidos y otro 235, **4,5 veces menos**.
5. **Memoria:** ~210 MiB por pod en reposo; con 1 réplica y lotes de 4.810 llegó a **428 MiB contra un límite de
   512 MiB**. Con más pedidos grandes simultáneos por pod, el OOM está cerca.
6. **El registro aguantó la carga** (ni errores ni descartes), pero **la base creció a 4,6 GB** con 40 millones de filas
   en `predicciones` (~115 bytes por tramo). En k3d no se notó porque `local-path` no respeta el tamaño del PVC; en GKE
   el disco de 1 GiB se llenaría en el primer cuarto de la grilla.

## A resolver antes de GKE

- ✅ **Tamaño de `predicciones`** (punto 6). Decidido por Juan: **resumen siempre y detalle por muestra**
  (`MUESTRA_TRAMOS=20`, esquema `002_resumen_y_muestra.sql`). Verificado con una grilla corta (3 réplicas, 5
  simultáneos, 30 s por lote): 3.410 pedidos, 172 con detalle (5,0 %), 138.528 filas en `predicciones` (16 MB) en lugar
  de 2,74 millones (~315 MB). La grilla completa quedaría en ~300 MB: entra en 1 GiB, pero con un margen de ~3 veces;
  si GKE rinde más que k3d, crear el PVC de Postgres con `persistencia.tamano=2Gi` (cuesta centavos en el día).
- ✅ **Límite de memoria** (punto 5): 768 MiB en `values.yaml` y `values-k3s.yaml`.
- La misma combinación (3 réplicas, 5 simultáneos, 156 tramos) dio 151 pedidos/s en la grilla y 97 en la corrida
  corta: otra muestra del reparto al azar de las conexiones (punto 4). En GKE conviene repetir cada combinación.
- **Reparto entre réplicas** (punto 4): en GKE, guardar los pedidos por pod (de Postgres, columna `pod`).
