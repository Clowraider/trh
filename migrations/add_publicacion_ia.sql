-- Migration: agregar columnas de publicacion IA
-- Fecha: 2026-05-28
-- Contexto: Panel de control necesita guardar contenido generado por IA
-- y rastrear estado de publicacion
--
-- CORRER EN LA DB:
--   psql -h 192.168.0.106 -U postgres -d trh -f migrations/add_publicacion_ia.sql

BEGIN;

-- Contenido generado por IA (JSON: titulo, resumen, articulo, categoria)
-- Solo existe si estado_publicacion = 'generado' o posterior
ALTER TABLE clusters_editoriales
    ADD COLUMN IF NOT EXISTS contenido_ia JSONB;

-- Estado del proceso de publicacion
-- Valores posibles:
--   pendiente   = listo para generar con IA
--   generando   = la IA está corriendo (para no tocar mientras tanto)
--   generado    = la IA terminó, esperando aprobacion del editor
--   publicado   = ya se publicó en WordPress
--   descartado = el editor lo sacó de la cola
ALTER TABLE clusters_editoriales
    ADD COLUMN IF NOT EXISTS estado_publicacion VARCHAR(30) DEFAULT 'pendiente'
    ADD CONSTRAINT chk_estado_publicacion
        CHECK (estado_publicacion IN ('pendiente','generando','generado','publicado','descartado'));

-- Foto principal elegida por el editor (URL de url_imagen de alguna noticia)
ALTER TABLE clusters_editoriales
    ADD COLUMN IF NOT EXISTS foto_principal TEXT;

-- Notas del editor antes de publicar (edicion minima)
ALTER TABLE clusters_editoriales
    ADD COLUMN IF NOT EXISTS nota_editor TEXT;

-- URL de la publicacion en WordPress (luego de publicar)
ALTER TABLE clusters_editoriales
    ADD COLUMN IF NOT EXISTS url_wp TEXT;

COMMIT;

-- Índices para las nuevas columnas (aceleran las consultas del panel)

-- El panel filtra por estado_publicacion constantemente
CREATE INDEX IF NOT EXISTS idx_clusters_estado_publicacion
    ON clusters_editoriales(estado_publicacion);

-- El panel busca clusters de las últimas 72h
CREATE INDEX IF NOT EXISTS idx_clusters_ultima_noticia
    ON clusters_editoriales(ultima_noticia DESC);

-- Verificar que las columnas se crearon
DO $$
BEGIN
    -- Verificar cada columna
    PERFORM column_name FROM information_schema.columns
        WHERE table_name = 'clusters_editoriales' AND column_name = 'contenido_ia';
    PERFORM column_name FROM information_schema.columns
        WHERE table_name = 'clusters_editoriales' AND column_name = 'estado_publicacion';
    PERFORM column_name FROM information_schema.columns
        WHERE table_name = 'clusters_editoriales' AND column_name = 'nota_editor';
    PERFORM column_name FROM information_schema.columns
        WHERE table_name = 'clusters_editoriales' AND column_name = 'url_wp';

    RAISE NOTICE '✅ Migration completada exitosamente';
EXCEPTION WHEN OTHERS THEN
    RAISE WARNING '⚠️  Verificar las columnas manualmente';
END $$;