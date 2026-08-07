-- Migration 003: create per-user WordPress configuration table
CREATE TABLE IF NOT EXISTS public.user_wordpress_configs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE REFERENCES public.users(id) ON DELETE CASCADE,
    wp_url VARCHAR(500) NOT NULL,
    wp_username VARCHAR(100) NOT NULL,
    wp_app_password VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_wordpress_configs_user_id
    ON public.user_wordpress_configs USING btree (user_id);
