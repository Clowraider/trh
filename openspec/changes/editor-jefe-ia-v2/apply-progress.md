# Apply Progress: Editor Jefe IA v2

> Historical note: this file preserves the original apply-phase execution evidence from the implementation slices that built the feature. The primary contract artifacts (`proposal.md`, `design.md`, `tasks.md`, and `specs/editor-jefe-ia/spec.md`) were later rewritten to align with the implemented workflow as a whole, so this progress log should be read as historical delivery evidence rather than the current feature contract.

## Current boundary

- Authorized work unit: **Slice A — bounded read-only editorial context only**.
- Delivery boundary: `stacked-to-main`; Slice B remains blocked until Slice A is reviewed and integrated into `main`.
- Review workload: 370 implementation additions/deletions (158 `editor_jefe_ia.py` + 212 `tests/test_editor_jefe_ia_context.py`), below the 400-line limit.
- No commit, push, PR, review lifecycle command, route, AI client, prompt, Flask composition, template, navigation, or UI work was performed.

## Completed implementation tasks

- [x] Slice A RED repository tests and expected failing execution.
- [x] Slice A GREEN read-only context builder and focused passing execution.
- [x] Slice A TRIANGULATE rich-context normalization, association, bounds, null handling, and deterministic order.
- [x] Slice A REFACTOR guards, focused/full regression verification, static dependency check, line-budget measurement, and PostgreSQL read-only smoke evidence.

The matching four Slice A implementation-owned rows are visibly checked in `tasks.md`. Parent-owned rows were preserved.

## Files changed

- `editor_jefe_ia.py` — new read-only deterministic context builder.
- `tests/test_editor_jefe_ia_context.py` — new mapping-row, query, score-parity, normalization, bounds, and side-effect tests.
- `openspec/changes/editor-jefe-ia-v2/tasks.md` — checked only the four completed Slice A implementation tasks.
- `openspec/changes/editor-jefe-ia-v2/apply-progress.md` — cumulative Slice A evidence.

## TDD Cycle Evidence

| Task | Test file | Layer | Safety net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| Slice A RED | `tests/test_editor_jefe_ia_context.py` | Unit/repository boundary | N/A — new production and test files | Exit 2: collection failed with `ModuleNotFoundError: No module named 'editor_jefe_ia'`; all three new tests were unavailable until production existed | See GREEN | Query assertions cover pending/null-as-pending eligibility, three-day publication/extraction fallback, no eligibility limit, ranked batch news, stable tie-break, and read-only behavior | Query spy rejects writes, commit, explicit cursor factories, tuple indexing, and N+1 behavior |
| Slice A GREEN | `tests/test_editor_jefe_ia_context.py` | Unit/composition | N/A — new file | Same RED above | `.venv/bin/python -m pytest -q tests/test_editor_jefe_ia_context.py -k 'eligibility or score or connection'`: exit 0, 1 passed, 2 deselected | Score parity uses direct `calcular_score_editorial` with the same maps and frozen `_ahora_utc`; factory and connection identity are asserted | Focused test remained green after ranked-query and deterministic-order cleanup |
| Slice A TRIANGULATE | `tests/test_editor_jefe_ia_context.py` | Unit | N/A — new file | Rich bounds were authored before production mapping | `.venv/bin/python -m pytest -q tests/test_editor_jefe_ia_context.py`: exit 0, 3 passed | Distinct candidates/news prove cluster association, three-item bound, keyword 8×120 bounds, title/source/excerpt 300/100/600 bounds, null handling, ISO timestamps, title fallback, and technical-score `0.0` | Mapping helpers centralize normalization and timestamp validation |
| Slice A REFACTOR | `tests/test_editor_jefe_ia_context.py` | Unit + PostgreSQL smoke | 3/3 focused green before final regression | N/A — behavior-preserving cleanup | Focused exit 0, 3 passed; full suite exit 0, 7 passed | PostgreSQL runtime smoke used actual `get_connection` and `app.obtener_keywords_por_clusters_ids`, returned 528 bounded candidates, and closed the read-only transaction without commit | Removed redundant ISO-string resort; static forbidden-import check returned `none`; `py_compile` passed |

## Test and verification commands

1. `.venv/bin/python -m pytest -q tests/test_editor_jefe_ia_context.py` — RED exit 2, collection error because `editor_jefe_ia` did not exist.
2. `.venv/bin/python -m pytest -q tests/test_editor_jefe_ia_context.py -k 'eligibility or score or connection'` — intermediate failures exposed ranked-query alias and input-order issues; final exit 0, 1 passed, 2 deselected.
3. `.venv/bin/python -m pytest -q tests/test_editor_jefe_ia_context.py` — exit 0, 3 passed.
4. `.venv/bin/python -m pytest -q` — first exit 2 due the existing `test_crawler_common.py` process-wide `psycopg2` stub lacking `psycopg2.extras`; test isolation was added without changing production behavior. Final exit 0, 7 passed.
5. `.venv/bin/python -m pytest -q tests/test_editor_jefe_ia_context.py && .venv/bin/python -m pytest -q` — exit 0; 3 passed, then 7 passed.
6. `.venv/bin/python -m py_compile editor_jefe_ia.py tests/test_editor_jefe_ia_context.py` — exit 0.
7. Forbidden-import grep over `editor_jefe_ia.py` — no Flask, `publicador`, `publicapress`, writer, review, correction, publication, or scheduler imports.
8. PostgreSQL read-only smoke using actual `pipeline.seleccionar_publicables.get_connection` plus `app.obtener_keywords_por_clusters_ids` — exit 0, `postgres_read_only_context_candidates=528`.
9. `git diff --no-index --numstat /dev/null ...` — 158 + 212 = **370 A+D**, below 400.

## Design adherence and deviations

- Reused the exact score primitive and existing score loaders; no scoring constants or formula were copied.
- Used the injected connection factory once, its unchanged default mapping cursor behavior, one eligibility query, and one ranked `ANY(%s)` news query; no write or commit path exists.
- The ranked-news SQL uses separate `qualifying` and `ranked` CTEs so the `effective_at` alias can be used directly and validly in the window ordering. This is semantically equivalent to the design query.
- Actual Slice A size is 370 A+D, above its 215–285 forecast but still below the hard 400-line boundary. Slice B was not started.
- Runtime smoke found 528 currently eligible candidates. Slice B must account for the already-designed 48,000-byte fail-closed prompt budget; no prompt or AI behavior was added here.

## Structured status consumed

- Change: `editor-jefe-ia-v2`
- Authoritative store: OpenSpec (`both` configured; OpenSpec authoritative)
- Consumed apply state: `ready`; dependencies proposal/spec/design/tasks `all_done`; no blocked reasons.
- Action context: `repo-local`, workspace root `/home/proyectos/TRH`, allowed edit root `/home/proyectos/TRH`.
- Action-context warnings: none; every edited path is within the allowed root.
- Engram warning: the injected Engram HTTP provider was unavailable at `127.0.0.1:7437` during artifact reads; OpenSpec artifacts remained authoritative and available.

## Remaining tasks

### Slice B implementation — intentionally untouched

- [ ] **RED:** After chain strategy approval, create `tests/test_editor_jefe_ia_route.py` with failing pure-boundary tests for positive-whole-number parsing; fixed code-owned policy; compact byte-stable `json.dumps(... ensure_ascii=False, sort_keys=True, separators=(',', ':'))` payload containing every Slice A candidate's full approved score/keyword/recent-news context in server order; a strict 48,000 UTF-8-byte complete-user-payload limit that fails before HTTP without truncating candidates/context or lowering the maximum; and exact AI response validation rejecting malformed/extra/missing fields, boolean/noninteger/unknown/duplicate IDs, over-ceiling counts, and blank/control/over-240-code-point reasons without partial acceptance. Include 48,000-byte boundary and 48,001-byte cases, deterministic candidate/result ordering, and the bounded 1,200-token response allowance. Run `.venv/bin/python -m pytest -q tests/test_editor_jefe_ia_route.py -k 'maximum or prompt or budget or validation'` and record expected RED evidence. <!-- sdd-owner: implementation -->
- [ ] **GREEN:** Extend `editor_jefe_ia.py` with immutable `EDITOR_JEFE_SYSTEM_PROMPT`, compact payload serialization/budget enforcement, `OpenRouterSelectionClient` with injectable HTTP `post`, primary/fallback model and current environment conventions, bounded timeout/response allowance, strict parsing/validation, server-order result joining, and synchronous orchestration. Provider/network/non-2xx/missing-choice/invalid-JSON/budget failures must become one generic retryable feature error without logging secrets, full prompts, excerpts, or raw output; do not import `publicador` or writer/publication code. Run the focused pure-boundary tests and record exact passing evidence. <!-- sdd-owner: implementation -->
- [ ] **TRIANGULATE:** Add route-level tests in `tests/test_editor_jefe_ia_route.py` before Flask/template behavior: `GET /editor-jefe-ia` performs no retrieval or AI call and shows only form/empty state; explicit POST directly returns status 200 for complete newest-first, AI-zero, and no-eligible outcomes; invalid maximum, context/score, retrieval, payload-budget, provider/JSON, and response-validation failures render only generic retryable feedback with no partial/prior recommendation. The composition regression must pass the configured `EDITOR_JEFE_CONNECTION_FACTORY` object unchanged, exercise Slice A through runtime-equivalent `RealDictCursor` mapping rows and the same connection across eligibility/score loaders/panel keywords/news, then context → prompt → validation → HTML; assert no plain cursor, tuple indexing, redirect/`Location`, session, result cookie, persistence, mutation, or writer/publication/review/correction call, and prove GET-after-POST forgets the result. Then add only the sibling GET/POST route and explicit dependency providers in `app.py`, reusing its existing `get_connection` and `obtener_keywords_por_clusters_ids` objects; add Bootstrap `nav nav-tabs mb-4` navigation to `templates/panel_index.html` without changing existing list/actions, and create `templates/panel_editor_jefe_ia.html` with the existing Bootstrap/card vocabulary for the positive-integer form and response-local complete recommendation, valid zero, and retryable error states. Label results as AI recommendations, explain that refresh/navigation does not preserve them, and expose no downstream controls. Where a PostgreSQL DSN exists, add a rolled-back test through `pipeline.seleccionar_publicables.get_connection`; otherwise record the limitation without treating tuple fakes as production evidence. Run `.venv/bin/python -m pytest -q tests/test_editor_jefe_ia_route.py` and record exact evidence. <!-- sdd-owner: implementation -->
- [ ] **REFACTOR:** Reduce duplicated route fixtures and template shell while retaining every parser, payload-budget, strict-response, failure, response-only, side-effect, and RealDictCursor assertion. Run `.venv/bin/python -m pytest -q tests/test_editor_jefe_ia_context.py tests/test_editor_jefe_ia_route.py`, then `.venv/bin/python -m pytest -q`; run static forbidden-dependency checks over `editor_jefe_ia.py`, `app.py`, and `templates/panel_editor_jefe_ia.html`; capture Flask `test_client()` smoke evidence for GET plus success/zero/error POST; and record exact commands, exit codes, test counts, reviewed static matches, no `Location`/result-cookie/downstream calls, and GET forgetting. Measure Slice B against its selected chain base with `git diff --numstat -- editor_jefe_ia.py app.py templates/panel_index.html templates/panel_editor_jefe_ia.html tests/test_editor_jefe_ia_route.py`; stop and re-plan if additions plus deletions reach 400. <!-- sdd-owner: implementation -->

### Deferred parent lifecycle actions — preserved byte-for-byte in `tasks.md`

- [ ] After Slice A verification, run or reuse the native bounded review for Slice A's exact bytes and paths, preserve its receipt, and ensure the slice remains independently rollback-safe and below 400 changed lines. <!-- sdd-owner: parent -->
- [ ] Review Slice B as its own below-400 target after implementation, then use only the native-authorized lifecycle transitions against each slice's exact reviewed receipt before commit, push, or PR. <!-- sdd-owner: parent -->

---

## Slice B cumulative update

### Current boundary

- Authorized and completed work unit: **Slice B — synchronous recommendation surface only**.
- Delivery boundary: `stacked-to-main`; Slice B is based on local Slice A commit `acf8fdd55cb138f4730b33a5c1c1169914ed87a4` and remains local as instructed.
- Review workload: **346 additions/deletions** against `acf8fdd` (34 `app.py` + 102 `editor_jefe_ia.py` + 4 `templates/panel_index.html` + 46 `templates/panel_editor_jefe_ia.html` + 160 `tests/test_editor_jefe_ia_route.py`), below the strict 400-line limit.
- No commit, push, PR, review/lifecycle command, archive, persistence, redirect, cookie/result storage, background work, mutation, writer, reviewer, correction, or publication call was performed.

### Completed implementation tasks

- [x] Slice B RED parser, payload, budget, provider, and strict-response boundary tests.
- [x] Slice B GREEN fixed prompt, compact serializer, 48,000-byte guard, isolated OpenRouter client, response validator, and server-order joining.
- [x] Slice B TRIANGULATE sibling GET/POST route, unchanged dependency-provider objects, navigation, response-only template, and failure/forgetting tests.
- [x] Slice B REFACTOR focused/full verification, static dependency checks, Flask smoke evidence, and line-budget measurement.

The matching four Slice B implementation-owned rows are visibly checked in `tasks.md`. Parent-owned rows were preserved byte-for-byte.

### Slice B files changed

- `editor_jefe_ia.py` — strict maximum parser, immutable policy, compact/budgeted payload, dedicated OpenRouter adapter, all-or-nothing validator, and synchronous selection orchestration.
- `app.py` — sibling GET/POST route and explicit injectable context/connection/client providers.
- `templates/panel_index.html` — panel-tab navigation only.
- `templates/panel_editor_jefe_ia.html` — form plus response-local recommendation, zero, no-eligible, and retryable-error states.
- `tests/test_editor_jefe_ia_route.py` — pure boundaries, provider request, Flask composition, failures, no redirect/cookie, and GET-forgetting tests.
- `openspec/changes/editor-jefe-ia-v2/tasks.md` — checked only the four completed Slice B implementation tasks.
- `openspec/changes/editor-jefe-ia-v2/apply-progress.md` — merged this evidence after the preserved Slice A record.

### TDD Cycle Evidence — Slice B

| Task | Test file | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|
| RED | `tests/test_editor_jefe_ia_route.py` | Focused command exit 1: **24 failed, 3 deselected** because Slice A exposed none of the new parser/prompt/budget/validation symbols. | See GREEN. | Boundary cases included exact 48,000/48,001 UTF-8 bytes, booleans, malformed/extra fields, duplicates, unknown IDs, control characters, 240/241 reason limits, and server ordering. | Parameterized invalid cases keep the boundary suite compact. |
| GREEN | `tests/test_editor_jefe_ia_route.py` | Same RED evidence. | Focused pure-boundary command exit 0: **24 passed, 3 deselected**. | Dedicated adapter asserts fixed system policy, JSON response mode, and 1,200-token allowance without importing writer/publication modules. | Provider fallback and validation share one generic `FeatureError` boundary without logging raw provider data. |
| TRIANGULATE | `tests/test_editor_jefe_ia_route.py` | Full route suite exit 1: **2 failed, 25 passed**, both expected 404s before route/template production existed. | After the sibling route and templates, route suite exit 0: **27 passed**, then provider/invalid-response triangulation exit 0: **28 passed**. | GET performs no builder/client work; POST success/AI-zero/no-eligible/error render directly with status 200; configured factory identity is unchanged; no `Location` or `Set-Cookie`; GET forgets prior output. | One template shell handles all response-local states; no downstream controls exist. |
| REFACTOR | context + route + full suite | Safety net was 28/28 route tests green before final provider-shape guard. | Final route exit 0: **29 passed**; context+route exit 0: **32 passed**; full suite exit 0: **36 passed**. | Flask smoke: GET/success/zero/error all 200; success label, valid-zero text, generic retryable text, no location/cookies, and GET forgetting all true. | `py_compile` exit 0; forbidden-dependency checks returned no feature-module, route, or template matches; size **346 A+D**. |

### Slice B commands and exact evidence

1. `.venv/bin/python -m pytest -q tests/test_editor_jefe_ia_route.py -k 'maximum or prompt or budget or validation'` — RED exit 1, 24 failed, 3 deselected.
2. Same focused command after production boundaries — exit 0, 24 passed, 3 deselected.
3. `.venv/bin/python -m pytest -q tests/test_editor_jefe_ia_route.py` before route/template production — exit 1, 2 failed, 25 passed (expected GET/POST 404s).
4. Same route command after composition — exit 0, 27 passed; after provider/invalid-response triangulation — exit 0, 28 passed.
5. Final regression chain: route suite exit 0, 29 passed; `.venv/bin/python -m pytest -q tests/test_editor_jefe_ia_context.py tests/test_editor_jefe_ia_route.py` — exit 0, 32 passed.
6. `.venv/bin/python -m pytest -q` — exit 0, 36 passed.
7. `.venv/bin/python -m py_compile editor_jefe_ia.py app.py tests/test_editor_jefe_ia_route.py` — exit 0.
8. Static forbidden-dependency grep over `editor_jefe_ia.py`, the new `app.py` route block, and `templates/panel_editor_jefe_ia.html` — exit 0, no matches.
9. Flask `test_client()` smoke — exit 0: GET/success/zero/error status 200; `Location=None`; `Set-Cookie=[]`; GET forgetting true; success/zero/retryable states true.
10. `git diff --numstat acf8fdd` for tracked Slice B paths plus `git diff --no-index --numstat /dev/null` for new template/test — 34 + 102 + 4 + 46 + 160 = **346 additions/deletions**, below 400.

### Design adherence and deviations — Slice B

- The payload uses the specified compact deterministic JSON settings and includes complete Slice A candidate mappings without truncation; the complete user payload fails closed above 48,000 UTF-8 bytes.
- OpenRouter uses the existing environment names, primary/fallback defaults, JSON-object response mode, timeout 70, and response allowance 1,200 through a dedicated adapter that does not import `publicador`.
- AI output is accepted only with exact object shapes, eligible unique integer/non-boolean IDs, ceiling compliance, and trimmed nonempty control-free reasons of at most 240 code points; accepted output is restored to server candidate order.
- GET is form/empty only. POST renders complete success, valid zero, no-eligible, or generic retryable error directly with status 200. No PRG, session, cookie, cache, or persistence was added.
- Route composition proves the configured connection factory object is passed unchanged into the already-tested Slice A builder. Slice A's actual PostgreSQL read-only smoke remains the runtime `RealDictCursor` evidence; no new database write or integration fixture was needed for Slice B.
- The route catches the complete request-local feature boundary to prevent provider/context details from reaching HTML; no raw prompt, excerpt, output, or secret is logged.

### Structured status consumed — Slice B

- Change: `editor-jefe-ia-v2`
- Authoritative store/status: OpenSpec; `artifactStore=openspec`, `nextRecommended=apply`, `dependencies.apply=ready`, task progress 6/12 at delegation.
- Action context: workspace root and allowed edit root `/home/proyectos/TRH`; all target files are within that root and there were no action-context warnings.
- Delivery decision: Slice B explicitly authorized; `auto-forecast`, `stacked-to-main`, local-only branch, hard `<400` Slice B budget against `acf8fdd`.
- Strict TDD: active; runner `.venv/bin/python -m pytest -q`.

### Remaining tasks

All implementation-owned Slice A and Slice B rows are complete. Deferred parent lifecycle actions remain exactly unchecked in `tasks.md`:

- [ ] After Slice A verification, run or reuse the native bounded review for Slice A's exact bytes and paths, preserve its receipt, and ensure the slice remains independently rollback-safe and below 400 changed lines. <!-- sdd-owner: parent -->
- [ ] Review Slice B as its own below-400 target after implementation, then use only the native-authorized lifecycle transitions against each slice's exact reviewed receipt before commit, push, or PR. <!-- sdd-owner: parent -->
