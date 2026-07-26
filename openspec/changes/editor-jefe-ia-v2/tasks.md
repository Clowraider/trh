# Implementation Tasks: Editor Jefe IA v2

## Documentation alignment summary

This change is already implemented in the branch. These tasks reflect the implemented behavior that the OpenSpec artifacts must describe consistently.

## Implemented workflow checklist

- [x] Persist accepted Editor Jefe IA recommendations in dedicated storage.
- [x] Exclude already-saved recommendations from future recommendation runs.
- [x] Batch recommendation selection requests in groups of up to five candidates.
- [x] Load and render saved recommendations in the Editor Jefe IA panel.
- [x] Bulk-generate articles from saved recommendations.
- [x] Run editorial control after generation with at most one regeneration/review retry.
- [x] Set and preserve `requiere_revision_editorial` when editorial review does not pass cleanly.
- [x] Block publication until a human clears the review gate from `/cluster/<id>`.
- [x] Allow quick publish from Editor Jefe IA only for generated items that do not require editorial review.
- [x] Externalize prompt/rules loading to env-configured files.
- [x] Sanitize generated article HTML before rendering it in the admin panel.

## Documentation tasks

- [x] Update `proposal.md` to describe the persisted recommendation queue, bulk generation, editorial-control retry limit, publication gate, prompt/rules externalization, and sanitized rendering.
- [x] Update `design.md` to describe the implemented request flow, saved recommendation storage, batch-of-five AI calls, review gating, human approval path, quick publish rules, prompt/rules loading, and panel sanitization boundary.
- [x] Update `specs/editor-jefe-ia/spec.md` so the requirements match the implemented workflow instead of the older response-only contract.
- [x] Keep these artifacts internally consistent and avoid introducing features not present in the implementation.

## Verification tasks

- [x] Sanity-check the updated OpenSpec artifacts against the implemented Flask/editorial workflow.
- [x] Close GitHub issue #12 with a short alignment summary.
- [x] Commit and push the documentation update branch.
