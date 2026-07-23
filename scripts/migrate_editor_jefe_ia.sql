CREATE TABLE IF NOT EXISTS editor_jefe_ia_recommendations (
    cluster_id bigint PRIMARY KEY REFERENCES clusters_editoriales(id) ON DELETE CASCADE,
    title text NOT NULL,
    reason text NOT NULL,
    editorial_score double precision NOT NULL,
    technical_score double precision NOT NULL,
    news_count integer NOT NULL,
    source_count integer NOT NULL,
    newest_at timestamptz NOT NULL,
    recommended_at timestamptz NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_editor_jefe_ia_recommendations_recommended_at
ON editor_jefe_ia_recommendations (recommended_at DESC);
