# Editor Jefe IA Specification

## Purpose

Provide an on-demand, read-only AI recommendation shortlist inside the existing editorial panel while preserving all existing editorial behavior and keeping each result limited to the HTML response returned by its explicit POST.

## Requirements

### Requirement: Existing panel tab and explicit batch initiation

The existing editorial panel MUST provide an Editor Jefe IA tab using the panel's existing context and MUST start a selection batch only after an explicit action by the human editorial operator.

#### Scenario: Operator starts a batch

- GIVEN the operator is viewing the existing editorial panel
- WHEN the operator opens the Editor Jefe IA tab and explicitly requests a batch
- THEN the system starts one on-demand selection request
- AND the system MUST NOT start selection from GET navigation, scheduling, or background execution
- AND refresh or navigation MUST NOT be relied on to preserve the POST response result

### Requirement: Pending recent cluster eligibility

A batch MUST consider only pending editorial clusters that have qualifying news published or extracted within the immediately preceding three days. The qualifying timestamp MUST use publication time when present and extraction time as the fallback. Eligible clusters MUST be presented to selection newest first by their most recent qualifying news timestamp.

#### Scenario: Build the eligible input

- GIVEN clusters contain news with publication and extraction timestamps
- WHEN the operator requests a batch
- THEN the selection input contains only pending clusters with at least one qualifying news item in the immediately preceding three days
- AND a news item's publication timestamp is used when available
- AND its extraction timestamp is used only when publication time is unavailable
- AND the eligible input is ordered from newest to oldest
- AND clusters outside the window or not pending are absent from the input

#### Scenario: No eligible clusters

- GIVEN no pending cluster has qualifying news in the preceding three days
- WHEN the operator requests a batch
- THEN the system reports a clear empty state
- AND no selection result is displayed as a recommendation
- AND no downstream editorial action occurs

### Requirement: Existing panel score and keyword context

For every eligible cluster, the AI selection context MUST include the cluster's `editorial_score` calculated with exact parity to the existing panel calculation or primitive, and the normalized cluster keywords already associated with that cluster in the panel. This context MUST NOT introduce a new scoring formula or unrelated keyword source.

#### Scenario: Preserve editorial score parity

- GIVEN an eligible cluster has an editorial score shown by the existing panel
- WHEN the system builds the AI selection context
- THEN the context includes `editorial_score`
- AND its value is calculated by reusing the exact existing panel calculation or primitive
- AND the value matches the score represented by the existing panel for that cluster

#### Scenario: Associate normalized keywords with their cluster

- GIVEN an eligible cluster has normalized keywords available to the existing panel
- WHEN the system builds the AI selection context
- THEN the context includes those normalized keywords for that same cluster
- AND keywords from another cluster or an unrelated normalization source are not associated with it

### Requirement: Bounded recent-news context

For every eligible cluster, the AI selection context MUST include no more than the three most recent qualifying news items for that cluster, ordered newest first by effective timestamp. Each item MUST contain its title, source, effective timestamp, and a whitespace-normalized excerpt of at most 600 Unicode characters from existing news text. The effective timestamp MUST use publication time when present and extraction time as its fallback. No fourth item or text beyond the 600-character excerpt bound MAY enter the AI payload.

#### Scenario: Order and limit qualifying news

- GIVEN an eligible cluster has four or more qualifying news items
- WHEN the system builds the AI selection context
- THEN it includes only the three most recent items for that cluster
- AND those items are ordered newest first by effective timestamp
- AND no fourth item enters the AI payload

#### Scenario: Build bounded excerpts

- GIVEN a qualifying news item has existing news text containing arbitrary whitespace and more than 600 Unicode characters
- WHEN the system builds its AI context
- THEN the excerpt is whitespace-normalized
- AND the excerpt contains at most 600 Unicode characters
- AND no text beyond that bound enters the AI payload

#### Scenario: Apply timestamp fallback and null handling

- GIVEN a qualifying news item has a publication timestamp
- WHEN the system builds its AI context
- THEN its effective timestamp is the publication timestamp
- GIVEN another qualifying news item has no publication timestamp but has an extraction timestamp
- WHEN the system builds its AI context
- THEN its effective timestamp is the extraction timestamp
- GIVEN title, source, or news text is null
- WHEN the system builds its AI context
- THEN the item remains bounded and valid without inventing text or timestamps
- AND null values do not cause an additional news item or unbounded excerpt to enter the AI payload

### Requirement: Complete approved context in the fixed prompt payload

The fixed, code-owned AI selection prompt MUST receive the approved context for every eligible cluster: `editorial_score`, normalized cluster keywords, and the bounded recent-news items with their title, source, effective timestamp, and excerpt. The prompt payload MUST preserve cluster association and MUST NOT omit or replace this context with a minimal field set. This AI-only context MUST NOT add writing, persistence, mutation, or extra UI controls.

#### Scenario: Include richer context for every candidate

- GIVEN the eligible input contains one or more clusters
- WHEN the system requests AI selection
- THEN the prompt payload contains the approved score, normalized keywords, and bounded recent-news context for every eligible cluster
- AND the payload contains no fourth recent-news item or excerpt exceeding 600 Unicode characters
- AND the response-only lifecycle, result display, and read-only boundaries remain unchanged

### Requirement: Positive maximum as a selection ceiling

The operator MUST provide a positive whole-number maximum for a batch. The maximum MUST be a ceiling rather than a target; the AI MAY select any number from zero through the lesser of that maximum and the number of eligible clusters, and MUST select only eligible cluster IDs. No additional arbitrary product maximum applies in this first slice.

#### Scenario: Valid bounded request

- GIVEN the operator provides a positive whole-number maximum
- WHEN the batch is requested with an eligible input
- THEN the AI may return zero or more recommendations up to the applicable ceiling
- AND the result contains no cluster ID outside the eligible input

#### Scenario: Invalid maximum

- GIVEN the operator provides a non-numeric, non-integer, zero, or negative maximum
- WHEN the operator requests a batch
- THEN the system rejects the request before AI selection
- AND the system explains that a positive whole number is required
- AND no editorial state changes

### Requirement: Fixed selection policy

Selection MUST use one fixed, code-owned AI prompt and policy for this first slice. The operator MUST NOT edit or replace that prompt or policy through the panel.

#### Scenario: Batch uses the approved policy

- GIVEN the operator starts a valid batch
- WHEN the system requests AI selection
- THEN the request uses the fixed selection prompt and policy
- AND no user-provided prompt or policy changes the selection contract

### Requirement: Recommendation presentation

Each displayed selection MUST include the existing panel context needed to identify and understand the cluster, a concise reason supplied by the AI, and explicit wording that frames the selection as an AI recommendation rather than an editorial decision or approval. A successful result containing zero selections MUST be presented as a valid empty recommendation outcome.

#### Scenario: Display a non-empty recommendation

- GIVEN a batch completes successfully with one or more selected eligible clusters
- WHEN the result is shown in the Editor Jefe IA tab
- THEN each selection includes its cluster identity, useful existing panel context, and a concise AI reason
- AND the result is explicitly labeled as a recommendation
- AND selections are shown newest first

#### Scenario: Display a zero-selection recommendation

- GIVEN a batch completes successfully with zero selected clusters
- WHEN the result is shown
- THEN the system displays a clear empty recommendation outcome
- AND it does not treat the outcome as a system failure

### Requirement: Response-only result lifetime

The system MUST render a batch outcome only in the HTML response returned by the explicit POST. A GET MUST render the form and empty state without a prior recommendation. The system MUST NOT add authentication, Flask session state, cookie result storage, server cache, browser-storage preservation, PRG redirect, prior-result preservation, PostgreSQL persistence, or any other result history. Refresh behavior MAY prompt browser POST resubmission and is explicitly not guaranteed.

#### Scenario: Successful POST response

- GIVEN the operator submits a valid explicit POST
- WHEN retrieval, AI selection, and response validation succeed
- THEN that same POST response contains the complete recommendation or valid zero-selection state
- AND no subsequent request is required to display it

#### Scenario: Navigate or load the page with GET

- GIVEN a recommendation was previously returned
- WHEN the operator navigates away, navigates back, or requests the tab with GET
- THEN the page displays the form and empty state
- AND the previous recommendation is not restored

#### Scenario: Failed POST response

- GIVEN the operator submits an explicit POST
- WHEN input validation, retrieval, AI selection, or response validation fails
- THEN that same POST response displays retryable error feedback
- AND no recommendation or partial result is displayed
- AND no prior result is restored
- AND no batch or result is persisted

### Requirement: Fail-closed AI response validation

The system MUST fail closed and display no partial selection when an AI response is malformed, contains duplicate IDs, contains an unknown or ineligible ID, omits a required reason, or exceeds the applicable maximum. A validation failure MUST leave editorial state unchanged and render only retryable error feedback in the POST response.

#### Scenario: Reject an invalid response

- GIVEN the AI returns malformed output, duplicate IDs, unknown or ineligible IDs, a selected item without a reason, or too many selections
- WHEN the system validates the response
- THEN the batch is rejected as invalid
- AND no partial selection or prior result is displayed
- AND retryable error feedback is rendered in the POST response
- AND no writer, review, correction, publication, scheduler, background process, or editorial-state mutation is triggered

### Requirement: Advisory read-only boundary

The Editor Jefe IA batch and its result MUST be advisory and read-only. The feature MUST NOT invoke article writing, review, correction, approval, or publication; schedule or run work in the background; or mutate cluster, publication, priority, assignment, or other editorial state. It MUST NOT introduce PostgreSQL persistence or migrations.

#### Scenario: Recommendation has no downstream effect

- GIVEN an operator has requested or displayed a recommendation
- WHEN the batch completes or the operator views the result
- THEN no article or editorial workflow is started automatically
- AND no scheduler or background execution is created
- AND no editorial data is changed
- AND no PostgreSQL table, migration, or durable result record is required

### Requirement: Existing panel behavior is preserved

Adding Editor Jefe IA MUST preserve the existing editorial panel, cluster detail, writer, and publication behavior outside this first-slice recommendation flow.

#### Scenario: Existing editorial flows remain unchanged

- GIVEN an operator uses an existing panel tab or editorial flow other than Editor Jefe IA
- WHEN the operator views clusters, opens details, writes, reviews, corrects, or publishes through those existing flows
- THEN those flows retain their existing behavior
- AND the Editor Jefe IA feature does not alter their editorial state or results
