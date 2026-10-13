# Clase 8 · La línea base PoW, de punta a punta

Complementa la [guía de la clase 8](../clase-08.md). Hacé primero sus pasos 1 y
2 (tests, imágenes y observabilidad en k3d); esto es lo propio de tu curso. Los
comandos se corren desde la raíz del repo, con el cluster local activo.

## 1. Desplegá la línea base (un nodo)

```bash
helm upgrade --install pow helm/charts/pow -f helm/charts/pow/values-k3s.yaml --wait
kubectl get pods,pvc -l app=pow             # pow-0 Running y su PVC data-pow-0 Bound
```

El chart de `pow` no trae HPA. La línea base es un solo nodo y escalar nodos
que no se sincronizan solo crea cadenas sueltas. Si tu red escala sola, y cómo,
es una decisión de diseño de tu TF.

## 2. Verificá

```bash
kubectl port-forward pod/pow-0 18090:8090    # otra terminal
curl -s localhost:18090/healthz; echo
curl -s -X POST localhost:18090/tx -H 'Content-Type: application/json' -d '{"sender":"ana","to":"beto","amount":1}'; echo
curl -s -X POST localhost:18090/mine | head -c 200; echo
curl -s localhost:18090/chain | python3 -c 'import json,sys; c=json.load(sys.stdin); print(len(c)-1, c[-1]["hash"])'
curl -s localhost:18090/metrics | grep '^pow_block_height'
```

Esperado: `/mine` devuelve el bloque 1 con un hash que empieza con `000`
(dificultad fija), `/chain` tiene altura 1 y `pow_block_height` vale 1. Borrá el
pod (`kubectl delete pod pow-0`): vuelve con la misma cadena, porque vive en el PVC.

En Grafana, `Mini PoW baseline` muestra la altura de cada nodo (los paneles de
tu red los agregás vos).

**De acá en adelante es tu TF.** Lo que falta está marcado `TODO(TF)` en
`pow/blockchain.py` y `pow/node.py`: dificultad ajustable, validar la cadena
que llega de otro nodo, peers (`GET /peers`, `POST /peers/sync`), consenso por
la cadena más larga y válida, reglas del mempool y seguridad ante concurrencia.
El chart ya te da lo de infraestructura: `--set replicaCount=3` levanta
`pow-0..2`, cada uno con su disco y su nombre DNS estable, y les pasa la lista
en la variable `PEERS`. Hoy son tres cadenas independientes; el mínimo del TF es
**al menos 2 nodos que sincronizan**, en la nube. Lo que ya trae la línea base y
lo que falta está en [pow/README.md](../../pow/README.md).

## 3. Carga

`loadtest/k6-script.js` no trae un escenario de `pow`: cuando tu red funcione,
sumá uno que ejercite tus endpoints (por ejemplo `POST /tx` y, cada tanto,
`POST /mine`) y corrélo con el Job de k6 de la guía de la clase.

## 4. Un cambio y un nuevo deploy

Hacé un cambio visible (un campo nuevo en la respuesta de `/mine`, o tu primer
`TODO(TF)`), corré `make test-pow`, reconstruí y actualizá:

```bash
make k3d-images TAG=v2
helm upgrade pow helm/charts/pow -f helm/charts/pow/values-k3s.yaml --set image.tag=v2 --wait
kubectl rollout status statefulset/pow
```

> ### En la nube (deploy.yml contra GKE)
>
> El paso "Una sola vez" es el de la guía de la clase. Al lanzar
> **Actions → deploy → Run workflow**, poné `charts` = `pow`. Después, con
> `kubectl` apuntando a GKE, repetí la verificación de arriba (sin
> `-f values-k3s.yaml`).

## Limpieza

```bash
helm uninstall --ignore-not-found pow
kubectl delete pvc -l app=pow        # borra la cadena
```

## Errores frecuentes

| Si ves | Causa | Hacé |
|---|---|---|
| `ErrImagePull` en k3s (busca `pow:v1` en Docker Hub) | Instalaste sin `-f values-k3s.yaml` | `helm uninstall pow`, `kubectl delete pvc -l app=pow`, reinstalá con `-f values-k3s.yaml` |
| `UPGRADE FAILED: ... updates to statefulset spec ... are forbidden` | Cambiaste la StorageClass o el tamaño del volumen (`volumeClaimTemplates` es inmutable) de un release existente; `replicaCount` sí se puede cambiar con `helm upgrade` | `helm uninstall pow`, `kubectl delete pvc -l app=pow` y reinstalá |
| `422` en `POST /tx` | Falta `-H 'Content-Type: application/json'` o el campo es `sender` (no `from`) | Copiá el curl de arriba |
| `404` en `/peers` o `/peers/sync` | La línea base no los trae | Es `TODO(TF)` en `pow/node.py` |
| Con 3 réplicas cada nodo tiene otra altura | Sin `/peers/sync` no hay consenso | Es el corazón del TF |
