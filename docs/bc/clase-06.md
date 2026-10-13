# Clase 6 · Blockchain: métricas de Anvil

Complementa la [guía de la clase 6](../clase-06.md). Hacé primero sus pasos 1
a 4 (Prometheus, Grafana, ServiceMonitors y dashboards); esto es lo propio de
tu área. Los comandos se corren desde la raíz del repo.

Anvil habla JSON-RPC, no Prometheus. `observability/anvil-exporter/` es un
traductor de 40 líneas que publica `anvil_block_number`.

Si instalaste en un namespace (en el lab: `bc-clase5`), agregá
`-n <tu-namespace>` a cada `helm` y `kubectl` de esta guía (los ejemplos ya lo
traen; sin namespace, usá `-n default`).

```bash
make k3d-images      # incluye anvil-exporter:local
helm upgrade --install anvil helm/charts/anvil -n <tu-namespace> \
  -f helm/charts/anvil/values-k3s.yaml --set exporter.enabled=true --wait
kubectl get pod anvil-0 -n <tu-namespace>        # 2/2: anvil + exporter
kubectl exec -n <tu-namespace> anvil-0 -c anvil -- cast rpc evm_mine
```

En Prometheus, `anvil_block_number` sube con cada `evm_mine` (o con cada
transacción). Con dos contenedores en el pod, `kubectl exec` y `kubectl logs`
necesitan `-c anvil`. Sin tráfico Anvil no mina (automine) y el chart no expone
`--block-time`, así que una alerta de "bloque sin avanzar" se dispara sola: miná
con `kubectl exec -n <tu-namespace> anvil-0 -c anvil -- cast rpc evm_mine` o justificá la ventana.
Para esa alerta usá `changes(anvil_block_number[5m]) == 0`: `anvil_block_number`
es un gauge, y `rate()`/`increase()` van sobre counters.

En Grafana, el dashboard `Anvil dev chain` muestra la altura de bloque. El
de la línea base PoW (`Mini PoW baseline`) trae solo la altura de bloque por
nodo: los paneles de tu red los agregás en el TF.

## Limpieza

```bash
helm upgrade --install anvil helm/charts/anvil -n <tu-namespace> \
  -f helm/charts/anvil/values-k3s.yaml --wait   # sin el exporter
```

o `helm uninstall anvil -n <tu-namespace>` si ya no lo usás (el PVC queda; ver la clase 5).

## Errores frecuentes

| Si ves | Causa | Hacé |
|---|---|---|
| `anvil-0` en `ErrImageNeverPull` | La imagen del exporter no está en el cluster | `make k3d-images` |
| `kubectl exec anvil-0 -- cast ...` dice `container not found` o entra al exporter | El pod tiene dos contenedores | `kubectl exec -n <tu-namespace> anvil-0 -c anvil -- cast ...` |
| La alerta de bloque sin avanzar se dispara sola | Anvil no mina sin transacciones | Miná con `cast rpc evm_mine` o ampliá la ventana |
| El target del exporter no aparece en `/targets` | Instalaste Anvil sin `--set exporter.enabled=true` | Repetí el `helm upgrade` de arriba |
