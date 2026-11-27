# `/` y `/healthz` como `async def` — medición en k3d (13/11/2026)

Arreglo de fondo de la decisión 37. En la sesión de GKE 1, con 1 réplica saturada (4.810 tramos, 10 usuarios), `/` tardó
más de 1 s y la liveness reinició el pod dos veces (36 % de errores). Causa: los endpoints livianos eran `def`, así que
FastAPI los mandaba al mismo pool de hilos que los `/predict` y hacían cola detrás de ellos.

Cambio: `/`, `/healthz`, `/version` y `/metrics` pasan a `async def` (corren en el bucle de eventos); `/predict` sigue
siendo `def` (CPU, en el pool). Test: `test_endpoints_livianos_no_esperan_al_pool`.

Medición con `sondas-bajo-carga.sh`: k6 satura 1 réplica (límite 1 CPU) durante 60 s y, desde adentro del pod, se piden
`/` y `/healthz` 80 veces cada 0,4 s. Mismo clúster k3d, misma carga, imagen antes y después.

| | `/` p50 / p95 / máx | `/healthz` p50 / p95 / máx | k6: pedidos/s, p95 | Reinicios |
|---|---|---|---|---|
| Antes (`def`) | 213 / 676 / 986 ms | 180 / 701 / 881 ms | 3,80 · 3,25 s | 0 |
| Después (`async def`) | **103 / 296 / 369 ms** | **104 / 287 / 368 ms** | 3,74 · 3,34 s | 0 |

- Los probes contestan **~2,5 veces más rápido** bajo saturación (p95 de ~700 a ~290 ms) y el throughput de `/predict`
  no cambia.
- No baja a cero: `/predict` usa la CPU en el mismo proceso y el intérprete se reparte entre hilos (GIL), así que el bucle
  de eventos igual espera su turno. Por eso se mantienen los timeouts con margen de la decisión 37 (3 s y 5 × 6).
- En k3d el «antes» no llegó a 1 s (la mini es 3–4 veces más rápida por pedido que una vCPU de e2): en GKE el máximo de
  ~1 s pasaba a ~3–4 s. Con el cambio, el equivalente en GKE quedaría en ~1–1,5 s, dentro del timeout de 5 s.
