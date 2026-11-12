#!/usr/bin/env bash
# Grilla de pruebas de la API lluvia (Trabajo Final, consigna 4): réplicas × pedidos simultáneos × tamaño de lote.
# Para cada combinación fija las réplicas (HPA apagado), corre loadtest/lluvia.js como Job dentro del clúster y agrega
# una fila al CSV con lo que mide k6, la CPU y memoria de los pods de la API (kubectl top, cerca del final) y cuántos
# pedidos quedaron registrados en Postgres. Al terminar vuelve a prender el HPA.
#
# Uso (desde la raíz del repo, con kubectl apuntando al clúster):
#   loadtest/lluvia-grilla.sh resultados.csv
# Variables opcionales (con sus valores por defecto):
#   REPLICAS="1 3 5"  VUS="1 2 5 10"  FILAS="156 4810"  DURACION=60s  PAUSA=15  RELEASE=lluvia  CLAVE=
set -euo pipefail

SALIDA="${1:?uso: $0 salida.csv}"
REPLICAS="${REPLICAS:-1 3 5}"
VUS="${VUS:-1 2 5 10}"
FILAS="${FILAS:-156 4810}"
DURACION="${DURACION:-60s}"
PAUSA="${PAUSA:-15}"          # segundos de descanso entre corridas (que la CPU baje)
RELEASE="${RELEASE:-lluvia}"
CHART="$(dirname "$0")/../helm/charts/lluvia"
SCRIPT="$(dirname "$0")/lluvia.js"
dur_s=${DURACION%s}

kubectl create configmap k6-lluvia --from-file=lluvia.js="$SCRIPT" --dry-run=client -o yaml | kubectl apply -f - >/dev/null
nodos="$(kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.labels.node\.kubernetes\.io/instance-type}{" "}{end}' | xargs)"
nodos="${nodos:-$(kubectl get nodes --no-headers | wc -l) nodos sin tipo}"  # k3d no tiene la etiqueta de tipo de máquina
[ -f "$SALIDA" ] || echo "fecha_utc,nodos,replicas,filas,vus,duracion_s,pedidos,pedidos_s,tramos_s,ms_prom,ms_p50,ms_p90,ms_p95,ms_p99,ms_max,errores_pct,checks_ok_pct,api_ms_prom,registrados,cpu_api_m,mem_api_mi,reinicios" > "$SALIDA"

restaurar() { helm upgrade "$RELEASE" "$CHART" --reuse-values --set autoscaling.enabled=true --wait >/dev/null && echo "HPA prendido de nuevo"; }
trap restaurar EXIT

for r in $REPLICAS; do
  echo "== $r réplica(s)"
  helm upgrade "$RELEASE" "$CHART" --reuse-values --set autoscaling.enabled=false --set replicaCount="$r" --wait >/dev/null
  kubectl rollout status deploy/"$RELEASE" --timeout=180s >/dev/null
  sleep "$PAUSA"
  for f in $FILAS; do
    for v in $VUS; do
      kubectl delete job k6-lluvia --ignore-not-found --wait=true >/dev/null
      desde="$(date -u +%FT%T.%3NZ)"
      reinicios0="$(kubectl get pods -l app="$RELEASE" -o jsonpath='{range .items[*]}{.status.containerStatuses[0].restartCount}{"+"}{end}')0"
      cat <<EOF | kubectl apply -f - >/dev/null
apiVersion: batch/v1
kind: Job
metadata: {name: k6-lluvia, labels: {app: k6-lluvia}}
spec:
  backoffLimit: 0
  template:
    metadata: {labels: {app: k6-lluvia}}
    spec:
      restartPolicy: Never
      containers:
        - name: k6
          image: grafana/k6:2.3.0
          args: ["run", "--quiet", "/scripts/lluvia.js"]
          env:
            - {name: URL, value: "http://$RELEASE:8083"}
            - {name: FILAS, value: "$f"}
            - {name: VUS, value: "$v"}
            - {name: DURACION, value: "$DURACION"}
            - {name: CLAVE, value: "${CLAVE:-}"}
          resources: {requests: {cpu: 500m, memory: 256Mi}}
          volumeMounts: [{name: s, mountPath: /scripts}]
      volumes: [{name: s, configMap: {name: k6-lluvia}}]
EOF
      # CPU y memoria de la API cerca del final de la corrida (ventana de ~15 s de metrics-server).
      sleep $((dur_s - 10 > 5 ? dur_s - 10 : 5))
      top="$(kubectl top pods -l app="$RELEASE" --no-headers 2>/dev/null | awk '{gsub("m","",$2); gsub("Mi","",$3); c+=$2; m+=$3} END {print c+0","m+0}')"
      kubectl wait --for=condition=complete job/k6-lluvia --timeout=$((dur_s + 300))s >/dev/null || true
      linea="$(kubectl logs job/k6-lluvia | grep '"resultado_k6"' | tail -1)"
      hasta="$(date -u +%FT%T.%3NZ)"
      reinicios1="$(kubectl get pods -l app="$RELEASE" -o jsonpath='{range .items[*]}{.status.containerStatuses[0].restartCount}{"+"}{end}')0"
      sleep 3  # que el registro termine de escribir el último lote
      bd="$(kubectl exec postgres-0 -- psql -U lluvia -d lluvia -tAF, -c \
        "SELECT round(avg(latencia_ms)::numeric,1), count(*) FROM pedidos WHERE recibido_utc BETWEEN '$desde' AND '$hasta'" 2>/dev/null || echo ",")"
      if [ -z "$linea" ]; then echo "  !! sin resultado de k6 (filas=$f vus=$v)"; continue; fi
      fila="$(python3 -c '
import json, sys
d = json.loads(sys.argv[1])
cols = ["pedidos","pedidos_s","tramos_s","ms_prom","ms_p50","ms_p90","ms_p95","ms_p99","ms_max","errores","checks_ok"]
print(",".join(str(d[c]) for c in cols))' "$linea")"
      echo "$hasta,$nodos,$r,$f,$v,$dur_s,$fila,$bd,$top,$(( $(echo "$reinicios1") - $(echo "$reinicios0") ))" >> "$SALIDA"
      echo "  filas=$f vus=$v -> $(echo "$fila" | cut -d, -f2,5,7,10) (pedidos/s, ms_p50, ms_p95, errores %)"
      sleep "$PAUSA"
    done
  done
done
kubectl delete job k6-lluvia --ignore-not-found >/dev/null
