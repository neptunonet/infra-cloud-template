# Servicio de probabilidad de lluvia (Trabajo Final). Una sola imagen para los dos usos:
#   - API (por defecto):          python serve.py      -> Deployment
#   - entrenamiento diario:       python train.py      -> Job / CronJob
# Multi-arch (amd64 para GKE, arm64 para el VPS): todas las dependencias tienen rueda para las dos.
# El modelo NO va adentro: lo lee de DESTINO (carpeta o gs://), donde lo deja train.py.

# Mismas prácticas que llm-gateway/: tag fijo y usuario sin privilegios.
FROM python:3.12.15-slim-trixie

# LightGBM necesita la biblioteca de OpenMP, que la imagen slim no trae.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY variables.py recetas.py evaluacion.py train.py serve.py exportar.py estaciones.csv ./

RUN useradd --create-home --uid 1000 appuser && chown -R appuser /app
USER appuser

# Commit del código, para el metadata.json de cada entrenamiento (lo pasa el CI al publicar).
ARG GIT_SHA=desconocido
ENV GIT_SHA=$GIT_SHA

EXPOSE 8083
ENV PORT=8083 PYTHONUNBUFFERED=1

HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=10 \
  CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://localhost:%s/healthz' % os.environ.get('PORT', '8083'), timeout=2)"]

CMD ["python", "serve.py"]
