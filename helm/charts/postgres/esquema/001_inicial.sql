-- Esquema de la base del servicio de lluvia (Trabajo Final, consigna 2.4).
-- Idempotente: lo corre Postgres al crear el volumen (docker-entrypoint-initdb.d) y se puede volver a correr con psql.
-- Sin coordenadas ni datos de dispositivos (decisión 20): de cada tramo solo se guarda lo que sirve para medir el
-- servicio. El uso de CPU y memoria por pod lo mide Prometheus; `pedidos.pod` permite cruzarlo.

-- Un registro por llamada a POST /predict.
CREATE TABLE IF NOT EXISTS pedidos (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    recibido_utc  timestamptz NOT NULL,
    consumidor    text,                 -- nombre de la clave (CLAVES), no la clave
    filas         integer     NOT NULL, -- tramos del lote
    version       text,                 -- versión servida (NULL = todavía no hay modelo)
    receta        text        NOT NULL, -- logistica_rayos, tabla_app, ...
    latencia_ms   real        NOT NULL, -- tiempo dentro de la API
    resultado     text        NOT NULL, -- ok, clave_invalida, ...
    pod           text                  -- réplica que atendió (para cruzar con Prometheus)
);
CREATE INDEX IF NOT EXISTS pedidos_recibido_idx ON pedidos (recibido_utc);

-- Una fila por tramo de cada pedido: el resultado de la inferencia.
CREATE TABLE IF NOT EXISTS predicciones (
    pedido_id       bigint   NOT NULL REFERENCES pedidos (id) ON DELETE CASCADE,
    idx             integer  NOT NULL, -- posición del tramo en el lote
    p               real,              -- probabilidad (NULL = sin dato)
    fuente          text     NOT NULL, -- modelo, tabla_app, sin_dato
    zona            text     NOT NULL, -- verificada, region_entrenada, no_vista
    degradado       boolean  NOT NULL,
    motivo          text,
    votos           smallint NOT NULL,
    anticipacion_h  real     NOT NULL, -- horas entre la emisión y el paso por el tramo
    PRIMARY KEY (pedido_id, idx)
);

-- Una fila por versión entrenada (lo carga el Job desde los metadata.json del bucket).
CREATE TABLE IF NOT EXISTS versiones (
    version            text PRIMARY KEY,  -- vAAAAMMDD_HHMMSS
    creada_utc         timestamptz NOT NULL,
    receta             text,              -- receta entrenada en esta versión
    receta_elegida     text NOT NULL,     -- lo que decidió train.py (puede ser tabla_app)
    promovida          boolean NOT NULL,
    motivo             text,
    git_sha            text,
    t_evaluacion_s     real,
    t_entrenamiento_s  real,
    datos_desde        date,
    datos_hasta        date,
    casos              integer,
    casos_con_lluvia   integer,
    metadata           jsonb NOT NULL,    -- el metadata.json completo
    cargada_utc        timestamptz NOT NULL DEFAULT now()
);

-- Una fila por receta evaluada en cada versión (evaluación día por día de train.py).
CREATE TABLE IF NOT EXISTS evaluaciones (
    version          text NOT NULL REFERENCES versiones (version) ON DELETE CASCADE,
    receta           text NOT NULL,
    brier            real NOT NULL,
    brier_ic90_bajo  real,
    brier_ic90_alto  real,
    ece              real,
    sensibilidades   jsonb,               -- POD, FAR y CSI con 0,10 / 0,20 / 0,40
    PRIMARY KEY (version, receta)
);
