# Editor Jefe IA Specification

## Purpose

Provide an AI-assisted editorial workflow inside the existing panel that can persist accepted recommendations, generate articles from those saved recommendations, require human editorial approval when automated review does not pass cleanly, and render generated article previews safely in the admin UI.

## Requirements

### Requirement: Explicit recommendation requests with persistent saved results

The existing editorial panel MUST provide an Editor Jefe IA tab and MUST start recommendation selection only after an explicit action by the human operator. Accepted recommendations MUST be persisted in dedicated storage and MUST be available again on later page loads.

#### Scenario: Operator requests recommendations

- GIVEN the operator is viewing the Editor Jefe IA panel
- WHEN the operator submits a recommendation request
- THEN the system performs one explicit recommendation run
- AND GET navigation alone does not trigger recommendation selection
- AND accepted recommendations are persisted for later retrieval

### Requirement: Saved recommendations are excluded from future recommendation runs

The recommendation selector MUST avoid re-selecting clusters that are already persisted as saved recommendations.

#### Scenario: Persisted recommendation is not reconsidered

- GIVEN a cluster is already saved as an Editor Jefe IA recommendation
- WHEN the operator requests another recommendation run
- THEN that cluster is excluded from the candidate set for the new run

### Requirement: Recommendation selection is processed in batches of five

Recommendation selection MUST split the bounded candidate list into deterministic groups of at most five candidates per AI request.

#### Scenario: Request more than five candidates

- GIVEN the operator requests more than five candidate slots
- WHEN the system performs recommendation selection
- THEN the system sends one or more AI requests containing at most five candidates each
- AND the final accepted selections are combined into one result set for persistence/display

### Requirement: Saved recommendations support bulk article generation

The Editor Jefe IA panel MUST allow bulk article generation from the saved recommendation queue.

#### Scenario: Generate from saved recommendations

- GIVEN one or more recommendations are saved
- WHEN the operator starts bulk generation from Editor Jefe IA
- THEN the system attempts article generation for each saved recommendation whose current cluster state still allows generation
- AND the system reports generated, skipped, and failed outcomes

### Requirement: Editorial control allows at most one regeneration

Generated articles MUST pass through editorial control with one initial review and at most one regeneration/review retry.

#### Scenario: First review fails and retry succeeds

- GIVEN article generation succeeds
- AND the first editorial review fails
- WHEN the system regenerates the article with the review corrections
- THEN the system performs exactly one retry generation
- AND exactly one final review of that regenerated article

#### Scenario: Review still fails after retry budget is exhausted

- GIVEN the first generated article fails editorial review
- AND the regenerated article also fails review or retry-generation cannot complete cleanly
- WHEN the retry budget is exhausted
- THEN the system requires human editorial review instead of retrying again

### Requirement: `requiere_revision_editorial` is a real publication gate

The system MUST use `requiere_revision_editorial` as a real publication gate for generated articles.

#### Scenario: Review-required article cannot be published yet

- GIVEN a cluster is generated
- AND `requiere_revision_editorial` is true
- WHEN a publication action is attempted
- THEN the system blocks publication server-side
- AND the system instructs the operator to approve editorial review from the cluster detail flow

### Requirement: Human approval happens from `/cluster/<id>`

When editorial review is required, a human MUST be able to clear that gate from the cluster detail page before publication.

#### Scenario: Human approves editorial review

- GIVEN a generated cluster requires editorial review
- WHEN the operator approves the review from `/cluster/<id>`
- THEN the system clears `requiere_revision_editorial`
- AND the cluster becomes publishable again if no other publication blocker exists

### Requirement: Quick publish is available only when review is not required

The Editor Jefe IA panel MUST expose quick publish only for saved recommendations whose cluster is already generated and does not require editorial review.

#### Scenario: Quick publish is enabled

- GIVEN a saved recommendation points to a generated cluster
- AND `requiere_revision_editorial` is false
- WHEN the operator opens the quick-publish controls
- THEN the system allows inline photo selection and direct publication

#### Scenario: Quick publish is hidden behind the review gate

- GIVEN a saved recommendation points to a generated cluster
- AND `requiere_revision_editorial` is true
- WHEN the operator views the item in Editor Jefe IA
- THEN the quick-publish action is not available there
- AND the UI directs the operator to approve the review in the cluster detail

### Requirement: Prompt text and editorial rules come from env-configured files

Prompt text and editorial rules used by the workflow MUST load from files configured through environment variables, and invalid configuration MUST fail closed.

#### Scenario: Relative configured path resolves from the project root

- GIVEN a prompt or rules env var contains a relative file path
- WHEN the application loads that configuration
- THEN the path resolves relative to the project root

#### Scenario: Missing or invalid prompt/rules file

- GIVEN a required prompt or rules file is missing, unreadable, malformed, or invalid
- WHEN the application loads it
- THEN the workflow fails closed instead of silently falling back to hidden defaults

### Requirement: Generated article HTML is sanitized for panel rendering

Generated article HTML rendered in the admin panel MUST be sanitized before output.

#### Scenario: Unsafe markup is removed from the panel preview

- GIVEN a generated article contains unsafe HTML markup
- WHEN the article is rendered in the admin/editorial panel
- THEN dangerous tags, unsafe protocols, event attributes, comments, and invalid image markup are removed
- AND allowed editorial formatting remains visible to the operator

### Requirement: Existing editorial control remains human-led

The workflow MUST remain human-led even though AI assists with recommendation and generation.

#### Scenario: Automation stops at the approval gate

- GIVEN Editor Jefe IA has recommended a cluster and generated an article
- WHEN automated editorial control still requires review
- THEN the system does not auto-publish
- AND a human must explicitly approve the cluster before publication can proceed
