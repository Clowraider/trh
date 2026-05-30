
--
-- PostgreSQL database dump
--

\restrict n9ISVamm1c0e9FBfFi13e1EI0ee9AvaBocjjcARMzGRHPF3euNtUJ0oA4rzmFFb

-- Dumped from database version 18.3 (Debian 18.3-1.pgdg13+1)
-- Dumped by pg_dump version 18.3 (Debian 18.3-1.pgdg13+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: datos; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA datos;


ALTER SCHEMA datos OWNER TO postgres;

--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: EXTENSION vector; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: clusters_editoriales; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.clusters_editoriales (
    id bigint NOT NULL,
    titulo_representativo text,
    embedding_centroide public.vector(768),
    cantidad_noticias integer DEFAULT 0,
    cantidad_fuentes integer DEFAULT 0,
    primera_noticia timestamp without time zone,
    ultima_noticia timestamp without time zone,
    score double precision DEFAULT 0,
    tendencia double precision DEFAULT 0,
    estado character varying(30) DEFAULT 'nuevo'::character varying,
    veces_publicado integer DEFAULT 0,
    ultima_publicacion timestamp without time zone,
    creado_en timestamp without time zone DEFAULT now(),
    actualizado_en timestamp without time zone DEFAULT now()
);


ALTER TABLE public.clusters_editoriales OWNER TO postgres;

--
-- Name: clusters_editoriales_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.clusters_editoriales_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.clusters_editoriales_id_seq OWNER TO postgres;

--
-- Name: clusters_editoriales_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.clusters_editoriales_id_seq OWNED BY public.clusters_editoriales.id;


--
-- Name: keywords_prioridad; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.keywords_prioridad (
    id bigint NOT NULL,
    keyword text NOT NULL,
    tipo character varying(30),
    puntos integer DEFAULT 0 NOT NULL,
    activo boolean DEFAULT true,
    creado_en timestamp without time zone DEFAULT now()
);


ALTER TABLE public.keywords_prioridad OWNER TO postgres;

--
-- Name: keywords_prioridad_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.keywords_prioridad_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.keywords_prioridad_id_seq OWNER TO postgres;

--
-- Name: keywords_prioridad_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.keywords_prioridad_id_seq OWNED BY public.keywords_prioridad.id;


--
-- Name: noticias_historico; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.noticias_historico (
    id integer CONSTRAINT noticias_id_not_null NOT NULL,
    noticia_hash character varying(64) CONSTRAINT noticias_noticia_hash_not_null NOT NULL,
    fuente character varying(100) CONSTRAINT noticias_fuente_not_null NOT NULL,
    url_original text CONSTRAINT noticias_url_original_not_null NOT NULL,
    titulo text CONSTRAINT noticias_titulo_not_null NOT NULL,
    texto_completo text,
    url_imagen text,
    fecha_publicacion timestamp without time zone,
    fecha_extraccion timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    embedding public.vector(768),
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
    cluster_id bigint
);


ALTER TABLE public.noticias_historico OWNER TO postgres;

--
-- Name: noticias_historico_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.noticias_historico_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.noticias_historico_id_seq OWNER TO postgres;

--
-- Name: noticias_historico_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.noticias_historico_id_seq OWNED BY public.noticias_historico.id;


--
-- Name: noticias_keywords; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.noticias_keywords (
    id bigint NOT NULL,
    noticia_id bigint NOT NULL,
    tipo character varying(30) NOT NULL,
    valor text NOT NULL,
    score double precision,
    creado_en timestamp without time zone DEFAULT now(),
    valor_normalizado text
);


ALTER TABLE public.noticias_keywords OWNER TO postgres;

--
-- Name: noticias_keywords_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.noticias_keywords_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.noticias_keywords_id_seq OWNER TO postgres;

--
-- Name: noticias_keywords_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.noticias_keywords_id_seq OWNED BY public.noticias_keywords.id;


--
-- Name: publicaciones; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.publicaciones (
    id bigint NOT NULL,
    cluster_id bigint,
    wordpress_post_id bigint,
    tipo character varying(30),
    titulo text,
    score_publicado double precision,
    cantidad_noticias integer,
    publicada_en timestamp without time zone DEFAULT now(),
    url_wordpress text
);


ALTER TABLE public.publicaciones OWNER TO postgres;

--
-- Name: publicaciones_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.publicaciones_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.publicaciones_id_seq OWNER TO postgres;

--
-- Name: publicaciones_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.publicaciones_id_seq OWNED BY public.publicaciones.id;


--
-- Name: urls; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.urls (
    id integer NOT NULL,
    url text NOT NULL,
    estado integer DEFAULT 0,
    fecha_creacion timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    fecha_procesado timestamp without time zone,
    fuente character varying(100)
);


ALTER TABLE public.urls OWNER TO postgres;

--
-- Name: TABLE urls; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.urls IS 'URLs para crawler interno';


--
-- Name: urls_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.urls_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.urls_id_seq OWNER TO postgres;

--
-- Name: urls_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.urls_id_seq OWNED BY public.urls.id;


--
-- Name: clusters_editoriales id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.clusters_editoriales ALTER COLUMN id SET DEFAULT nextval('public.clusters_editoriales_id_seq'::regclass);


--
-- Name: keywords_prioridad id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.keywords_prioridad ALTER COLUMN id SET DEFAULT nextval('public.keywords_prioridad_id_seq'::regclass);


--
-- Name: noticias_historico id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.noticias_historico ALTER COLUMN id SET DEFAULT nextval('public.noticias_historico_id_seq'::regclass);


--
-- Name: noticias_keywords id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.noticias_keywords ALTER COLUMN id SET DEFAULT nextval('public.noticias_keywords_id_seq'::regclass);


--
-- Name: publicaciones id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.publicaciones ALTER COLUMN id SET DEFAULT nextval('public.publicaciones_id_seq'::regclass);


--
-- Name: urls id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.urls ALTER COLUMN id SET DEFAULT nextval('public.urls_id_seq'::regclass);


--
-- Name: clusters_editoriales clusters_editoriales_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.clusters_editoriales
    ADD CONSTRAINT clusters_editoriales_pkey PRIMARY KEY (id);


--
-- Name: keywords_prioridad keywords_prioridad_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.keywords_prioridad
    ADD CONSTRAINT keywords_prioridad_pkey PRIMARY KEY (id);


--
-- Name: noticias_historico noticias_historico_noticia_hash_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.noticias_historico
    ADD CONSTRAINT noticias_historico_noticia_hash_key UNIQUE (noticia_hash);


--
-- Name: noticias_historico noticias_historico_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.noticias_historico
    ADD CONSTRAINT noticias_historico_pkey PRIMARY KEY (id);


--
-- Name: noticias_historico noticias_historico_url_original_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.noticias_historico
    ADD CONSTRAINT noticias_historico_url_original_key UNIQUE (url_original);


--
-- Name: noticias_keywords noticias_keywords_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.noticias_keywords
    ADD CONSTRAINT noticias_keywords_pkey PRIMARY KEY (id);


--
-- Name: publicaciones publicaciones_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.publicaciones
    ADD CONSTRAINT publicaciones_pkey PRIMARY KEY (id);


--
-- Name: urls urls_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.urls
    ADD CONSTRAINT urls_pkey PRIMARY KEY (id);


--
-- Name: urls urls_url_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.urls
    ADD CONSTRAINT urls_url_key UNIQUE (url);


--
-- Name: clusters_embedding_idx; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX clusters_embedding_idx ON public.clusters_editoriales USING hnsw (embedding_centroide public.vector_cosine_ops);


--
-- Name: idx_estado; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_estado ON public.urls USING btree (estado);


--
-- Name: idx_hash_contenido; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_hash_contenido ON public.noticias_historico USING btree (hash_contenido);


--
-- Name: idx_keywords_noticia; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_keywords_noticia ON public.noticias_keywords USING btree (noticia_id);


--
-- Name: idx_keywords_prioridad_activo; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_keywords_prioridad_activo ON public.keywords_prioridad USING btree (activo);


--
-- Name: idx_keywords_prioridad_keyword; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_keywords_prioridad_keyword ON public.keywords_prioridad USING btree (keyword);


--
-- Name: idx_keywords_prioridad_tipo; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_keywords_prioridad_tipo ON public.keywords_prioridad USING btree (tipo);


--
-- Name: idx_keywords_tipo; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_keywords_tipo ON public.noticias_keywords USING btree (tipo);


--
-- Name: idx_keywords_valor; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_keywords_valor ON public.noticias_keywords USING btree (valor);


--
-- Name: idx_keywords_valor_tipo; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_keywords_valor_tipo ON public.noticias_keywords USING btree (valor, tipo);


--
-- Name: idx_url; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_url ON public.urls USING btree (url);


--
-- Name: noticias_historico_embedding_idx; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX noticias_historico_embedding_idx ON public.noticias_historico USING hnsw (embedding public.vector_cosine_ops);


--
-- Name: noticias_historico_fecha_extraccion_idx; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX noticias_historico_fecha_extraccion_idx ON public.noticias_historico USING btree (fecha_extraccion);


--
-- Name: noticias_historico_fuente_idx; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX noticias_historico_fuente_idx ON public.noticias_historico USING btree (fuente);


--
-- Name: noticias_historico_procesado_idx; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX noticias_historico_procesado_idx ON public.noticias_historico USING btree (procesado);


--
-- Name: noticias_historico_url_original_idx; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX noticias_historico_url_original_idx ON public.noticias_historico USING btree (url_original);


--
-- Name: noticias_keywords fk_noticia_keywords; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.noticias_keywords
    ADD CONSTRAINT fk_noticia_keywords FOREIGN KEY (noticia_id) REFERENCES public.noticias_historico(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict n9ISVamm1c0e9FBfFi13e1EI0ee9AvaBocjjcARMzGRHPF3euNtUJ0oA4rzmFFb

