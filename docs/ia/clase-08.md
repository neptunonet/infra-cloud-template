# Clase 8 · El modelo escalando con el HPA

Complementa la [guía de la clase 8](../clase-08.md). Hacé primero sus pasos 1 a
3 (tests, imágenes, observabilidad y servicio patrón en k3d); esto es lo propio
de tu curso. Los comandos se corren desde la raíz del repo, con el cluster local
activo.

## 1. Desplegá el modelo

```bash
helm upgrade --install model helm/charts/model -f helm/charts/model/values-k3s.yaml --wait
kubectl get deploy,hpa model -w             # Ctrl+C cuando haya 2 réplicas
```

Sin el HPA el chart pondría las réplicas fijas; con el HPA prendido no las pone
(si no, cada `helm upgrade` pisaría lo que decidió el HPA). Por eso una
instalación nueva arranca con **1 pod** y en unos segundos el HPA la lleva a
`minReplicas` (2). `helm --wait` vuelve antes: esperá con el `-w`.

## 2. Verificá

```bash
kubectl port-forward svc/model 18081:8081    # otra terminal
curl -s -X POST localhost:18081/predict -H 'Content-Type: application/json' -d '{"features":[5.1,3.5,1.4,0.2]}'; echo
```

## 3. Carga y escalado

La carga se genera **adentro del cluster** (un port-forward mandaría todo a un
solo pod). `loadtest/k6-job.yaml` viene con `TARGET=model` y `SLEEP=0.05`:

```bash
kubectl create configmap k6-script --from-file=loadtest/k6-script.js --dry-run=client -o yaml | kubectl apply -f -
kubectl delete job k6 --ignore-not-found
kubectl apply -f loadtest/k6-job.yaml
kubectl get hpa model -w                    # Ctrl+C para salir
```

Esperado: las réplicas pasan de 2 a 4 o más en uno o dos minutos (lo medimos:
2 → 4 → 6 → 8). Al terminar la carga bajan solas en unos 5 minutos. En Grafana,
`Model server` muestra la latencia y las réplicas.

`kubectl logs job/k6` muestra el resumen: `checks` cerca de 100% y
`http_req_failed` debajo de 5%.

## 4. Un cambio y un nuevo deploy

Hacé un cambio visible (por ejemplo un `model_version` en la respuesta de
`/predict`), corré `make test-model`, reconstruí y actualizá:

```bash
make k3d-images TAG=v2
helm upgrade model helm/charts/model -f helm/charts/model/values-k3s.yaml --set image.tag=v2 --wait
kubectl rollout status deploy/model
```

Las réplicas que había elegido el HPA se mantienen durante el upgrade.

> ### En la nube (deploy.yml contra GKE)
>
> El paso "Una sola vez" es el de la guía de la clase. Al lanzar
> **Actions → deploy → Run workflow**, poné `charts` = `servicio-patron model`.
> Después, con `kubectl` apuntando a GKE, repetí la verificación y la carga de
> arriba.

## Limpieza

```bash
kubectl delete job k6 --ignore-not-found
helm uninstall --ignore-not-found model
```

## Errores frecuentes

| Si ves | Causa | Hacé |
|---|---|---|
| El HPA no pasa de 2 réplicas | Poca carga (k6 por port-forward o `SLEEP=1`) | El Job de k6 con `SLEEP=0.05` |
| `error: lost connection to pod` | El HPA borró el pod del port-forward al bajar réplicas | Relanzá el port-forward |
| `/predict` responde 503 | El pod todavía carga el modelo | `kubectl wait --for=condition=Ready pod -l app=model --timeout=120s` |
| `ImagePullBackOff` del modelo en GKE | Ese tag no existe en Artifact Registry | `gcloud artifacts docker images list $AR --include-tags` |
