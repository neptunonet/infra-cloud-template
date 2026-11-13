# Limpieza del registry (Trabajo Final)

El CI publica una imagen por push (`:<sha>`), así que el repositorio `infra-cloud-template` de Artifact Registry
crece solo: el 13/11/2026 pesaba 8 GB con ~200 versiones. `limpieza.json` es la regla que lo mantiene chico.

| Regla | Acción | Qué cubre |
|---|---|---|
| `conservar-versiones` | Keep | toda etiqueta que empiece con `v` (`app:v1`, `model:v1.1`, `ollama:v1`, `lluvia:v0.1.0`, ...) |
| `conservar-recientes` | Keep | las 10 versiones más recientes de cada imagen |
| `borrar-viejas` | Delete | lo demás con más de 30 días |

- Si una versión cumple una regla Keep y una Delete, se conserva.
- Las capas de una imagen multi-arch (manifiestos hijos sin etiqueta) no se borran mientras exista el índice.
- La regla corre en segundo plano, más o menos una vez por día.
- 30 días y no menos: `gcloud artifacts docker tags add` (lo usa `ci.yml` para no reconstruir) no cambia la fecha de
  creación de la versión, que es la del build original.

**Todo lo que se use fuera del CI va con una etiqueta `v`.** El VPS de Clima Rutero usa `lluvia:v0.1.0` (el mismo
digest que `lluvia:8682c28…`). Para pasarlo a otra imagen:

```bash
gcloud artifacts docker tags add <registry>/lluvia:<sha> <registry>/lluvia:v0.x.0
# y en el .env del VPS: LLUVIA_IMAGEN=<registry>/lluvia:v0.x.0
```

Aplicar o cambiar la regla:

```bash
gcloud artifacts repositories set-cleanup-policies infra-cloud-template \
  --project=unlu-ia-armas --location=us-central1 --policy=registry/limpieza.json --no-dry-run
```
