# Clase 7: servir un modelo y medirlo (Cloud Run, Ollama, vast.ai)

Complementa la [guía de la clase 7](../clase-07.md): ahí está el método
(quién opera qué, cómo medir y cómo costear). Los comandos se corren desde la
raíz del repo. Lo que se entrega es lo que pide el «Lab Clase 7 - Modelos de
IA en la nube» de tu aula.

El servidor de `model/` es el *stand-in* local de un endpoint de inferencia. Lo
medís en tu laptop y comparás con una opción administrada (Vertex AI / Cloud
Run), una autogestionada (Ollama en una VM) o una GPU alquilada (vast.ai).

## 0. Prerrequisitos

- [ ] `make doctor` sin `[FAIL]`, en la raíz del repo.
- [ ] `make build-model` (imagen `model:local`).

## 1. El servidor y su contrato

```bash
make test-model                    # 6 passed
docker run -d --name model -p 8081:8081 model:local
until curl -sf localhost:8081/healthz; do sleep 1; done; echo
curl -s -X POST localhost:8081/predict -H 'Content-Type: application/json' \
  -d '{"features": [6.7, 3.0, 5.2, 2.3]}'; echo
```

Esperado: `{"status":"ok"}` y `{"class":"virginica","confidence":0.9...}`.
`GET /` lista los endpoints y `/docs` muestra la API. El modelo se carga **al
arrancar**: `/healthz` da 503 hasta que está listo, así que el primer
`/predict` ya no paga la carga.

## 2. Medilo

`hey` genera carga y te da la distribución de latencias. Sin instalarlo:

```bash
docker run --rm --network host williamyeh/hey -n 2000 -c 20 -m POST \
  -H 'Content-Type: application/json' -d '{"features":[5.1,3.5,1.4,0.2]}' \
  http://localhost:8081/predict
```

(`--network host` funciona en Linux y WSL; en macOS usá
`http://host.docker.internal:8081/predict` sin `--network host`.)
Mirá `Requests/sec` y la línea `95% in ...`: esa es tu p95. Para comparar con
la nube anotá también la primera request en frío
(`curl -w '%{time_total}\n' -o /dev/null -s ...` justo después de arrancar).

Limpieza: `docker rm -f model`.

## 3. (Opcional) En el cluster local

```bash
make k3d-up && make k3d-images
helm upgrade --install model helm/charts/model -f helm/charts/model/values-k3s.yaml --wait
kubectl port-forward svc/model 18081:8081          # otra terminal
curl -s -X POST localhost:18081/predict -H 'Content-Type: application/json' -d '{"features":[5.1,3.5,1.4,0.2]}'
```

> ### En la nube
>
> **Cloud Run** (lo más directo para este contenedor):
>
> ```bash
> export PROJECT_ID="mi-proyecto-123" REGION="us-central1"
> export AR="${REGION}-docker.pkg.dev/${PROJECT_ID}/infra-cloud-template"
> gcloud services enable run.googleapis.com   # una sola vez por proyecto
> docker build --platform linux/amd64 -t "$AR/model:v1" ./model && docker push "$AR/model:v1"
> gcloud run deploy model-server --image="$AR/model:v1" --region="$REGION" --port=8081 --allow-unauthenticated
> URL=$(gcloud run services describe model-server --region="$REGION" --format='value(status.url)')
> curl -s -X POST "$URL/predict" -H 'Content-Type: application/json' -d '{"features":[5.1,3.5,1.4,0.2]}'
> ```
>
> (`--platform linux/amd64` es obligatorio en Mac M1/M2/M3: Cloud Run solo corre amd64.)
>
> **Vertex AI**: un *custom container* de Vertex recibe `{"instances": [...]}`
> en la ruta que le indiques y responde `{"predictions": [...]}`; nuestro
> `/predict` usa `{"features": [...]}`. Para usar Vertex tal cual hay que
> agregar esa ruta adaptadora en `model/serve.py`. Por eso para comparar te
> recomendamos Cloud Run.
>
> **Ollama en una VM**: usá **e2-medium** o más (`llama3.2:1b` ocupa ~1,5 GB de
> RAM), y recordá que Ollama tiene otro contrato (`/api/generate`) y es otro tipo
> de modelo: la comparación de latencia no es "manzana con manzana". El firewall
> del curso solo abre el 8080: medí desde la VM contra `localhost`, o con un
> túnel (`gcloud compute ssh <vm> -- -L 11434:localhost:11434`), o agregá el
> puerto con `extra_ports` en `terraform/modules/network`.
>
> **vast.ai**: seguí la herramienta que indica el «Lab Clase 7 - Modelos de IA en la nube» de tu aula. El contenedor es el mismo;
> lo que cambia es la máquina.
>
> Al terminar: `gcloud run services delete model-server --region="$REGION"` y
> apagá/borrá cualquier VM o instancia con GPU (se cobran por hora).

## Limpieza

```bash
docker rm -f model 2>/dev/null
```

Y lo de la nube, en el recuadro de arriba.

## Errores frecuentes

| Si ves | Causa | Hacé |
|---|---|---|
| `port is already allocated` | Quedó un contenedor `model` u otro servicio en el 8081 | `docker ps` y `docker rm -f model` |
| `hey` se cuelga contra la VM | El firewall solo abre 8080 | Medí desde la VM o con un túnel SSH |
| `ImagePullBackOff` del modelo en k3s | No importaste la imagen o usaste `values.yaml` | `make k3d-images` y `-f values-k3s.yaml` |
| Pods evicted (`ephemeral-storage`) | Disco casi lleno | Ver la [clase 5](../clase-05.md#errores-frecuentes) |
