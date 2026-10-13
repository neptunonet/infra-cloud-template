# Clase 7: del artefacto local a la nube, medido

## Objetivo

Llevás un artefacto que ya corre en tu laptop a la nube y lo medís con el
mismo método en los dos lados. Lo que se entrega es lo que pide el lab de tu
aula; esta guía te da el método y te deja lo del repo funcionando para hacerlo.

Al terminar tenés:

1. Para cada opción que compares, quién opera qué (vos o el proveedor).
2. Una medición reproducible: latencia en frío, p95 y requests/s, con el mismo
   comando contra tu laptop y contra la nube.
3. Un costo estimado por hora y por mes de cada opción.
4. Lo mismo con la carga de ejemplo de tu área, en su guía específica:
   [docs/bc/clase-07.md](bc/clase-07.md) o [docs/ia/clase-07.md](ia/clase-07.md)
   (seguí la que te indica tu aula).

## Prerrequisitos

- [ ] `make doctor` sin `[FAIL]`, en la raíz del repo.
- [ ] Docker corriendo (las herramientas de medición corren en contenedores).

## Pasos

### 1. Quién opera qué

Antes de medir, anotá para cada opción qué parte operás vos:

| Capa | En tu laptop | En una VM (Compute Engine) | En un servicio administrado |
|---|---|---|---|
| Hardware y red | vos | el proveedor | el proveedor |
| Sistema operativo y parches | vos | vos | el proveedor |
| Runtime (Docker, versiones) | vos | vos | el proveedor |
| Escalado y disponibilidad | vos | vos | el proveedor (según el plan) |
| Tu código y tus datos | vos | vos | vos |

Cada fila que pasa al proveedor te ahorra trabajo y te quita control. Eso es
lo que vas a poner en la balanza junto con la latencia y el costo.

### 2. Medí con el mismo comando en los dos lados

Con el servicio patrón como ejemplo (`make compose-up`, puerto 8080):

```bash
make compose-up
URL=http://localhost:8080
curl -s -o /dev/null -w '%{time_total}\n' "$URL/"      # primera request
curl -s -o /dev/null -w '%{time_total}\n' "$URL/"      # ya en caliente
```

`hey` genera carga y te da la distribución de latencias. Sin instalarlo:

```bash
docker run --rm --network host williamyeh/hey -n 2000 -c 20 "$URL/"
```

(`--network host` funciona en Linux y WSL; en macOS usá
`http://host.docker.internal:8080/` sin `--network host`.)

Anotá `Requests/sec` y la línea `95% in ...`: esa es tu p95. Para la nube,
cambiá solo `URL` y repetí los mismos comandos. Si la primera request contra
la nube tarda mucho más que las siguientes, eso es el arranque en frío: anotalo
aparte, no lo promedies con el resto.

### 3. Costeá

Para cada opción, con la [calculadora de precios de Google
Cloud](https://cloud.google.com/products/calculator) o la página de precios del
proveedor:

- **Por hora**: lo que cuesta la máquina o el servicio encendido.
- **Por mes**: por hora × las horas que de verdad va a estar prendido (730 si
  es 24/7), más el disco y el tráfico de salida.
- **Por request**, si el servicio cobra así: precio × las requests/s que
  mediste × los segundos del mes.

Una opción más rápida pero diez veces más cara no siempre gana: escribí qué
elegirías y por qué, con los números de los pasos 2 y 3.

> ### En la nube
>
> Lo que se despliega en la nube (y cómo) depende de la carga: está en la
> guía específica del punto 4 del objetivo. Todo lo que levantes ahí se cobra
> por hora mientras esté prendido: apagalo o borralo apenas termines de medir.

## Limpieza

```bash
make compose-down
```

Y lo de la nube, siguiendo la limpieza de tu guía específica.

## Errores frecuentes

| Si ves | Causa | Hacé |
|---|---|---|
| `port is already allocated` | Quedó un contenedor en el 8080 | `docker ps` y `docker rm -f <nombre>` o `make compose-down` |
| `hey` se cuelga contra una VM | El firewall no abre ese puerto | Medí desde la VM contra `localhost` o con un túnel SSH (`gcloud compute ssh <vm> -- -L 8080:localhost:8080`) |
| `connection refused` con `--network host` en macOS | Docker Desktop no soporta `--network host` igual que Linux | Usá `host.docker.internal` sin `--network host` |
| Latencias muy dispares entre corridas | Otra carga en tu máquina o la red | Repetí 3 veces y anotá la mediana |
