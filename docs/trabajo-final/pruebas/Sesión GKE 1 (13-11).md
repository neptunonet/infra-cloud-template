# Sesión de GKE 1 — 13/11/2026

Primera sesión del TF en GKE. Todo por `deploy.yml` (desplegar y apagar) con aprobación en el Environment `dev`.
Clúster zonal `infra-cloud-dev-gke` (us-central1-a, GKE 1.36.4), pool **e2-standard-2** que escaló de 1 a **2 nodos**
(máximo). Imagen `lluvia:22598cc…` (= `a97e85b`, con el cierre de conexiones). Prendido de ~13:10 a ~15:47 UTC
(~2 h 40 min). El segundo nodo se sumó a las ~14:06 UTC, al pasar la grilla a 3 réplicas. Capturas 29–48.

## Despliegue

| Paso | Resultado |
|---|---|
| `deploy.yml` accion=desplegar (run 43431069079) | Clúster 8 min 41 s, pool 1 min 44 s. **Falló el vínculo de Workload Identity**: «Identity Pool does not exist». El output `workload_pool` del módulo se armaba con variables y el vínculo se creó en paralelo con el clúster. Re-run de los jobs fallidos: terraform 17 s (1 recurso), helm 3 min 51 s. Arreglo en el repo: el output sale del clúster (dependencia implícita) |
| Workload Identity | El pod se identifica como `lluvia-servicio` (metadata server) y no hay ningún Secret con clave. Sirve `v20261113_073003` (la del VPS de hoy) desde el bucket |
| Job de carga de versiones | 4 versiones nuevas en 8 s |
| kube-prom 91.9.0 + `observability/lluvia` | 4 min 13 s. Target lluvia `up`, 6 reglas cargadas (la recarga de Prometheus tarda ~1 min después del `apply -k`) |
| `kubectl` en la mini | El gcloud del snap no trae `gke-gcloud-auth-plugin`: reemplazo de 10 líneas en `~/.local/bin/gke-gcloud-auth-plugin` (token de `gcloud config config-helper`) |

## Grilla de carga (`loadtest/lluvia-grilla.sh`, 2 pasadas, 48 corridas de 60 s)

CSV: `grilla-gke-2026-11-13.csv`. HPA apagado, réplicas fijas. P1 = pasada 1, P2 = pasada 2. Postgres registró
30.696 de 30.730 pedidos (99,9 %; los 34 que faltan son los rechazados durante los reinicios).

### Lote de 156 tramos

| Réplicas | Simultáneos | pedidos/s (P1 / P2) | p50 ms (P1 / P2) | p95 ms (P1 / P2) | errores % (P1 / P2) |
|---|---|---|---|---|---|
| 1 | 1 | 13,54 / 7,98 | 63 / 106 | 131 / 245 | 0 / 0 |
| 1 | 2 | 13,35 / 8,13 | 134 / 209 | 259 / 506 | 0 / 0 |
| 1 | 5 | 12,25 / 9,82 | 376 / 474 | 660 / 888 | 0 / 0 |
| 1 | 10 | 11,67 / 11,40 | 825 / 862 | 1329 / 1304 | 0 / 0 |
| 3 | 1 | 15,60 / 16,07 | 55 / 56 | 108 / 92 | 0 / 0 |
| 3 | 2 | 22,01 / 22,74 | 77 / 81 | 176 / 153 | 0 / 0 |
| 3 | 5 | 29,11 / 28,50 | 155 / 143 | 349 / 399 | 0 / 0 |
| 3 | 10 | 30,22 / 29,95 | 324 / 252 | 628 / 749 | 0 / 0 |
| 5 | 1 | 13,48 / 16,37 | 61 / 54 | 136 / 93 | 0 / 0 |
| 5 | 2 | 18,62 / 21,96 | 73 / 77 | 273 / 184 | 0 / 0 |
| 5 | 5 | 29,29 / 18,21 | 147 / 158 | 387 / 815 | 0 / 0 |
| 5 | 10 | 31,23 / 28,54 | 226 / 325 | 805 / 720 | 0 / 0 |

### Lote de 4.810 tramos

| Réplicas | Simultáneos | pedidos/s (P1 / P2) | p50 ms (P1 / P2) | p95 ms (P1 / P2) | errores % (P1 / P2) |
|---|---|---|---|---|---|
| 1 | 1 | 1,19 / 1,17 | 732 / 802 | 1068 / 1103 | 0 / 0 |
| 1 | 2 | 1,24 / 1,22 | 1491 / 1528 | 1935 / 1963 | 0 / 0 |
| 1 | 5 | 1,19 / 1,16 | 3887 / 4099 | 4822 / 5013 | 0 / 0 |
| 1 | 10 | 1,31 / 1,13 | 6373 / 8078 | 10252 / 10480 | 36,17 / 0 |
| 3 | 1 | 1,01 / 1,31 | 854 / 666 | 1362 / 1137 | 0 / 0 |
| 3 | 2 | 1,95 / 1,25 | 973 / 1414 | 1378 / 2274 | 0 / 0 |
| 3 | 5 | 2,60 / 2,09 | 1156 / 2156 | 3689 / 3608 | 0 / 0 |
| 3 | 10 | 2,35 / 2,40 | 3679 / 3583 | 6516 / 6290 | 0 / 0 |
| 5 | 1 | 1,51 / 1,49 | 596 / 613 | 830 / 832 | 0 / 0 |
| 5 | 2 | 1,45 / 2,58 | 1205 / 669 | 1785 / 1048 | 0 / 0 |
| 5 | 5 | 2,62 / 2,70 | 1217 / 1267 | 3789 / 4491 | 0 / 0 |
| 5 | 10 | 2,43 / 2,75 | 3017 / 3065 | 9495 / 6209 | 0 / 0 |

La columna `cpu_api_m` del CSV no es confiable con lotes grandes (`kubectl top` toma una ventana de ~15 s cerca del
final y con pedidos de varios segundos cae entre pedidos): no se usa.

### Lectura

1. **Una réplica no gana con más simultáneos:** ~12–13 pedidos/s con 156 tramos y ~1,2 con 4.810, haya 1 o 10 usuarios;
   solo crece la latencia (cola). Igual que en k3d.
2. **3 réplicas: ~2,5× el throughput** con 156 tramos y 10 usuarios (30 contra 12 pedidos/s; p50 de 825 a ~290 ms).
3. **5 réplicas ≈ 3 réplicas** (~30 pedidos/s; ~2,6 con lotes grandes). El techo es la CPU de los nodos: 2 × e2-standard-2
   = 4 vCPU compartidas con kube-prom, Postgres y el propio k6 (~550m). Más réplicas sirven solo si hay CPU donde ponerlas.
4. **GKE es ~3–4 veces más lento por pedido que la mini** (156 tramos: p50 63 ms contra 17 ms en k3d; entrenamiento:
   evaluación 64,8 s contra 31,1 s en el VPS ARM y 28,8 s en k3d). Una vCPU de e2 es medio núcleo físico compartido.
5. **Variación entre pasadas:** 1 réplica, 156 tramos y 1 usuario dio 13,5 y 8,0 pedidos/s. El pod que queda al bajar a
   1 réplica puede caer en el nodo cargado (kube-prom + Postgres). Por eso se repitió todo.

### Incidente: reinicios por la liveness (pasada 1, 1 réplica, 4.810 tramos, 10 usuarios)

La réplica saturada tardó más de 1 s en contestar `/` (timeout por defecto), el kubelet la reinició **dos veces** en plena
carga y fallaron el 36 % de los pedidos (`connection refused`). Saltó la alerta real `LluviaLatenciaAlta` en Telegram
(capturas 36, 39 y 42). Arreglo en el chart, aplicado desde las 3 réplicas: readiness con timeout de 3 s y liveness con
5 s y 6 fallas (~1 min). Pasada 2, misma combinación: **0 % de errores y 0 reinicios** (p95 10,5 s: sigue saturada, pero
no se pierde nada). Arreglo de fondo hecho el mismo día: `/` y `/healthz` como `async def` (p95 de los probes bajo saturación de ~700 a
~290 ms en k3d; `Probes async en k3d (13-11).md`).

## HPA con lotes grandes (4.810 tramos, 5 usuarios, 4 min)

Archivo: `hpa-lotes-grandes-gke-2026-11-13.txt` (capturas 43 y 44). Responde la pregunta del docente.

| Momento | CPU / objetivo | Réplicas |
|---|---|---|
| 0–56 s | 1 % (metrics-server todavía no vio la carga) | 1 |
| 75 s | 359 % | el HPA pide 4 y 5 s después 5 |
| 94 s | 359 % | **5 listas** |
| 150–240 s | 167–230 % | 5 (en el máximo) |
| fin + ~5 min | 1 % | 5 → 4 → 1 (ventana de estabilización) |

k6: 572 pedidos, 2,31 pedidos/s (11.109 tramos/s), p50 1,86 s, p95 4,65 s, 0 errores. Con 5 réplicas la CPU sigue al
~220 % del request: el límite es `maxReplicas` y los nodos, no el HPA. El escalado tarda ~95 s, casi todo en detectar la
carga; los pods arrancan en ~20 s (imagen ya en el nodo).

## Entrenamiento a mano (CronJob suspendido → Job)

`kubectl create job --from=cronjob/lluvia-entrenamiento entrenamiento-gke-manual` con
`entrenamiento.destino=gs://unlu-ia-armas-lluvia/modelos/pruebas-gke` (no pisa `activa.json` del VPS). 79 s en total:
`v20261113_153021`, logística con rayos promovida (Brier 0,0679 contra 0,0728 de la tabla y 0,0699 de LightGBM; ventana
30/10–12/11, 856 casos), cargada en Postgres. Captura 45. Juan borró `modelos/pruebas-gke/` al terminar.

## Postgres al final (captura 46)

31.268 pedidos (1.573 con detalle = 5,0 %), 1.045.876 predicciones, 5 versiones, 15 evaluaciones; **143 MB** en el disco
de 1 GiB (decisión 33).

## Apagado

`deploy.yml` accion=apagar (run 43454508564, 9 min 55 s): `vaciar` 1 min 5 s (uninstall de kube-prom, lluvia y postgres,
PVC borrado, disco eliminado), `terraform` 8 min 9 s. Verificado: 0 clústeres, 0 discos, 0 VMs. Capturas 47 y 48.

## Alertas reales

`LluviaLatenciaAlta` disparó dos veces (11:00 y 11:24, hora local) y se resolvió sola (11:05 y 11:29). El mensaje de
«resuelta» repite el valor de la última evaluación activa (4,875 s), no el del momento de resolverse: es así en
Alertmanager.
