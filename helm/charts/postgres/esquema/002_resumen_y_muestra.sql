-- Resumen por pedido y detalle por muestra (ensayo de carga del 12/11: guardar cada tramo llevó la base a 4,6 GB con
-- 40 millones de filas en `predicciones`; en GKE el disco de 1 GiB no alcanzaba).
-- Cada pedido guarda siempre su resumen; el detalle tramo por tramo, solo uno de cada MUESTRA_TRAMOS pedidos.
-- Idempotente: corre solo con el volumen vacío (después de 001) y se puede correr a mano con psql sobre una base vieja.

-- {"fuente": {"modelo": n, ...}, "zona": {"verificada": n, ...}, "motivo": {...}, "degradados": n, "p_media": x,
--  "p_max": x, "sin_dato": n}. Sin coordenadas (decisión 20).
ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS resumen jsonb;

-- true si los tramos de este pedido están en `predicciones`.
ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS con_detalle boolean NOT NULL DEFAULT false;
