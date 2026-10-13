# Pipeline de contratos (contracts.yml)

Proyecto Foundry de ejemplo: el contrato `Counter` (`src/Counter.sol`), sus
tests (`test/Counter.t.sol`) y el script de deploy (`script/Deploy.s.sol`).
`.github/workflows/contracts.yml` lo prueba en cada cambio y lo despliega a
una testnet solo con un tag de release.

## En cada PR o push a `main` que toque `contracts/`

El workflow corre `forge fmt --check` (estilo) y después `forge test -vv`. Lo
mismo en tu laptop, desde la raíz del repo:

```bash
cd contracts && forge fmt --check && forge test -vv && cd ..
# o, sin Foundry instalado:
make test-contracts
```

Esperado: `5 tests passed`. Si `forge fmt --check` falla, corré `forge fmt`
en `contracts/` y commiteá.

## Deploy a testnet (Base Sepolia), solo con un tag `v*`

Un contrato desplegado no se puede volver atrás: por eso no hay deploy en cada
merge, y nunca a mainnet desde este pipeline. Antes del primer tag:

1. **Settings → Environments → New environment** `testnet`.
2. Adentro, *secret* `BASE_SEPOLIA_DEPLOYER_KEY`: la clave privada de una
   cuenta **solo de testnet** (con o sin `0x`, las dos sirven).
3. Adentro, *variable* `BASE_SEPOLIA_RPC_URL`: `https://sepolia.base.org`.
4. Cargale ETH de prueba a esa cuenta con un faucet (clase 7).

Después: `git tag v0.1.0 && git push origin v0.1.0` → job `deploy-testnet` →
artifact `contracts-v0.1.0` con el ABI, el bytecode y el registro del deploy.
Los *required reviewers* de un environment solo existen en repos públicos (o
planes pagos): en un repo privado gratis el deploy no espera aprobación.

## Errores frecuentes

| Si ves | Causa | Hacé |
|---|---|---|
| `forge fmt --check` falla | Estilo (indentación, espacios al final) | Corré `forge fmt` en `contracts/` y commiteá |
| `contracts` no corrió con mi push | No tocaste `contracts/` (filtro de paths) | Es lo esperado; con un tag corre siempre |
| `secret BASE_SEPOLIA_DEPLOYER_KEY is empty` | El secret no está en el environment `testnet` | Cargalo en Settings → Environments → testnet |
| `forge: command not found` | Foundry no está en tu máquina | `make test-contracts` (usa la imagen de Docker de Foundry) |
