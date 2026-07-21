# TRH project context

TRH is a Python 3.11 Flask application for news crawling, embeddings and clustering, an editorial control panel, AI-assisted article generation, and explicit WordPress publication.

## Conventions

- Preserve existing root compatibility wrappers and current manual editorial behavior.
- Keep secrets in `.env`; never commit credentials.
- Use PostgreSQL through the project's established connection helpers.
- Follow strict TDD with `.venv/bin/python -m pytest -q`.
- Keep changes reviewable and below the 400 changed-line review budget unless explicitly approved.
- AI features must not publish, modify existing editorial state, or invoke the existing writer unless their approved scope explicitly requires it.
