-- Migration 005: per-user cluster visibility and publication state
CREATE TABLE IF NOT EXISTS public.user_cluster_states (
    user_id INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    cluster_id INTEGER NOT NULL REFERENCES public.clusters_editoriales(id) ON DELETE CASCADE,
    estado_publicacion VARCHAR(50) NOT NULL DEFAULT 'pendiente',
    requiere_revision_editorial BOOLEAN NOT NULL DEFAULT FALSE,
    url_wp VARCHAR(500),
    veces_publicado INTEGER NOT NULL DEFAULT 0,
    ultima_publicacion TIMESTAMP,
    descartado_en TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (user_id, cluster_id)
);

CREATE INDEX IF NOT EXISTS idx_user_cluster_states_user_id
    ON public.user_cluster_states USING btree (user_id);
CREATE INDEX IF NOT EXISTS idx_user_cluster_states_cluster_id
    ON public.user_cluster_states USING btree (cluster_id);
CREATE INDEX IF NOT EXISTS idx_user_cluster_states_estado
    ON public.user_cluster_states USING btree (user_id, estado_publicacion);
