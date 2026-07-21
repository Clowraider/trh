# Add a response-only AI Editor-in-Chief selection tab

## Decision summary

Add a single **Editor Jefe IA** tab to the existing editorial panel. An editorial user explicitly starts a batch, chooses the maximum number of candidates, and receives zero through that maximum selected clusters from the preceding three days, ordered newest to oldest. Each selection shows useful information already available in the panel and a short AI reason.

This first slice is advisory and read-only. Its result exists only in the HTML response returned by the explicit POST and disappears on refresh or navigation. It does not create durable history, schedule work, invoke the writer, review or correct articles, publish content, or mutate editorial state.

## Intent

### Business problem

The editorial panel exposes many cluster candidates but leaves the human editor to inspect and prioritize them without an AI-assisted shortlist. That creates repetitive triage work and makes it harder to focus quickly on the most promising recent stories.

### Target user and situation

The target user is the human editorial operator already working in the existing Panel Editorial. The feature is used when that person wants an on-demand shortlist of recent clusters before deciding what editorial work, if any, should happen next.

### Product outcome

The operator can request a bounded batch from a visually integrated panel tab and quickly understand both what the AI selected and why. The operator remains in control: requesting a maximum does not force the AI to fill it, and no downstream action occurs automatically.

## Current-state evidence

The proposal was checked against the clean current working tree only:

- `templates/panel_index.html` is the existing Panel Editorial view and already presents cluster title, technical score, editorial score, news count, source count, recency, keywords, and publication state.
- `app.py` supplies that view from `clusters_editoriales` joined to `noticias_historico`, uses `COALESCE(fecha_publicacion, fecha_extraccion)` for recency, and currently excludes only clusters whose publication state is `descartado`.
- The current code has a visible semantics mismatch: UI copy and the function documentation say 72 hours, while the underlying query currently uses a seven-day interval. This change must implement an explicit three-day eligibility window for Editor Jefe IA rather than inherit that inconsistency.

CodeGraph's index directory exists, but no CodeGraph query tool or executable interface was available to this executor. Inspection therefore fell back to the two directly relevant working-tree files above. No abandoned change artifacts were used as product input.

## Scope

### In scope

- Add one tab, labeled and dedicated to **Editor Jefe IA**, within the existing editorial panel's navigation and visual language.
- Require explicit human action to start each selection batch.
- Let the user provide the maximum number of candidates the AI may select.
- Build the eligible input from current panel cluster semantics:
  - use existing editorial clusters backed by historical news;
  - include only clusters still pending editorial work;
  - exclude discarded, generating, generated, and published clusters;
  - determine news recency from publication date with extraction date as fallback;
  - include only clusters with qualifying news in the immediately preceding three days.
- Present eligible clusters to the AI newest to oldest. “Newest” means the most recent qualifying news timestamp associated with the cluster.
- Include richer context for every eligible cluster in the AI request: the existing panel's editorial score calculation, normalized panel keywords, and up to the three most recent qualifying news items newest first. Each news item includes its title, source, effective timestamp, and a whitespace-normalized excerpt of at most 600 Unicode characters from existing news text. The effective timestamp uses publication time with extraction time as fallback.
    - Use one fixed selection prompt/policy defined in code and include the complete approved cluster context in its payload. This richer context is for AI selection only; it adds no writing, persistence, mutation, or extra UI controls.
- Allow the AI to return any count from zero through the requested maximum.
- For every selected cluster, show a useful subset of information already available in the panel plus a short AI selection reason.
- Render the complete validated result only in the HTML response to the explicit POST; do not preserve it across refresh, navigation, or another request.
- Keep the implementation small enough to remain under the 400 changed-line review budget.

### Acceptance boundaries

- The requested maximum is a positive whole number. It is a ceiling, not a target, and cannot cause more selections than eligible clusters exist.
- A cluster outside the three-day window, a cluster not in pending editorial state, or a cluster absent from the eligible input cannot appear in the result.
- Every eligible cluster sent to the AI includes an editorial score with exact parity to the existing panel calculation/primitive and the panel's normalized cluster keywords.
    - Each eligible cluster sends no more than its three most recent qualifying news items, ordered newest first; no fourth item or excerpt beyond 600 Unicode characters enters the AI payload.
    - News context uses publication time with extraction fallback, and handles null text, source, and timestamps without inventing content or violating the item and excerpt bounds.
    - Results are ordered newest to oldest in the user-facing list, regardless of the order in which the AI returns them.
- Zero selections is a valid successful outcome and is explained as an empty result, not treated as a system failure.
- Each non-empty result identifies the cluster, provides useful existing panel context, and includes a concise AI reason.
- Starting a batch never invokes article generation, publication, review, correction, or any state-changing editorial action.
- No batch or result is written to PostgreSQL or exposed as durable history.

## Failure behavior

- If there are no eligible clusters, show a clear empty state and do not call downstream editorial actions.
- Reject invalid maximum values before requesting AI selection and explain how to correct the input.
- If cluster retrieval or the AI request fails, show a retryable error without changing cluster or publication state.
- Treat malformed AI output, selections outside the eligible set, missing reasons, or a count above the requested maximum as an invalid batch response. Fail closed rather than displaying an untrusted partial selection.
- A failed batch renders a retryable error page with no recommendation or partial result.
- The feature must not silently fall back to writer, publication, scheduled, or state-mutating behavior.

## Non-goals

- Prompt or policy editing in the UI.
- Multiple AI-editor roles or a generic AI tab.
- PostgreSQL tables, schema migrations, durable result storage, audit history, or analytics history.
- Authentication, Flask session state, cookie result storage, server caches, browser-storage preservation, or prior-result retention.
- Scheduling, recurring runs, background execution, queues, or automatic refresh.
- Invoking the existing writer or changing writer behavior.
- Article generation, editorial review, correction, approval, or publication.
- Automatically changing cluster status, publication status, priority, assignment, or any other editorial data.
- Reworking the existing editorial list, cluster detail view, writer flow, or publication flow.
- Reusing or porting the abandoned `editor-ia-v2` implementation or its SDD artifacts.

## Affected areas

| Area | Proposal-level impact |
|---|---|
| Editorial panel UX | One integrated tab, a maximum-candidate input, explicit run action, and POST-response recommendation/error/empty states. |
| Cluster retrieval | A read-only three-day candidate view aligned with current cluster identity, date fallback, and discarded-cluster exclusion semantics. |
| AI integration | One code-owned selection policy and a bounded, validated selection response with reasons, using the existing panel score, normalized keywords, and bounded recent-news context for every eligible cluster. |
| Result lifetime | Response-only HTML; no session, cookie, cache, browser-storage, or durable history. |
| Existing editorial flows | Must remain behaviorally unchanged. |

## Risks and tradeoffs

- **Eligibility difference from current code:** the panel advertises 72 hours while its query uses seven days and excludes only discarded clusters. The new tab must use the explicit three-day, pending-only contract without silently changing the existing tab's behavior.
- **AI output trust:** unconstrained or malformed model output could select ineligible clusters or exceed the human limit. The response boundary must validate identity, count, and required reasons.
- **Operator over-trust:** an AI reason may look authoritative. The UX should frame the result as a recommendation and retain explicit human control.
- **Response lifetime:** users may expect results to survive refresh or navigation. The slice intentionally keeps the result only in the POST response and should communicate that refresh/navigation loses it; browser POST resubmission behavior is not guaranteed.
- **Model latency or availability:** on-demand selection can be slow or fail. The panel needs visible progress and retryable failure behavior without background processing.
- **Scope growth:** prompt editors, history, workflow actions, and richer automation would quickly increase product risk and review size. They remain separate future decisions.
- **Review budget:** the under-400-line constraint favors reuse of existing panel data and styling over a new subsystem. If later design cannot fit safely, scope must be reduced rather than bypassing the review budget.

## Rollback

Remove the Editor Jefe IA tab and its dedicated read-only request/result path. Because the slice creates no migrations, durable records, scheduled jobs, or automatic state changes, rollback requires no data migration or cleanup. Existing writer and publication behavior must be identical before, during, and after rollback.

## Success criteria

- An editorial operator can find the Editor Jefe IA tab within the existing panel without entering a separate product surface.
- The operator can explicitly request a batch with a maximum and receive a valid zero-to-maximum shortlist.
- Every displayed selection is an eligible pending cluster from the preceding three days and appears newest to oldest.
- Every displayed selection includes useful existing panel context and a short AI reason.
- Empty, invalid-input, retrieval-failure, AI-failure, and malformed-response states are understandable and cause no editorial data mutation.
- No PostgreSQL migration or durable history is introduced.
- Existing writer and publication flows remain untouched.
- The delivered first slice remains below 400 changed lines.

## Resolved product decisions

- The recommendation exists only in the HTML response returned by the explicit POST.
- Refresh or navigation loses the result; browser POST resubmission prompts and behavior are not guaranteed.
- No authentication, Flask session, cookie storage, server cache, browser-storage preservation, PRG redirect, or prior-result preservation is part of this slice.
- No additional arbitrary product maximum applies beyond the eligible input count.
- Only pending clusters are eligible, and displayed output is explicitly labeled as an AI recommendation.
