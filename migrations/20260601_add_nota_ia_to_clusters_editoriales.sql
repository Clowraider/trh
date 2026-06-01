-- Campo opcional para guías editoriales que se adjuntan al prompt de IA
ALTER TABLE public.clusters_editoriales
    ADD COLUMN IF NOT EXISTS nota_ia TEXT;