# Clase 3 · Anvil + servicio patrón con compose

Complementa la [guía de la clase 3](../clase-03.md). Hacé primero sus pasos 1 a
3 (servicio patrón con Docker y con compose); esto agrega Anvil al mismo circuito.
Los comandos se corren desde la raíz del repo.

## Prerrequisitos

- [ ] Nada corriendo en 8080 ni en 8545 (`make doctor` lo chequea).

## 1. Construí las imágenes

```bash
make build-app build-pow
docker images --format '{{.Repository}}:{{.Tag}}  {{.Size}}' | grep ':local'
```

Esperado (aproximado): `app:local 256MB` y `pow:local 259MB`. Anvil no se
construye: es la imagen oficial de Foundry.

## 2. Anvil + servicio patrón con compose

```bash
make compose-anvil-up      # Anvil en :8545 y el servicio patrón en :8080
docker compose -f compose/docker-compose.anvil.yml logs anvil | sed -n '/Available Accounts/,/Wallet/p' | head -8
```

Ahí aparecen las cuentas de prueba y sus claves privadas. Son **públicas** (las
mismas en cualquier Anvil): sirven solo para esta red local.

Foundry no hace falta en tu máquina: `cast` corre adentro del contenedor.

```bash
dc() { docker compose -f compose/docker-compose.anvil.yml "$@"; }   # works in bash and zsh
KEY0=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80   # cuenta (0) de Anvil
ACC1=0x70997970C51812dc3A010C7d01b50e0d17dc79C8                           # cuenta (1)
dc exec anvil cast send --rpc-url http://localhost:8545 --private-key $KEY0 --value 1ether $ACC1
dc exec anvil cast block-number --rpc-url http://localhost:8545
dc exec anvil cast balance $ACC1 --ether --rpc-url http://localhost:8545
```

Esperado: bloque `1` y saldo `10001.000000000000000000`.

(`dc` es una función: funciona igual en bash y en zsh, el shell por defecto de
macOS. Una variable `DC="docker compose ..."` usada como `$DC exec` falla en
zsh con `no such file or directory`.)

Ahora la prueba de persistencia:

```bash
make compose-anvil-down    # down SIN -v
make compose-anvil-up
dc exec anvil cast block-number --rpc-url http://localhost:8545   # sigue en 1
dc exec anvil ls -la /state                                        # anvil-state.json
```

Cómo lo logra el compose (está comentado en el archivo):

- `anvil-state-init` le da el volumen al uid 1000 antes de arrancar Anvil. Sin
  eso Anvil no puede escribir y **no avisa**: la cadena vuelve a cero en cada
  reinicio.
- `--state-interval 5` guarda cada 5 segundos, así un `kill` pierde a lo sumo 5 s.
- `entrypoint: ["anvil"]` hace que Anvil reciba la señal de stop y guarde al salir.
- `FOUNDRY_TAG` (por defecto `stable`) fija la versión de Foundry.

> ### En la nube (Artifact Registry)
>
> Con `AR` exportado como en la guía de la clase:
>
> ```bash
> docker tag pow:local "$AR/pow:v1"
> docker push "$AR/pow:v1"
> gcloud artifacts docker images list "$AR"
> ```

## Limpieza

```bash
make compose-anvil-reset   # baja todo y BORRA la cadena
```

En GCP: `gcloud artifacts docker images delete "$AR/pow:v1"` cuando ya no la uses.

## Errores frecuentes

| Si ves | Causa | Hacé |
|---|---|---|
| El saldo de Anvil volvió a 10000 ETH / bloque 0 | El volumen de estado no era escribible (o borraste con `down -v`) | Usá el compose del repo tal cual; `ls -la /state` adentro del contenedor tiene que mostrar `anvil-state.json` |
| `cast: command not found` | Foundry no está en tu máquina | `dc exec anvil cast ...` (la función de arriba) |
| `no such file or directory: docker compose -f ...` | Usaste `$DC` en zsh | Definí la función `dc` de arriba |
| `port is already allocated` en 8545 u 8080 | Quedó otro compose o un contenedor de la clase 1 | `docker ps`; `make compose-down` o `docker rm -f <nombre>` |
