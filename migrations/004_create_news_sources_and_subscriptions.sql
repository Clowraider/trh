-- Migration 004: create news sources and user subscriptions tables
CREATE TABLE IF NOT EXISTS public.news_sources (
    id SERIAL PRIMARY KEY,
    slug VARCHAR(100) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_news_sources_slug ON public.news_sources(slug);
CREATE INDEX IF NOT EXISTS idx_news_sources_active ON public.news_sources(is_active);

CREATE TABLE IF NOT EXISTS public.user_source_subscriptions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    source_id INTEGER NOT NULL REFERENCES public.news_sources(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, source_id)
);

CREATE INDEX IF NOT EXISTS idx_user_source_subscriptions_user_id
    ON public.user_source_subscriptions USING btree (user_id);
