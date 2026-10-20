# Carga de IA del artefacto (Clase 1): Ollama + llama3.2:1b en CPU.
# Lab Clase 3, entregable 5.2. Los pesos NO van en la imagen: se bajan una vez
# al primer arranque a /models, que se monta como volumen (mismo patrón que /data).

# --- etapa 1: de la imagen oficial nos quedamos solo con lo que corre en CPU ---
FROM ollama/ollama:0.34.4 AS ollama
# La VM no tiene GPU: afuera CUDA, MLX y Vulkan (~4,7 GB de los 9,3 GB de la imagen).
RUN rm -rf /usr/lib/ollama/cuda_* /usr/lib/ollama/mlx_* /usr/lib/ollama/vulkan \
           /usr/lib/ollama/include

# --- etapa 2: runtime ---
# Misma distro que la imagen oficial (Ubuntu 24.04), con tag fechado y no móvil.
FROM ubuntu:noble-20260911

# ca-certificates: ollama pull descarga los pesos por HTTPS.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ollama /usr/bin/ollama /usr/bin/ollama
COPY --from=ollama /usr/lib/ollama /usr/lib/ollama
COPY entrypoint.sh /usr/local/bin/entrypoint.sh

# Usuario sin privilegios, dueño del directorio de pesos.
# (uid 1000 ya lo usa el usuario "ubuntu" de la imagen base.)
RUN useradd --create-home --uid 10001 ollama \
    && mkdir -p /models \
    && chown ollama /models \
    && chmod +x /usr/local/bin/entrypoint.sh
USER ollama

EXPOSE 11434
ENV OLLAMA_HOST=0.0.0.0:11434 \
    OLLAMA_MODELS=/models \
    MODEL=llama3.2:1b

# healthy recién cuando el modelo está bajado y el servidor lo puede servir.
HEALTHCHECK --interval=10s --timeout=5s --start-period=10m --retries=3 \
  CMD ["sh", "-c", "ollama show \"$MODEL\" > /dev/null"]

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
