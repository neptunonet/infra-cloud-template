# Clase 8: Caso integrador, de git push a producción

## Objetivo

Conectar todo lo que construiste: un commit pasa por CI (clase 4), queda como
imagen versionada en Artifact Registry (clase 3), Terraform asegura la
infraestructura (clase 2), Helm la despliega en Kubernetes (clase 5), Grafana
la muestra (clase 6) y una prueba de carga hace escalar el HPA.

```
git push ─> ci.yml (test, build, publish :sha) ─> Artifact Registry
                                                        │
Run workflow "deploy" (image_tag=<sha>) ─> terraform ─> GKE ─> helm upgrade ─> pods + HPA
                                                                    │
                                     k6 (Job en el cluster) ─> carga ─> Grafana
```

Al terminar tenés:

1. Un **ensayo completo en tu laptop** (k3d) con el servicio patrón: despliegue,
   verificación, carga y un nuevo deploy.
2. Lo mismo con la carga de tu curso:
   [docs/bc/clase-08.md](bc/clase-08.md) o [docs/ia/clase-08.md](ia/clase-08.md).
3. (En la nube) el mismo flujo con `deploy.yml` contra GKE.

## Prerrequisitos

- [ ] Clases 4, 5 y 6 hechas (o al menos `make doctor` con `kubectl`, `helm` y `k3d` en `[ok]`).
- [ ] ~10 GB y más de 15% de disco libre; ~4 GB de RAM para el cluster con observabilidad.

## Ensayo local (k3d)

### 1. Tests e imágenes

```bash
make test
make k3d-up
make k3d-images
```

### 2. Observabilidad

Los mismos pasos 1 a 4 de la [clase 6](clase-06.md) (kube-prometheus-stack,
ServiceMonitors y dashboards). Loki es opcional hoy.

### 3. Desplegá y verificá el servicio patrón

```bash
helm upgrade --install servicio-patron helm/charts/servicio-patron \
  -f helm/charts/servicio-patron/values-k3s.yaml --wait
kubectl get pods,pvc,hpa -l app=servicio-patron
kubectl port-forward svc/servicio-patron 18080:8080    # otra terminal
curl -s localhost:18080/healthz; echo
curl -s localhost:18080/
```

Esperado: `servicio-patron-0` en `Running`, su PVC `Bound`, `{"status":"ok"}`
y el contador de visitas.

### 4. Carga y escalado

La carga se genera **adentro del cluster** (un port-forward mandaría todo a un
solo pod). `loadtest/k6-job.yaml` elige el destino con `TARGET`; para el
servicio patrón:

```bash
kubectl create configmap k6-script --from-file=loadtest/k6-script.js --dry-run=client -o yaml | kubectl apply -f -
kubectl delete job k6 --ignore-not-found
sed 's/value: model$/value: servicio-patron/' loadtest/k6-job.yaml | kubectl apply -f -
kubectl get hpa servicio-patron -w        # Ctrl+C para salir
```

`kubectl logs job/k6` muestra el resumen: `checks` cerca de 100% y
`http_req_failed` debajo de 5%. En Grafana, el dashboard `Servicio patron`
muestra requests/s y latencia mientras dura la carga. El valor de `TARGET` y
`SLEEP` para la carga de tu curso está en su guía.

### 5. Un cambio y un nuevo deploy

Hacé un cambio visible (por ejemplo, otro texto en la respuesta de `GET /` en
`app/main.py`), corré `make test`, reconstruí y actualizá:

```bash
make k3d-images TAG=v2
helm upgrade servicio-patron helm/charts/servicio-patron \
  -f helm/charts/servicio-patron/values-k3s.yaml --set image.tag=v2 --wait
kubectl rollout status statefulset/servicio-patron
curl -s localhost:18080/       # relanzá el port-forward si se cortó
```

Las réplicas que había elegido el HPA se mantienen durante el upgrade, y el
contador sigue: vive en el PVC.

> ### En la nube (deploy.yml contra GKE)
>
> **Una sola vez**:
>
> ```bash
> export PROJECT_ID="mi-proyecto-123" REGION="us-central1"
> export POOL_ID="github-pool"          # el pool de Workload Identity de la clase 4
> export REPO="<usuario>/<repo>"        # tu repo, exacto
> gcloud storage buckets create "gs://${PROJECT_ID}-tfstate" --location="$REGION"   # si no lo creaste en la clase 2
> gcloud services enable container.googleapis.com compute.googleapis.com
> gcloud iam service-accounts create ci-deployer
> DSA="ci-deployer@${PROJECT_ID}.iam.gserviceaccount.com"
> for role in roles/compute.admin roles/container.admin roles/artifactregistry.admin \
>             roles/iam.serviceAccountUser roles/storage.objectAdmin; do
>   gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:${DSA}" --role="$role"
> done
> # El mismo binding de OIDC de la clase 4, ahora para esta cuenta:
> PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
> gcloud iam service-accounts add-iam-policy-binding "$DSA" --role=roles/iam.workloadIdentityUser \
>   --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}/attribute.repository/${REPO}"
> ```
>
> En GitHub:
>
> - Variable `GCP_DEPLOY_SERVICE_ACCOUNT` = `ci-deployer@<proyecto>.iam.gserviceaccount.com`
>   (la de la clase 4 solo puede subir imágenes).
> - Opcional: `GCP_ZONE` (default `us-central1-a`).
> - **Settings → Environments**: `dev` y `prod`. Un *required reviewer* ahí es
>   la aprobación manual, pero solo existe en repos públicos o planes pagos.
>
> **Cada deploy**:
>
> 1. `git push` a `main` y esperá que `ci` publique (el sha está en el log de
>    `publish`: `pushed .../app:<sha>`; o `git rev-parse HEAD`).
> 2. **Actions → deploy → Run workflow**: `env=dev`, `image_tag=<ese sha>` (o
>    `v0.1.0` si creaste el tag) y `charts` con los charts de tu curso (ver tu guía de la clase 8; el
>    default es solo `servicio-patron`). `latest` se rechaza.
> 3. El job `terraform` aplica la red y GKE (`enable_gke=true`); el job `helm`
>    hace `helm upgrade --install --wait` de los charts del input `charts`, con
>    esa imagen. El primer run tarda ~15 minutos (crear el cluster). En `dev`
>    la imagen también va a la VM de la clase 2: cambiarla **recrea la VM** (el
>    disco de datos es otro recurso y queda).
> 4. `gcloud container clusters get-credentials infra-cloud-dev-gke --zone us-central1-a`
>    y repetí los pasos 3 y 4 de arriba contra GKE (sin `-f values-k3s.yaml`).
>
> **Al terminar**, GKE se cobra por hora: desde `terraform/envs/dev`,
> `tofu destroy -var-file=dev.tfvars -var enable_gke=true` (o al menos
> `enable_gke=false` + `apply`). Los PVC de GKE son discos: borralos antes con
> `kubectl delete pvc --all`.

## Limpieza (local)

```bash
kubectl delete job k6 --ignore-not-found
helm uninstall --ignore-not-found servicio-patron
helm uninstall --ignore-not-found kube-prom loki alloy -n observability
make k3d-down
```

## Errores frecuentes

| Si ves | Causa | Hacé |
|---|---|---|
| PVC `Pending`, `storageclass "standard" not found` | Instalaste con los valores de GKE | `helm uninstall <release>`, `kubectl delete pvc -l app=<release>`, reinstalá con `-f values-k3s.yaml` |
| `UPGRADE FAILED: ... updates to statefulset spec ... are forbidden` | Cambiaste StorageClass, tamaño u otro campo fijo de un StatefulSet existente | `helm uninstall <release>`, `kubectl delete pvc -l app=<release>` y reinstalá |
| `error: lost connection to pod` | El HPA borró el pod del port-forward al bajar réplicas | Relanzá el port-forward |
| `field is immutable` al aplicar el Job de k6 | Quedó el Job de una corrida anterior | `kubectl delete job k6 --ignore-not-found` y aplicalo de nuevo |
| El HPA no sube réplicas | Poca carga (k6 por port-forward o `SLEEP=1`) | El Job de k6, adentro del cluster |
| El HPA sube sin carga recién instalado | CPU del arranque | Esperá ~5 min antes de medir la línea base |
| HPA `<unknown>` | metrics-server sin datos todavía | Esperá un minuto |
| `publish` skipped en `ci` | Faltan las variables de la clase 4 | Cargalas; no hay imagen para desplegar sin eso |
| `deploy` falla en `terraform init` con `bucket doesn't exist` | No creaste `gs://<proyecto>-tfstate` | El `gcloud storage buckets create` de arriba |
| `deploy` falla con `image_tag must be a git sha or vX.Y.Z` | Pusiste `latest` o nada | El sha que publicó `ci` |
| `ImagePullBackOff` en GKE | Ese tag no existe en Artifact Registry | `gcloud artifacts docker images list $AR --include-tags` |
| En GKE aparecen pods de un chart que no usás | Lanzaste `deploy` con otro valor de `charts` | `helm uninstall <release>` y `kubectl delete pvc -l app=<release>` |
| `Error 409: already exists` en el plan de `prod` | El registry ya lo creó `dev` | Es el default (`enable_artifact_registry = false` en prod); no lo prendas |
