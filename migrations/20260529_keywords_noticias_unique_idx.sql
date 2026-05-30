-- Evita duplicados de keywords por noticia/tipo/valor normalizado
CREATE UNIQUE INDEX IF NOT EXISTS uq_noticias_keywords_noticia_tipo_valor
ON noticias_keywords (noticia_id, tipo, valor_normalizado);
