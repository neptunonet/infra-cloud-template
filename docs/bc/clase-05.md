# Clase 5 · Ejercicio para tu área: Anvil como StatefulSet

Complementa la [guía de la clase 5](../clase-05.md). Hacé primero sus pasos 1 a
6 (cluster k3d, imágenes y servicio patrón); esto es el ejercicio para tu área. Los
comandos se corren desde la raíz del repo, con el cluster local activo.

```bash
helm upgrade --install anvil helm/charts/anvil -f helm/charts/anvil/values-k3s.yaml --wait
kubectl logs anvil-0 | sed -n '/Available Accounts/,/Wallet/p' | head -8   # cuentas y claves de prueba
KEY0=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
ACC1=0x70997970C51812dc3A010C7d01b50e0d17dc79C8
kubectl exec anvil-0 -- cast send --private-key $KEY0 --value 1ether $ACC1
kubectl exec anvil-0 -- cast block-number                  # 1
kubectl delete pod anvil-0 && kubectl wait --for=condition=Ready pod/anvil-0 --timeout=120s
kubectl exec anvil-0 -- cast block-number                  # sigue en 1
kubectl exec anvil-0 -- cast balance $ACC1 --ether         # 10001
```

`cast` viene en la imagen de Foundry, así que corre adentro del pod: no hace
falta instalar nada. El chart pone `fsGroup: 1000` (Anvil no corre como root) y
`--state-interval 5`: aunque el pod muera de golpe (OOM, nodo caído) se pierden
a lo sumo 5 segundos. Lo probamos con `kubectl delete pod anvil-0 --grace-period=0 --force`.

El nodo PoW (`helm/charts/pow`) es la **línea base** de tu TF: un StatefulSet
con un PVC por nodo y un Service headless, para que cada pod tenga un nombre
DNS estable (`pow-0.pow-headless`). Si querés mirarlo hoy:
`helm upgrade --install pow helm/charts/pow -f helm/charts/pow/values-k3s.yaml --wait`
y `kubectl get pods,pvc -l app=pow` (1 pod, 1 PVC). Con `--set replicaCount=3`
levantás 3 nodos, pero cada uno con **su propia** cadena: que se sincronicen es
el trabajo del TF.

> ### En la nube (GKE)
>
> Con `kubectl` apuntando al cluster como en la guía de la clase:
> `helm upgrade --install anvil helm/charts/anvil --wait` (la imagen es pública).
> En GKE el PVC queda en la StorageClass por defecto del cluster (`standard-rwo`).

## Limpieza

```bash
helm uninstall --ignore-not-found anvil pow
kubectl delete pvc -l app=anvil      # borra la cadena de Anvil
kubectl delete pvc -l app=pow        # borra la cadena del nodo PoW
```

## Errores frecuentes

| Si ves | Causa | Hacé |
|---|---|---|
| `cast block-number` vuelve a 0 después de borrar el pod | El PVC no quedó `Bound` o instalaste con los valores de GKE | `kubectl get pvc`; reinstalá con `-f helm/charts/anvil/values-k3s.yaml` |
| `UPGRADE FAILED: ... updates to statefulset spec ... are forbidden` al cambiar `replicaCount` de `pow` | `PEERS` (la lista de nodos) es parte del spec del StatefulSet | `helm uninstall pow`, `kubectl delete pvc -l app=pow` y reinstalá |
