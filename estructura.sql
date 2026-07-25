-- Adminer 5.2.1 PostgreSQL 18.3 dump

\connect "trh";

DROP FUNCTION IF EXISTS "array_to_halfvec";;
CREATE FUNCTION "array_to_halfvec" () RETURNS halfvec LANGUAGE c AS 'array_to_halfvec';

DROP FUNCTION IF EXISTS "array_to_halfvec";;
CREATE FUNCTION "array_to_halfvec" () RETURNS halfvec LANGUAGE c AS 'array_to_halfvec';

DROP FUNCTION IF EXISTS "array_to_halfvec";;
CREATE FUNCTION "array_to_halfvec" () RETURNS halfvec LANGUAGE c AS 'array_to_halfvec';

DROP FUNCTION IF EXISTS "array_to_halfvec";;
CREATE FUNCTION "array_to_halfvec" () RETURNS halfvec LANGUAGE c AS 'array_to_halfvec';

DROP FUNCTION IF EXISTS "array_to_sparsevec";;
CREATE FUNCTION "array_to_sparsevec" () RETURNS sparsevec LANGUAGE c AS 'array_to_sparsevec';

DROP FUNCTION IF EXISTS "array_to_sparsevec";;
CREATE FUNCTION "array_to_sparsevec" () RETURNS sparsevec LANGUAGE c AS 'array_to_sparsevec';

DROP FUNCTION IF EXISTS "array_to_sparsevec";;
CREATE FUNCTION "array_to_sparsevec" () RETURNS sparsevec LANGUAGE c AS 'array_to_sparsevec';

DROP FUNCTION IF EXISTS "array_to_sparsevec";;
CREATE FUNCTION "array_to_sparsevec" () RETURNS sparsevec LANGUAGE c AS 'array_to_sparsevec';

DROP FUNCTION IF EXISTS "array_to_vector";;
CREATE FUNCTION "array_to_vector" () RETURNS vector LANGUAGE c AS 'array_to_vector';

DROP FUNCTION IF EXISTS "array_to_vector";;
CREATE FUNCTION "array_to_vector" () RETURNS vector LANGUAGE c AS 'array_to_vector';

DROP FUNCTION IF EXISTS "array_to_vector";;
CREATE FUNCTION "array_to_vector" () RETURNS vector LANGUAGE c AS 'array_to_vector';

DROP FUNCTION IF EXISTS "array_to_vector";;
CREATE FUNCTION "array_to_vector" () RETURNS vector LANGUAGE c AS 'array_to_vector';

DROP  IF EXISTS "avg";;
CREATE  "avg" () LANGUAGE internal AS 'aggregate_dummy';

DROP  IF EXISTS "avg";;
CREATE  "avg" () LANGUAGE internal AS 'aggregate_dummy';

DROP FUNCTION IF EXISTS "binary_quantize";;
CREATE FUNCTION "binary_quantize" () RETURNS bit LANGUAGE c AS 'binary_quantize';

DROP FUNCTION IF EXISTS "binary_quantize";;
CREATE FUNCTION "binary_quantize" () RETURNS bit LANGUAGE c AS 'halfvec_binary_quantize';

DROP FUNCTION IF EXISTS "cosine_distance";;
CREATE FUNCTION "cosine_distance" () RETURNS float8 LANGUAGE c AS 'cosine_distance';

DROP FUNCTION IF EXISTS "cosine_distance";;
CREATE FUNCTION "cosine_distance" () RETURNS float8 LANGUAGE c AS 'halfvec_cosine_distance';

DROP FUNCTION IF EXISTS "cosine_distance";;
CREATE FUNCTION "cosine_distance" () RETURNS float8 LANGUAGE c AS 'sparsevec_cosine_distance';

DROP FUNCTION IF EXISTS "halfvec";;
CREATE FUNCTION "halfvec" () RETURNS halfvec LANGUAGE c AS 'halfvec';

DROP FUNCTION IF EXISTS "halfvec_accum";;
CREATE FUNCTION "halfvec_accum" () RETURNS _float8 LANGUAGE c AS 'halfvec_accum';

DROP FUNCTION IF EXISTS "halfvec_add";;
CREATE FUNCTION "halfvec_add" () RETURNS halfvec LANGUAGE c AS 'halfvec_add';

DROP FUNCTION IF EXISTS "halfvec_avg";;
CREATE FUNCTION "halfvec_avg" () RETURNS halfvec LANGUAGE c AS 'halfvec_avg';

DROP FUNCTION IF EXISTS "halfvec_cmp";;
CREATE FUNCTION "halfvec_cmp" () RETURNS int4 LANGUAGE c AS 'halfvec_cmp';

DROP FUNCTION IF EXISTS "halfvec_combine";;
CREATE FUNCTION "halfvec_combine" () RETURNS _float8 LANGUAGE c AS 'vector_combine';

DROP FUNCTION IF EXISTS "halfvec_concat";;
CREATE FUNCTION "halfvec_concat" () RETURNS halfvec LANGUAGE c AS 'halfvec_concat';

DROP FUNCTION IF EXISTS "halfvec_eq";;
CREATE FUNCTION "halfvec_eq" () RETURNS bool LANGUAGE c AS 'halfvec_eq';

DROP FUNCTION IF EXISTS "halfvec_ge";;
CREATE FUNCTION "halfvec_ge" () RETURNS bool LANGUAGE c AS 'halfvec_ge';

DROP FUNCTION IF EXISTS "halfvec_gt";;
CREATE FUNCTION "halfvec_gt" () RETURNS bool LANGUAGE c AS 'halfvec_gt';

DROP FUNCTION IF EXISTS "halfvec_in";;
CREATE FUNCTION "halfvec_in" () RETURNS halfvec LANGUAGE c AS 'halfvec_in';

DROP FUNCTION IF EXISTS "halfvec_l2_squared_distance";;
CREATE FUNCTION "halfvec_l2_squared_distance" () RETURNS float8 LANGUAGE c AS 'halfvec_l2_squared_distance';

DROP FUNCTION IF EXISTS "halfvec_le";;
CREATE FUNCTION "halfvec_le" () RETURNS bool LANGUAGE c AS 'halfvec_le';

DROP FUNCTION IF EXISTS "halfvec_lt";;
CREATE FUNCTION "halfvec_lt" () RETURNS bool LANGUAGE c AS 'halfvec_lt';

DROP FUNCTION IF EXISTS "halfvec_mul";;
CREATE FUNCTION "halfvec_mul" () RETURNS halfvec LANGUAGE c AS 'halfvec_mul';

DROP FUNCTION IF EXISTS "halfvec_ne";;
CREATE FUNCTION "halfvec_ne" () RETURNS bool LANGUAGE c AS 'halfvec_ne';

DROP FUNCTION IF EXISTS "halfvec_negative_inner_product";;
CREATE FUNCTION "halfvec_negative_inner_product" () RETURNS float8 LANGUAGE c AS 'halfvec_negative_inner_product';

DROP FUNCTION IF EXISTS "halfvec_out";;
CREATE FUNCTION "halfvec_out" () RETURNS cstring LANGUAGE c AS 'halfvec_out';

DROP FUNCTION IF EXISTS "halfvec_recv";;
CREATE FUNCTION "halfvec_recv" () RETURNS halfvec LANGUAGE c AS 'halfvec_recv';

DROP FUNCTION IF EXISTS "halfvec_send";;
CREATE FUNCTION "halfvec_send" () RETURNS bytea LANGUAGE c AS 'halfvec_send';

DROP FUNCTION IF EXISTS "halfvec_spherical_distance";;
CREATE FUNCTION "halfvec_spherical_distance" () RETURNS float8 LANGUAGE c AS 'halfvec_spherical_distance';

DROP FUNCTION IF EXISTS "halfvec_sub";;
CREATE FUNCTION "halfvec_sub" () RETURNS halfvec LANGUAGE c AS 'halfvec_sub';

DROP FUNCTION IF EXISTS "halfvec_to_float4";;
CREATE FUNCTION "halfvec_to_float4" () RETURNS _float4 LANGUAGE c AS 'halfvec_to_float4';

DROP FUNCTION IF EXISTS "halfvec_to_sparsevec";;
CREATE FUNCTION "halfvec_to_sparsevec" () RETURNS sparsevec LANGUAGE c AS 'halfvec_to_sparsevec';

DROP FUNCTION IF EXISTS "halfvec_to_vector";;
CREATE FUNCTION "halfvec_to_vector" () RETURNS vector LANGUAGE c AS 'halfvec_to_vector';

DROP FUNCTION IF EXISTS "halfvec_typmod_in";;
CREATE FUNCTION "halfvec_typmod_in" () RETURNS int4 LANGUAGE c AS 'halfvec_typmod_in';

DROP FUNCTION IF EXISTS "hamming_distance";;
CREATE FUNCTION "hamming_distance" () RETURNS float8 LANGUAGE c AS 'hamming_distance';

DROP FUNCTION IF EXISTS "hnsw_bit_support";;
CREATE FUNCTION "hnsw_bit_support" () RETURNS internal LANGUAGE c AS 'hnsw_bit_support';

DROP FUNCTION IF EXISTS "hnsw_halfvec_support";;
CREATE FUNCTION "hnsw_halfvec_support" () RETURNS internal LANGUAGE c AS 'hnsw_halfvec_support';

DROP FUNCTION IF EXISTS "hnsw_sparsevec_support";;
CREATE FUNCTION "hnsw_sparsevec_support" () RETURNS internal LANGUAGE c AS 'hnsw_sparsevec_support';

DROP FUNCTION IF EXISTS "hnswhandler";;
CREATE FUNCTION "hnswhandler" () RETURNS index_am_handler LANGUAGE c AS 'hnswhandler';

DROP FUNCTION IF EXISTS "inner_product";;
CREATE FUNCTION "inner_product" () RETURNS float8 LANGUAGE c AS 'inner_product';

DROP FUNCTION IF EXISTS "inner_product";;
CREATE FUNCTION "inner_product" () RETURNS float8 LANGUAGE c AS 'halfvec_inner_product';

DROP FUNCTION IF EXISTS "inner_product";;
CREATE FUNCTION "inner_product" () RETURNS float8 LANGUAGE c AS 'sparsevec_inner_product';

DROP FUNCTION IF EXISTS "ivfflat_bit_support";;
CREATE FUNCTION "ivfflat_bit_support" () RETURNS internal LANGUAGE c AS 'ivfflat_bit_support';

DROP FUNCTION IF EXISTS "ivfflat_halfvec_support";;
CREATE FUNCTION "ivfflat_halfvec_support" () RETURNS internal LANGUAGE c AS 'ivfflat_halfvec_support';

DROP FUNCTION IF EXISTS "ivfflathandler";;
CREATE FUNCTION "ivfflathandler" () RETURNS index_am_handler LANGUAGE c AS 'ivfflathandler';

DROP FUNCTION IF EXISTS "jaccard_distance";;
CREATE FUNCTION "jaccard_distance" () RETURNS float8 LANGUAGE c AS 'jaccard_distance';

DROP FUNCTION IF EXISTS "l1_distance";;
CREATE FUNCTION "l1_distance" () RETURNS float8 LANGUAGE c AS 'l1_distance';

DROP FUNCTION IF EXISTS "l1_distance";;
CREATE FUNCTION "l1_distance" () RETURNS float8 LANGUAGE c AS 'halfvec_l1_distance';

DROP FUNCTION IF EXISTS "l1_distance";;
CREATE FUNCTION "l1_distance" () RETURNS float8 LANGUAGE c AS 'sparsevec_l1_distance';

DROP FUNCTION IF EXISTS "l2_distance";;
CREATE FUNCTION "l2_distance" () RETURNS float8 LANGUAGE c AS 'l2_distance';

DROP FUNCTION IF EXISTS "l2_distance";;
CREATE FUNCTION "l2_distance" () RETURNS float8 LANGUAGE c AS 'halfvec_l2_distance';

DROP FUNCTION IF EXISTS "l2_distance";;
CREATE FUNCTION "l2_distance" () RETURNS float8 LANGUAGE c AS 'sparsevec_l2_distance';

DROP FUNCTION IF EXISTS "l2_norm";;
CREATE FUNCTION "l2_norm" () RETURNS float8 LANGUAGE c AS 'halfvec_l2_norm';

DROP FUNCTION IF EXISTS "l2_norm";;
CREATE FUNCTION "l2_norm" () RETURNS float8 LANGUAGE c AS 'sparsevec_l2_norm';

DROP FUNCTION IF EXISTS "l2_normalize";;
CREATE FUNCTION "l2_normalize" () RETURNS vector LANGUAGE c AS 'l2_normalize';

DROP FUNCTION IF EXISTS "l2_normalize";;
CREATE FUNCTION "l2_normalize" () RETURNS halfvec LANGUAGE c AS 'halfvec_l2_normalize';

DROP FUNCTION IF EXISTS "l2_normalize";;
CREATE FUNCTION "l2_normalize" () RETURNS sparsevec LANGUAGE c AS 'sparsevec_l2_normalize';

DROP FUNCTION IF EXISTS "sparsevec";;
CREATE FUNCTION "sparsevec" () RETURNS sparsevec LANGUAGE c AS 'sparsevec';

DROP FUNCTION IF EXISTS "sparsevec_cmp";;
CREATE FUNCTION "sparsevec_cmp" () RETURNS int4 LANGUAGE c AS 'sparsevec_cmp';

DROP FUNCTION IF EXISTS "sparsevec_eq";;
CREATE FUNCTION "sparsevec_eq" () RETURNS bool LANGUAGE c AS 'sparsevec_eq';

DROP FUNCTION IF EXISTS "sparsevec_ge";;
CREATE FUNCTION "sparsevec_ge" () RETURNS bool LANGUAGE c AS 'sparsevec_ge';

DROP FUNCTION IF EXISTS "sparsevec_gt";;
CREATE FUNCTION "sparsevec_gt" () RETURNS bool LANGUAGE c AS 'sparsevec_gt';

DROP FUNCTION IF EXISTS "sparsevec_in";;
CREATE FUNCTION "sparsevec_in" () RETURNS sparsevec LANGUAGE c AS 'sparsevec_in';

DROP FUNCTION IF EXISTS "sparsevec_l2_squared_distance";;
CREATE FUNCTION "sparsevec_l2_squared_distance" () RETURNS float8 LANGUAGE c AS 'sparsevec_l2_squared_distance';

DROP FUNCTION IF EXISTS "sparsevec_le";;
CREATE FUNCTION "sparsevec_le" () RETURNS bool LANGUAGE c AS 'sparsevec_le';

DROP FUNCTION IF EXISTS "sparsevec_lt";;
CREATE FUNCTION "sparsevec_lt" () RETURNS bool LANGUAGE c AS 'sparsevec_lt';

DROP FUNCTION IF EXISTS "sparsevec_ne";;
CREATE FUNCTION "sparsevec_ne" () RETURNS bool LANGUAGE c AS 'sparsevec_ne';

DROP FUNCTION IF EXISTS "sparsevec_negative_inner_product";;
CREATE FUNCTION "sparsevec_negative_inner_product" () RETURNS float8 LANGUAGE c AS 'sparsevec_negative_inner_product';

DROP FUNCTION IF EXISTS "sparsevec_out";;
CREATE FUNCTION "sparsevec_out" () RETURNS cstring LANGUAGE c AS 'sparsevec_out';

DROP FUNCTION IF EXISTS "sparsevec_recv";;
CREATE FUNCTION "sparsevec_recv" () RETURNS sparsevec LANGUAGE c AS 'sparsevec_recv';

DROP FUNCTION IF EXISTS "sparsevec_send";;
CREATE FUNCTION "sparsevec_send" () RETURNS bytea LANGUAGE c AS 'sparsevec_send';

DROP FUNCTION IF EXISTS "sparsevec_to_halfvec";;
CREATE FUNCTION "sparsevec_to_halfvec" () RETURNS halfvec LANGUAGE c AS 'sparsevec_to_halfvec';

DROP FUNCTION IF EXISTS "sparsevec_to_vector";;
CREATE FUNCTION "sparsevec_to_vector" () RETURNS vector LANGUAGE c AS 'sparsevec_to_vector';

DROP FUNCTION IF EXISTS "sparsevec_typmod_in";;
CREATE FUNCTION "sparsevec_typmod_in" () RETURNS int4 LANGUAGE c AS 'sparsevec_typmod_in';

DROP FUNCTION IF EXISTS "subvector";;
CREATE FUNCTION "subvector" () RETURNS vector LANGUAGE c AS 'subvector';

DROP FUNCTION IF EXISTS "subvector";;
CREATE FUNCTION "subvector" () RETURNS halfvec LANGUAGE c AS 'halfvec_subvector';

DROP  IF EXISTS "sum";;
CREATE  "sum" () LANGUAGE internal AS 'aggregate_dummy';

DROP  IF EXISTS "sum";;
CREATE  "sum" () LANGUAGE internal AS 'aggregate_dummy';

DROP FUNCTION IF EXISTS "vector";;
CREATE FUNCTION "vector" () RETURNS vector LANGUAGE c AS 'vector';

DROP FUNCTION IF EXISTS "vector_accum";;
CREATE FUNCTION "vector_accum" () RETURNS _float8 LANGUAGE c AS 'vector_accum';

DROP FUNCTION IF EXISTS "vector_add";;
CREATE FUNCTION "vector_add" () RETURNS vector LANGUAGE c AS 'vector_add';

DROP FUNCTION IF EXISTS "vector_avg";;
CREATE FUNCTION "vector_avg" () RETURNS vector LANGUAGE c AS 'vector_avg';

DROP FUNCTION IF EXISTS "vector_cmp";;
CREATE FUNCTION "vector_cmp" () RETURNS int4 LANGUAGE c AS 'vector_cmp';

DROP FUNCTION IF EXISTS "vector_combine";;
CREATE FUNCTION "vector_combine" () RETURNS _float8 LANGUAGE c AS 'vector_combine';

DROP FUNCTION IF EXISTS "vector_concat";;
CREATE FUNCTION "vector_concat" () RETURNS vector LANGUAGE c AS 'vector_concat';

DROP FUNCTION IF EXISTS "vector_dims";;
CREATE FUNCTION "vector_dims" () RETURNS int4 LANGUAGE c AS 'vector_dims';

DROP FUNCTION IF EXISTS "vector_dims";;
CREATE FUNCTION "vector_dims" () RETURNS int4 LANGUAGE c AS 'halfvec_vector_dims';

DROP FUNCTION IF EXISTS "vector_eq";;
CREATE FUNCTION "vector_eq" () RETURNS bool LANGUAGE c AS 'vector_eq';

DROP FUNCTION IF EXISTS "vector_ge";;
CREATE FUNCTION "vector_ge" () RETURNS bool LANGUAGE c AS 'vector_ge';

DROP FUNCTION IF EXISTS "vector_gt";;
CREATE FUNCTION "vector_gt" () RETURNS bool LANGUAGE c AS 'vector_gt';

DROP FUNCTION IF EXISTS "vector_in";;
CREATE FUNCTION "vector_in" () RETURNS vector LANGUAGE c AS 'vector_in';

DROP FUNCTION IF EXISTS "vector_l2_squared_distance";;
CREATE FUNCTION "vector_l2_squared_distance" () RETURNS float8 LANGUAGE c AS 'vector_l2_squared_distance';

DROP FUNCTION IF EXISTS "vector_le";;
CREATE FUNCTION "vector_le" () RETURNS bool LANGUAGE c AS 'vector_le';

DROP FUNCTION IF EXISTS "vector_lt";;
CREATE FUNCTION "vector_lt" () RETURNS bool LANGUAGE c AS 'vector_lt';

DROP FUNCTION IF EXISTS "vector_mul";;
CREATE FUNCTION "vector_mul" () RETURNS vector LANGUAGE c AS 'vector_mul';

DROP FUNCTION IF EXISTS "vector_ne";;
CREATE FUNCTION "vector_ne" () RETURNS bool LANGUAGE c AS 'vector_ne';

DROP FUNCTION IF EXISTS "vector_negative_inner_product";;
CREATE FUNCTION "vector_negative_inner_product" () RETURNS float8 LANGUAGE c AS 'vector_negative_inner_product';

DROP FUNCTION IF EXISTS "vector_norm";;
CREATE FUNCTION "vector_norm" () RETURNS float8 LANGUAGE c AS 'vector_norm';

DROP FUNCTION IF EXISTS "vector_out";;
CREATE FUNCTION "vector_out" () RETURNS cstring LANGUAGE c AS 'vector_out';

DROP FUNCTION IF EXISTS "vector_recv";;
CREATE FUNCTION "vector_recv" () RETURNS vector LANGUAGE c AS 'vector_recv';

DROP FUNCTION IF EXISTS "vector_send";;
CREATE FUNCTION "vector_send" () RETURNS bytea LANGUAGE c AS 'vector_send';

DROP FUNCTION IF EXISTS "vector_spherical_distance";;
CREATE FUNCTION "vector_spherical_distance" () RETURNS float8 LANGUAGE c AS 'vector_spherical_distance';

DROP FUNCTION IF EXISTS "vector_sub";;
CREATE FUNCTION "vector_sub" () RETURNS vector LANGUAGE c AS 'vector_sub';

DROP FUNCTION IF EXISTS "vector_to_float4";;
CREATE FUNCTION "vector_to_float4" () RETURNS _float4 LANGUAGE c AS 'vector_to_float4';

DROP FUNCTION IF EXISTS "vector_to_halfvec";;
CREATE FUNCTION "vector_to_halfvec" () RETURNS halfvec LANGUAGE c AS 'vector_to_halfvec';

DROP FUNCTION IF EXISTS "vector_to_sparsevec";;
CREATE FUNCTION "vector_to_sparsevec" () RETURNS sparsevec LANGUAGE c AS 'vector_to_sparsevec';

DROP FUNCTION IF EXISTS "vector_typmod_in";;
CREATE FUNCTION "vector_typmod_in" () RETURNS int4 LANGUAGE c AS 'vector_typmod_in';

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
    "nota_editor" text,
    "url_wp" text,
    "fotos_secundarias" jsonb DEFAULT '[]',
    "nota_ia" text,
    "requiere_revision_editorial" boolean DEFAULT false,
    CONSTRAINT "clusters_editoriales_pkey" PRIMARY KEY ("id")
) WITH (oids = false);

CREATE INDEX clusters_embedding_idx ON public.clusters_editoriales USING hnsw (embedding_centroide vector_cosine_ops);

CREATE INDEX idx_clusters_estado_pub ON public.clusters_editoriales USING btree (estado_publicacion);

CREATE TABLE "public"."editor_jefe_ia_recommendations" (
    "cluster_id" bigint NOT NULL,
    "title" text NOT NULL,
    "reason" text NOT NULL,
    "editorial_score" double precision NOT NULL,
    "technical_score" double precision NOT NULL,
    "news_count" integer NOT NULL,
    "source_count" integer NOT NULL,
    "newest_at" timestamp with time zone NOT NULL,
    "recommended_at" timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT "editor_jefe_ia_recommendations_pkey" PRIMARY KEY ("cluster_id"),
    CONSTRAINT "editor_jefe_ia_recommendations_cluster_id_fkey" FOREIGN KEY ("cluster_id") REFERENCES "public"."clusters_editoriales"("id") ON DELETE CASCADE
) WITH (oids = false);

CREATE INDEX idx_editor_jefe_ia_recommendations_recommended_at ON public.editor_jefe_ia_recommendations USING btree (recommended_at DESC);


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

-- 2026-06-01 14:45:49 UTC
