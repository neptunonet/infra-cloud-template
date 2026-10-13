# Clase 6 · IA: el modelo bajo carga

Complementa la [guía de la clase 6](../clase-06.md). Hacé primero sus pasos 1
a 4 (Prometheus, Grafana, ServiceMonitors y dashboards); esto es lo propio de
tu área. Los comandos se corren desde la raíz del repo.

Si instalaste en un namespace (en el lab: `$MI_NAMESPACE`), agregá
`-n <tu-namespace>` a cada `helm` y `kubectl` de esta guía (los ejemplos ya lo
traen; sin namespace, usá `-n default`).

```bash
helm upgrade --install model helm/charts/model -n <tu-namespace> \
  -f helm/charts/model/values-k3s.yaml --wait
kubectl create configmap k6-script -n <tu-namespace> --from-file=loadtest/k6-script.js \
  --dry-run=client -o yaml | kubectl apply -n <tu-namespace> -f -
kubectl delete job k6 -n <tu-namespace> --ignore-not-found
kubectl apply -n <tu-namespace> -f loadtest/k6-job.yaml   # TARGET=model, SLEEP=0.05
kubectl get hpa model -n <tu-namespace> -w               # Ctrl+C para salir
```

El dashboard `Model server` muestra predicciones/s, latencia p95 y las réplicas
del HPA. La carga se genera **adentro del cluster**: un port-forward manda todo
a un solo pod y las réplicas nuevas no reciben tráfico.

Las métricas del modelo son `model_predictions_total` y el histograma
`model_predict_seconds`. Si querés una métrica propia (por ejemplo la
confianza), agregala en `model/serve.py` con `prometheus_client`.
Después reconstruí la imagen y reiniciá el Deployment, porque Prometheus
scrapea el pod que corre, no tu archivo:

```bash
make build-model && k3d image import model:local -c infra-cloud
kubectl rollout restart -n <tu-namespace> deploy/model
```

En GKE: subí un tag nuevo a Artifact Registry y
`helm upgrade model helm/charts/model -n <tu-namespace> --reuse-values --set image.tag=<tag>`.

## Limpieza

```bash
kubectl delete job k6 -n <tu-namespace> --ignore-not-found
kubectl delete configmap k6-script -n <tu-namespace> --ignore-not-found
```

`helm uninstall model -n <tu-namespace>` si ya no lo usás.

## Errores frecuentes

| Si ves | Causa | Hacé |
|---|---|---|
| El HPA no sube réplicas | La carga se mandó por port-forward (va a un solo pod) | Usá el Job de k6 de arriba, adentro del cluster |
| `field is immutable` al aplicar el Job | Ya existe un Job `k6` de una corrida anterior | `kubectl delete job k6 --ignore-not-found` y aplicalo de nuevo |
| El dashboard `Model server` está vacío | Falta el ServiceMonitor o no hubo tráfico | `kubectl apply -f observability/servicemonitors.yaml` y corré el Job |
