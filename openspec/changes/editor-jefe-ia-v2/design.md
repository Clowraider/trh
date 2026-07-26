# Design: implemented Editor Jefe IA workflow

## Decision summary

Editor Jefe IA is implemented as a synchronous Flask workflow with two durable stages:

1. **Recommendation stage** — the operator requests recommendations, AI selection runs over eligible candidates in batches of five, and accepted selections are persisted in dedicated recommendation storage.
2. **Article stage** — the operator bulk-generates articles from saved recommendations, each generation passes through editorial control, and publication is gated by `requiere_revision_editorial` until a human clears it from the cluster detail page.

The design keeps humans in charge of publication, externalizes prompts/rules to files, and sanitizes generated article HTML before panel rendering.

## Main flow

### 1. Recommendation request

- `GET /editor-jefe-ia` loads saved recommendations from dedicated storage and renders the panel.
- `POST /editor-jefe-ia` validates `maximum` and `minimum_editorial_score`, builds current eligible candidates, excludes cluster IDs that are already saved, and calls `select_recommendations(...)`.
- `select_recommendations(...)` slices the bounded candidate list into groups of `SELECTION_BATCH_LIMIT = 5` and sends one AI request per batch.
- Valid selections are persisted with `save_recommendations(...)` and reloaded for display.

### 2. Saved recommendation queue

- Saved recommendations live in their own storage table managed by `editor_jefe_ia.py`.
- The panel treats this queue as durable editorial state: recommendations survive refresh/navigation and are not reconsidered in later recommendation runs.
- Before rendering quick actions, `app.py` enriches saved rows with the current cluster record so stale snapshots do not expose invalid publish actions.

### 3. Bulk article generation

- `POST /editor-jefe-ia/generar-guardadas` loads all saved recommendations and iterates them.
- Each saved item attempts generation only if the current cluster state is still allowed for generation.
- Generation uses `generate_article_with_editorial_control(...)` as the bulk generator.

### 4. Editorial control and regeneration limit

- `generate_article_with_editorial_control(...)` performs:
  1. one initial article generation;
  2. one editorial review pass;
  3. if the first review fails, one regeneration using appended correction instructions;
  4. one final review of the regenerated article.
- This is a **maximum of one retry/regeneration**. There is no loop beyond the second attempt.
- Any failed review path, failed retry-generation path, or review exception sets `requiere_revision_editorial = True`.
- If the first or second review passes cleanly, the flag is cleared or remains clear.

## Publication gate design

### Review-required path

- `_bloquea_publicacion_por_revision_editorial(cluster)` blocks publication whenever the cluster is in `estado_publicacion='generado'` and `requiere_revision_editorial` is true.
- `/publicar/<id>` enforces the same server-side gate even if a client bypasses UI affordances.
- Editor Jefe IA hides quick publish for those items and shows guidance to approve review in the cluster detail.
- `POST /aprobar-revision-editorial/<id>` is the human approval action exposed from `/cluster/<id>`; it clears the review flag and returns the item to a publishable state.

### Quick-publish path

- Quick publish is available from Editor Jefe IA only for saved recommendations whose cluster is already generated and does not require editorial review.
- The panel can collect photo selections inline and submit publication directly to `/publicar/<id>`.

## Prompt and rules externalization

- `trh/infrastructure/prompt_loader.py` requires env vars that point to prompt/rules files.
- Relative paths resolve from the project root, not the current working directory.
- `editorial_control.py` loads editorial rules JSON and the editorial-control system prompt from files.
- The feature fails closed when the configured prompt/rules files are missing, unreadable, malformed, or invalid.

## Sanitized panel rendering

- Stored generated article HTML is not rendered directly into the admin panel.
- `sanitize_article_html(...)` removes dangerous tags, comments, event handlers, unsafe protocols, and invalid image markup while preserving allowed editorial formatting.
- `app.py` uses sanitized markup for panel/detail rendering so admins can preview content safely without mutating the stored article body used elsewhere.

## Persistence and state boundaries

| Concern | Implemented boundary |
|---|---|
| Recommendations | Persisted in dedicated Editor Jefe IA storage |
| Recommendation retries | User-triggered rerun; previously saved IDs are excluded |
| Article generation | Explicit bulk action from saved recommendations |
| Editorial retry budget | One regeneration maximum |
| Review gate | `requiere_revision_editorial` plus human approval from `/cluster/<id>` |
| Quick publish | Allowed only for generated items with no review gate |
| Prompt/rules config | External files configured via env vars |
| Panel article rendering | Sanitized HTML only |

## Failure behavior

- Invalid recommendation inputs fail before AI selection.
- Recommendation storage failures degrade to visible warnings instead of silently pretending persistence succeeded.
- Bulk generation reports generated/skipped/failed counts.
- Editorial review failures fail closed into human review rather than auto-publishing.
- Missing or invalid prompt/rules files fail at load time instead of falling back to hidden defaults.

## Invariants

- Recommendation selection is explicit and human-triggered.
- Saved recommendations are durable and excluded from later recommendation runs until removed.
- Selection batching stays capped at five candidates per AI request.
- Editorial control never regenerates more than once.
- `requiere_revision_editorial` is a real publication gate.
- Human approval to clear that gate happens from `/cluster/<id>`.
- Quick publish never bypasses the review gate.
- Admin panel article previews render sanitized HTML.
