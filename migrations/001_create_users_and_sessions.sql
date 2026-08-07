-- Migration 001: create users and sessions tables for SaaS auth
-- Run this against the TRH database after estructura.sql has been applied.

CREATE TABLE IF NOT EXISTS public.users (
    id SERIAL PRIMARY KEY,
    usuario VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    nombre VARCHAR(100) NOT NULL,
    ciudad VARCHAR(100),
    provincia VARCHAR(100),
    pais VARCHAR(100),
    notas TEXT,
    is_admin BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    last_login_at TIMESTAMP NULL
);

CREATE TABLE IF NOT EXISTS public.sessions (
    id SERIAL PRIMARY KEY,
    session_token VARCHAR(64) UNIQUE NOT NULL,
    user_id INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL,
    ip_address INET NULL,
    user_agent VARCHAR(255) NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_session_token
    ON public.sessions USING btree (session_token);

-- Seed admin user. CHANGE THIS PASSWORD IN PRODUCTION.
-- The hash below is for password 'admin'. Rotate it immediately after first login.
INSERT INTO public.users (
    usuario,
    email,
    password_hash,
    nombre,
    is_admin
) VALUES (
    'admin',
    'admin@example.com',
    'scrypt:32768:8:1$3RoU31Z0zUQRvKQc$ad3387890d7a5bef6d969f14c71a8937530a2e6151fd8f39ff65419a5df811653b4e540867bfe11332e4bc87dc84dfe51e13bbeb147dca53e2047cebca8e5e2d',
    'Administrador',
    TRUE
)
ON CONFLICT (usuario) DO NOTHING;
