# Design: response-only Editor Jefe IA with bounded editorial context

## Decision summary

Implement a synchronous, read-only Editor Jefe IA tab in the existing Flask panel. `GET /editor-jefe-ia` renders only the form and empty state. An explicit `POST /editor-jefe-ia` renders exactly one HTML response containing either a complete validated recommendation, a valid zero-selection state, or retryable error feedback with no result.

Every eligible cluster sent to the AI carries bounded, deterministic editorial context: existing core fields, the exact editorial score produced by the panel's existing score primitive, normalized panel keywords, and at most three qualifying news items with bounded excerpts. The feature adds no authentication, session/cookie/cache/browser storage, redirect, persistence, writer/publication call, or editorial mutation.

The richer context and required parity/composition tests raise the honest total forecast above 400 changed lines. Delivery should use two reviewable work units, each below 400 lines; details are in **Work-unit plan and forecast**.

## Verified current-main primitives

| Concern | Current-main primitive | Design decision |
|---|---|---|
| Panel score | `app.index()` calls `generar_candidatos(conn)` and reads each `score_editorial`. `generar_candidatos` delegates the formula to `pipeline.seleccionar_publicables.calcular_score_editorial(...)`. | Reuse `calcular_score_editorial` directly with the same existing supporting loaders. Do not copy, translate to SQL, or reinterpret the formula. |
| Score inputs | `obtener_recientes_por_cluster`, `obtener_keywords_por_cluster`, and `obtener_prioridades` supply the maps consumed by `calcular_score_editorial`. | Invoke these existing functions on the same runtime `RealDictCursor` connection. The dedicated feature query supplies the same cluster fields required by the primitive. |
| Panel keywords | `app.obtener_keywords_por_clusters_ids(conn, ids)` selects `valor_normalizado`, groups by cluster, deduplicates, and sorts; `panel_index.html` displays `kws[:8]`. | Reuse this exact helper/output and the panel's existing first-eight presentation bound. Do not source keywords elsewhere. |
| Runtime rows | `pipeline.seleccionar_publicables.get_connection()` creates psycopg2 connections with `cursor_factory=RealDictCursor`. | Pass the same connection factory through Flask composition and use mapping rows throughout. Never request a plain cursor. |
| Existing recent-news seam | `obtener_noticias_fuente_por_cluster` already demonstrates a batch window-function query, but uses a different window, fields, timestamp expression, and limit. | Follow its batch/window shape, but add a dedicated qualifying-news query for the approved three-day/three-item/text contract. |
| AI seam | `publicador.llamar_ia` is OpenRouter-specific but also writer-specific. | Follow its environment/provider conventions in a dedicated adapter; never import or call `publicador`. |

`generar_candidatos` itself cannot be used as the feature's score map because it sorts and truncates to `MAX_CANDIDATOS = 200` after applying broader panel eligibility. The feature needs a score for every independently eligible pending cluster. Calling the underlying `calcular_score_editorial` primitive with its existing loaders preserves the formula exactly without inheriting that unrelated top-200 slice.

CodeGraph could not be queried because no CodeGraph MCP/CLI tool is available in this executor. Inspection used targeted current-main files only. Abandoned artifacts, remote branches, and `.git` candidate views are not design inputs.

## Route and visual composition

Add Bootstrap `nav nav-tabs mb-4` navigation to both panel views:

- **Clusters** → `url_for('index')`, active on `/`.
- **Editor Jefe IA** → `url_for('editor_jefe_ia')`, active on `/editor-jefe-ia`.

`templates/panel_index.html` otherwise remains unchanged. Add `templates/panel_editor_jefe_ia.html` using the same Bootstrap CDN, light body, container, alert, badge, score, and cluster-card vocabulary. Recommendation cards may link to existing cluster detail but expose no discard, generation, review, correction, or publication controls.

- `GET /editor-jefe-ia`: render form, advisory copy, and empty state; perform no retrieval or AI call.
- `POST /editor-jefe-ia`: validate the positive integer maximum, synchronously build all eligible context, call AI when candidates exist, validate all output, and directly render one complete outcome with status `200`.

There is no PRG redirect or result preservation. Refresh/navigation may discard the result or prompt browser POST resubmission; no behavior is guaranteed and no JavaScript storage is required.

## Read-only data flow

Use one connection created by the exact configured runtime `get_connection` factory for the complete candidate-building step. The connection is closed after request-local context assembly. No commit or write statement is permitted.

```text
connection_factory() -> RealDictCursor connection
  -> dedicated eligible-cluster query
  -> existing score input loaders (recent counts, score keywords, priorities)
  -> existing calcular_score_editorial for every eligible cluster
  -> existing panel keyword helper for eligible IDs
  -> dedicated ranked qualifying-news query for eligible IDs
  -> deterministic bounded candidate mappings
  -> close connection
  -> deterministic compact JSON prompt
```

This is a fixed number of batch queries, independent of candidate count: one eligibility query, the three existing score-loader queries, one panel-keyword query, and one ranked-news query. It avoids N+1. The score loaders currently read their normal panel-wide windows; that cost is accepted to preserve exact parity rather than introduce subtly different filtered copies.

### Eligible-cluster query

The dedicated query remains independent from `listar_todos_los_clusters()` and must select every field required by `calcular_score_editorial`:

```sql
SELECT
    ce.id AS cluster_id,
    ce.titulo_representativo,
    ce.cantidad_noticias,
    ce.cantidad_fuentes,
    ce.score AS technical_score,
    ce.tendencia,
    ce.primera_noticia,
    ce.ultima_noticia,
    ce.ultima_publicacion,
    MAX(COALESCE(n.fecha_publicacion, n.fecha_extraccion)) AS newest_at
FROM clusters_editoriales ce
JOIN noticias_historico n ON n.cluster_id = ce.id
WHERE COALESCE(ce.estado_publicacion, 'pendiente') = 'pendiente'
  AND COALESCE(n.fecha_publicacion, n.fecha_extraccion)
      >= NOW() - INTERVAL '3 days'
GROUP BY ce.id, ce.titulo_representativo, ce.cantidad_noticias,
         ce.cantidad_fuentes, ce.score, ce.tendencia,
         ce.primera_noticia, ce.ultima_noticia, ce.ultima_publicacion
ORDER BY newest_at DESC, ce.id DESC
```

There is no requested-maximum SQL limit because every eligible ID must reach AI-response validation. `COALESCE(..., 'pendiente')` preserves the current template's null-as-pending treatment while excluding discarded, generating, generated, and published states.

### Exact editorial-score parity

For each eligible row:

1. adapt field names only (`cluster_id` to `id` where required); do not alter values used by the primitive;
2. obtain `recientes` from `obtener_recientes_por_cluster(conn)` with its existing zero-count default;
3. obtain score keywords from `obtener_keywords_por_cluster(conn)` and priorities from `obtener_prioridades(conn)`;
4. call `calcular_score_editorial(cluster, recientes, score_keywords, prioridades)`;
5. publish exactly `resultado['score_final']` as `editorial_score`.

The richer prompt's bounded display-keyword list must never replace `score_keywords` as the formula input. The formula's current clock, penalties, bonuses, rounding, priority matching, and configured panel windows remain owned by the existing primitive. Tests freeze `_ahora_utc` when comparing values so parity is deterministic.

If required score inputs are malformed and the existing primitive cannot calculate, fail the entire POST as a retryable retrieval/context error. Do not invent a fallback score, use technical score as a substitute, or omit the candidate.

### Deterministic panel keywords

Call existing `app.obtener_keywords_por_clusters_ids(conn, eligible_ids)` once. It already removes SQL null/empty values, groups by cluster, deduplicates, and sorts. For prompt mapping:

- take the helper's sorted values for that exact cluster;
- apply the same `[:8]` bound already used by `panel_index.html`;
- trim surrounding whitespace and discard values that become empty;
- deduplicate again after trimming and sort by Unicode code-point order before taking the final first eight;
- cap each serialized keyword at 120 Unicode code points after normalization.

The payload therefore contains at most eight deterministic strings and cannot associate a keyword from another cluster. The score primitive still receives its original, uncapped typed keyword inputs from `obtener_keywords_por_cluster`; payload bounding cannot change score parity.

### Ranked qualifying news query

Use one `ANY(%s)` batch query with a CTE/window function:

```sql
WITH qualifying AS (
    SELECT
        n.id,
        n.cluster_id,
        n.titulo,
        n.fuente,
        n.texto_completo,
        COALESCE(n.fecha_publicacion, n.fecha_extraccion) AS effective_at,
        ROW_NUMBER() OVER (
            PARTITION BY n.cluster_id
            ORDER BY COALESCE(n.fecha_publicacion, n.fecha_extraccion) DESC,
                     n.id DESC
        ) AS rn
    FROM noticias_historico n
    WHERE n.cluster_id = ANY(%s)
      AND COALESCE(n.fecha_publicacion, n.fecha_extraccion)
          >= NOW() - INTERVAL '3 days'
)
SELECT id, cluster_id, titulo, fuente, texto_completo, effective_at
FROM qualifying
WHERE rn <= 3
ORDER BY cluster_id, effective_at DESC, id DESC
```

The stable `id DESC` tie-break is mandatory both inside `ROW_NUMBER` and final ordering. No fourth item is loaded into the mapping.

For each news item:

- `title`: normalize all whitespace runs with `" ".join(value.split())`; null/empty becomes `""`; cap at 300 Unicode code points;
- `source`: same whitespace normalization; null/empty becomes `""`; cap at 100 Unicode code points (matching the current schema width);
- `effective_at`: publication timestamp with extraction fallback from SQL, serialized as ISO-8601; a null cannot pass the qualifying predicate, and an unexpected null fails context assembly rather than inventing a timestamp;
- `excerpt`: null/empty `texto_completo` becomes `""`; otherwise normalize all Unicode whitespace runs to one ASCII space, trim, then slice to at most 600 Unicode code points;
- `id` is used only for deterministic ranking/testing and is not required in the AI mapping.

## Bounded candidate mapping

The exact AI candidate shape is:

```json
{
  "cluster_id": 123,
  "title": "Representative cluster title",
  "technical_score": 41.0,
  "editorial_score": 87.0,
  "news_count": 5,
  "source_count": 3,
  "newest_at": "2026-03-06T12:30:00+00:00",
  "keywords": ["economía", "mercados"],
  "recent_news": [
    {
      "title": "Most recent qualifying headline",
      "source": "Source",
      "effective_at": "2026-03-06T12:30:00+00:00",
      "excerpt": "Whitespace-normalized existing text"
    }
  ]
}
```

Core handling:

- cluster `title` is whitespace-normalized, null/empty becomes `"(Sin título)"`, and prompt text is capped at 300 Unicode code points;
- `technical_score` null becomes `0.0`, matching current panel display behavior;
- score-input counts/timestamps needed by `calcular_score_editorial` are not defaulted except for the primitive's existing recent-count default; malformed required values fail closed;
- `newest_at` is non-null by eligibility and serialized ISO-8601;
- candidates remain ordered `newest_at DESC, cluster_id DESC`;
- keywords and recent news obey their independent deterministic bounds.

Per candidate, variable prompt text is bounded to 300 title characters, eight × 120 keyword characters, three × (300 title + 100 source + 600 excerpt), plus fixed-size scalar/timestamp structure. This is a structural per-candidate bound.

### Whole-prompt/token safety

Serialize only the fixed policy metadata, requested maximum, and ordered candidate mappings with:

```python
json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
```

Encode once as UTF-8. Enforce a code-owned transport limit of **48,000 UTF-8 bytes for the complete user payload**, with the fixed system prompt and output allowance budgeted separately. For byte-level/BPE tokenizers, token count cannot exceed the UTF-8 byte count; configured selection models must advertise a context window large enough for that request plus the fixed system prompt and response allowance. Set a bounded selection response allowance (forecast: 1,200 tokens).

If complete approved context exceeds the byte budget, fail before the AI call with generic retryable feedback. Do not truncate candidates, remove context categories, split into independently selected batches, or silently lower the operator's maximum, because those alternatives would change the global selection contract. This is a technical request-size guard, not an additional product maximum.

## Fixed prompt and OpenRouter seam

Create `editor_jefe_ia.py` to own candidate assembly, normalization, compact serialization, fixed prompt policy, dedicated `OpenRouterSelectionClient`, strict output validation, and synchronous orchestration. Inject the HTTP `post` callable and runtime connection factory for tests.

The prompt states that the model is an advisory Editor-in-Chief, may select zero through the supplied ceiling, may select only supplied IDs, must use the complete supplied context, must not imply approval or trigger actions, and must return only the required JSON object. There is no operator prompt field.

The adapter follows current OpenRouter environment names, URL/model fallback convention, JSON response format, and bounded timeout, but imports neither `publicador` nor any writer/publication module. Network, provider, shape, JSON, or payload-budget failures become generic retryable POST errors; secrets, complete prompts, excerpts, and raw output are not logged.

## Strict AI response validation

Accept only:

```json
{"selections":[{"cluster_id":123,"reason":"Short concrete reason"}]}
```

Before rendering any recommendation, require:

1. exact top-level `selections` object shape;
2. a list of exact `{cluster_id, reason}` objects;
3. integer/non-boolean IDs from the eligible set;
4. unique IDs;
5. count at most `min(requested_maximum, eligible_count)`;
6. trimmed, nonempty, control-free reasons of at most 240 Unicode code points;
7. no coercion, truncation, dropping, or partial acceptance.

On success, join selected IDs back to request-local server mappings and sort by candidate order, never model order. Rich context supports selection but need not all be repeated in result cards; the cards retain useful panel fields and the reason.

## Response-only and side-effect boundaries

```text
GET -> form + empty state

explicit POST
  -> validate maximum
  -> build bounded read-only candidate context
  -> if empty: render valid zero-selection response
  -> enforce prompt byte/context budget
  -> synchronously call dedicated AI client
  -> validate whole response
  -> reorder selected candidates
  -> render complete recommendation response
```

Every POST directly renders status `200`: complete nonempty recommendation, valid zero outcome, or retryable error with no recommendation/partial/prior result. There is no session access, result cookie, server/browser cache, filesystem or PostgreSQL record, redirect, queue, background execution, or history.

No feature path imports or calls writer, publication, review, correction, scheduler, discard, save, or state-transition behavior. All SQL is `SELECT`; existing panel/list/detail/editorial behavior remains unchanged.

## Strict TDD and composition evidence

Implementation follows RED → GREEN → TRIANGULATE → REFACTOR.

### Context-builder tests

- eligibility is exactly pending-only and three days using publication/extraction fallback;
- candidate ordering is `newest_at DESC, cluster_id DESC`;
- score parity compares feature `editorial_score` to direct `calcular_score_editorial` output using the same frozen clock, existing recent map, score-keyword map, and priorities;
- test fails if feature code duplicates formula constants/bonuses or substitutes technical score;
- panel keyword helper association, trim/dedupe/sort, first-eight bound, and per-keyword bound are deterministic;
- ranked-news query uses one batch, `rn <= 3`, effective timestamp descending, and stable ID descending;
- null/empty title/source/text handling and Unicode whitespace normalization are exact;
- excerpts are at most 600 Unicode code points after normalization; fourth news never enters mapping;
- compact JSON is byte-stable, includes rich context for every candidate, and fails before AI above 48,000 UTF-8 bytes;
- repository performs no writes/commit and no per-candidate query.

### RealDictCursor and route composition tests

- route passes the configured connection factory object unchanged;
- the same factory/connection supplies eligibility, existing score loaders/primitive, panel keywords, and news query;
- rows are mappings with runtime-equivalent `RealDictCursor` semantics;
- regression guard proves feature code neither requests a plain cursor nor tuple-indexes rows;
- where a PostgreSQL test DSN exists, run a rolled-back integration fixture through the actual `pipeline.seleccionar_publicables.get_connection` factory and compare score parity;
- without PostgreSQL evidence, verification reports the limitation and does not treat tuple fakes as production-composition proof;
- POST composes context → prompt → validation → direct rendering with newest-first results;
- invalid context/provider/output renders no partial recommendation and makes no writer/publication calls;
- GET after POST has no prior result; response sets no result cookie and redirects nowhere.

## Work-unit plan and changed-line forecast

The richer context no longer fits safely under 400 total changed lines without dropping mandatory tests. Estimated total is **455–585 lines**.

| File | Change | Forecast |
|---|---|---:|
| `app.py` | GET/POST route, existing keyword-helper reuse, dependency composition. | 40–55 |
| `editor_jefe_ia.py` | Eligibility/news queries, score-primitive composition, bounded mappings, prompt/client/validator/orchestration. | 185–230 |
| `templates/panel_index.html` | Tab navigation only. | 8–12 |
| `templates/panel_editor_jefe_ia.html` | Form and response-local success/zero/error UI. | 55–70 |
| `tests/test_editor_jefe_ia_context.py` | Query, score parity, keyword/news bounds, prompt budget, RealDict tests. | 100–130 |
| `tests/test_editor_jefe_ia_route.py` | AI validation, direct-render route, failure and side-effect composition. | 67–88 |
| **Total** | | **455–585** |

Use the smallest safe split:

1. **Work unit A — bounded read-only editorial context (215–285 lines):** add the context-building portion of `editor_jefe_ia.py` plus `tests/test_editor_jefe_ia_context.py`. It exposes a tested function returning deterministic bounded mappings and performs no route/AI/UI work.
2. **Work unit B — synchronous recommendation surface (240–300 lines):** add OpenRouter/prompt/response validation and orchestration, Flask GET/POST composition, templates/navigation, and route tests. It consumes Work unit A without changing its contracts.

Each work unit keeps behavior and tests together, remains below 400, and has an independent review purpose. Do not collapse them into one oversized review or omit score-parity/RealDict/output-validation tests.

## Rollout and rollback

No migration, persistence service, cache, or data rollout exists. Merge/deploy the two work units in dependency order. Rollback removes the tab, route, feature module, templates, and tests; there is no stored result or editorial data cleanup.

## Invariants

- Existing panel query and editorial flows remain unchanged.
- `calcular_score_editorial` and its existing inputs remain the sole score formula authority.
- Rich candidate context is deterministic, bounded, newest-first, and read-only.
- AI output is all-or-nothing validated.
- GET is empty/form only; POST directly renders one complete outcome.
- No result preservation, persistence, writer/publication call, or mutation is added.
- Runtime and end-to-end tests preserve the `get_connection`/`RealDictCursor` mapping contract.
