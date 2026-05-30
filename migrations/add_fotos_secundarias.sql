-- Agrega soporte para múltiples fotos en publicación editorial
ALTER TABLE clusters_editoriales
    ADD COLUMN IF NOT EXISTS fotos_secundarias JSONB DEFAULT '[]'::jsonb;

-- Normaliza nulos existentes
UPDATE clusters_editoriales
SET fotos_secundarias = '[]'::jsonb
WHERE fotos_secundarias IS NULL;
