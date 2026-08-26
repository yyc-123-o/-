# Three-Agent Platform Integration Design

## Status

Approved on 2026-08-16. The first platform release is a single-process FastAPI
application with a LangGraph orchestration graph, a deterministic controlled
resource generator, and a minimal web console. The Learner Profile Agent is not
part of this release; the platform accepts an already normalized learner-profile
JSON document as input.

## Goal

Connect the Course Planning Agent, Domain Retrieval Agent, and Resource
Generation Agent into one auditable workflow that can be run from an HTTP API or
the browser. Preserve each Agent's ownership boundary, enforce the existing
planning and evidence contracts, and expose both successful and blocked runs
without requiring an API key.

## Selected Approach

The platform runs as one Python process:

```text
Browser
  |
  v
FastAPI /api/v1/runs
  |
  v
Platform LangGraph
  |
  +--> CoursePlanningAgent facade
  |      -> PathDecision + current PathNode
  |
  +--> DomainRetrievalAdapter
  |      -> RetrievalResult + EvidenceBundle
  |
  +--> ResourceHandoffContract + GenerationGate
  |      |                     |
  |      | blocked             | ready
  |      v                     v
  |   structured gap      ControlledResourceGenerationAdapter
  |                             -> validated candidate package
  |
  v
RunResult + audit trail + web result view
```

FastAPI is the transport boundary and LangGraph is the orchestration boundary.
Neither layer may recalculate a path, rewrite evidence status, or synthesize
resource requirements. The existing deterministic planning, retrieval,
generation, and validation code remains responsible for domain decisions.

This release does not split the Agents into separate services. All Agent calls
are nevertheless hidden behind typed ports so a later deployment can replace an
in-process adapter with an HTTP client without changing the orchestration state
or public API.

## Source Integration Strategy

The Course Planning Agent branch is the integration base because it has the
most complete path, handoff, feedback, and generation-gate contracts. The other
branches must be imported selectively; they must not be merged wholesale.

- Reuse `CoursePlanningAgent`, `ResourceBriefBuilder`,
  `ResourceHandoffContract`, and `GenerationGate` from the course-planning
  branch.
- Adapt the teammate retrieval implementation from
  `src/skillforge_kb/domain/src/retrieval_agent.py` behind a new typed retrieval
  port. Normalize its numeric depth and legacy concept fields before they enter
  platform state. Do not expose its internal dataclasses through the API.
- Import the focused controlled-generation service and input conversion code
  from the resource branch. Use `FakeLLMAdapter` or the framework-neutral
  deterministic resource generator; do not enable `OpenAICompatibleLLMAdapter`
  in this release.
- Do not import generated reports, raw course documents, pickle indexes, FAISS
  binaries, local logs, or unrelated branch deletions.
- Retain the original Agent implementations as independently testable modules;
  platform adapters translate contracts but do not absorb their business logic.

## Component Boundaries

### Platform Contracts

`skillforge_kb.platform.models` owns only cross-Agent and API contracts:

- `PlatformRunRequest`
  - normalized `LearnerProfileSnapshot`
  - caller-supplied `idempotency_key`
  - `top_k`, constrained to 1 through 20
  - `execution_mode`, either `strict` or `candidate_preview`
- `PlatformRunStatus`
  - `pending`, `planning`, `retrieving`, `blocked`, `generating`, `completed`,
    or `failed`
- `PlatformStepRecord`
  - step name, status, started/finished timestamps, input/output digest, and
    structured failure
- `PlatformRunResult`
  - `run_id`, canonical identity fields, status, planning result, retrieval
    result, handoff, resource package, evidence gap, and ordered audit records
- `PlatformFailure`
  - stable failure code, safe message, responsible stage, retryability, and
    field-level details

The canonical identity tuple is:

```text
profile_id, path_id, graph_version, concept_id, depth
```

After planning selects the current node, every downstream result must contain
the same tuple. A mismatch is a terminal `contract_mismatch` failure and never a
warning.

### Agent Ports

`skillforge_kb.platform.ports` defines three protocols:

```python
class PlanningAgentPort(Protocol):
    def plan(self, profile: LearnerProfileSnapshot, *, thread_id: str) -> PlanningOutput: ...

class RetrievalAgentPort(Protocol):
    def retrieve(self, request: RetrievalRequest) -> RetrievalOutput: ...

class ResourceAgentPort(Protocol):
    def generate(self, request: ResourceGenerationRequest) -> ResourceGenerationOutput: ...
```

The orchestration graph depends only on these protocols. Production adapters
wrap the three current Agent implementations. Test adapters provide fixed
outputs for failure, retry, and idempotency tests.

### Domain Retrieval Adapter

The adapter receives only the planner-selected current node. It constructs a
query around the canonical concept name, aliases, prerequisites, learning
outcomes, requested resource content kinds, and delivery depth. It emits:

- original and rewritten queries;
- `profile_id`, `concept_id`, canonical string `depth`, and `top_k`;
- approved `evidence` and unapproved `candidate_evidence` as separate lists;
- `concept_evidence` keyed by the same canonical concept ID;
- an evidence summary and explicit gaps for `definition`, `code`, and
  `exercise`.

Legacy numeric depths are mapped at the adapter boundary. Retrieval hits for a
different concept may remain diagnostic candidates but cannot satisfy the
current concept's generation gate. GAN, DCGAN, TextCNN, and transposed
convolution evidence cannot satisfy standard convolution requirements.

The initial adapter may read deterministic JSONL candidate data. It must not
deserialize teammate pickle indexes in the platform process. A future Qdrant
adapter can implement the same port.

### Course Planning Adapter

The adapter invokes the public `CoursePlanningAgent` facade with a stable
LangGraph `thread_id` derived from `run_id`. It returns the existing immutable
path decision, current node, adaptations, `ResourceBrief`, and
`ResourceHandoffContract`.

The platform may not override `concept_id`, depth, node order, prerequisites,
learning outcomes, allocation, or resource types. If the profile asks for a
chapter-level label such as CNN while the selected current node is an earlier
prerequisite, the selected node remains authoritative and retrieval follows
that node.

### Resource Generation Adapter

The adapter consumes only a validated handoff and evidence bundle. In this
release it runs a deterministic controlled generator and returns lecture,
practical-guide, and assessment outputs when those types are requested.

Generated resources must preserve the canonical identity tuple, allocation,
learning outcomes, and allowed evidence IDs. Every factual claim requiring a
citation must resolve to an evidence item accepted by the active execution
mode. Output validation runs before the platform can mark the run completed.

Two execution modes are supported:

- `strict` is the default. Only reviewed, licensed, published evidence may open
  the formal `GenerationGate`. Missing evidence returns `blocked`; the resource
  generator is not called.
- `candidate_preview` is an explicit demonstration mode. It may produce a
  `candidate_draft` from structurally valid candidate evidence, but the result
  is marked non-publishable and cannot be converted to a formal package. The
  UI must display the candidate status next to every generated resource.

Candidate preview does not change `GenerationGate.allowed`; it uses a separate
preview route after the formal gate reports the expected evidence gap. This
prevents candidate material from being represented as formal evidence.

### Orchestration Graph

`skillforge_kb.platform.graph` owns one outer LangGraph with these nodes:

```text
validate_input
  -> plan_course
  -> select_current_node
  -> retrieve_evidence
  -> build_handoff
  -> evaluate_generation_gate
       -> blocked_finalize
       -> candidate_preview_generate
       -> strict_generate
  -> validate_resources
  -> completed_finalize
```

Every node appends one immutable `PlatformStepRecord`. Domain exceptions are
converted into `PlatformFailure`; raw stack traces are logged but never returned
by the API. A failure after planning retains the planning and retrieval results
already produced so the web console can explain the run.

The graph is idempotent by `(profile_id, idempotency_key)`. Repeating the same
payload returns the same `run_id`, `path_id`, and result. Reusing a key with a
different request digest returns an idempotency conflict.

## API Design

The first release exposes:

- `GET /api/v1/health`
  - process health and enabled adapter modes; no learner data
- `POST /api/v1/runs`
  - validates and executes one synchronous controlled run
  - returns HTTP 201 for a newly completed or blocked run
  - returns HTTP 200 for an identical idempotent replay
- `GET /api/v1/runs/{run_id}`
  - returns the stored structured run result
- `GET /api/v1/runs/{run_id}/events`
  - returns ordered step records for the audit timeline

Input validation errors use HTTP 422. An idempotency-key conflict uses HTTP
409. Missing runs use HTTP 404. An unexpected dependency failure uses HTTP 503
and leaves a retryable `failed` run record when a `run_id` was already assigned.
Blocked evidence is a valid domain result, not an HTTP error.

The API never accepts an API key, model name, arbitrary file-system path, or raw
pickle/index upload.

## Persistence

The first release uses an injected `InMemoryPlatformRunRepository` so the full
workflow and UI can run without Docker. The repository stores request digests,
results, and step records and is safe for concurrent calls within one process.

The repository protocol is kept separate from the graph. PostgreSQL persistence
is a later adapter and is not required for this milestone. Restarting the
development process may clear run history; the UI states this through normal
empty-state behavior rather than explanatory product copy.

## Minimal Web Console

FastAPI serves a compact operational console at `/`. It is the usable first
screen, not a landing page. It contains:

- a JSON file picker and validated profile summary;
- an execution-mode segmented control with `strict` selected by default;
- one run action;
- a stable run-status and step timeline area;
- a learning-path table with node position, chapter, section, depth, and status;
- evidence tabs separating approved evidence, candidate evidence, and gaps;
- resource tabs for lecture, practical guide, and assessment;
- a persistent candidate/non-publishable status on preview output.

The console uses server-rendered HTML plus a small static JavaScript module. No
frontend framework or Node build chain is added. It consumes only the public
API and does not import Python-domain assumptions into browser code.

## Error and Recovery Rules

- Invalid profile input stops before the planning Agent and returns field-level
  validation details.
- A planning failure stops retrieval and resource generation.
- Empty or failed retrieval produces an explicit evidence gap. In strict mode
  the run is `blocked`; in candidate-preview mode generation proceeds only when
  structurally valid candidate evidence exists.
- Any identity, graph-version, depth, node-order, scope, allocation, or citation
  mismatch produces `failed` with `contract_mismatch`.
- Generator exceptions produce a retryable `resource_generation_failed` result
  while retaining upstream outputs.
- Replaying a completed or blocked request is a read, not a second execution.
- A failed run may be retried with a new idempotency key in this release. An
  explicit retry endpoint is deferred.

## Testing Strategy

Unit tests cover:

- request and result validation, including the identity tuple;
- numeric-to-canonical depth translation and off-topic evidence isolation;
- strict and candidate-preview evidence handling;
- planning, retrieval, and resource adapter input/output preservation;
- every graph route and stable failure code;
- in-memory repository idempotency and conflict behavior;
- API response codes and OpenAPI schemas;
- frontend asset and primary-control smoke tests.

End-to-end tests use `PROFILE-2026-0001-DEMO` and
`dl.cnn.convolution` fixtures:

1. Strict mode with no published evidence ends `blocked` and proves that the
   resource generator was not invoked.
2. Candidate-preview mode produces a non-publishable lecture, practical guide,
   and assessment from controlled candidate inputs.
3. Published fixture evidence produces a completed formal package in tests
   without network access.
4. Replaying each request preserves `run_id`, `path_id`, and all output digests.

The milestone passes only when unit tests, end-to-end tests, Ruff, and strict
mypy all pass from the integration worktree. Existing service-backed Neo4j and
PostgreSQL tests remain optional integration checks.

## Out of Scope

- Learner Profile Agent runtime or profile inference.
- Real LLM calls, prompt optimization, or API-key management.
- Separate Agent deployments, queues, streaming, or distributed tracing.
- Authentication, multi-user authorization, or production persistence.
- Automatic evidence approval, license decisions, or formal publication.
- BKT, IRT, forgetting-model, adaptive-question, or knowledge-tracing changes.
- A production design system or a second frontend application.

## Acceptance Criteria

1. One command starts FastAPI and the browser console without an API key.
2. A normalized profile JSON can run through planning, retrieval, gate
   evaluation, and the appropriate blocked or generation route.
3. The current planner node, not the profile's chapter-level label, determines
   retrieval and resource scope.
4. `profile_id`, `path_id`, `graph_version`, `concept_id`, and `depth` are equal
   across every downstream contract.
5. Strict mode never calls the resource generator without reviewed, licensed,
   published evidence.
6. Candidate preview is clearly non-publishable and cannot be returned as a
   formal resource package.
7. Repeated identical calls are idempotent and conflicting reuses are rejected.
8. The web console displays the path, evidence split, gate decision, generated
   resources when available, and the ordered audit timeline.
9. All new tests and static checks pass without network or service containers.

