# Align Editor Jefe IA v2 docs with the implemented editorial workflow

## Decision summary

Update the OpenSpec change artifacts so they describe the workflow that already exists in this branch: Editor Jefe IA is no longer a response-only shortlist. It now persists accepted recommendations, sends selection requests in batches of five candidates, supports bulk article generation from saved recommendations, runs editorial-control review with at most one regeneration attempt, requires human approval from `/cluster/<id>` before publication when `requiere_revision_editorial` is set, allows quick publish from Editor Jefe IA only when review is not required, externalizes prompts/rules to files configured through env vars, and sanitizes generated article HTML before rendering it in the admin panel.

## Why this change

The current proposal/spec/design still describe an intentionally smaller first slice that is advisory, transient, and read-only. The implementation moved past that boundary. Reviewers and maintainers now need the change artifacts to match the real contract so they can reason about behavior, risks, and follow-up work without reverse-engineering the branch.

## Current-state evidence

- `editor_jefe_ia.py` persists saved recommendations and splits AI selection into `SELECTION_BATCH_LIMIT` batches of five.
- `app.py` loads persisted recommendations into `/editor-jefe-ia`, exposes `/editor-jefe-ia/generar-guardadas`, enriches saved rows with current cluster state, blocks quick publish when `requiere_revision_editorial` is true, and adds `/aprobar-revision-editorial/<id>` for the human approval gate.
- `editorial_control.py` wraps article generation with one review pass plus at most one regeneration attempt, and sets `requiere_revision_editorial` when review does not pass cleanly.
- `trh/infrastructure/prompt_loader.py` resolves prompt/rules files from required env-configured paths relative to the project root.
- `trh/infrastructure/html_sanitizer.py` sanitizes generated article HTML before panel rendering.

## Scope

### In scope

- Persist Editor Jefe IA recommendations in dedicated storage so accepted recommendations survive refresh/navigation.
- Exclude already-saved recommendations from future recommendation runs.
- Send AI recommendation requests in deterministic batches of up to five candidates each.
- Allow the operator to bulk-generate articles for saved recommendations from the Editor Jefe IA panel.
- Apply editorial control to generated articles with one initial review and at most one regeneration/review retry.
- Persist and surface `requiere_revision_editorial` as a publication gate.
- Require human approval from `/cluster/<id>` before publication when editorial review is still required.
- Allow quick publish from Editor Jefe IA for generated saved recommendations only when the review gate is clear.
- Externalize prompt text and editorial rules to files configured through environment variables.
- Sanitize generated article HTML before it is rendered in admin/editorial panel views.

### Out of scope

- New product behavior beyond what is already implemented in the branch.
- Reworking scoring, recommendation ranking semantics, or publication mechanics outside the existing implementation.
- New background processing, scheduling, or multi-step workflow orchestration.

## User-visible outcome

An editorial operator can request AI recommendations, keep accepted ones in a saved queue, generate articles in bulk from that queue, review generated output through the existing cluster detail flow when required, and quick-publish directly from Editor Jefe IA only when the article is already generated and does not require editorial approval.

## Acceptance boundaries

- Recommendation selection remains explicit and on-demand.
- Saved recommendations are durable application state, not just transient HTML.
- Recommendation selection requests are processed in groups of at most five candidates.
- Bulk article generation only attempts saved recommendations whose cluster state is still eligible for generation.
- Editorial control allows at most one regeneration after a failed first review.
- `requiere_revision_editorial` blocks publication until a human clears it from `/cluster/<id>`.
- Quick publish from Editor Jefe IA is available only for generated items that do not require editorial review.
- Prompt/rules loading fails closed when required env-configured files are missing or invalid.
- Generated article HTML shown in the panel is sanitized before rendering.

## Risks and tradeoffs

- Persisted recommendations can drift from live cluster state, so the panel must enrich saved rows from the current cluster record before showing publish actions.
- Batching by five reduces request size risk but means one user action may fan out into multiple AI calls.
- Editorial control is intentionally shallow: one retry only. Remaining issues are handed back to humans instead of adding deeper autonomous loops.
- Prompt/rules externalization improves maintainability but turns file-path validation into a runtime dependency.
- Sanitized panel rendering protects the admin UI while preserving the stored article for editorial/publication use.

## Success criteria

- The change artifacts describe the persisted recommendation queue instead of a response-only result.
- The artifacts describe the real article-generation and editorial-review workflow, including the review gate.
- The artifacts document prompt/rules externalization and sanitized panel rendering.
- Reviewers can reconcile the docs with the implemented Flask routes and helper modules without seeing contradictory contracts.
