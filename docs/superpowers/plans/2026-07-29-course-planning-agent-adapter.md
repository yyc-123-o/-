# Course Planning Agent Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose deterministic course creation and chapter-update operations as LangChain StructuredTools plus LangGraph-compatible state nodes.

**Architecture:** A new `planning_tools.py` adapter owns Pydantic request/result contracts, canonical request/result digests, two `StructuredTool` factories, and two callable state-node factories. It delegates all path behavior to `CoursePlanner` and `DepthUpdater`; the framework layer never computes ordering, depth, or prerequisite decisions.

**Tech Stack:** Python 3.12, Pydantic 2, LangChain Core `StructuredTool`, pytest, Ruff, mypy

## Global Constraints

- Do not add `langgraph` as a runtime dependency in this slice; LangGraph accepts ordinary callable nodes.
- Do not modify path ordering, hard prerequisites, depth selection, skip rules, or update rules.
- Identical semantic inputs must produce identical request digest, result digest, and path ID.
- Completed concept IDs are set-like: reject duplicates and sort them before hashing.
- Tool functions raise validation/planning errors; node functions convert only expected errors to structured failure state.
- A failed update node must not return a replacement `path` field.

---

### Task 1: Tool Request, Result, and Audit Contracts

**Files:**
- Create: `src/skillforge_kb/agents/planning_tools.py`
- Create: `tests/unit/agents/test_planning_tools.py`

**Interfaces:**
- Consumes: `LearnerProfileSnapshot`, `PathDecision`, `PlanningError`.
- Produces: `PlanningOperation`, `CreateCoursePlanInput`, `UpdateCoursePlanInput`, `PlanningToolAudit`, `PlanningToolResult`, `build_request_digest()`.

- [ ] **Step 1: Write failing contract tests**

Create tests that instantiate both request models, reject duplicate completed IDs, and reject a `PlanningToolResult` whose path was modified after its result digest was calculated:

```python
def test_request_contracts_reject_duplicate_completed_ids(profile, existing_path) -> None:
    with pytest.raises(ValidationError, match="completed concept IDs must be unique"):
        CreateCoursePlanInput(
            profile=profile,
            completed_concept_ids=("math.linear-algebra.scalar",) * 2,
        )
    with pytest.raises(ValidationError, match="completed concept IDs must be unique"):
        UpdateCoursePlanInput(
            existing=existing_path,
            profile=profile,
            completed_concept_ids=("math.linear-algebra.scalar",) * 2,
        )


def test_result_digest_rejects_path_mutation(valid_tool_result) -> None:
    changed = valid_tool_result.path.model_copy(
        update={"generated_at": datetime(2026, 7, 30, tzinfo=UTC)}
    )
    invalid = valid_tool_result.model_copy(update={"path": changed})
    with pytest.raises(ValidationError, match="result digest"):
        PlanningToolResult.model_validate(invalid.model_dump())
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `uv run pytest tests/unit/agents/test_planning_tools.py -q`

Expected: collection fails because `skillforge_kb.agents.planning_tools` does not exist.

- [ ] **Step 3: Implement immutable contracts and canonical hashing**

Implement these exact public signatures:

```python
class PlanningOperation(StrEnum):
    CREATE = "create_course_plan"
    UPDATE = "update_course_plan"


class CreateCoursePlanInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    profile: LearnerProfileSnapshot
    completed_concept_ids: tuple[str, ...] = ()
    allow_skips: bool = True


class UpdateCoursePlanInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    existing: PathDecision
    profile: LearnerProfileSnapshot
    completed_concept_ids: tuple[str, ...]


class PlanningToolAudit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: str = "planning-tool-audit.v1"
    operation: PlanningOperation
    request_digest: str = Field(pattern=r"^request_[0-9a-f]{64}$")
    result_digest: str = Field(pattern=r"^result_[0-9a-f]{64}$")
    path_id: str = Field(pattern=r"^path_[0-9a-f]{64}$")
    profile_id: str = Field(min_length=1)
    graph_version: str = Field(min_length=1)
    policy_digest: str = Field(pattern=r"^policy_[0-9a-f]{64}$")


class PlanningToolResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: str = "planning-tool-result.v1"
    path: PathDecision
    audit: PlanningToolAudit
```

Add validators for unique completed IDs and result/audit consistency. Implement ASCII canonical JSON hashing with sorted keys and compact separators. `build_request_digest()` must accept a `PlanningOperation`, either request model, and the policy digest; it must sort `completed_concept_ids` in the hash payload.

- [ ] **Step 4: Run contract tests and verify GREEN**

Run: `uv run pytest tests/unit/agents/test_planning_tools.py -q`

Expected: all Task 1 tests pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add src/skillforge_kb/agents/planning_tools.py tests/unit/agents/test_planning_tools.py
git commit -m "feat: define planning agent contracts"
```

### Task 2: LangChain StructuredTool Factories

**Files:**
- Modify: `src/skillforge_kb/agents/planning_tools.py`
- Modify: `tests/unit/agents/test_planning_tools.py`

**Interfaces:**
- Consumes: Task 1 request/result contracts, `CoursePlanner`, `DepthUpdater`, `PlannerPolicy`, `OntologyCatalog`.
- Produces: `create_course_plan_tool()` and `update_course_plan_tool()`, each returning `StructuredTool`.

- [ ] **Step 1: Write failing tool tests**

Add tests for stable metadata, core equivalence, retry idempotency, completed-ID order independence, and update invariants:

```python
def test_create_tool_matches_planner_and_is_idempotent(catalog, profile) -> None:
    tool = create_course_plan_tool(catalog)
    payload = {"profile": profile.model_dump(mode="json")}
    first = PlanningToolResult.model_validate(tool.invoke(payload))
    second = PlanningToolResult.model_validate(tool.invoke(payload))

    assert tool.name == "create_course_plan"
    assert first == second
    assert first.path == CoursePlanner(catalog).plan(profile)


def test_update_tool_preserves_path_identity(catalog, profile) -> None:
    existing = CoursePlanner(catalog).plan(profile)
    completed = existing.nodes[0].concept_id
    result = PlanningToolResult.model_validate(
        update_course_plan_tool(catalog).invoke(
            {
                "existing": existing.model_dump(mode="json"),
                "profile": profile.model_dump(mode="json"),
                "completed_concept_ids": [completed],
            }
        )
    )

    assert result.path.path_id == existing.path_id
    assert [node.concept_id for node in result.path.nodes] == [
        node.concept_id for node in existing.nodes
    ]
```

- [ ] **Step 2: Run the new tests and verify RED**

Run: `uv run pytest tests/unit/agents/test_planning_tools.py -q`

Expected: failures report that the two tool factories are missing.

- [ ] **Step 3: Implement the two tool factories**

Implement these signatures:

```python
def create_course_plan_tool(
    catalog: OntologyCatalog,
    policy: PlannerPolicy | None = None,
) -> StructuredTool: ...


def update_course_plan_tool(
    catalog: OntologyCatalog,
    policy: PlannerPolicy | None = None,
) -> StructuredTool: ...
```

Each factory must:

1. Construct its core planner/updater once in the closure.
2. Reconstruct the matching Pydantic request inside the function.
3. Call only `CoursePlanner.plan()` or `DepthUpdater.update()` for path behavior.
4. Build a `PlanningToolResult` with canonical request and result digests.
5. Return `result.model_dump(mode="json")` for framework-safe serialization.
6. Use `StructuredTool.from_function(..., args_schema=<request type>, infer_schema=False)`.

- [ ] **Step 4: Run tool tests and verify GREEN**

Run: `uv run pytest tests/unit/agents/test_planning_tools.py -q`

Expected: all contract and tool tests pass.

- [ ] **Step 5: Commit Task 2**

```bash
git add src/skillforge_kb/agents/planning_tools.py tests/unit/agents/test_planning_tools.py
git commit -m "feat: expose deterministic planning tools"
```

### Task 3: LangGraph-Compatible State Nodes and Public Exports

**Files:**
- Modify: `src/skillforge_kb/agents/planning_tools.py`
- Modify: `src/skillforge_kb/agents/__init__.py`
- Modify: `tests/unit/agents/test_planning_tools.py`

**Interfaces:**
- Consumes: Task 2 tool factories and their serialized `PlanningToolResult` output.
- Produces: `PlanningNodeStatus`, `PlanningFailureCode`, `PlanningNodeFailure`, `CoursePlanningState`, `build_create_course_plan_node()`, `build_update_course_plan_node()`.

- [ ] **Step 1: Write failing node tests**

Add tests for successful state transitions and structured failures:

```python
def test_create_node_returns_planned_state(catalog, profile) -> None:
    update = build_create_course_plan_node(catalog)({"profile": profile})
    assert update["planning_status"] is PlanningNodeStatus.PLANNED
    assert update["path"].profile_id == profile.profile_id
    assert update["planning_audit"].path_id == update["path"].path_id
    assert update["planning_failure"] is None


def test_update_node_failure_does_not_replace_existing_path(catalog, profile) -> None:
    existing = CoursePlanner(catalog).plan(profile)
    update = build_update_course_plan_node(catalog)(
        {
            "profile": profile,
            "path": existing,
            "completed_concept_ids": ("unknown.concept",),
        }
    )
    assert update["planning_status"] is PlanningNodeStatus.FAILED
    assert update["planning_failure"].code is PlanningFailureCode.PLANNING_ERROR
    assert "path" not in update
```

- [ ] **Step 2: Run node tests and verify RED**

Run: `uv run pytest tests/unit/agents/test_planning_tools.py -q`

Expected: failures report missing node contracts/factories.

- [ ] **Step 3: Implement state and failure contracts**

Implement:

```python
class PlanningNodeStatus(StrEnum):
    PLANNED = "planned"
    UPDATED = "updated"
    FAILED = "failed"


class PlanningFailureCode(StrEnum):
    INVALID_STATE = "invalid_state"
    PLANNING_ERROR = "planning_error"


class PlanningNodeFailure(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    code: PlanningFailureCode
    operation: PlanningOperation
    message: str = Field(min_length=1)


class CoursePlanningState(TypedDict, total=False):
    profile: LearnerProfileSnapshot
    path: PathDecision
    completed_concept_ids: tuple[str, ...]
    allow_skips: bool
    planning_status: PlanningNodeStatus
    planning_audit: PlanningToolAudit | None
    planning_failure: PlanningNodeFailure | None
```

Implement the exact factories:

```python
def build_create_course_plan_node(
    catalog: OntologyCatalog,
    policy: PlannerPolicy | None = None,
) -> Callable[[CoursePlanningState], CoursePlanningState]: ...


def build_update_course_plan_node(
    catalog: OntologyCatalog,
    policy: PlannerPolicy | None = None,
) -> Callable[[CoursePlanningState], CoursePlanningState]: ...
```

Missing required state or Pydantic validation errors become `invalid_state`. Core `PlanningError` and other expected contract `ValueError` instances become `planning_error`. Success clears `planning_failure`; failure clears `planning_audit`. Update failure does not return `path`.

- [ ] **Step 4: Export the public adapter API**

Update `src/skillforge_kb/agents/__init__.py` so all public planning contracts and factories are importable from `skillforge_kb.agents`, while retaining `FakeResourceGenerator` and `ResourceGenerationTool`.

- [ ] **Step 5: Run focused tests and static checks**

Run:

```bash
uv run pytest tests/unit/agents/test_planning_tools.py -q
uv run ruff check src/skillforge_kb/agents tests/unit/agents
uv run mypy src
```

Expected: all commands exit `0`.

- [ ] **Step 6: Run the complete unit regression suite**

Run: `uv run pytest tests/unit -q`

Expected: all prior 201 tests plus the new planning adapter tests pass.

- [ ] **Step 7: Commit Task 3**

```bash
git add src/skillforge_kb/agents/planning_tools.py src/skillforge_kb/agents/__init__.py tests/unit/agents/test_planning_tools.py
git commit -m "feat: add langgraph-compatible planning nodes"
```

### Task 4: Final Contract Verification

**Files:**
- Verify: `docs/superpowers/specs/2026-07-29-course-planning-agent-adapter-design.md`
- Verify: all files changed in Tasks 1-3.

**Interfaces:**
- Consumes: completed adapter implementation.
- Produces: verified branch ready for code review.

- [ ] **Step 1: Verify full test collection**

Run: `uv run pytest --collect-only -q`

Expected: no import mismatch and all unit/integration tests are collected.

- [ ] **Step 2: Run final quality gates**

Run:

```bash
uv run pytest tests/unit -q
uv run ruff check .
uv run mypy src
```

Expected: all commands exit `0`.

- [ ] **Step 3: Review the diff against the design**

Confirm that no path algorithm changed, no `langgraph` dependency was added, every new public function is tested, and failure updates do not overwrite an existing path.

- [ ] **Step 4: Record final branch state**

Run: `git status --short && git log --oneline -5`

Expected: clean tracked worktree and separate commits for baseline repair, design, contracts, tools, and nodes.
