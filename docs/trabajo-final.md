# Trabajo Final — Clima Rutero: probabilidad de lluvia por tramo (despliegue reproducible)

Cómo levantar, probar y apagar el servicio `lluvia` desde cero. El detalle de cada pieza está en su carpeta:
`lluvia/README.md` (código, entrenamiento, API), `helm/charts/lluvia` y `helm/charts/postgres` (charts),
`observability/lluvia/` (métricas, alertas, dashboard), `loadtest/` (pruebas de carga).

```
VPS (24/7, ARM64)                     GCS (persistente)                    GKE (solo en sesiones)
cron 07:00 exportar.py  ──────────▶  datasets/AAAA-MM-DD.parquet
cron 07:30 train.py     ◀── lee ───  datasets/
                        ── versión ▶ modelos/versiones/v.../ ─▶ activa.json ──relee c/5 min──▶ API lluvia (HPA 1–5)
                                                                                           ├▶ Postgres (registro)
GitHub Actions (OIDC): ci.yml → Artifact Registry (amd64 + arm64)  ·  deploy.yml → Terraform + Helm → GKE
```

## 0. Prerrequisitos (una vez)

Herramientas: `gcloud`, OpenTofu 1.13 (`tofu`), `kubectl`, `helm` 3/4, `gh`, Docker. Para k3d: `k3d` 5.9.

En GCP (lo arman las clases 2, 4 y 8 de `docs/`):

| Qué | Dónde se crea |
|---|---|
| Proyecto con facturación y presupuesto con alertas | Consola de Billing (Clase 1) |
| Bucket del state: `gs://<PROYECTO>-tfstate` | Clase 2 |
| Artifact Registry `infra-cloud-template` (us-central1) | Clase 3 (a mano; `enable_artifact_registry=false` en `dev`) |
| Workload Identity Federation para GitHub (`github-pool` / `github-provider`) y la cuenta `ci-artifact-writer` | Clase 4 (`docs/clase-04.md`) |
| Cuenta `ci-deployer` y Environment `dev` con aprobación | Clase 8 (`docs/clase-08.md`) |
| Variables del repo: `GCP_PROJECT_ID`, `GCP_REGION`, `AR_REPOSITORY`, `GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_SERVICE_ACCOUNT`, `GCP_DEPLOY_SERVICE_ACCOUNT` | `gh variable set` (Clases 4 y 8). El repo **no** tiene Secrets |

> El bucket del caso es `gs://unlu-ia-armas-lluvia` y está escrito en `helm/charts/lluvia/values.yaml`
> (`modelos.destino`, `entrenamiento.datos`). En otro proyecto, cambiarlo ahí o con `--set`.

## 1. Lo persistente: bucket y cuentas (`terraform/envs/tf-persistente`)

No se destruye al apagar. Crea `gs://<PROYECTO>-lluvia` (versionado, sin acceso público, `prevent_destroy`) y las cuentas
`lluvia-export` (solo crea en `datasets/`), `lluvia-entrena` y `lluvia-servicio` (escriben solo en `modelos/`), más el
permiso de `ci-deployer` para vincular `lluvia-servicio` desde `deploy.yml`.

```bash
cd terraform/envs/tf-persistente
cp backend.hcl.example backend.hcl            # bucket = "<PROYECTO>-tfstate"
cp persistente.tfvars.example persistente.tfvars   # project_id = "<PROYECTO>"
tofu init -backend-config=backend.hcl
tofu plan -var-file=persistente.tfvars        # revisar: todo «+», ningún «-»
tofu apply -var-file=persistente.tfvars
```

Las claves JSON de `lluvia-export` y `lluvia-entrena` **no** se crean con Terraform (quedarían en el state): se crean a
mano y viven solo en el VPS (`chmod 600`).

```bash
gcloud iam service-accounts keys create lluvia-export.json --iam-account=lluvia-export@<PROYECTO>.iam.gserviceaccount.com
```

## 2. Datos y primer modelo

El VPS exporta un día por vez (`scripts/export_lluvia.sh` en el repo de Clima Rutero; cron 07:00 UTC) y entrena
(`scripts/entrenar_lluvia.sh`; cron 07:30 UTC) con la imagen de `lluvia` fijada a una etiqueta `v*`
(`LLUVIA_IMAGEN` en su `.env`). Para entrenar desde una máquina propia contra el bucket:

```bash
cd lluvia
uv run --python 3.12 --with-requirements requirements.txt python train.py \
  --datos 'gs://<PROYECTO>-lluvia/datasets/*.parquet' --destino gs://<PROYECTO>-lluvia/modelos
```

Cada corrida deja `modelos/versiones/vAAAAMMDD_HHMMSS/` (`modelo.joblib` + `metadata.json`) y, si la versión nueva le
gana a la activa con evidencia, actualiza `modelos/activa.json`.

## 3. Imagen (CI)

Un push a `main` corre `ci.yml`: tests, build **multi-arch** (amd64 + arm64) y push a Artifact Registry con la etiqueta
del commit (`lluvia:<sha>`). Si el código de una imagen no cambió, se le agrega la etiqueta nueva a la imagen anterior
(`gcloud artifacts docker tags add`) en vez de reconstruirla.

Lo que se usa fuera del CI (el VPS) va con etiqueta `v*`, que la regla de limpieza del registry conserva
(`registry/README.md`):

```bash
R=us-central1-docker.pkg.dev/<PROYECTO>/infra-cloud-template
gcloud artifacts docker tags add $R/lluvia:<sha> $R/lluvia:v0.x.0
```

## 4. Desplegar en GKE (`deploy.yml`)

GitHub → **Actions → deploy → Run workflow**:

| Campo | Valor |
|---|---|
| env | `dev` |
| accion | `desplegar` |
| image_tag | el sha completo de `main` (o una etiqueta `v*`) |
| charts | `postgres lluvia` (en ese orden) |

Hay que aprobar dos veces en el Environment `dev`: el job `terraform` (red + GKE `e2-standard-2` × 1–2 + vínculo de
Workload Identity `default/lluvia` → `lluvia-servicio`; ~10 min) y el job `helm` (Postgres, la API y el Job que carga los
`metadata.json` en Postgres; ~4 min).

Verificar desde una terminal:

```bash
gcloud container clusters get-credentials infra-cloud-dev-gke --zone us-central1-a --project <PROYECTO>
kubectl get pods,svc,hpa,pvc,jobs,cronjobs
kubectl logs job/lluvia-cargar-versiones                     # «nuevas: N»
kubectl port-forward svc/lluvia 18083:8083 &
curl -s localhost:18083/version
curl -s -X POST localhost:18083/predict -H 'Content-Type: application/json' -d @lluvia/ejemplo-predict.json
```

(`lluvia/ejemplo-predict.json`: un tramo en zona verificada, uno en región entrenada sin WRF y uno en zona no vista.
Sin `gke-gcloud-auth-plugin`, `kubectl` no se conecta: con el gcloud de apt se instala
`google-cloud-cli-gke-gcloud-auth-plugin`.)

## 5. Observabilidad (opcional, en la misma sesión)

```bash
kubectl create namespace observability
kubectl -n observability create secret generic alertmanager-telegram --from-file=token=<archivo-con-el-token-del-bot>
helm upgrade --install kube-prom oci://ghcr.io/prometheus-community/charts/kube-prometheus-stack --version 91.9.0 \
  -n observability -f observability/kube-prometheus-stack-values.yaml -f observability/lluvia/kube-prom-tf.yaml \
  --set grafana.adminPassword='<contraseña>' \
  --set "alertmanager.config.receivers[1].telegram_configs[0].chat_id=<chat>" --wait
kubectl apply -k observability/lluvia/        # ServiceMonitor, 6 alertas y el dashboard «lluvia»
kubectl -n observability port-forward svc/kube-prom-grafana 13000:80 &
```

Prometheus tarda ~1 min en tomar el ServiceMonitor y las reglas.

## 6. Pruebas

```bash
loadtest/lluvia-grilla.sh resultados.csv      # 1/3/5 réplicas × 1/2/5/10 simultáneos × lotes de 156 y 4.810 tramos
kubectl create job --from=cronjob/lluvia-entrenamiento entrenamiento-manual   # entrenamiento dentro del clúster
```

La grilla apaga el HPA mientras corre y lo vuelve a prender al final. El CronJob está suspendido (el diario corre en el
VPS); para no pisar `activa.json`, antes apuntarlo a un prefijo de prueba:
`helm upgrade lluvia helm/charts/lluvia --reuse-values --set entrenamiento.destino=gs://<PROYECTO>-lluvia/modelos/pruebas`.

## 7. Apagar (el mismo día)

GitHub → **Actions → deploy → Run workflow** con `accion = apagar` (aprobar `vaciar` y `terraform`). `vaciar` desinstala
todas las releases y borra los PVC (sus discos no se borran con el clúster); después Terraform destruye el clúster. La red
queda (no cuesta). Verificar:

```bash
gcloud container clusters list --project <PROYECTO>
gcloud compute disks list --project <PROYECTO>       # «Listed 0 items.»
```

## 8. En local con k3d (sin costo)

```bash
k3d cluster create tf-lluvia --agents 2 --k3s-arg "--disable-cloud-controller@server:0" --wait
docker build -t lluvia:local lluvia/ && k3d image import lluvia:local -c tf-lluvia
kubectl create secret generic lluvia-gcs --from-file=clave.json=<clave-de-lluvia-servicio>.json   # fuera de GKE no hay Workload Identity
helm install postgres helm/charts/postgres
helm install lluvia helm/charts/lluvia -f helm/charts/lluvia/values-k3s.yaml
```

La clave de `lluvia-servicio` es solo para el clúster local: se borra al terminar
(`gcloud iam service-accounts keys delete`). Detrás de una VPN con *exit node* (Tailscale), los contenedores pueden
quedarse sin red: `sudo ip rule add to 172.16.0.0/12 lookup main priority 5200` (se pierde al reiniciar).
