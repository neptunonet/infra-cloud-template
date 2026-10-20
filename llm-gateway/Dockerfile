# Gateway HTTP delante de Ollama (Lab Clase 4, entregable 3.3).
# Sin pesos adentro: el modelo lo sirve el contenedor ollama:v1 (Clase 3),
# con los pesos en su volumen /models. Acá solo va el código del gateway.

# Mismas prácticas que app/Dockerfile.mejorado (Clase 3): tag fijo y no root.
FROM python:3.12.15-slim-trixie

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY serve.py .

RUN useradd --create-home --uid 1000 appuser && chown -R appuser /app
USER appuser

EXPOSE 8082
ENV PORT=8082 MODEL=llama3.2:1b OLLAMA_URL=http://localhost:11434

HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=10 \
  CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://localhost:%s/healthz' % os.environ.get('PORT', '8082'), timeout=2)"]

CMD ["python", "serve.py"]
