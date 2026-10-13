# Clase 4: CI/CD con GitHub Actions y OIDC

## Objetivo

Cada push corre los tests y construye las imágenes; cada push a `main` (y cada
tag de release) publica la imagen en Artifact Registry. Sin ninguna clave
guardada: GitHub emite un token de corta duración (OIDC) y GCP confía en él a
través de un Workload Identity Provider.

Al terminar tenés:

1. Un primer run verde (`test` y `build`) con `publish` en gris (skipped).
2. Workload Identity Federation configurado y las variables del repo cargadas.
3. `$AR/app:<sha>` publicado por un push a `main` y `$AR/app:v0.1.0` por un tag.
4. (Opcional) Un servicio propio agregado al pipeline.

## Prerrequisitos

- [ ] Tu repo creado con **Use this template** (en un fork las Actions arrancan deshabilitadas).
- [ ] El repositorio `infra-cloud-template` de Artifact Registry de la clase 3, en `us-central1`.
- [ ] `make doctor` sin `[FAIL]`. `gh` (GitHub CLI) es opcional: todo se puede hacer desde la web.

## Pasos

### 1. Lo mismo que corre CI, en tu laptop

```bash
make test-app    # corre los tests del servicio patrón
make build-app   # construye app:local, como el job build
```

Los tests corren con `uv` (si falta, `make doctor` te dice cómo instalarlo).
Si agregaste un servicio propio, corré también su test y su build.

### 2. Primer push, sin variables

Hacé cualquier cambio chico, `git commit` y `git push`. En la pestaña
**Actions** el workflow `ci` muestra:

- `test (...)` y `build (...)`: un test y un build por cada servicio de las
  matrices de `ci.yml`, verdes (el build incluye un smoke test contra `/healthz`).
- `publish`: **gris, skipped**. Es lo esperado: todavía no cargaste `GCP_PROJECT_ID`.

### 3. Workload Identity Federation (una vez por proyecto)

> ### En la nube (GCP)
>
> Reemplazá `<usuario>/<repo>` por el tuyo, **exacto** (mayúsculas incluidas).
>
> ```bash
> export PROJECT_ID="mi-proyecto-123" REGION="us-central1"
> export REPO="<usuario>/<repo>"
> gcloud services enable iam.googleapis.com iamcredentials.googleapis.com \
>   sts.googleapis.com artifactregistry.googleapis.com --project="$PROJECT_ID"
>
> export POOL_ID="github-pool"
> gcloud iam workload-identity-pools create "$POOL_ID" --project="$PROJECT_ID" \
>   --location=global --display-name="GitHub Actions"
> gcloud iam workload-identity-pools providers create-oidc github-provider --project="$PROJECT_ID" \
>   --location=global --workload-identity-pool="$POOL_ID" \
>   --issuer-uri="https://token.actions.githubusercontent.com" \
>   --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
>   --attribute-condition="assertion.repository=='${REPO}'"
>
> gcloud iam service-accounts create ci-artifact-writer --project="$PROJECT_ID"
> SA="ci-artifact-writer@${PROJECT_ID}.iam.gserviceaccount.com"
> gcloud artifacts repositories add-iam-policy-binding infra-cloud-template \
>   --project="$PROJECT_ID" --location="$REGION" \
>   --member="serviceAccount:${SA}" --role=roles/artifactregistry.writer
>
> PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
> gcloud iam service-accounts add-iam-policy-binding "$SA" --project="$PROJECT_ID" \
>   --role=roles/iam.workloadIdentityUser \
>   --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}/attribute.repository/${REPO}"
>
> # El nombre COMPLETO del provider, para la variable GCP_WORKLOAD_IDENTITY_PROVIDER:
> gcloud iam workload-identity-pools providers describe github-provider --project="$PROJECT_ID" \
>   --location=global --workload-identity-pool="$POOL_ID" --format='value(name)'
> ```
>
> El último comando imprime algo como
> `projects/123456789012/locations/global/workloadIdentityPools/github-pool/providers/github-provider`
> (con el **número** de proyecto, no el id).
>
> Los labs dan el rol `roles/artifactregistry.writer` a nivel proyecto; acá se
> acota al repositorio: cualquiera de los dos alcanza.
>
> El binding puede tardar unos 5 minutos en propagarse: si el primer `publish`
> falla con `Permission 'iam.serviceAccounts.getAccessToken' denied`, esperá y
> volvé a correr el job.

### 4. Variables del repositorio

En GitHub: **Settings → Secrets and variables → Actions → Variables → New
repository variable**. Son identificadores, no secretos.

| Variable | Valor | De dónde sale |
|---|---|---|
| `GCP_PROJECT_ID` | `mi-proyecto-123` | tu proyecto |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | `projects/<NÚMERO>/locations/global/workloadIdentityPools/github-pool/providers/github-provider` | el `describe` del paso 3 |
| `GCP_SERVICE_ACCOUNT` | `ci-artifact-writer@mi-proyecto-123.iam.gserviceaccount.com` | el `SA` del paso 3 |
| `GCP_REGION` | `us-central1` | opcional (es el default) |
| `AR_REPOSITORY` | `infra-cloud-template` | opcional (es el default) |

Con `gh`: `gh variable set GCP_PROJECT_ID --body "$PROJECT_ID"` (y así con cada una).

### 5. Push a `main`: imagen con el sha

Hacé otro push. Ahora corren los `publish (...)`, uno por cada servicio de la
matriz, y terminan con líneas `pushed .../app:<sha de 40 caracteres>`.

```bash
gcloud artifacts docker images list "${REGION}-docker.pkg.dev/${PROJECT_ID}/infra-cloud-template" --include-tags
```

### 6. Tag de release: imagen con la versión

```bash
git tag v0.1.0
git push origin v0.1.0
```

El workflow corre otra vez (por el tag) y publica **también** `:v0.1.0`. Los
tags tienen que ser `vMAJOR.MINOR.PATCH`; `v1` o `vprueba` se rechazan a
propósito (lo decide `scripts/compute-tags.sh`). No hay `:latest`.

Si querés poner una versión a una imagen ya publicada sin rebuild:
`gcloud artifacts docker tags add "$AR/app:<sha>" "$AR/app:v0.1.1"`.

## Agregar un servicio propio al pipeline

Si sumás una carpeta nueva (por ejemplo `mi-servicio/` con su `Dockerfile`,
`requirements.txt`, `tests/` y un `/healthz`), agregala en tres lugares de
`ci.yml`:

1. `test.strategy.matrix.service`: `mi-servicio`.
2. `build.strategy.matrix.include`: `- service: mi-servicio` y `port: <su puerto>`.
3. `publish.strategy.matrix.service`: `mi-servicio`.

La imagen queda como `$AR/mi-servicio:<sha>`. Al revés, si tu aula no usa
una de las cargas de ejemplo del repo, sacala de esas tres matrices. Los `${{ github.sha }}` son
sintaxis de Actions: **no** funcionan en tu terminal (ahí usá `$(git rev-parse HEAD)`).

## Limpieza

Nada que cueste plata. Si querés desarmar OIDC al final de la cursada:
`gcloud iam workload-identity-pools delete github-pool --location=global`.

## Errores frecuentes

| Si ves | Causa | Hacé |
|---|---|---|
| `publish` gris (skipped) | Falta la variable `GCP_PROJECT_ID` | Es lo esperado hasta el paso 4 |
| `::error::GCP_WORKLOAD_IDENTITY_PROVIDER must be the full name` | Pusiste solo `github-provider` o el id del proyecto en vez del número | Copiá la salida del `describe` del paso 3 |
| `IAM Service Account Credentials API has not been used` | Falta habilitar las APIs | El `gcloud services enable ...` del paso 3 |
| `Permission 'iam.serviceAccounts.getAccessToken' denied` | El binding todavía no propagó, o `attribute.repository` no coincide con tu repo | Esperá 5 min; revisá `<usuario>/<repo>` exacto |
| `denied: Permission "artifactregistry.repositories.uploadArtifacts"` | La cuenta no tiene `artifactregistry.writer` sobre ese repositorio | El `add-iam-policy-binding` del paso 3, en la misma región |
| `name unknown` | `AR_REPOSITORY`/`GCP_REGION` no coinciden con el repositorio de la clase 3 | `gcloud artifacts repositories list` |
| `tag 'v1' is not semver` | El tag no es `vX.Y.Z` | `git tag v1.0.0` |
| No veo la pestaña Actions o no corre nada | El repo es un fork | Creá el repo con **Use this template** |
| `bad substitution` en tu terminal | Pegaste `${{ github.sha }}` en bash | Usá `$(git rev-parse HEAD)` |
