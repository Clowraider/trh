# Implementation Tasks: Editor Jefe IA v2

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 455–585 additions + deletions cumulatively; Slice A 215–285, Slice B 240–300 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1: bounded read-only editorial context → PR 2: synchronous recommendation surface |
| Delivery strategy | auto-forecast |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

The cumulative scope cannot safely fit the 400-line review budget without dropping mandatory validation. Keep the two behavior-and-test slices separate, each below 400 changed lines. **Only Slice A is authorized for the next apply. Slice B remains blocked until Slice A is reviewed and integrated into `main`.**

## Chain plan

```text
main/base
  └── Slice A 📍 — bounded read-only editorial context (215–285 A+D)
        └── Slice B — synchronous recommendation surface (240–300 A+D)
```

Slice A establishes a tested, read-only context-builder contract without exposing a route. Slice B depends only on that contract and adds the user-visible flow. Each slice must keep its tests and verification evidence with its behavior, remain reviewable independently, and expose its dependency, finish state, rollback, and follow-up scope in the eventual PR description.

## Slice A — Bounded read-only editorial context

**Current apply boundary:** Slice A only.  
**Start:** Current main has no `editor_jefe_ia.py` context builder or feature tests.  
**Finish:** A tested function returns deterministic, bounded candidate mappings for every eligible pending cluster using one runtime-compatible read-only connection; there is no route, AI call, prompt, template, or UI behavior.  
**Rollback:** Remove `editor_jefe_ia.py` and `tests/test_editor_jefe_ia_context.py`; no migration, record, cache, scheduled work, or existing panel behavior requires cleanup.  
**Follow-up/out of scope:** OpenRouter, response validation, Flask composition, navigation, and rendering belong exclusively to Slice B.

- [x] **RED:** Create `tests/test_editor_jefe_ia_context.py` with failing repository tests for one dedicated eligibility query and one ranked-news `ANY(%s)` batch query: pending/null-as-pending only; publication timestamp with extraction fallback; exact `NOW() - INTERVAL '3 days'`; all eligible IDs with no requested-maximum `LIMIT`; cluster order `newest_at DESC, cluster_id DESC`; `ROW_NUMBER() OVER (PARTITION BY cluster_id ... effective_at DESC, id DESC)`, `rn <= 3`, and final stable ID tie-break; no fourth item, N+1 query, write statement, or commit. Use mapping rows shaped like runtime `RealDictCursor`, reject plain-cursor arguments and tuple indexing, run `.venv/bin/python -m pytest -q tests/test_editor_jefe_ia_context.py`, and record the expected failing test names and exit code in the Slice A apply evidence. <!-- sdd-owner: implementation -->
- [x] **GREEN:** Add only the context-building portion of `editor_jefe_ia.py`: call the exact injected `connection_factory` once, use its unchanged default `RealDictCursor` connection for eligibility, `obtener_recientes_por_cluster`, `obtener_keywords_por_cluster`, `obtener_prioridades`, `calcular_score_editorial`, the injected existing `app.obtener_keywords_por_clusters_ids` helper, and ranked qualifying news; close without commit and publish `resultado['score_final']` as `editorial_score` for every eligible cluster. Adapt `cluster_id` to `id` only where the primitive requires it; do not copy formula constants, substitute technical score, alter loader windows, or default malformed score inputs. Freeze `_ahora_utc` in parity tests and compare feature scores with direct primitive output from the same maps. Run `.venv/bin/python -m pytest -q tests/test_editor_jefe_ia_context.py -k 'eligibility or score or connection'` and record exact passing evidence. <!-- sdd-owner: implementation -->
- [x] **TRIANGULATE:** Extend `tests/test_editor_jefe_ia_context.py` before behavior changes to prove exact rich-context bounds and association: panel-helper keywords stay with their cluster, trim/discard-empty/deduplicate/Unicode-sort deterministically, use the panel-equivalent first eight, and cap each at 120 Unicode code points without replacing score keywords; recent news is newest-first and limited to three, with whitespace-normalized title/source/excerpt capped at 300/100/600 Unicode code points, null text fields becoming empty strings, and non-null effective timestamps serialized as ISO-8601; cluster title is normalized/capped at 300 with `"(Sin título)"` fallback, technical-score null matches panel `0.0`, and candidate order remains `newest_at DESC, cluster_id DESC`. Implement the smallest normalization/mapping code and rerun `.venv/bin/python -m pytest -q tests/test_editor_jefe_ia_context.py`, recording exact results. <!-- sdd-owner: implementation -->
- [x] **REFACTOR:** Consolidate mapping-row fixtures and query spies without weakening score-parity, keyword, news-bound, deterministic-order, no-N+1, no-write, and RealDictCursor guards. Keep `editor_jefe_ia.py` free of Flask route/template code and imports of `publicador`, `publicapress`, writer, review, correction, publication, scheduler, or mutation modules. Run `.venv/bin/python -m pytest -q tests/test_editor_jefe_ia_context.py` followed by `.venv/bin/python -m pytest -q`; record commands, exit codes, pass/skip/fail counts, and any PostgreSQL limitation. Measure Slice A with `git diff --numstat -- editor_jefe_ia.py tests/test_editor_jefe_ia_context.py`; stop and re-plan if additions plus deletions reach 400. <!-- sdd-owner: implementation -->

## Slice B — Synchronous recommendation surface

**Dependency:** Slice A must be complete, reviewed, and available according to the selected chain strategy.  
**Start:** Slice A exposes deterministic bounded candidate mappings but no route, provider request, or UI.  
**Finish:** The existing panel provides an explicit response-only Editor Jefe IA GET/POST flow with compact budgeted prompting, isolated OpenRouter selection, strict all-or-nothing validation, direct success/zero/error rendering, and no downstream effects.  
**Rollback:** Revert Slice B's additions to `editor_jefe_ia.py`, `app.py`, both panel templates, and `tests/test_editor_jefe_ia_route.py`; Slice A remains a harmless tested internal context builder and no data cleanup is needed.  
**Out of scope:** Persistence, PRG, session/cookies/cache/browser storage, background work, authentication, prompt editing, writing, review, correction, publication, and editorial mutation.

- [x] **RED:** After chain strategy approval, create `tests/test_editor_jefe_ia_route.py` with failing pure-boundary tests for positive-whole-number parsing; fixed code-owned policy; compact byte-stable `json.dumps(... ensure_ascii=False, sort_keys=True, separators=(',', ':'))` payload containing every Slice A candidate's full approved score/keyword/recent-news context in server order; a strict 48,000 UTF-8-byte complete-user-payload limit that fails before HTTP without truncating candidates/context or lowering the maximum; and exact AI response validation rejecting malformed/extra/missing fields, boolean/noninteger/unknown/duplicate IDs, over-ceiling counts, and blank/control/over-240-code-point reasons without partial acceptance. Include 48,000-byte boundary and 48,001-byte cases, deterministic candidate/result ordering, and the bounded 1,200-token response allowance. Run `.venv/bin/python -m pytest -q tests/test_editor_jefe_ia_route.py -k 'maximum or prompt or budget or validation'` and record expected RED evidence. <!-- sdd-owner: implementation -->
- [x] **GREEN:** Extend `editor_jefe_ia.py` with immutable `EDITOR_JEFE_SYSTEM_PROMPT`, compact payload serialization/budget enforcement, `OpenRouterSelectionClient` with injectable HTTP `post`, primary/fallback model and current environment conventions, bounded timeout/response allowance, strict parsing/validation, server-order result joining, and synchronous orchestration. Provider/network/non-2xx/missing-choice/invalid-JSON/budget failures must become one generic retryable feature error without logging secrets, full prompts, excerpts, or raw output; do not import `publicador` or writer/publication code. Run the focused pure-boundary tests and record exact passing evidence. <!-- sdd-owner: implementation -->
- [x] **TRIANGULATE:** Add route-level tests in `tests/test_editor_jefe_ia_route.py` before Flask/template behavior: `GET /editor-jefe-ia` performs no retrieval or AI call and shows only form/empty state; explicit POST directly returns status 200 for complete newest-first, AI-zero, and no-eligible outcomes; invalid maximum, context/score, retrieval, payload-budget, provider/JSON, and response-validation failures render only generic retryable feedback with no partial/prior recommendation. The composition regression must pass the configured `EDITOR_JEFE_CONNECTION_FACTORY` object unchanged, exercise Slice A through runtime-equivalent `RealDictCursor` mapping rows and the same connection across eligibility/score loaders/panel keywords/news, then context → prompt → validation → HTML; assert no plain cursor, tuple indexing, redirect/`Location`, session, result cookie, persistence, mutation, or writer/publication/review/correction call, and prove GET-after-POST forgets the result. Then add only the sibling GET/POST route and explicit dependency providers in `app.py`, reusing its existing `get_connection` and `obtener_keywords_por_clusters_ids` objects; add Bootstrap `nav nav-tabs mb-4` navigation to `templates/panel_index.html` without changing existing list/actions, and create `templates/panel_editor_jefe_ia.html` with the existing Bootstrap/card vocabulary for the positive-integer form and response-local complete recommendation, valid zero, and retryable error states. Label results as AI recommendations, explain that refresh/navigation does not preserve them, and expose no downstream controls. Where a PostgreSQL DSN exists, add a rolled-back test through `pipeline.seleccionar_publicables.get_connection`; otherwise record the limitation without treating tuple fakes as production evidence. Run `.venv/bin/python -m pytest -q tests/test_editor_jefe_ia_route.py` and record exact evidence. <!-- sdd-owner: implementation -->
- [x] **REFACTOR:** Reduce duplicated route fixtures and template shell while retaining every parser, payload-budget, strict-response, failure, response-only, side-effect, and RealDictCursor assertion. Run `.venv/bin/python -m pytest -q tests/test_editor_jefe_ia_context.py tests/test_editor_jefe_ia_route.py`, then `.venv/bin/python -m pytest -q`; run static forbidden-dependency checks over `editor_jefe_ia.py`, `app.py`, and `templates/panel_editor_jefe_ia.html`; capture Flask `test_client()` smoke evidence for GET plus success/zero/error POST; and record exact commands, exit codes, test counts, reviewed static matches, no `Location`/result-cookie/downstream calls, and GET forgetting. Measure Slice B against its selected chain base with `git diff --numstat -- editor_jefe_ia.py app.py templates/panel_index.html templates/panel_editor_jefe_ia.html tests/test_editor_jefe_ia_route.py`; stop and re-plan if additions plus deletions reach 400. <!-- sdd-owner: implementation -->

## Parent-owned chain, review, and lifecycle gates

- [x] Record Slice A as the only authorized next apply boundary under `stacked-to-main`; Slice B remains blocked until Slice A is reviewed and integrated into `main`. <!-- sdd-owner: parent -->
- [ ] After Slice A verification, run or reuse the native bounded review for Slice A's exact bytes and paths, preserve its receipt, and ensure the slice remains independently rollback-safe and below 400 changed lines. <!-- sdd-owner: parent -->
- [x] Before Slice B, record `stacked-to-main` as the sole chain strategy and bind Slice B's future base to the integrated Slice A main commit; do not mix strategies or hide polluted cross-slice diffs. <!-- sdd-owner: parent -->
- [ ] Review Slice B as its own below-400 target after implementation, then use only the native-authorized lifecycle transitions against each slice's exact reviewed receipt before commit, push, or PR. <!-- sdd-owner: parent -->
