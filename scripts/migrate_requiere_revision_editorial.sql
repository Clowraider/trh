ALTER TABLE clusters_editoriales
ADD COLUMN IF NOT EXISTS requiere_revision_editorial boolean DEFAULT false;

UPDATE clusters_editoriales
SET requiere_revision_editorial = false
WHERE requiere_revision_editorial IS NULL;
