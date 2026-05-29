ALTER TABLE public.urls
ADD COLUMN IF NOT EXISTS importancia TEXT NOT NULL DEFAULT 'baja';

ALTER TABLE public.urls
ADD CONSTRAINT urls_importancia_check
CHECK (importancia IN ('alta', 'baja'));

CREATE INDEX IF NOT EXISTS idx_urls_fuente_estado_importancia_id
ON public.urls (fuente, estado, importancia, id);
