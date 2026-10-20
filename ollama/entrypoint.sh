#!/bin/sh
# Arranca el servidor y, solo si el modelo no está en el volumen, lo baja.
# Con el volumen ya poblado (segundo arranque en adelante) no descarga nada.
set -e

ollama serve &
pid=$!

until ollama list > /dev/null 2>&1; do sleep 1; done

if ollama show "$MODEL" > /dev/null 2>&1; then
  echo "modelo $MODEL ya está en $OLLAMA_MODELS: no se descarga"
else
  echo "modelo $MODEL no está en $OLLAMA_MODELS: descargando (una sola vez)"
  ollama pull "$MODEL"
fi

wait "$pid"
