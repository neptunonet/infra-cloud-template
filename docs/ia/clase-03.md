# Clase 3 · El servidor de inferencia

Complementa la [guía de la clase 3](../clase-03.md). Hacé primero sus pasos 1 a
3 (servicio patrón con Docker y con compose); esto agrega el servidor de inferencia al mismo circuito.
Los comandos se corren desde la raíz del repo.

## Prerrequisitos

- [ ] Nada corriendo en 8080 ni en 8081 (`make doctor` lo chequea).

## 1. Construí las imágenes

```bash
make build-app build-model
docker images --format '{{.Repository}}:{{.Tag}}  {{.Size}}' | grep ':local'
```

Esperado (aproximado): `app:local 256MB` y `model:local 635MB`. El modelo pesa
más por scikit-learn, numpy y scipy, y se entrena **durante el build**
(`RUN python train.py` en `model/Dockerfile`), no en cada arranque.

## 2. Corré el servidor de inferencia

```bash
docker run -d --name model -p 8081:8081 model:local
until curl -sf localhost:8081/healthz; do sleep 1; done; echo
curl -s -X POST localhost:8081/predict -H 'Content-Type: application/json' \
  -d '{"features": [5.1, 3.5, 1.4, 0.2]}'; echo
curl -s localhost:8081/metrics | grep '^model_predictions_total'
docker rm -f model
```

Esperado: `{"class":"setosa","confidence":0.9...}` y `model_predictions_total 1.0`.
`/healthz` responde 503 mientras el modelo carga y 200 cuando ya está listo.
En `http://localhost:8081/docs` tenés la API interactiva.

Para tu propio modelo: los pesos van **adentro de la imagen** (como acá) o se
bajan de un bucket al arrancar a un disco montado; nunca en cada request.

Multi-stage casi no achica esta imagen (lo medimos: 623 MB contra 621 MB):
no hay compiladores que dejar afuera.

> ### En la nube (Artifact Registry)
>
> Con `AR` exportado como en la guía de la clase:
>
> ```bash
> docker tag model:local "$AR/model:v1"
> docker push "$AR/model:v1"
> gcloud artifacts docker images list "$AR"
> ```

## Limpieza

```bash
docker rm -f model 2>/dev/null
```

En GCP: `gcloud artifacts docker images delete "$AR/model:v1"` cuando ya no la uses.

## Errores frecuentes

| Si ves | Causa | Hacé |
|---|---|---|
| `/healthz` da 503 | El modelo todavía carga | Esperá con el `until curl -sf ...` de arriba |
| `422` en `/predict` | El JSON no tiene `features` (o falta el header `Content-Type`) | `-d '{"features": [5.1, 3.5, 1.4, 0.2]}'` con `-H 'Content-Type: application/json'` |
| `400 expected 4 features` | Mandaste otra cantidad de números | Son 4: largo y ancho de sépalo y de pétalo |
| `port is already allocated` en 8081 | Quedó un contenedor `model` de antes | `docker rm -f model` |
