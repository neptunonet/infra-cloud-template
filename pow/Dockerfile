FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY blockchain.py node.py .

RUN mkdir -p /data

EXPOSE 8090
ENV DATA_DIR=/data PORT=8090 PEERS=""

# `docker ps` shows (healthy) once /healthz answers. Kubernetes ignores this
# and uses the chart's probes instead.
HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=10 \
  CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://localhost:%s/healthz' % os.environ.get('PORT', '8090'), timeout=2)"]

CMD ["python", "node.py"]
