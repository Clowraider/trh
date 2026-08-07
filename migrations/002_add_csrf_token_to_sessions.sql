-- Migration 002: add server-side CSRF token storage to sessions
ALTER TABLE public.sessions
    ADD COLUMN IF NOT EXISTS csrf_token VARCHAR(64) NOT NULL DEFAULT '';
