-- Migration 006: per-user generated content for clusters
ALTER TABLE public.user_cluster_states
ADD COLUMN IF NOT EXISTS titulo_representativo TEXT,
ADD COLUMN IF NOT EXISTS contenido_ia JSONB,
ADD COLUMN IF NOT EXISTS foto_principal TEXT,
ADD COLUMN IF NOT EXISTS fotos_secundarias JSONB DEFAULT '[]'::jsonb,
ADD COLUMN IF NOT EXISTS nota_editor TEXT,
ADD COLUMN IF NOT EXISTS nota_ia TEXT;
