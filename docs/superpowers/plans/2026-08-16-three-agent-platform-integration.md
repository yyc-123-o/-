# Three-Agent Platform Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one locally runnable SkillForge platform that accepts a normalized learner profile and connects the Course Planning, Domain Retrieval, and Resource Generation Agents through an auditable LangGraph workflow, FastAPI, and a minimal web console.

**Architecture:** The course-planning branch remains the integration base. A new `skillforge_kb.platform` package owns cross-Agent contracts, idempotent run storage, adapters, and the outer LangGraph; Agent business logic remains in its current package. FastAPI exposes the workflow and serves a small framework-free console. Strict mode requires published evidence, while explicit candidate-preview mode can create a non-publishable deterministic draft.

**Tech Stack:** Python 3.12, Pydantic 2.11+, LangGraph 0.6.x, LangChain Core 0.3.x, FastAPI 0.116+, Uvicorn 0.35+, vanilla HTML/CSS/JavaScript, pytest 8.4+, Ruff 0.12+, strict mypy 1.16+.

## Global Constraints

- Exclude the Learner Profile Agent; consume `LearnerProfileSnapshot` JSON directly.
- Do not add or request an API key, model name, arbitrary filesystem path, pickle upload, or network dependency.
- LangGraph orchestrates existing deterministic components and may not recalculate path order, depth, resource allocation, or evidence status.
- The canonical identity tuple is `profile_id`, `path_id`, `graph_version`, `concept_id`, and `depth`; all downstream results must match it exactly.
- `strict` is the default execution mode and may call formal generation only when `GenerationGate.allowed` is true.
- `candidate_preview` may create only a non-publishable `candidate_draft`; it must not change `GenerationGate.allowed` or promote candidate evidence.
- Never deserialize teammate pickle or FAISS artifacts in the platform process.
- Do not merge `main` or `agent/cnn-resource-candidate-demo` wholesale; import only reviewed modules and tests.
- Every run must be idempotent by `(profile_id, idempotency_key)` and retain ordered audit records.
- New unit and end-to-end tests must run without Docker, Neo4j, PostgreSQL, Qdrant, an API key, or network access.

## File Map

| Path | Responsibility |
|---|---|
| `src/skillforge_kb/agents/retrieval_agent_models.py` | Canonical retrieval request, evidence, gap, summary, and result contracts. |
| `src/skillforge_kb/agents/retrieval_agent.py` | Typed Domain Retrieval Agent over the existing BM25 tool, candidate corpus, and published evidence index. |
| `src/skillforge_kb/resources/controlled_generation.py` | Selectively imported resource-team controlled generation and audit contracts. |
| `src/skillforge_kb/agents/resource_agent.py` | Strict and candidate-preview adapters around existing resource-generation implementations. |
| `src/skillforge_kb/platform/models.py` | Public platform request, status, failure, audit, and result models. |
| `src/skillforge_kb/platform/ports.py` | Planning, retrieval, resource, clock, and run-repository protocols. |
| `src/skillforge_kb/platform/repository.py` | Thread-safe in-memory idempotent run repository. |
| `src/skillforge_kb/platform/graph.py` | Outer LangGraph nodes and conditional routing. |
| `src/skillforge_kb/platform/runtime.py` | Default dependency loading and application service facade. |
| `src/skillforge_kb/api/app.py` | FastAPI factory, JSON endpoints, and frontend routes. |
| `src/skillforge_kb/api/static/index.html` | Operational console structure. |
| `src/skillforge_kb/api/static/app.css` | Responsive, restrained console presentation. |
| `src/skillforge_kb/api/static/app.js` | Profile upload, run submission, and result rendering. |

---

### Task 1: Land the Existing Course-Agent Handoff Baseline

**Files:**
- Modify: `src/skillforge_kb/resources/models.py`
- Modify: `src/skillforge_kb/resources/briefs.py`
- Create: `src/skillforge_kb/resources/handoff.py`
- Modify: `src/skillforge_kb/agents/resource_tools.py`
- Create: `src/skillforge_kb/agents/feedback.py`
- Modify: `src/skillforge_kb/resources/__init__.py`
- Modify: `src/skillforge_kb/agents/__init__.py`
- Modify: `src/skillforge_kb/planning/__init__.py`
- Test: `tests/unit/agents/test_resource_generation_gate.py`
- Test: `tests/unit/agents/test_resource_handoff.py`
- Test: `tests/unit/planning/test_feedback.py`
- Test: `tests/unit/integration/test_personalized_resource_flow.py`
- Test: `tests/unit/resources/test_briefs.py`

**Interfaces:**
- Consumes: existing `PathDecision`, `LearnerProfileSnapshot`, `ResourceBrief`, and `EvidenceIndex`.
- Produces: `GenerationGate`, `ResourceHandoffContract.from_brief(...)`, `ResourceBriefBuilder.build_handoff(...)`, formal generation rejection for blocked handoffs, and `PlanningFeedbackCoordinator`.

- [ ] **Step 1: Inspect the existing local delta and confirm only known course-agent files are selected**

Run:

```powershell
git status --short
git diff -- src/skillforge_kb/resources src/skillforge_kb/agents src/skillforge_kb/planning tests/unit/resources tests/unit/agents tests/unit/planning tests/unit/integration
```

Expected: the delta contains the gate, handoff, feedback coordinator, exports, and their focused tests; unrelated untracked team documents and ZIP files remain outside the selection.

- [ ] **Step 2: Run the focused handoff and feedback contract suite**

Run:

```powershell
uv run pytest tests/unit/agents/test_resource_generation_gate.py tests/unit/agents/test_resource_handoff.py tests/unit/planning/test_feedback.py tests/unit/resources/test_briefs.py tests/unit/integration/test_personalized_resource_flow.py -q
```

Expected: all selected tests pass and formal generation is proven not to invoke a generator when the gate is blocked.

- [ ] **Step 3: Run static checks over the baseline files**

Run:

```powershell
uv run ruff check src/skillforge_kb/resources src/skillforge_kb/agents src/skillforge_kb/planning tests/unit/resources tests/unit/agents tests/unit/planning
uv run mypy src/skillforge_kb/resources src/skillforge_kb/agents src/skillforge_kb/planning
```

Expected: both commands exit zero.

- [ ] **Step 4: Commit only the known baseline files**

Run:

```powershell
git add README.md reports/generated/personalized-flow-matrix.json src/skillforge_kb/agents/__init__.py src/skillforge_kb/agents/feedback.py src/skillforge_kb/agents/resource_tools.py src/skillforge_kb/planning/__init__.py src/skillforge_kb/resources/__init__.py src/skillforge_kb/resources/briefs.py src/skillforge_kb/resources/handoff.py src/skillforge_kb/resources/models.py tests/unit/agents/test_resource_generation_gate.py tests/unit/agents/test_resource_handoff.py tests/unit/integration/test_personalized_resource_flow.py tests/unit/planning/test_feedback.py tests/unit/resources/test_briefs.py
git diff --cached --name-only
git commit -m "feat: complete course agent resource handoff"
```

Expected: the staged-name list contains exactly the listed files and the commit succeeds without adding unrelated worktree content.

---

### Task 2: Import and Stabilize the Controlled Resource Generator

**Files:**
- Create: `src/skillforge_kb/resources/controlled_generation.py`
- Create: `tests/unit/resources/test_controlled_generation.py`
- Modify: `src/skillforge_kb/resources/__init__.py`

**Interfaces:**
- Consumes: resource-team implementation at `origin/agent/cnn-resource-candidate-demo`.
- Produces: `GenerationPolicy`, `ResourceGenerationBrief`, `StructuredResourceDraft`, `CandidateLearningPackage`, `FakeLLMAdapter`, `ConservativeSpanVerifier`, and `ControlledResourceGenerationService.generate(...)`.

- [ ] **Step 1: Import only the controlled-generation module and its focused tests**

Run:

```powershell
git restore --source=origin/agent/cnn-resource-candidate-demo -- src/skillforge_kb/resources/controlled_generation.py tests/unit/resources/test_controlled_generation.py
git status --short
```

Expected: only the two requested paths are added; generated reports, raw documents, binary indexes, and other resource-branch files do not appear.

- [ ] **Step 2: Run the imported tests before integration edits**

Run:

```powershell
uv run pytest tests/unit/resources/test_controlled_generation.py -q
```

Expected: controlled generation, repair, audit, candidate publication state, and no-network fake-adapter tests pass. If an imported assertion fails because it depends on an omitted branch-only module, replace that fixture dependency with an equivalent local Pydantic fixture rather than importing the unrelated module.

- [ ] **Step 3: Export only the platform-used controlled contracts**

Add these imports and names to `src/skillforge_kb/resources/__init__.py`:

```python
from .controlled_generation import (
    AllowedEvidence,
    CandidateLearningPackage,
    ControlledResourceGenerationService,
    EvidenceApprovalStatus,
    FakeLLMAdapter,
    GenerationPolicy,
    PublicationStatus,
    ResourceGenerationBrief,
    StructuredResourceDraft,
)
```

Keep `__all__` alphabetical and include exactly those names.

- [ ] **Step 4: Verify and commit the imported capability**

Run:

```powershell
uv run pytest tests/unit/resources/test_controlled_generation.py tests/unit/agents/test_resource_tools.py -q
uv run ruff check src/skillforge_kb/resources/controlled_generation.py src/skillforge_kb/resources/__init__.py tests/unit/resources/test_controlled_generation.py
uv run mypy src/skillforge_kb/resources/controlled_generation.py
git add src/skillforge_kb/resources/controlled_generation.py src/skillforge_kb/resources/__init__.py tests/unit/resources/test_controlled_generation.py
git commit -m "feat: import controlled resource generation"
```

Expected: all commands exit zero and the commit contains no resource-team generated artifacts.

---

### Task 3: Build the Canonical Domain Retrieval Agent

**Files:**
- Create: `src/skillforge_kb/agents/retrieval_agent_models.py`
- Create: `src/skillforge_kb/agents/retrieval_agent.py`
- Modify: `src/skillforge_kb/agents/__init__.py`
- Test: `tests/unit/agents/test_retrieval_agent_models.py`
- Test: `tests/unit/agents/test_retrieval_agent.py`

**Interfaces:**
- Consumes: `KnowledgeCorpus`, `KnowledgeRetrievalTool`, `EvidenceIndex`, `ResourceHandoffContract`, `ContentKind`, and canonical `DepthLevel`.
- Produces: `DomainRetrievalRequest`, `RetrievedEvidence`, `EvidenceGap`, `EvidenceSummary`, `DomainRetrievalResult`, and `DomainRetrievalAgent.retrieve(request, handoff)`.

- [ ] **Step 1: Write failing contract tests**

Create tests asserting the following exact contract behavior:

```python
def test_retrieval_result_separates_formal_and_candidate_evidence() -> None:
    result = DomainRetrievalResult(
        request=request,
        evidence=(published_definition,),
        candidate_evidence=(candidate_code,),
        concept_evidence={request.concept_id: (published_definition.evidence_key,)},
        evidence_summary=EvidenceSummary(
            formal_count=1,
            candidate_count=1,
            available_content_kinds=(ContentKind.DEFINITION,),
            missing_content_kinds=(ContentKind.CODE, ContentKind.EXERCISE),
        ),
        evidence_gap=EvidenceGap(
            missing_content_kinds=(ContentKind.CODE, ContentKind.EXERCISE),
            message="published code and exercise evidence is missing",
        ),
    )
    assert result.evidence[0].review_status is EvidenceReviewStatus.PUBLISHED
    assert result.candidate_evidence[0].evidence_status == "candidate"


def test_retrieval_result_rejects_identity_mismatch() -> None:
    with pytest.raises(ValueError, match="retrieval evidence scope"):
        DomainRetrievalResult(
            request=request,
            evidence=(published_definition.model_copy(update={"concept_id": "dl.cnn.pooling"}),),
            candidate_evidence=(),
            concept_evidence={},
            evidence_summary=empty_summary,
            evidence_gap=full_gap,
        )
```

- [ ] **Step 2: Verify contract tests fail**

Run:

```powershell
uv run pytest tests/unit/agents/test_retrieval_agent_models.py -q
```

Expected: collection fails because `retrieval_agent_models` does not exist.

- [ ] **Step 3: Implement frozen retrieval contracts**

Implement these model shapes in `retrieval_agent_models.py`:

```python
class DomainRetrievalRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    original_query: str = Field(min_length=1)
    rewritten_queries: tuple[str, ...] = Field(min_length=1)
    profile_id: str = Field(min_length=1)
    concept_id: str = Field(pattern=CONCEPT_ID_PATTERN)
    depth: DepthLevel
    top_k: int = Field(default=5, ge=1, le=20)


class RetrievedEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    evidence_key: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_title: str = Field(min_length=1)
    heading_path: tuple[str, ...] = ()
    excerpt: str = Field(min_length=1)
    locator: str = Field(min_length=1)
    score: float = Field(ge=0)
    retrieval_method: Literal["published_index", "bm25"]
    concept_id: str = Field(pattern=CONCEPT_ID_PATTERN)
    depth: DepthLevel
    content_kind: ContentKind
    review_status: EvidenceReviewStatus
    license_status: LicenseStatus
    evidence_status: Literal["formal", "candidate"]


class EvidenceSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    formal_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    available_content_kinds: tuple[ContentKind, ...]
    missing_content_kinds: tuple[ContentKind, ...]


class EvidenceGap(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    missing_content_kinds: tuple[ContentKind, ...]
    message: str = Field(min_length=1)


class DomainRetrievalResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    request: DomainRetrievalRequest
    evidence: tuple[RetrievedEvidence, ...]
    candidate_evidence: tuple[RetrievedEvidence, ...]
    concept_evidence: dict[str, tuple[str, ...]]
    evidence_summary: EvidenceSummary
    evidence_gap: EvidenceGap | None
```

Add an `after` validator that enforces request identity on every evidence item,
requires formal items to be published/allowed, requires candidate items to use
`evidence_status="candidate"`, and derives no hidden promotion from score.

- [ ] **Step 4: Write failing Agent behavior tests**

Cover three deterministic queries and the separation rule:

```python
def test_agent_queries_definition_code_and_exercise(agent, handoff) -> None:
    result = agent.retrieve(request_for(handoff), handoff)
    assert set(result.request.rewritten_queries) == {
        "卷积运算 CNN padding stride 输出尺寸",
        "PyTorch nn.Conv2d 输入输出 shape 参数",
        "卷积输出尺寸 参数量 padding stride 练习 答案",
    }
    assert {item.content_kind for item in result.candidate_evidence} == {
        ContentKind.DEFINITION,
        ContentKind.CODE,
        ContentKind.EXERCISE,
    }


def test_agent_never_promotes_candidate_hits(agent, handoff) -> None:
    result = agent.retrieve(request_for(handoff), handoff)
    assert result.evidence == ()
    assert all(item.evidence_status == "candidate" for item in result.candidate_evidence)
```

- [ ] **Step 5: Implement the retrieval Agent**

`DomainRetrievalAgent.__init__` receives `KnowledgeCorpus`,
`KnowledgeRetrievalTool`, and `EvidenceIndex`. `retrieve` must:

1. Validate `profile_id`, `concept_id`, and `depth` against the handoff.
2. Build one query for each required handoff content kind.
3. Invoke the existing BM25 tool with `concept_id`, `top_k`, and concept-name anchors.
4. Tag a returned candidate with the query's content kind without changing its candidate status.
5. Join published index records to corpus text by `chunk_id`; omit an unresolved record from formal evidence and report the gap.
6. Deduplicate by `(chunk_id, content_kind)` using highest score, then stable-sort by content kind, negative score, and chunk ID.
7. Compute formal availability and explicit missing kinds from the handoff requirements.

The constructor stores this lookup without I/O after startup:

```python
self._chunks_by_id = {chunk.chunk_id: chunk for chunk in corpus.chunks}
```

- [ ] **Step 6: Verify and commit retrieval integration**

Run:

```powershell
uv run pytest tests/unit/retrieval tests/unit/agents/test_retrieval_agent_models.py tests/unit/agents/test_retrieval_agent.py -q
uv run ruff check src/skillforge_kb/agents/retrieval_agent.py src/skillforge_kb/agents/retrieval_agent_models.py tests/unit/agents/test_retrieval_agent.py tests/unit/agents/test_retrieval_agent_models.py
uv run mypy src/skillforge_kb/agents/retrieval_agent.py src/skillforge_kb/agents/retrieval_agent_models.py
git add src/skillforge_kb/agents/retrieval_agent.py src/skillforge_kb/agents/retrieval_agent_models.py src/skillforge_kb/agents/__init__.py tests/unit/agents/test_retrieval_agent.py tests/unit/agents/test_retrieval_agent_models.py
git commit -m "feat: add canonical domain retrieval agent"
```

Expected: all commands exit zero.

---

### Task 4: Wrap Strict and Candidate-Preview Resource Generation

**Files:**
- Create: `src/skillforge_kb/agents/resource_agent.py`
- Modify: `src/skillforge_kb/agents/__init__.py`
- Test: `tests/unit/agents/test_resource_agent.py`

**Interfaces:**
- Consumes: `LearnerProfileSnapshot`, `ResourceHandoffContract`, `DomainRetrievalResult`, `EvidenceBundle`, `ResourceGenerationTool`, and controlled-generation contracts from Task 2.
- Produces: `ResourceGenerationMode`, `ResourceAgentResult`, and `ResourceGenerationAgent.generate_strict(...)` / `generate_preview(...)`.

- [ ] **Step 1: Write failing strict and preview tests**

```python
def test_strict_generation_uses_formal_tool(resource_agent, allowed_handoff, bundle) -> None:
    result = resource_agent.generate_strict(allowed_handoff, bundle)
    assert result.mode is ResourceGenerationMode.STRICT
    assert result.formal_package is not None
    assert result.preview_package is None
    assert result.publication_status == "formal"


def test_preview_does_not_open_formal_gate(resource_agent, profile, blocked_handoff, retrieval) -> None:
    result = resource_agent.generate_preview(profile, blocked_handoff, retrieval)
    assert blocked_handoff.generation_gate.allowed is False
    assert result.formal_package is None
    assert result.preview_package is not None
    assert result.publication_status == "candidate_draft"


def test_preview_rejects_hard_prerequisite_block(resource_agent, profile, hard_blocked, retrieval) -> None:
    with pytest.raises(ValueError, match="hard prerequisites"):
        resource_agent.generate_preview(profile, hard_blocked, retrieval)
```

- [ ] **Step 2: Verify tests fail**

Run:

```powershell
uv run pytest tests/unit/agents/test_resource_agent.py -q
```

Expected: collection fails because `resource_agent` does not exist.

- [ ] **Step 3: Implement the resource adapter contracts**

Use frozen Pydantic models:

```python
class ResourceGenerationMode(StrEnum):
    STRICT = "strict"
    CANDIDATE_PREVIEW = "candidate_preview"


class ResourceAgentResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    mode: ResourceGenerationMode
    profile_id: str = Field(min_length=1)
    path_id: str = Field(pattern=r"^path_[0-9a-f]{64}$")
    graph_version: str = Field(min_length=1)
    concept_id: str = Field(pattern=CONCEPT_ID_PATTERN)
    depth: DepthLevel
    publication_status: Literal["formal", "candidate_draft"]
    formal_package: ValidatedResourcePackage | None = None
    preview_package: CandidateLearningPackage | None = None
```

Its validator requires exactly one package, matches that package to the selected
mode, and keeps the handoff identity fields.

- [ ] **Step 4: Implement strict generation**

`generate_strict` performs no translation of the planning contract:

```python
package = ResourceGenerationTool().invoke(
    ResourceBrief.model_validate(handoff.model_dump()),
    bundle,
    FakeResourceGenerator(),
)
```

Return the package only after checking handoff and bundle identity. A blocked
gate must fail before the generator is called.

- [ ] **Step 5: Implement deterministic candidate preview**

`generate_preview` must reject hard-prerequisite blockers, require candidate
definition/code/exercise evidence, and build `AllowedEvidence` with
`EvidenceApprovalStatus.CANDIDATE`. Build `GenerationPolicy` from the immutable
handoff and profile preferences. Build a deterministic `StructuredResourceDraft`
whose technical claims quote the selected evidence excerpts exactly and cite
only their candidate evidence keys. Then run:

```python
service = ControlledResourceGenerationService(FakeLLMAdapter(draft))
package = service.generate(generation_brief, notebook_passed=False)
```

The result must retain `PublicationStatus.CANDIDATE_DRAFT` even when structural
audit passes. It must never construct `EvidenceBundle` from candidates.

- [ ] **Step 6: Verify and commit the resource Agent**

Run:

```powershell
uv run pytest tests/unit/agents/test_resource_agent.py tests/unit/agents/test_resource_generation_gate.py tests/unit/resources/test_controlled_generation.py -q
uv run ruff check src/skillforge_kb/agents/resource_agent.py tests/unit/agents/test_resource_agent.py
uv run mypy src/skillforge_kb/agents/resource_agent.py
git add src/skillforge_kb/agents/resource_agent.py src/skillforge_kb/agents/__init__.py tests/unit/agents/test_resource_agent.py
git commit -m "feat: adapt controlled resource generation"
```

Expected: all commands exit zero.

---

### Task 5: Define Platform Contracts and Idempotent Storage

**Files:**
- Create: `src/skillforge_kb/platform/__init__.py`
- Create: `src/skillforge_kb/platform/models.py`
- Create: `src/skillforge_kb/platform/ports.py`
- Create: `src/skillforge_kb/platform/repository.py`
- Test: `tests/unit/platform/__init__.py`
- Test: `tests/unit/platform/test_models.py`
- Test: `tests/unit/platform/test_repository.py`

**Interfaces:**
- Consumes: canonical profile, planning, retrieval, handoff, and resource results from Tasks 1 through 4.
- Produces: public run request/result contracts, protocol boundaries, stable digests/IDs, and `InMemoryPlatformRunRepository`.

- [ ] **Step 1: Write failing request, identity, and status tests**

```python
def test_request_builds_stable_digest_and_run_id(profile) -> None:
    request = PlatformRunRequest(
        profile=profile,
        idempotency_key="demo-run-1",
        execution_mode=ExecutionMode.STRICT,
        top_k=5,
    )
    assert build_run_id(request) == build_run_id(request.model_copy())
    assert build_request_digest(request).startswith("request_")


def test_completed_result_requires_resources(base_result) -> None:
    with pytest.raises(ValueError, match="completed run requires resources"):
        PlatformRunResult(**base_result, status=PlatformRunStatus.COMPLETED)


def test_blocked_result_requires_gap_and_no_resources(base_result, gap) -> None:
    result = PlatformRunResult(
        **base_result,
        status=PlatformRunStatus.BLOCKED,
        evidence_gap=gap,
    )
    assert result.resources is None
```

- [ ] **Step 2: Verify model tests fail**

Run:

```powershell
uv run pytest tests/unit/platform/test_models.py -q
```

Expected: collection fails because `skillforge_kb.platform` does not exist.

- [ ] **Step 3: Implement the public platform models**

Define:

```python
class ExecutionMode(StrEnum):
    STRICT = "strict"
    CANDIDATE_PREVIEW = "candidate_preview"


class PlatformRunStatus(StrEnum):
    PENDING = "pending"
    PLANNING = "planning"
    RETRIEVING = "retrieving"
    BLOCKED = "blocked"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class PlatformStage(StrEnum):
    VALIDATE_INPUT = "validate_input"
    PLAN_COURSE = "plan_course"
    RETRIEVE_EVIDENCE = "retrieve_evidence"
    BUILD_HANDOFF = "build_handoff"
    EVALUATE_GATE = "evaluate_generation_gate"
    GENERATE_RESOURCE = "generate_resource"
    VALIDATE_RESOURCE = "validate_resource"
    FINALIZE = "finalize"


class PlatformRunRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    profile: LearnerProfileSnapshot
    idempotency_key: str = Field(min_length=1, max_length=128)
    execution_mode: ExecutionMode = ExecutionMode.STRICT
    top_k: int = Field(default=5, ge=1, le=20)
```

Also implement frozen `PlatformFailure`, `PlatformStepRecord`, and
`PlatformRunResult`. The result stores `CoursePlanningAgentResult`,
`DomainRetrievalResult`, `ResourceHandoffContract`, `ResourceAgentResult`,
`EvidenceGap`, and ordered steps as optional fields with status-dependent
validators. Use canonical sorted JSON and SHA-256 for `request_...` and
`run_...` identities.

The concrete result field names are:

```python
class PlatformRunResult(BaseModel):
    run_id: str
    request_digest: str
    profile_id: str
    status: PlatformRunStatus
    planning: CoursePlanningAgentResult | None = None
    retrieval: DomainRetrievalResult | None = None
    handoff: ResourceHandoffContract | None = None
    resources: ResourceAgentResult | None = None
    evidence_gap: EvidenceGap | None = None
    failure: PlatformFailure | None = None
    steps: tuple[PlatformStepRecord, ...] = ()
```

The `after` validator requires planning and a handoff for every non-input
terminal state, requires `evidence_gap` and forbids `resources` for
`blocked`, requires `resources` for `completed`, and requires `failure` for
`failed`.

- [ ] **Step 4: Write failing repository idempotency tests**

```python
def test_repository_replays_identical_request(repository, request, result) -> None:
    assert repository.reserve(request) is None
    repository.save(result)
    assert repository.reserve(request) == result


def test_repository_rejects_key_reuse_with_different_payload(repository, request) -> None:
    repository.reserve(request)
    changed = request.model_copy(update={"top_k": request.top_k + 1})
    with pytest.raises(IdempotencyConflict):
        repository.reserve(changed)
```

- [ ] **Step 5: Implement protocols and thread-safe repository**

`ports.py` defines `PlanningAgentPort`, `RetrievalAgentPort`,
`ResourceAgentPort`, `PlatformRunRepository`, and `Clock`. `repository.py` uses
one `threading.RLock` and two maps: `(profile_id, idempotency_key)` to request
digest/run ID, and run ID to result. `reserve(request)` returns an existing
result for an identical completed request, returns `None` for a new reservation,
and raises `IdempotencyConflict` for a digest mismatch. The first release's
`PlatformService` holds its own `RLock` across reserve, graph execution, and save,
which deliberately serializes in-process runs and prevents duplicate concurrent
execution. Repository reads remain independently locked.

- [ ] **Step 6: Verify and commit contracts/storage**

Run:

```powershell
uv run pytest tests/unit/platform/test_models.py tests/unit/platform/test_repository.py -q
uv run ruff check src/skillforge_kb/platform tests/unit/platform
uv run mypy src/skillforge_kb/platform
git add src/skillforge_kb/platform tests/unit/platform
git commit -m "feat: add platform run contracts and storage"
```

Expected: all commands exit zero.

---

### Task 6: Build the Outer LangGraph and Runtime

**Files:**
- Create: `src/skillforge_kb/platform/graph.py`
- Create: `src/skillforge_kb/platform/runtime.py`
- Modify: `src/skillforge_kb/platform/__init__.py`
- Test: `tests/unit/platform/test_graph.py`
- Test: `tests/unit/platform/test_runtime.py`

**Interfaces:**
- Consumes: platform contracts/ports, `CoursePlanningAgent`, `ResourceBriefBuilder`, `DomainRetrievalAgent`, `ResourceGenerationAgent`, ontology/blueprint/evidence/corpus loaders.
- Produces: `build_platform_graph(...)`, `PlatformService.run(request)`, `PlatformService.peek(request)`, `PlatformService.get(run_id)`, and `build_default_platform_service(project_root)`.

- [ ] **Step 1: Write failing graph-route tests using recording fakes**

```python
def test_strict_gap_blocks_without_calling_resource_agent(graph_case) -> None:
    result = graph_case.service.run(graph_case.strict_request)
    assert result.status is PlatformRunStatus.BLOCKED
    assert graph_case.resource.calls == []
    assert [step.stage for step in result.steps][-1] is PlatformStage.FINALIZE


def test_candidate_preview_runs_only_without_hard_blockers(graph_case) -> None:
    result = graph_case.service.run(graph_case.preview_request)
    assert result.status is PlatformRunStatus.COMPLETED
    assert result.resources.mode is ResourceGenerationMode.CANDIDATE_PREVIEW
    assert len(graph_case.resource.preview_calls) == 1


def test_identity_mismatch_fails_before_generation(graph_case) -> None:
    graph_case.retrieval.return_mismatched_concept = True
    result = graph_case.service.run(graph_case.strict_request)
    assert result.status is PlatformRunStatus.FAILED
    assert result.failure.code == "contract_mismatch"
    assert graph_case.resource.calls == []
```

- [ ] **Step 2: Verify graph tests fail**

Run:

```powershell
uv run pytest tests/unit/platform/test_graph.py -q
```

Expected: collection fails because `platform.graph` does not exist.

- [ ] **Step 3: Implement the graph state and nodes**

Use a `TypedDict(total=False)` named `PlatformGraphState` with validated request,
planning, retrieval, handoff, resources, failure, status, and tuple of step
records. Compile exactly these nodes:

```text
validate_input -> plan_course -> build_handoff -> retrieve_evidence
-> evaluate_generation_gate
   -> blocked_finalize
   -> preview_generate -> validate_resource -> completed_finalize
   -> strict_generate -> validate_resource -> completed_finalize
```

The planning node creates an initialize event with a stable event ID:

```python
event_id = "event_" + sha256(build_request_digest(request).encode("utf-8")).hexdigest()
event = PlanningAgentEvent(
    event_id=event_id,
    kind=PlanningEventKind.INITIALIZE,
    profile=request.profile,
)
planning = planning_agent.invoke(event, thread_id=run_id)
```

Build `ResourceBriefBuilder` only after planning returns its path and
adaptations. Strict generation requires both `GenerationGate.allowed` and a
retrieval result with complete formal definition/code/exercise coverage; an
unresolved formal excerpt remains a retrieval gap and blocks generation. In
candidate-preview mode route to generation only when the sole gate blocker is
`blocked_missing_published_evidence` and all required candidate content kinds
are present. Catch domain validation errors at the node boundary, map them to
stable `PlatformFailure` codes, and retain completed upstream data.

- [ ] **Step 4: Implement idempotent PlatformService**

`PlatformService.run` acquires the service `RLock` and calls
`repository.reserve` first. It invokes the graph only for a new request,
validates the final state as `PlatformRunResult`, saves it, and returns it. An
identical replay returns the saved object without invoking an Agent.
`peek(request)` returns an existing identical result without reserving or raises
on a conflicting digest; `get(run_id)` delegates to the repository.

- [ ] **Step 5: Write and implement runtime dependency-loading tests**

Test a temporary project root containing the four ontology files, evidence
manifest, and JSONL corpus. `build_default_platform_service` must load and
validate them once, build a planning Agent without its internal knowledge tool,
build the separate Domain Retrieval Agent with BM25, and inject the controlled
Resource Generation Agent. Missing files must identify the exact required path
without exposing arbitrary traversal.

- [ ] **Step 6: Verify and commit orchestration**

Run:

```powershell
uv run pytest tests/unit/platform/test_graph.py tests/unit/platform/test_runtime.py -q
uv run ruff check src/skillforge_kb/platform tests/unit/platform
uv run mypy src/skillforge_kb/platform
git add src/skillforge_kb/platform tests/unit/platform
git commit -m "feat: orchestrate three agent workflow"
```

Expected: strict-blocked, candidate-preview, formal-complete, failed, and replay routes all pass.

---

### Task 7: Expose FastAPI and the Serve Command

**Files:**
- Create: `src/skillforge_kb/api/__init__.py`
- Create: `src/skillforge_kb/api/app.py`
- Modify: `src/skillforge_kb/cli.py`
- Test: `tests/unit/api/__init__.py`
- Test: `tests/unit/api/test_app.py`
- Modify: `tests/unit/test_cli.py`

**Interfaces:**
- Consumes: `PlatformService`, `PlatformRunRequest`, and `PlatformRunResult`.
- Produces: `create_app(service)`, `create_default_app()`, four HTTP routes, and `skillforge-kb platform-serve`.

- [ ] **Step 1: Write failing API tests**

```python
def test_create_run_returns_201_and_structured_result(client, profile_payload) -> None:
    response = client.post(
        "/api/v1/runs",
        json={
            "profile": profile_payload,
            "idempotency_key": "api-demo-1",
            "execution_mode": "strict",
            "top_k": 5,
        },
    )
    assert response.status_code == 201
    assert response.json()["status"] in {"blocked", "completed"}


def test_identical_replay_returns_200(client, request_payload) -> None:
    assert client.post("/api/v1/runs", json=request_payload).status_code == 201
    assert client.post("/api/v1/runs", json=request_payload).status_code == 200


def test_blocked_run_is_not_an_http_error(client, blocked_payload) -> None:
    response = client.post("/api/v1/runs", json=blocked_payload)
    assert response.status_code == 201
    assert response.json()["status"] == "blocked"
```

Also test health, 404, 409, 422, 503 mapping, event ordering, and that OpenAPI
contains `PlatformRunRequest` and `PlatformRunResult`.

- [ ] **Step 2: Verify API tests fail**

Run:

```powershell
uv run pytest tests/unit/api/test_app.py -q
```

Expected: collection fails because `skillforge_kb.api` does not exist.

- [ ] **Step 3: Implement the application factory**

`create_app(service)` creates FastAPI with no module-level runtime I/O, stores
the service on `app.state`, and implements:

```python
@app.get("/api/v1/health")
def health() -> dict[str, object]:
    return {"status": "ok", "execution_modes": ["strict", "candidate_preview"]}


@app.post("/api/v1/runs", response_model=PlatformRunResult)
def create_run(request: PlatformRunRequest, response: Response) -> PlatformRunResult:
    existed = service.peek(request) is not None
    result = service.run(request)
    response.status_code = status.HTTP_200_OK if existed else status.HTTP_201_CREATED
    return result
```

Add `GET /api/v1/runs/{run_id}` and
`GET /api/v1/runs/{run_id}/events`. Register exception handlers for
`IdempotencyConflict` (409), missing runs (404), and unexpected dependency
failure (503). Pydantic/FastAPI owns 422 validation.

- [ ] **Step 4: Add a non-interactive serve command**

Add `platform-serve` to `cli.py` with host default `127.0.0.1`, port default
`8000`, and project root default `Path.cwd()`. The command invokes:

```python
uvicorn.run(
    create_app(build_default_platform_service(project_root)),
    host=host,
    port=port,
)
```

Patch `uvicorn.run` in CLI tests; never start a real server in unit tests.

- [ ] **Step 5: Verify and commit API work**

Run:

```powershell
uv run pytest tests/unit/api/test_app.py tests/unit/test_cli.py -q
uv run ruff check src/skillforge_kb/api src/skillforge_kb/cli.py tests/unit/api tests/unit/test_cli.py
uv run mypy src/skillforge_kb/api src/skillforge_kb/cli.py
git add src/skillforge_kb/api src/skillforge_kb/cli.py tests/unit/api tests/unit/test_cli.py
git commit -m "feat: expose three agent platform api"
```

Expected: all commands exit zero.

---

### Task 8: Build the Minimal Web Console and End-to-End Acceptance

**Files:**
- Create: `src/skillforge_kb/api/static/index.html`
- Create: `src/skillforge_kb/api/static/app.css`
- Create: `src/skillforge_kb/api/static/app.js`
- Modify: `src/skillforge_kb/api/app.py`
- Create: `tests/unit/api/test_frontend.py`
- Create: `tests/unit/integration/test_three_agent_platform_flow.py`
- Create: `tests/fixtures/profile-2026-0001-demo.json`
- Modify: `README.md`

**Interfaces:**
- Consumes: the public API from Task 7 only.
- Produces: `/` operational console, responsive result views, committed demo fixture, complete local verification, and documented start command.

- [ ] **Step 1: Invoke the frontend design skill and write failing route/asset tests**

Use the existing frontend guidance to keep the console quiet, operational, and
scan-friendly. Tests must assert:

```python
def test_console_is_the_root_screen(client) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert 'id="profile-file"' in response.text
    assert 'id="run-platform"' in response.text
    assert 'id="path-view"' in response.text
    assert 'id="evidence-view"' in response.text
    assert 'id="resource-view"' in response.text


def test_static_assets_are_served(client) -> None:
    assert client.get("/static/app.css").status_code == 200
    assert client.get("/static/app.js").status_code == 200
```

- [ ] **Step 2: Verify frontend tests fail**

Run:

```powershell
uv run pytest tests/unit/api/test_frontend.py -q
```

Expected: root returns 404 because frontend assets are not implemented.

- [ ] **Step 3: Implement the operational console**

`index.html` contains one full-width application shell with:

- compact header containing `SkillForge` and current run status;
- left input pane with JSON file input, parsed profile summary, strict/preview
  segmented radio control, `top_k` numeric input, and one run button;
- main result pane with a stable audit timeline and tabs for path, evidence,
  resources, and raw JSON;
- empty, loading, blocked, failed, and completed states occupying stable layout
  dimensions;
- persistent `candidate_draft / 不可发布` label on preview resources.

Use semantic buttons, tabs, tables, radio controls, and status text. Use Lucide
icons only if the existing static strategy can load them without adding a build
step; otherwise use labeled text controls. Cards are limited to repeated
evidence/resource records and use at most 8px radius. No landing-page hero,
decorative gradients, nested cards, instructional feature copy, or viewport-
scaled typography.

- [ ] **Step 4: Implement browser behavior against the public API**

`app.js` must:

1. Read one local JSON profile without uploading until Run is pressed.
2. Validate that `profile_id`, `graph_version`, and `schema_version` are present.
3. Generate a stable idempotency key with
   `crypto.subtle.digest("SHA-256", ...)` over canonical profile JSON,
   execution mode, and `top_k`, so changing any request field produces a new key.
4. POST only `profile`, `idempotency_key`, `execution_mode`, and `top_k`.
5. Render ordered path rows, formal/candidate evidence separately, evidence gaps,
   resource output, and step records.
6. Keep raw JSON escaped through `textContent`; never inject response HTML.
7. Disable the run action while a request is active and restore it on every exit.

- [ ] **Step 5: Write the three end-to-end acceptance tests**

Use the committed normalized demo profile and local fixtures:

```python
def test_strict_run_blocks_without_published_evidence(platform_service, demo_request) -> None:
    result = platform_service.run(demo_request)
    assert result.status is PlatformRunStatus.BLOCKED
    assert result.resources is None
    assert result.evidence_gap is not None


def test_candidate_preview_completes_without_publish_rights(platform_service, preview_request) -> None:
    result = platform_service.run(preview_request)
    assert result.status is PlatformRunStatus.COMPLETED
    assert result.resources.publication_status == "candidate_draft"
    assert result.resources.formal_package is None


def test_published_fixture_completes_formal_run(published_platform, demo_request) -> None:
    result = published_platform.run(demo_request)
    assert result.status is PlatformRunStatus.COMPLETED
    assert result.resources.publication_status == "formal"
    assert result.resources.formal_package is not None
```

Each test replays the request and asserts identical `run_id`, `path_id`, and
serialized output digest.

- [ ] **Step 6: Document startup and current limitations**

Add to `README.md`:

```powershell
uv sync --frozen
uv run skillforge-kb platform-serve --project-root . --host 127.0.0.1 --port 8000
```

Document that profile JSON is externally supplied, strict mode blocks without
published evidence, candidate preview is non-publishable, run history is
in-memory, and no API key is used.

- [ ] **Step 7: Run complete automated verification**

Run:

```powershell
uv run pytest tests/unit -q
uv run ruff check src tests/unit
uv run mypy src/skillforge_kb
```

Expected: all commands exit zero with no failed tests, Ruff findings, or mypy errors.

- [ ] **Step 8: Start the platform and perform browser QA**

Run:

```powershell
uv run skillforge-kb platform-serve --project-root . --host 127.0.0.1 --port 8000
```

Use the browser QA workflow at desktop `1440x900` and mobile `390x844`. Verify
profile selection, strict blocked run, candidate preview run, every result tab,
no overlapping text, no horizontal page overflow, and a visible candidate
status. Capture screenshots and inspect the browser console for errors. Stop the
server only after QA finishes.

- [ ] **Step 9: Commit the complete platform surface**

Run:

```powershell
git add README.md src/skillforge_kb/api tests/unit/api tests/unit/integration/test_three_agent_platform_flow.py tests/fixtures/profile-2026-0001-demo.json
git commit -m "feat: add three agent platform console"
```

Expected: the commit contains frontend, acceptance tests, fixture, and documentation only.

## Final Verification Checklist

- [ ] `git status --short` contains no unexpected generated or binary files.
- [ ] The strict no-evidence test proves the resource Agent was not called.
- [ ] Candidate preview remains `candidate_draft` and non-publishable.
- [ ] Formal fixture generation preserves the canonical identity tuple.
- [ ] Identical requests reuse `run_id`, `path_id`, and output digests.
- [ ] OpenAPI includes run request/result schemas and four versioned endpoints.
- [ ] Desktop and mobile screenshots show no overlap, clipping, or horizontal page overflow.
- [ ] Full pytest, Ruff, and strict mypy verification exits zero.
