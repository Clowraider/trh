# Apply Progress: Editor Jefe IA v2

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
