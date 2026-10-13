# Clase 3: Contenedores con Docker y Artifact Registry

## Objetivo

"En mi máquina anda" se resuelve empaquetando el runtime completo (código +
dependencias) en una imagen, y publicándola en un registry del que cualquier
máquina la puede bajar.

Al terminar tenés:

1. La imagen del servicio patrón construida y probada en tu laptop.
2. El servicio patrón con compose, con el estado en un volumen que sobrevive a `down`/`up`.
3. Tu imagen publicada en Artifact Registry como `$AR/app:v1` y bajada desde otra máquina.
4. Lo mismo con la carga de ejemplo que pida tu aula:
   [docs/bc/clase-03.md](bc/clase-03.md) o [docs/ia/clase-03.md](ia/clase-03.md).

## Prerrequisitos

- [ ] `make doctor` sin `[FAIL]` y estás en la raíz del repo.
- [ ] Nada corriendo en 8080. Si quedó el contenedor de la clase 1:
      `docker rm -f servicio-patron`.
- [ ] Para la parte en la nube: las variables de la tabla del
      [README](../README.md#nombres-puertos-y-tags-una-sola-tabla-para-todo-el-curso)
      (`PROJECT_ID`, `REGION`, `AR`).

## Pasos

### 1. Construí la imagen

```bash
make build-app             # = docker build -t app:local ./app
docker images --format '{{.Repository}}:{{.Tag}}  {{.Size}}' | grep ':local'
```

Esperado (aproximado, según tu Docker):

```
app:local             256MB
```

La base `python:3.12-slim` ya pesa unos 190 MB. Los warnings
`Running pip as the 'root' user` del build no son errores. La imagen de la
carga de ejemplo de tu aula se construye en su guía (punto 4 del objetivo).

### 2. Corré una imagen con un volumen con nombre

```bash
docker run -d --name servicio-patron -p 8080:8080 -v servicio-patron-data:/data app:local
until curl -sf localhost:8080/healthz; do sleep 1; done; echo
curl localhost:8080/
curl -s -X POST localhost:8080/items -H 'Content-Type: application/json' -d '{"name":"hola"}'; echo
docker rm -f servicio-patron
docker run -d --name servicio-patron -p 8080:8080 -v servicio-patron-data:/data app:local
until curl -sf localhost:8080/healthz; do sleep 1; done; echo
curl localhost:8080/
docker rm -f servicio-patron
```

Esperado: el segundo `curl localhost:8080/` dice `Visitas persistidas en disco: 2`.
El campo del item se llama `name` (con `{"item": ...}` la API responde 422).

Un volumen con nombre (`servicio-patron-data`) lo crea Docker y es escribible
por el contenedor; no hace falta `--user` como con la carpeta de la clase 1.

### 3. Lo mismo con compose

```bash
make compose-up            # = docker compose -f compose/docker-compose.yml up -d --build --wait
curl localhost:8080/
make compose-down          # baja el contenedor, CONSERVA el volumen
make compose-up
curl localhost:8080/       # el contador sigue
make compose-reset         # baja todo y BORRA el volumen
```

`--wait` espera al healthcheck: cuando el comando termina, el servicio ya
contesta. `docker compose ps` muestra `(healthy)`.

### 4. Buenas prácticas que ya trae el repo

- Base `-slim`, `pip install --no-cache-dir`, un proceso y un puerto por imagen.
- `.dockerignore` en cada carpeta: los tests y los cachés no entran a la imagen.
- `HEALTHCHECK` contra `/healthz` en cada `Dockerfile`.
- Lo que se puede calcular una sola vez (un archivo generado, un artefacto
  compilado) se hace **durante el build** con un `RUN`, no en cada arranque.
- Sin `VOLUME` en los Dockerfile: montás `/data` vos, explícitamente.

Multi-stage: sirve cuando el build necesita compiladores o herramientas que no
querés en la imagen final (Go, Rust, wheels con C). Para estas imágenes de
Python puro casi no achica (lo medimos: unos 2 MB de diferencia).

Usuario no root: si agregás `USER` a un Dockerfile, creá el usuario con un uid
fijo (`useradd --create-home --uid 1000 appuser`) y asegurate de que el disco
sea suyo (`sudo chown -R 1000:1000 /mnt/disks/datos`). Si no, el servicio
responde 500 y en `docker logs` aparece `PermissionError`.

> ### En la nube (Artifact Registry)
>
> Un solo repositorio para todo el curso: `infra-cloud-template`, en
> `us-central1`. Si aplicaste `terraform/envs/dev` en la clase 2 ya
> existe; si no, crealo **una sola vez** de una de estas dos formas (no las dos:
> la segunda falla con "already exists"):
>
> ```bash
> export PROJECT_ID="mi-proyecto-123" REGION="us-central1"
> export AR="${REGION}-docker.pkg.dev/${PROJECT_ID}/infra-cloud-template"
> echo "$AR"     # revisalo: minúsculas, sin espacios, sin <...>
> # opción A, con terraform (clase 2): ya está.
> # opción B, a mano:
> gcloud artifacts repositories create infra-cloud-template --repository-format=docker --location="$REGION"
> ```
>
> Subí la imagen:
>
> ```bash
> gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet
> docker tag app:local "$AR/app:v1"
> docker push "$AR/app:v1"
> gcloud artifacts docker images list "$AR"
> ```
>
> Bajala en una segunda VM (`servicio-patron-2`, ver el «Lab Clase 3 - Docker y Artifact Registry» del aula: scope
> `cloud-platform` y rol `roles/artifactregistry.reader`). En la VM los comandos
> de docker van con `sudo`, así que la autenticación también:
>
> ```bash
> export PROJECT_ID="mi-proyecto-123" REGION="us-central1"
> export AR="${REGION}-docker.pkg.dev/${PROJECT_ID}/infra-cloud-template"
> sudo gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet
> sudo docker rm -f servicio-patron 2>/dev/null
> sudo docker run -d --name servicio-patron -p 8080:8080 \
>   -v servicio-patron-data:/data "$AR/app:v1"
> ```

## Limpieza

```bash
docker rm -f servicio-patron 2>/dev/null
make compose-reset
docker volume rm servicio-patron-data 2>/dev/null
```

En GCP las imágenes ocupan espacio (y se cobra pasado el free tier):
`gcloud artifacts docker images delete "$AR/app:v1"` cuando ya no la uses.

## Errores frecuentes

| Si ves | Causa | Hacé |
|---|---|---|
| `422 Unprocessable Entity` en `POST /items` | El JSON no tiene `name`, o falta `-H 'Content-Type: application/json'` | `-d '{"name":"hola"}'` con el header |
| `500` y `PermissionError` en `docker logs` | La imagen corre como no root y `/data` es de root | `sudo chown -R 1000:1000 <dir>` o un volumen con nombre |
| `port is already allocated` | Quedó el contenedor de la clase 1 o otro compose | `docker ps`; `docker rm -f servicio-patron` o `make compose-down` |
| `invalid reference format` | `$PROJECT_ID` vacío, con mayúsculas o con `<...>` | `echo "$AR"` y corregí el `export` |
| `syntax error near unexpected token 'newline'` | Copiaste `export PROJECT_ID=<tu-project-id>` literal | Poné tu valor entre comillas, sin `<>` |
| `denied` / `Unauthenticated` en `docker push` o `pull` | Falta `configure-docker` (o lo corriste sin `sudo` y usás `sudo docker`) | `gcloud auth configure-docker ${REGION}-docker.pkg.dev` con el mismo usuario que corre docker |
| `name unknown` en `docker push` | El repositorio no existe en esa región | `gcloud artifacts repositories list --location=$REGION` |
| `docker: 'compose' is not a docker command` | Docker instalado con `apt install docker.io` | `curl -fsSL https://get.docker.com \| sudo sh` |
