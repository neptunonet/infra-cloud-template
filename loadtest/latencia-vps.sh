#!/usr/bin/env bash
# H12 del Trabajo Final: latencia de la API en GKE vista desde el VPS de Clima Rutero (el consumidor real).
# Corre EN EL VPS, con el Service `lluvia-externo` prendido (chart: externo.habilitado, IP del VPS permitida, clave).
#
# Uso (en el VPS, con lluvia.js y ejemplo-predict.json en la misma carpeta):
#   URL=http://<IP del balanceador> CLAVE_ARCHIVO=~/.config/clima-rutero/lluvia-clave ./latencia-vps.sh > h12.txt
#
# Mide:
#   1. curl × 30 a /healthz y a /predict (3 tramos): conexión TCP (≈ ida y vuelta de red), primer byte y total;
#   2. k6 (imagen oficial, arm64) con lotes de 156 tramos: 1 usuario y 5 usuarios, 60 s cada uno.
# La clave se lee de un archivo y no aparece en la línea de comandos ni en la salida.
set -euo pipefail

URL="${URL:?falta URL=http://<ip>}"
CLAVE="$(cat "${CLAVE_ARCHIVO:?falta CLAVE_ARCHIVO}")"
export CLAVE  # docker la toma del entorno (-e CLAVE sin valor): no queda en la lista de procesos
ENCABEZADO="$(mktemp)"; chmod 600 "$ENCABEZADO"; trap 'rm -f "$ENCABEZADO"' EXIT
printf 'X-API-Key: %s\n' "$CLAVE" > "$ENCABEZADO"   # curl -H @archivo: tampoco va en la línea de comandos
AQUI="$(cd "$(dirname "$0")" && pwd)"
N="${N:-30}"

medir() {  # $1 = nombre, resto = argumentos de curl
  local nombre="$1"; shift
  for _ in $(seq "$N"); do
    curl -s -o /dev/null -w '%{time_connect} %{time_starttransfer} %{time_total} %{http_code}\n' "$@"
    sleep 0.5
  done | python3 -c '
import sys, statistics as st
filas = [l.split() for l in sys.stdin if l.strip()]
codigos = sorted({f[3] for f in filas})
def p(v, q): v = sorted(v); return v[min(len(v) - 1, int(q * len(v)))]
for i, nombre in ((0, "conexion"), (1, "primer_byte"), (2, "total")):
    v = [float(f[i]) * 1000 for f in filas]
    print(f"'"$nombre"' {nombre}: p50 {st.median(v):.1f} ms · p95 {p(v, .95):.1f} ms · min {min(v):.1f} ms")
print(f"'"$nombre"' codigos HTTP: {codigos} (n={len(filas)})")
'
}

echo "# H12 — $(date -u +%FT%TZ) — desde $(hostname)"
medir healthz "$URL/healthz"
medir predict_3 -X POST "$URL/predict" -H 'Content-Type: application/json' -H @"$ENCABEZADO" \
  --data @"$AQUI/ejemplo-predict.json"
echo "# sin clave (tiene que dar 401):"
curl -s -o /dev/null -w '%{http_code}\n' -X POST "$URL/predict" -H 'Content-Type: application/json' \
  --data @"$AQUI/ejemplo-predict.json"

for vus in 1 5; do
  echo "# k6: 156 tramos, $vus usuario(s), 60 s"
  docker run --rm -i -v "$AQUI:/scripts:ro" -e URL="$URL" -e CLAVE -e FILAS=156 -e VUS="$vus" \
    -e DURACION=60s grafana/k6:2.3.0 run --quiet /scripts/lluvia.js | grep '"resultado_k6"'
done
