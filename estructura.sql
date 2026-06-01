-- Adminer 5.2.1 PostgreSQL 18.3 dump

\connect "trh";

CREATE SEQUENCE clusters_editoriales_id_seq INCREMENT 1 MINVALUE 1 MAXVALUE 9223372036854775807 CACHE 1;

CREATE TABLE "public"."clusters_editoriales" (
    "id" bigint DEFAULT nextval('clusters_editoriales_id_seq') NOT NULL,
    "titulo_representativo" text,
    "embedding_centroide" vector(768),
    "cantidad_noticias" integer DEFAULT '0',
    "cantidad_fuentes" integer DEFAULT '0',
    "primera_noticia" timestamp,
    "ultima_noticia" timestamp,
    "score" double precision DEFAULT '0',
    "tendencia" double precision DEFAULT '0',
    "estado" character varying(30) DEFAULT 'nuevo',
    "veces_publicado" integer DEFAULT '0',
    "ultima_publicacion" timestamp,
    "creado_en" timestamp DEFAULT now(),
    "actualizado_en" timestamp DEFAULT now(),
    "contenido_ia" jsonb,
    "estado_publicacion" character varying(30) DEFAULT 'pendiente',
    "foto_principal" text,
    "fotos_secundarias" jsonb DEFAULT '[]'::jsonb,
    "nota_ia" text,
    "nota_editor" text,
    "url_wp" text,
    CONSTRAINT "clusters_editoriales_pkey" PRIMARY KEY ("id")
) WITH (oids = false);

CREATE INDEX clusters_embedding_idx ON public.clusters_editoriales USING hnsw (embedding_centroide vector_cosine_ops);

CREATE INDEX idx_clusters_estado_pub ON public.clusters_editoriales USING btree (estado_publicacion);


CREATE SEQUENCE keywords_prioridad_id_seq INCREMENT 1 MINVALUE 1 MAXVALUE 9223372036854775807 CACHE 1;

CREATE TABLE "public"."keywords_prioridad" (
    "id" bigint DEFAULT nextval('keywords_prioridad_id_seq') NOT NULL,
    "keyword" text NOT NULL,
    "tipo" character varying(30),
    "puntos" integer DEFAULT '0' NOT NULL,
    "activo" boolean DEFAULT true,
    "creado_en" timestamp DEFAULT now(),
    CONSTRAINT "keywords_prioridad_pkey" PRIMARY KEY ("id")
) WITH (oids = false);

CREATE INDEX idx_keywords_prioridad_keyword ON public.keywords_prioridad USING btree (keyword);

CREATE INDEX idx_keywords_prioridad_tipo ON public.keywords_prioridad USING btree (tipo);

CREATE INDEX idx_keywords_prioridad_activo ON public.keywords_prioridad USING btree (activo);


CREATE SEQUENCE noticias_historico_id_seq INCREMENT 1 MINVALUE 1 MAXVALUE 9223372036854775807 CACHE 1;

CREATE TABLE "public"."noticias_historico" (
    "id" integer DEFAULT nextval('noticias_historico_id_seq') NOT NULL,
    "noticia_hash" character varying(64) NOT NULL,
    "fuente" character varying(100) NOT NULL,
    "url_original" text NOT NULL,
    "titulo" text NOT NULL,
    "texto_completo" text,
    "url_imagen" text,
    "fecha_publicacion" timestamp,
    "fecha_extraccion" timestamp DEFAULT CURRENT_TIMESTAMP,
    "embedding" vector(768),
    "cluster_asignado_en" timestamp,
    "procesado" boolean DEFAULT false,
    "metadata" jsonb,
    "creado_en" timestamp DEFAULT CURRENT_TIMESTAMP,
    "publicado_en_cluster" boolean DEFAULT false,
    "score_individual" double precision DEFAULT '0',
    "relevancia_local" double precision DEFAULT '0',
    "duplicado" boolean DEFAULT false,
    "hash_contenido" character varying(64),
    "analizado_en" timestamp,
    "cluster_id" bigint,
    CONSTRAINT "noticias_historico_pkey" PRIMARY KEY ("id")
) WITH (oids = false);

CREATE UNIQUE INDEX noticias_historico_noticia_hash_key ON public.noticias_historico USING btree (noticia_hash);

CREATE UNIQUE INDEX noticias_historico_url_original_key ON public.noticias_historico USING btree (url_original);

CREATE INDEX noticias_historico_url_original_idx ON public.noticias_historico USING btree (url_original);

CREATE INDEX noticias_historico_fuente_idx ON public.noticias_historico USING btree (fuente);

CREATE INDEX noticias_historico_fecha_extraccion_idx ON public.noticias_historico USING btree (fecha_extraccion);

CREATE INDEX noticias_historico_procesado_idx ON public.noticias_historico USING btree (procesado);

CREATE INDEX noticias_historico_embedding_idx ON public.noticias_historico USING hnsw (embedding vector_cosine_ops);

CREATE INDEX idx_hash_contenido ON public.noticias_historico USING btree (hash_contenido);


CREATE SEQUENCE noticias_keywords_id_seq INCREMENT 1 MINVALUE 1 MAXVALUE 9223372036854775807 CACHE 1;

CREATE TABLE "public"."noticias_keywords" (
    "id" bigint DEFAULT nextval('noticias_keywords_id_seq') NOT NULL,
    "noticia_id" bigint NOT NULL,
    "tipo" character varying(30) NOT NULL,
    "valor" text NOT NULL,
    "score" double precision,
    "creado_en" timestamp DEFAULT now(),
    "valor_normalizado" text,
    CONSTRAINT "noticias_keywords_pkey" PRIMARY KEY ("id")
) WITH (oids = false);

CREATE INDEX idx_keywords_noticia ON public.noticias_keywords USING btree (noticia_id);

CREATE INDEX idx_keywords_tipo ON public.noticias_keywords USING btree (tipo);

CREATE INDEX idx_keywords_valor ON public.noticias_keywords USING btree (valor);

CREATE INDEX idx_keywords_valor_tipo ON public.noticias_keywords USING btree (valor, tipo);

CREATE UNIQUE INDEX uq_noticias_keywords_noticia_tipo_valor ON public.noticias_keywords USING btree (noticia_id, tipo, valor_normalizado);


CREATE SEQUENCE publicaciones_id_seq INCREMENT 1 MINVALUE 1 MAXVALUE 9223372036854775807 CACHE 1;

CREATE TABLE "public"."publicaciones" (
    "id" bigint DEFAULT nextval('publicaciones_id_seq') NOT NULL,
    "cluster_id" bigint,
    "wordpress_post_id" bigint,
    "tipo" character varying(30),
    "titulo" text,
    "score_publicado" double precision,
    "cantidad_noticias" integer,
    "publicada_en" timestamp DEFAULT now(),
    "url_wordpress" text,
    CONSTRAINT "publicaciones_pkey" PRIMARY KEY ("id")
) WITH (oids = false);


CREATE SEQUENCE urls_id_seq INCREMENT 1 MINVALUE 1 MAXVALUE 2147483647 CACHE 1;

CREATE TABLE "public"."urls" (
    "id" integer DEFAULT nextval('urls_id_seq') NOT NULL,
    "url" text NOT NULL,
    "estado" integer DEFAULT '0',
    "fecha_creacion" timestamp DEFAULT CURRENT_TIMESTAMP,
    "fecha_procesado" timestamp,
    "fuente" character varying(100),
    "importancia" text DEFAULT 'baja' NOT NULL,
    CONSTRAINT "urls_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "urls_importancia_check" CHECK (importancia = ANY (ARRAY['alta'::text, 'baja'::text]))
) WITH (oids = false);

COMMENT ON TABLE "public"."urls" IS 'URLs para crawler interno';

CREATE UNIQUE INDEX urls_url_key ON public.urls USING btree (url);

CREATE INDEX idx_estado ON public.urls USING btree (estado);

CREATE INDEX idx_url ON public.urls USING btree (url);

CREATE INDEX idx_urls_fuente_estado_importancia_id ON public.urls USING btree (fuente, estado, importancia, id);


ALTER TABLE ONLY "public"."noticias_keywords" ADD CONSTRAINT "fk_noticia_keywords" FOREIGN KEY (noticia_id) REFERENCES noticias_historico(id) ON DELETE CASCADE NOT DEFERRABLE;

-- 2026-05-30 12:04:08 UTC
