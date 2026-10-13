# Clase 7: la misma transacción en L1 y en L2 (Anvil, forge, Base Sepolia)

Complementa la [guía de la clase 7](../clase-07.md): ahí está el método
(quién opera qué, cómo medir y cómo costear). Los comandos se corren desde la
raíz del repo. Lo que se entrega es lo que pide el «Lab Clase 7 - Misma
transacción en Sepolia vs Base Sepolia» de tu aula.

El mismo contrato (`contracts/src/Counter.sol`), desplegado primero en Anvil
local y después en un rollup L2 de prueba (Base Sepolia).

## 0. Prerrequisitos

- [ ] `make doctor` sin `[FAIL]`, en la raíz del repo.
- [ ] Para testnet: una billetera de prueba (MetaMask) con ETH de Base Sepolia.
      Foundry no hace falta: corre en Docker.

## 1. Tests del contrato

```bash
make test-contracts        # usa la imagen de Foundry si no tenés forge
```

Esperado: `5 tests passed, 0 failed`.

## 2. Deploy en Anvil local

```bash
make compose-anvil-up
docker compose -f compose/docker-compose.anvil.yml logs anvil | sed -n '/Private Keys/,/Wallet/p' | head -4
```

Esas claves son **públicas y solo sirven en Anvil**. Usamos la (0):

```bash
export DEPLOYER_PRIVATE_KEY=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
cd contracts
forge script script/Deploy.s.sol --rpc-url http://localhost:8545 \
  --private-key "$DEPLOYER_PRIVATE_KEY" --broadcast
cd ..
```

Sin Foundry instalado, el mismo comando en Docker (Linux/WSL):

```bash
docker run --rm --network host -u "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/contracts:/w" -w /w \
  --entrypoint forge ghcr.io/foundry-rs/foundry:stable \
  script script/Deploy.s.sol --rpc-url http://localhost:8545 --private-key "$DEPLOYER_PRIVATE_KEY" --broadcast
```

Esperado: `Counter deployed at: 0x5FbDB2315678afecb367f032d93F642f64180aa3` y
`ONCHAIN EXECUTION COMPLETE & SUCCESSFUL.` (en un Anvil recién creado la
dirección es siempre esa).

## 3. Usalo

```bash
dc() { docker compose -f compose/docker-compose.anvil.yml "$@"; }
ADDR=0x5FbDB2315678afecb367f032d93F642f64180aa3
dc exec anvil cast send $ADDR "increment()" --private-key "$DEPLOYER_PRIVATE_KEY" --rpc-url http://localhost:8545
dc exec anvil cast call $ADDR "number()(uint256)" --rpc-url http://localhost:8545      # 1
dc exec anvil cast logs --address $ADDR --from-block 0 --rpc-url http://localhost:8545 # el evento NumberChanged
```

(`dc` es una función: funciona igual en bash y en zsh.)

`cast logs` es la idea de un *indexer*: leer los eventos del contrato en vez de
consultar su estado. Como el compose guarda la cadena (clase 3),
`make compose-anvil-down && make compose-anvil-up` y el `cast call` sigue dando 1.

> ### En la nube (testnet L2)
>
> | Red | chainId | RPC público |
> |---|---|---|
> | Base Sepolia (L2) | 84532 | `https://sepolia.base.org` |
> | Sepolia (L1) | 11155111 | `https://ethereum-sepolia-rpc.publicnode.com` |
>
> (`https://rpc.sepolia.org` ya no responde.) ETH de prueba: los faucets que
> lista `https://docs.base.org/tools/network-faucets`.
>
> Deploy manual, con **tu** clave de testnet (nunca una de mainnet, nunca en un archivo del repo):
>
> ```bash
> read -rs DEPLOYER_PRIVATE_KEY && export DEPLOYER_PRIVATE_KEY   # pegala y Enter; no se ve
> cd contracts
> forge script script/Deploy.s.sol --rpc-url https://sepolia.base.org \
>   --private-key "$DEPLOYER_PRIVATE_KEY" --broadcast
> ```
>
> Buscá la dirección en `https://sepolia.basescan.org` y compará gas y tiempo de
> confirmación con Sepolia. Por pipeline: el job `deploy-testnet` de
> `contracts.yml` hace lo mismo con un tag `vX.Y.Z` (ver
> [contracts/README.md](../../contracts/README.md): environment `testnet`, secret
> `BASE_SEPOLIA_DEPLOYER_KEY`, variable `BASE_SEPOLIA_RPC_URL`).
>
> Un rollup *optimistic* (Base) asume que los lotes son válidos y solo los
> disputa si alguien presenta una prueba de fraude dentro de una ventana de
> desafío; un rollup *ZK* prueba cada lote antes de aceptarlo. Comparalos en
> [L2Beat](https://l2beat.com).

## Limpieza

```bash
make compose-anvil-reset
rm -rf contracts/broadcast contracts/cache contracts/out
unset DEPLOYER_PRIVATE_KEY
```

## Errores frecuentes

| Si ves | Causa | Hacé |
|---|---|---|
| `Error: Failed to decode private key` | `$DEPLOYER_PRIVATE_KEY` vacía | `export DEPLOYER_PRIVATE_KEY=...` en la misma terminal |
| `Connection refused` en `forge script` | Anvil no está corriendo o el RPC es otro | `make compose-anvil-up`; `--rpc-url http://localhost:8545` |
| `contract ... does not have any code` | Anvil se reinició sin estado | Usá el compose del repo (persiste); redeployá |
| `insufficient funds` en testnet | La cuenta no tiene ETH de Base Sepolia | Faucet |
| `forge: command not found` | Foundry no instalado | `make test-contracts` o el comando con Docker de arriba |
| `port is already allocated` | Quedó un contenedor o el compose de otra clase en el 8545 o el 8080 | `docker ps` y `docker rm -f ...` / `make compose-down` |
| Pods evicted (`ephemeral-storage`) | Disco casi lleno | Ver la [clase 5](../clase-05.md#errores-frecuentes) |
| `rpc.sepolia.org` no responde | Ese RPC público dejó de funcionar | El de publicnode de la tabla |
