#!/usr/bin/env bash
# Satura 1 réplica (4810 tramos, 10 usuarios, 60 s) y mide cuánto tardan / y /healthz desde adentro del pod.
set -euo pipefail
kubectl delete job k6-sondas --ignore-not-found --wait=true >/dev/null
cat <<YAML | kubectl apply -f - >/dev/null
apiVersion: batch/v1
kind: Job
metadata: {name: k6-sondas}
spec:
  backoffLimit: 0
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: k6
          image: grafana/k6:2.3.0
          args: ["run", "--quiet", "/scripts/lluvia.js"]
          env: [{name: FILAS, value: "4810"}, {name: VUS, value: "10"}, {name: DURACION, value: "60s"}]
          volumeMounts: [{name: s, mountPath: /scripts}]
      volumes: [{name: s, configMap: {name: k6-lluvia}}]
YAML
sleep 15
kubectl exec deploy/lluvia -- python -c '
import time, urllib.request, statistics as st
r = {"/": [], "/healthz": []}
for i in range(80):
    for p in r:
        t = time.perf_counter()
        try:
            urllib.request.urlopen("http://localhost:8083" + p, timeout=10).read()
            r[p].append((time.perf_counter() - t) * 1000)
        except Exception:
            r[p].append(10000.0)
    time.sleep(0.4)
for p, v in r.items():
    v.sort()
    print(p, "n=%d p50=%.0fms p95=%.0fms max=%.0fms >1s=%d" % (len(v), st.median(v), v[int(.95*len(v))-1], v[-1], sum(x > 1000 for x in v)))
'
kubectl wait --for=condition=complete job/k6-sondas --timeout=180s >/dev/null || true
kubectl logs job/k6-sondas | grep resultado_k6
kubectl get pod -l app=lluvia -o jsonpath='{range .items[*]}{.metadata.name} reinicios={.status.containerStatuses[0].restartCount}{"\n"}{end}'
