# pow/: nodo de ejemplo de una cadena PoW

Un nodo HTTP de una mini-blockchain Proof of Work, en Python (FastAPI). Corre
como **un solo nodo**: guarda la cadena en JSON en `/data` (`DATA_DIR`), mina
con dificultad fija y expone `/healthz`, `/metrics`, `/chain`, `/tx` y `/mine`
en el puerto 8090.

```bash
make test-pow                       # 8 passed, 2 skipped (las partes del TF)
make build-pow                      # imagen pow:local
docker run -d --name pow -p 8090:8090 -v pow-data:/data pow:local
until curl -sf localhost:8090/healthz; do sleep 1; done; echo
curl -s -X POST localhost:8090/tx -H 'Content-Type: application/json' -d '{"sender":"ana","to":"beto","amount":1}'; echo
curl -s -X POST localhost:8090/mine | head -c 200; echo
curl -s localhost:8090/metrics | grep '^pow_block_height'
docker rm -f pow
```

En Kubernetes lo despliega `helm/charts/pow` (StatefulSet, un PVC por nodo y
un Service headless).

## Qué trae esta línea base y qué falta

El Trabajo Final es **tu propia blockchain PoW con varios nodos, en
producción en la nube**. `pow/` y `helm/charts/pow` no son esa blockchain:
son la línea base de la que partís.

| Ya está (no lo tenés que escribir) | Es tu TF (marcado `TODO(TF)` en el código) |
|---|---|
| `Block`, hash sha256, bloque génesis | dificultad ajustable |
| cadena en JSON en `/data` (sobrevive al pod) | validar una cadena que llega de otro nodo |
| `POST /mine` con un loop de dificultad fija | peers: `GET /peers` y `POST /peers/sync` |
| `/healthz`, `/metrics` (`pow_block_height`), `/chain`, `/tx` en el puerto 8090 | consenso: la cadena más larga y válida gana |
| chart con StatefulSet, un PVC por nodo, Service headless y `PEERS` | reglas del mempool y seguridad ante concurrencia |

Los tests de `pow/tests/` que están en `skip` son la guía: cuando implementes
cada parte, sacales el `skip`. Con `replicaCount: 3` hoy tenés tres cadenas
**independientes**; que converjan es tu trabajo (al menos 2 nodos sincronizando).
