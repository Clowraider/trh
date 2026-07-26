# Repository layout

This repository keeps runnable entrypoints at the root and moves reusable implementation code into domain-specific folders or the `trh/` package.

## Quick path

1. Keep root-level Python files only when they are real entrypoints or legacy top-level workflows.
2. Put shared runtime helpers under `trh/infrastructure/`.
3. Add new code next to the subsystem that owns it instead of creating new root-level utility modules.

## Current layout

| Path | Purpose |
|---|---|
| `app.py` | Main Flask entrypoint for the editorial panel. |
| `proceso.py` | Root workflow entrypoint that still orchestrates the existing process flow. |
| `trh/editorial/` | Reusable editorial selection and editorial-control modules. |
| `trh/publication/` | Reusable article-generation and WordPress-publication modules. |
| `crawler/` | News ingestion and crawling logic. |
| `pipeline/` | Data processing, clustering, and publication-selection pipeline code. |
| `prompts/` | Prompt and rules source files loaded from env-configured paths. |
| `templates/` | Flask HTML templates. |
| `tests/` | Automated tests. |
| `deploy/`, `scripts/` | Operational and deployment helpers. |
| `openspec/` | Change proposals, specs, design, and task artifacts. |
| `docs/` | Human-facing repository documentation. |
| `trh/infrastructure/` | Shared infrastructure helpers such as env loading, prompt/rules loading, and HTML sanitization. |

## Placement rules

| If you are adding... | Put it here |
|---|---|
| Shared Python helper used by multiple modules | `trh/infrastructure/` |
| Pipeline-stage logic or DB-selection flow code | `pipeline/` |
| Crawler-specific logic | `crawler/` |
| UI template markup | `templates/` |
| Prompt text or JSON rules loaded by configuration | `prompts/` |
| Tests for any module | `tests/` mirroring the behavior under test |
| Process or architecture documentation | `docs/` |

## Root-level rule

Do not add new generic helper modules at the repository root. If code is not an entrypoint, place it in the package or subsystem that owns it.
