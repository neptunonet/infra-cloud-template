# Sesión de GKE 2 — 16/11/2026 (H12: latencia desde el VPS)

Sesión corta para medir H12 y probar los arreglos de la sesión 1. Imagen `lluvia:db4ad07…` (con H10 y los probes
`async`), receta activa **LightGBM** (`v20261116_073003`). Clúster prendido ~13:20–14:05 UTC.

## Despliegue

- `deploy.yml` desplegar (run 43874698472): **terraform 11 min 3 s de una sola vez** (el arreglo del vínculo de Workload
  Identity del PR #17 funcionó) y helm 1 min 26 s. Capturas 53 y 54.
- Cloud Monitoring del clúster: solo `SYSTEM_COMPONENTS`, sin Managed Prometheus (PR #21): no debería repetirse el gasto
  de US$ 0,06 del 13/11 (a confirmar en la facturación).
- Exposición al VPS (PR #21): Secret `lluvia-claves` con una clave temporal (`vps:<clave>`, archivo 600 en la mini y en
  el VPS, borrada al terminar con `shred`) y `helm upgrade … externo.habilitado=true`, `ipsPermitidas={<IP del VPS>/32}`.
  Desde la mini el balanceador no responde (solo deja pasar al VPS); sin clave, `/predict` da **401**.

## H12 (`loadtest/latencia-vps.sh`, corrido en el VPS)

Salida completa: `h12-latencia-vps-2026-11-16.txt` (el primer intento, `…-intento1.txt`, tuvo la parte de k6 fallida por
permisos de la carpeta y una conexión de 19 s a `/healthz` apenas creado el balanceador; en la repetición no pasó).

| Desde el VPS (n = 30 con curl; 60 s con k6) | p50 | p95 |
|---|---|---|
| Conexión TCP (≈ ida y vuelta de red) | 26 ms | 27 ms |
| `/healthz` (conexión + pedido) | 53 ms | 55 ms |
| `/predict`, 3 tramos | 81 ms | 106 ms |
| k6, 156 tramos, 1 usuario — 10,2 pedidos/s, 0 errores | **78 ms** | **238 ms** |
| k6, 156 tramos, 5 usuarios — 19,0 pedidos/s, 0 errores | 253 ms | 491 ms |

Con 5 usuarios el HPA escaló de 1 a 5 réplicas durante la prueba.

**Lectura (H12: «responde en menos de 500 ms visto desde el VPS, y casi todo es red»):**
- ✅ **Menos de 500 ms:** p95 de 238 ms con un usuario (el uso real: ~120 pedidos por día) y 491 ms con cinco.
- ❌ **«Casi todo es red»:** la red pone ~26 ms por ida y vuelta (el VPS está mucho más cerca de us-central1 que la
  notebook del Lab 7, ~200 ms). Un pedido de 156 tramos tarda ~78 ms y dentro del clúster ya tardaba ~63 ms: **la mayor
  parte es cómputo** en la vCPU de e2, no red.
- Consecuencia para Clima Rutero: un timeout de ~1 s en el consumidor alcanza con margen; el respaldo en la tabla local
  se usaría solo si el servicio está caído, no por latencia.

## Apagado

`deploy.yml` apagar (run 43880310691): `vaciar` y `terraform` en verde. Verificado: 0 clústeres, 0 discos, 0 VMs,
0 reglas de reenvío (el balanceador se borró con el uninstall), 0 direcciones. Contexto de `kubectl` de vuelta en k3d.
