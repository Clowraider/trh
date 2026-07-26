CREATE EXTENSION IF NOT EXISTS vector;

CREATE SEQUENCE clusters_editoriales_id_seq
    INCREMENT 1
    MINVALUE 1
    MAXVALUE 9223372036854775807
    CACHE 1;

CREATE TABLE public.clusters_editoriales (
    id bigint DEFAULT nextval('clusters_editoriales_id_seq'::regclass) NOT NULL,
    titulo_representativo text,
    embedding_centroide vector(768),
    cantidad_noticias integer DEFAULT 0,
    cantidad_fuentes integer DEFAULT 0,
    primera_noticia timestamp without time zone,
    ultima_noticia timestamp without time zone,
    score double precision DEFAULT 0,
    tendencia double precision DEFAULT 0,
    estado character varying(30) DEFAULT 'nuevo',
    veces_publicado integer DEFAULT 0,
    ultima_publicacion timestamp without time zone,
    creado_en timestamp without time zone DEFAULT now(),
    actualizado_en timestamp without time zone DEFAULT now(),
    contenido_ia jsonb,
    estado_publicacion character varying(30) DEFAULT 'pendiente',
    foto_principal text,
    nota_editor text,
    url_wp text,
    fotos_secundarias jsonb DEFAULT '[]'::jsonb,
    nota_ia text,
    requiere_revision_editorial boolean DEFAULT false,
    CONSTRAINT clusters_editoriales_pkey PRIMARY KEY (id)
);

ALTER SEQUENCE clusters_editoriales_id_seq OWNED BY public.clusters_editoriales.id;

CREATE INDEX clusters_embedding_idx
    ON public.clusters_editoriales USING hnsw (embedding_centroide vector_cosine_ops);

CREATE INDEX idx_clusters_estado_pub
    ON public.clusters_editoriales USING btree (estado_publicacion);

CREATE TABLE public.editor_jefe_ia_recommendations (
    cluster_id bigint NOT NULL,
    title text NOT NULL,
    reason text NOT NULL,
    editorial_score double precision NOT NULL,
    technical_score double precision NOT NULL,
    news_count integer NOT NULL,
    source_count integer NOT NULL,
    newest_at timestamp with time zone NOT NULL,
    recommended_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT editor_jefe_ia_recommendations_pkey PRIMARY KEY (cluster_id),
    CONSTRAINT editor_jefe_ia_recommendations_cluster_id_fkey
        FOREIGN KEY (cluster_id) REFERENCES public.clusters_editoriales(id) ON DELETE CASCADE
);

CREATE INDEX idx_editor_jefe_ia_recommendations_recommended_at
    ON public.editor_jefe_ia_recommendations USING btree (recommended_at DESC);

CREATE SEQUENCE keywords_prioridad_id_seq
    INCREMENT 1
    MINVALUE 1
    MAXVALUE 9223372036854775807
    CACHE 1;

CREATE TABLE public.keywords_prioridad (
    id bigint DEFAULT nextval('keywords_prioridad_id_seq'::regclass) NOT NULL,
    keyword text NOT NULL,
    tipo character varying(30),
    puntos integer DEFAULT 0 NOT NULL,
    activo boolean DEFAULT true,
    creado_en timestamp without time zone DEFAULT now(),
    CONSTRAINT keywords_prioridad_pkey PRIMARY KEY (id)
);

ALTER SEQUENCE keywords_prioridad_id_seq OWNED BY public.keywords_prioridad.id;

CREATE INDEX idx_keywords_prioridad_keyword
    ON public.keywords_prioridad USING btree (keyword);

CREATE INDEX idx_keywords_prioridad_tipo
    ON public.keywords_prioridad USING btree (tipo);

CREATE INDEX idx_keywords_prioridad_activo
    ON public.keywords_prioridad USING btree (activo);

CREATE SEQUENCE noticias_historico_id_seq
    INCREMENT 1
    MINVALUE 1
    MAXVALUE 9223372036854775807
    CACHE 1;

CREATE TABLE public.noticias_historico (
    id integer DEFAULT nextval('noticias_historico_id_seq'::regclass) NOT NULL,
    noticia_hash character varying(64) NOT NULL,
    fuente character varying(100) NOT NULL,
    url_original text NOT NULL,
    titulo text NOT NULL,
    texto_completo text,
    url_imagen text,
    fecha_publicacion timestamp without time zone,
    fecha_extraccion timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    embedding vector(768),
    cluster_asignado_en timestamp without time zone,
    procesado boolean DEFAULT false,
    metadata jsonb,
    creado_en timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    publicado_en_cluster boolean DEFAULT false,
    score_individual double precision DEFAULT 0,
    relevancia_local double precision DEFAULT 0,
    duplicado boolean DEFAULT false,
    hash_contenido character varying(64),
    analizado_en timestamp without time zone,
    cluster_id bigint,
    CONSTRAINT noticias_historico_pkey PRIMARY KEY (id),
    CONSTRAINT noticias_historico_noticia_hash_key UNIQUE (noticia_hash),
    CONSTRAINT noticias_historico_url_original_key UNIQUE (url_original)
);

ALTER SEQUENCE noticias_historico_id_seq OWNED BY public.noticias_historico.id;

CREATE INDEX noticias_historico_url_original_idx
    ON public.noticias_historico USING btree (url_original);

CREATE INDEX noticias_historico_fuente_idx
    ON public.noticias_historico USING btree (fuente);

CREATE INDEX noticias_historico_fecha_extraccion_idx
    ON public.noticias_historico USING btree (fecha_extraccion);

CREATE INDEX noticias_historico_procesado_idx
    ON public.noticias_historico USING btree (procesado);

CREATE INDEX noticias_historico_embedding_idx
    ON public.noticias_historico USING hnsw (embedding vector_cosine_ops);

CREATE INDEX idx_hash_contenido
    ON public.noticias_historico USING btree (hash_contenido);

CREATE SEQUENCE noticias_keywords_id_seq
    INCREMENT 1
    MINVALUE 1
    MAXVALUE 9223372036854775807
    CACHE 1;

CREATE TABLE public.noticias_keywords (
    id bigint DEFAULT nextval('noticias_keywords_id_seq'::regclass) NOT NULL,
    noticia_id bigint NOT NULL,
    tipo character varying(30) NOT NULL,
    valor text NOT NULL,
    score double precision,
    creado_en timestamp without time zone DEFAULT now(),
    valor_normalizado text,
    CONSTRAINT noticias_keywords_pkey PRIMARY KEY (id),
    CONSTRAINT fk_noticia_keywords FOREIGN KEY (noticia_id)
        REFERENCES public.noticias_historico(id) ON DELETE CASCADE
);

ALTER SEQUENCE noticias_keywords_id_seq OWNED BY public.noticias_keywords.id;

CREATE INDEX idx_keywords_noticia
    ON public.noticias_keywords USING btree (noticia_id);

CREATE INDEX idx_keywords_tipo
    ON public.noticias_keywords USING btree (tipo);

CREATE INDEX idx_keywords_valor
    ON public.noticias_keywords USING btree (valor);

CREATE INDEX idx_keywords_valor_tipo
    ON public.noticias_keywords USING btree (valor, tipo);

CREATE UNIQUE INDEX uq_noticias_keywords_noticia_tipo_valor
    ON public.noticias_keywords USING btree (noticia_id, tipo, valor_normalizado);

CREATE SEQUENCE publicaciones_id_seq
    INCREMENT 1
    MINVALUE 1
    MAXVALUE 9223372036854775807
    CACHE 1;

CREATE TABLE public.publicaciones (
    id bigint DEFAULT nextval('publicaciones_id_seq'::regclass) NOT NULL,
    cluster_id bigint,
    wordpress_post_id bigint,
    tipo character varying(30),
    titulo text,
    score_publicado double precision,
    cantidad_noticias integer,
    publicada_en timestamp without time zone DEFAULT now(),
    url_wordpress text,
    CONSTRAINT publicaciones_pkey PRIMARY KEY (id)
);

ALTER SEQUENCE publicaciones_id_seq OWNED BY public.publicaciones.id;

CREATE SEQUENCE urls_id_seq
    INCREMENT 1
    MINVALUE 1
    MAXVALUE 2147483647
    CACHE 1;

CREATE TABLE public.urls (
    id integer DEFAULT nextval('urls_id_seq'::regclass) NOT NULL,
    url text NOT NULL,
    estado integer DEFAULT 0,
    fecha_creacion timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    fecha_procesado timestamp without time zone,
    fuente character varying(100),
    importancia text DEFAULT 'baja' NOT NULL,
    CONSTRAINT urls_pkey PRIMARY KEY (id),
    CONSTRAINT urls_url_key UNIQUE (url),
    CONSTRAINT urls_importancia_check
        CHECK (importancia = ANY (ARRAY['alta'::text, 'baja'::text]))
);

ALTER SEQUENCE urls_id_seq OWNED BY public.urls.id;

COMMENT ON TABLE public.urls IS 'URLs para crawler interno';

CREATE INDEX idx_estado
    ON public.urls USING btree (estado);

CREATE INDEX idx_url
    ON public.urls USING btree (url);

CREATE INDEX idx_urls_fuente_estado_importancia_id
    ON public.urls USING btree (fuente, estado, importancia, id);
