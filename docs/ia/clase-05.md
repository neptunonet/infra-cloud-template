# Clase 5 · Ejercicio para tu área: el modelo como Deployment con HPA

Complementa la [guía de la clase 5](../clase-05.md). Hacé primero sus pasos 1 a
6 (cluster k3d, imágenes y servicio patrón); esto es el ejercicio para tu área. Los
comandos se corren desde la raíz del repo, con el cluster local activo.

El modelo no tiene estado propio (los pesos están en la imagen), así que es un
Deployment sin PVC.

```bash
helm upgrade --install model helm/charts/model -f helm/charts/model/values-k3s.yaml --wait
kubectl get deploy,hpa model          # el HPA lo sube a 2 réplicas en unos segundos
kubectl port-forward svc/model 18081:8081     # en otra terminal
curl -s -X POST localhost:18081/predict -H 'Content-Type: application/json' -d '{"features":[5.1,3.5,1.4,0.2]}'; echo
```

Upgrade y rollback:

```bash
helm upgrade model helm/charts/model -f helm/charts/model/values-k3s.yaml --set autoscaling.minReplicas=3 --wait
kubectl get hpa model                 # MINPODS 3
helm history model
helm rollback model 1 --wait
```

Cuando un chart cambia entre clases, usá `-f` con los mismos valores (como
arriba) o `--reset-then-reuse-values`; `--reuse-values` solo ignora las claves
nuevas del chart.

> ### En la nube (GKE)
>
> Con `kubectl` apuntando al cluster como en la guía de la clase, y la imagen
> que subiste en la clase 3:
> `helm upgrade --install model helm/charts/model --set image.repository="$AR/model" --set image.tag=v1 --wait`.

## Limpieza

```bash
helm uninstall --ignore-not-found model
```

## Errores frecuentes

| Si ves | Causa | Hacé |
|---|---|---|
| El HPA tiene 2 réplicas sin carga | `minReplicas` del chart es 2 | Es lo esperado |
| `/predict` responde 503 | El pod todavía carga el modelo | `kubectl wait --for=condition=Ready pod -l app=model --timeout=120s` |
| `ErrImagePull` del modelo en GKE | `image.repository` o el tag no existen en Artifact Registry | `gcloud artifacts docker images list "$AR"` y revisá `$AR/model:v1` |
