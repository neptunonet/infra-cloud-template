# Minimal, student-readable image for the servicio patron.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# /data is where the persistent disk / PVC gets mounted in every class.
# No VOLUME instruction on purpose: it would leave an anonymous volume
# behind every `docker run` without -v. Mount /data explicitly instead.
RUN mkdir -p /data

EXPOSE 8080
ENV DATA_DIR=/data PORT=8080

# `docker ps` shows (healthy) once /healthz answers. Kubernetes ignores this
# and uses the chart's probes instead.
HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=10 \
  CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://localhost:%s/healthz' % os.environ.get('PORT', '8080'), timeout=2)"]

CMD ["python", "main.py"]
