# Course Planning Agent State Machine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone, deterministic CoursePlanningAgent with a compiled LangGraph state machine, in-memory sessions, event idempotency, node adaptation, and structured results.

**Architecture:** Event/result contracts live in `planning_agent_models.py`; graph construction and the public sync/async agent facade live in `planning_agent.py`. LangGraph owns routing and checkpointed session state, while existing `CoursePlanner`, `DepthUpdater`, and `NodeWeightEngine` remain the only decision engines.

**Tech Stack:** Python 3.12, Pydantic 2, LangGraph 0.6.x, LangChain Core, pytest, Ruff, mypy

## Global Constraints

- Do not call external agents, models, databases, Neo4j, HTTP services, or resource generators.
- Do not require API keys, Docker, or network access at runtime.
- Do not change path ordering, hard prerequisites, skip rules, depth rules, or node-weight formulas.
- A failed event must not overwrite the last valid path, profile, or adaptation tuple.
- A duplicate `thread_id + event_id` with identical payload must be a no-op.
- An existing event ID with a different payload must fail with `event_id_conflict`.
- Dynamic adaptation may change support metadata but must not change path ID, node set, or order.

---

### Task 1: Event, State, Failure, and Result Contracts

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `src/skillforge_kb/agents/planning_agent_models.py`
- Create: `tests/unit/agents/test_planning_agent_models.py`

**Interfaces:**
- Consumes: `LearnerProfileSnapshot`, `PathDecision`, `PathNode`, `NodeAdaptationDecision`, `PlanningToolAudit`.
- Produces: `PlanningEventKind`, `PlanningAgentEvent`, `PlanningAgentStatus`, `PlanningNextAction`, `PlanningAgentFailure`, `ProcessedPlanningEvent`, `CoursePlanningAgentState`, `CoursePlanningAgentResult`, `build_event_digest()`.

- [ ] **Step 1: Write failing event contract tests**

Cover all event invariants:

```python
def test_initialize_requires_only_a_profile(profile) -> None:
    event = PlanningAgentEvent(
        event_id="event_" + "1" * 64,
        kind=PlanningEventKind.INITIALIZE,
        profile=profile,
    )
    assert event.completed_concept_ids == ()


@pytest.mark.parametrize(
    "payload",
    [
        {
            "event_id": "event_" + "2" * 64,
            "kind": PlanningEventKind.INITIALIZE,
        },
        {
            "event_id": "event_" + "3" * 64,
            "kind": PlanningEventKind.PROFILE_REFRESHED,
        },
        {
            "event_id": "event_" + "4" * 64,
            "kind": PlanningEventKind.CONCEPTS_COMPLETED,
        },
        {
            "event_id": "event_" + "5" * 64,
            "kind": PlanningEventKind.RESET,
            "profile": {"invalid": "reset must not include a profile"},
        },
    ],
)
def test_event_rejects_invalid_payload_combinations(payload) -> None:
    with pytest.raises(ValidationError):
        PlanningAgentEvent.model_validate(payload)


def test_event_digest_is_stable_and_content_sensitive(profile) -> None:
    first = PlanningAgentEvent(
        event_id="event_" + "6" * 64,
        kind=PlanningEventKind.INITIALIZE,
        profile=profile,
    )
    same = PlanningAgentEvent.model_validate(first.model_dump())
    changed = first.model_copy(
        update={"profile": profile.model_copy(update={"profile_id": "changed"})}
    )
    assert build_event_digest(first) == build_event_digest(same)
    assert build_event_digest(first) != build_event_digest(changed)
```

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run pytest tests/unit/agents/test_planning_agent_models.py -q`

Expected: import failure because `planning_agent_models` does not exist.

- [ ] **Step 3: Add LangGraph dependency**

Run: `uv add "langgraph>=0.6,<1"`

Verify `pyproject.toml` and `uv.lock` contain the resolved LangGraph packages without upgrading unrelated project constraints.

- [ ] **Step 4: Implement event and state contracts**

Implement the exact public enums and models:

```python
class PlanningEventKind(StrEnum):
    INITIALIZE = "initialize"
    PROFILE_REFRESHED = "profile_refreshed"
    CONCEPTS_COMPLETED = "concepts_completed"
    RESET = "reset"


class PlanningAgentStatus(StrEnum):
    IDLE = "idle"
    PLANNING = "planning"
    UPDATING = "updating"
    READY = "ready"
    COMPLETED = "completed"
    FAILED = "failed"


class PlanningNextAction(StrEnum):
    START_CURRENT_NODE = "start_current_node"
    WAIT_FOR_EVENT = "wait_for_event"
    COURSE_COMPLETE = "course_complete"
    RESET_REQUIRED = "reset_required"


class PlanningAgentEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal["planning-agent-event.v1"] = "planning-agent-event.v1"
    event_id: str = Field(pattern=r"^event_[0-9a-f]{64}$")
    kind: PlanningEventKind
    profile: LearnerProfileSnapshot | None = None
    completed_concept_ids: tuple[str, ...] = ()
```

Implement `PlanningAgentFailureCode`, `PlanningAgentFailure`, `ProcessedPlanningEvent`, and `CoursePlanningAgentState` exactly as specified in the design. `build_event_digest()` uses canonical ASCII JSON with sorted keys and compact separators.

- [ ] **Step 5: Implement and test result consistency**

`CoursePlanningAgentResult` must expose `thread_id`, lifecycle state, path, current node/adaptation, all adaptations, audit, failure, last event ID, and duplicate flag. Its validator requires:

- `READY` has a current node and matching adaptation.
- `COMPLETED` has no current node/adaptation.
- `IDLE` has no path.
- current node ID equals current adaptation concept ID.

- [ ] **Step 6: Verify Task 1**

Run:

```bash
uv run pytest tests/unit/agents/test_planning_agent_models.py -q
uv run ruff check src/skillforge_kb/agents/planning_agent_models.py tests/unit/agents/test_planning_agent_models.py
uv run mypy src/skillforge_kb/agents/planning_agent_models.py
```

- [ ] **Step 7: Commit Task 1**

```bash
git add pyproject.toml uv.lock src/skillforge_kb/agents/planning_agent_models.py tests/unit/agents/test_planning_agent_models.py
git commit -m "feat: define course planning agent state contracts"
```

### Task 2: Compile the LangGraph Planning Lifecycle

**Files:**
- Create: `src/skillforge_kb/agents/planning_agent.py`
- Create: `tests/unit/agents/test_planning_agent.py`

**Interfaces:**
- Consumes: Task 1 contracts, `create_course_plan_tool()`, `update_course_plan_tool()`, `OntologyCatalog`, `PlannerPolicy`.
- Produces: `build_course_planning_graph()` and an internal compiled graph that routes initialize, refresh, completion, duplicate, conflict, failure, and reset branches.

- [ ] **Step 1: Write failing lifecycle tests**

```python
def test_initialize_builds_a_ready_path(agent, profile) -> None:
    result = agent.invoke(initialize_event(profile), thread_id="student-1")
    assert result.status is PlanningAgentStatus.READY
    assert result.path is not None
    assert result.current_node is not None
    assert result.path.path_id == result.planning_audit.path_id


def test_update_before_initialize_returns_failure(agent, profile) -> None:
    result = agent.invoke(refresh_event(profile), thread_id="student-1")
    assert result.status is PlanningAgentStatus.FAILED
    assert result.path is None
    assert result.failure.code is PlanningAgentFailureCode.INVALID_TRANSITION


def test_new_initialize_after_initialize_requires_reset(agent, profile) -> None:
    agent.invoke(initialize_event(profile, event_id=event_id("first")), "student-1")
    result = agent.invoke(initialize_event(profile, event_id=event_id("second")), "student-1")
    assert result.failure.code is PlanningAgentFailureCode.INVALID_TRANSITION
```

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run pytest tests/unit/agents/test_planning_agent.py -q`

Expected: import failure for `CoursePlanningAgent`/graph builder.

- [ ] **Step 3: Implement route and path nodes**

Use:

```python
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
```

Build sequential nodes:

```text
validate_and_route_event
create_path
update_path
reset_state
record_failure
```

`validate_and_route_event` must inspect existing checkpoint state before deciding the route. Path nodes invoke the existing LangChain tools and return Pydantic `PathDecision`/`PlanningToolAudit`, not JSON dictionaries.

- [ ] **Step 4: Implement conditional edges**

Map route values to create, update, reset, or `END`. After create/update, branch to `END` on structured failure and to the later adaptation node on success.

- [ ] **Step 5: Verify Task 2 lifecycle tests**

Run: `uv run pytest tests/unit/agents/test_planning_agent.py -q`

- [ ] **Step 6: Commit Task 2**

```bash
git add src/skillforge_kb/agents/planning_agent.py tests/unit/agents/test_planning_agent.py
git commit -m "feat: compile course planning lifecycle graph"
```

### Task 3: Dynamic Adaptation and Current Node Selection

**Files:**
- Modify: `src/skillforge_kb/agents/planning_agent.py`
- Modify: `tests/unit/agents/test_planning_agent.py`

**Interfaces:**
- Consumes: successful path/profile state, `ConceptAttributeCatalog`, `NodeWeightEngine`.
- Produces: `recompute_adaptations` and `select_current_node` graph nodes.

- [ ] **Step 1: Write failing adaptation tests**

```python
def test_initialize_computes_ordered_unfinished_adaptations(agent, profile) -> None:
    result = agent.invoke(initialize_event(profile), "student-1")
    unfinished = [
        node for node in result.path.nodes
        if node.status not in {PathStatus.COMPLETED, PathStatus.SKIPPED}
    ]
    assert [item.concept_id for item in result.adaptations] == [
        node.concept_id for node in unfinished
    ]
    assert result.current_adaptation.concept_id == result.current_node.concept_id


def test_completion_advances_current_node_without_changing_path_id(agent, profile) -> None:
    initial = agent.invoke(initialize_event(profile), "student-1")
    updated = agent.invoke(
        completion_event(initial.current_node.concept_id),
        "student-1",
    )
    assert updated.path.path_id == initial.path.path_id
    assert updated.current_node.concept_id != initial.current_node.concept_id
    assert initial.current_node.concept_id not in {
        item.concept_id for item in updated.adaptations
    }
```

- [ ] **Step 2: Run adaptation tests and verify RED**

Run:

```bash
uv run pytest tests/unit/agents/test_planning_agent.py::test_initialize_computes_ordered_unfinished_adaptations tests/unit/agents/test_planning_agent.py::test_completion_advances_current_node_without_changing_path_id -q
```

- [ ] **Step 3: Implement adaptation node**

Instantiate one `NodeWeightEngine` per agent. For every path node not `COMPLETED`/`SKIPPED`, call `evaluate(profile, node, completed_ids)` in path order. Catch only expected `ValueError` and return `adaptation_error` without replacing valid path/profile.

- [ ] **Step 4: Implement selection node**

- One available node -> `READY`, `START_CURRENT_NODE`.
- All nodes finished -> `COMPLETED`, `COURSE_COMPLETE`.
- Zero available while unfinished -> `FAILED`, `NO_AVAILABLE_NODE`.
- Multiple available -> `FAILED`, `MULTIPLE_AVAILABLE_NODES`.

Append a `ProcessedPlanningEvent` only after a successful select or reset.

- [ ] **Step 5: Verify Task 3**

Run focused tests, then `uv run pytest tests/unit/agents/test_planning_agent.py -q`.

- [ ] **Step 6: Commit Task 3**

```bash
git add src/skillforge_kb/agents/planning_agent.py tests/unit/agents/test_planning_agent.py
git commit -m "feat: adapt and advance course planning state"
```

### Task 4: Agent Facade, Checkpoint Sessions, Idempotency, Reset, and Async

**Files:**
- Modify: `src/skillforge_kb/agents/planning_agent.py`
- Modify: `src/skillforge_kb/agents/__init__.py`
- Modify: `tests/unit/agents/test_planning_agent.py`

**Interfaces:**
- Consumes: compiled graph and Task 1 result contract.
- Produces: `CoursePlanningAgent.create()`, `invoke()`, `ainvoke()`, and `get_state()`.

- [ ] **Step 1: Write failing session tests**

Cover:

- same event retry returns `event_duplicate=True` and unchanged path/result state;
- same event ID with different payload returns `event_id_conflict` and preserves path;
- reset clears path/profile/adaptations and returns `IDLE`;
- reset followed by a new initialize succeeds;
- two thread IDs have independent paths/profiles;
- `ainvoke()` equals synchronous semantics;
- `get_state()` returns the latest checkpoint and returns `None` for an unknown thread.

- [ ] **Step 2: Run session tests and verify RED**

Run only the new test names and confirm expected missing behavior.

- [ ] **Step 3: Implement the public facade**

```python
class CoursePlanningAgent:
    def __init__(self, graph: _PlanningGraph) -> None:
        self._graph = graph

    @classmethod
    def create(
        cls,
        catalog: OntologyCatalog,
        attributes: ConceptAttributeCatalog,
        planner_policy: PlannerPolicy | None = None,
        node_weight_policy: NodeWeightPolicy | None = None,
    ) -> "CoursePlanningAgent":
        return cls(
            build_course_planning_graph(
                catalog,
                attributes,
                planner_policy,
                node_weight_policy,
                checkpointer=InMemorySaver(),
            )
        )

    def invoke(
        self,
        event: PlanningAgentEvent,
        thread_id: str,
    ) -> CoursePlanningAgentResult:
        config = _thread_config(thread_id)
        values = self._graph.invoke({"event": event}, config=config)
        return _build_result(thread_id, values)

    async def ainvoke(
        self,
        event: PlanningAgentEvent,
        thread_id: str,
    ) -> CoursePlanningAgentResult:
        config = _thread_config(thread_id)
        values = await self._graph.ainvoke({"event": event}, config=config)
        return _build_result(thread_id, values)

    def get_state(self, thread_id: str) -> CoursePlanningAgentResult | None:
        snapshot = self._graph.get_state(_thread_config(thread_id))
        if not snapshot.values:
            return None
        return _build_result(thread_id, snapshot.values)
```

The facade constructs LangGraph config as `{"configurable": {"thread_id": thread_id}}`, validates non-empty thread IDs, and converts graph values to the frozen result contract.

- [ ] **Step 4: Export public API**

Export the Agent, event/status/result/failure models, and event digest builder from `skillforge_kb.agents` without removing existing resource/planning tool exports.

- [ ] **Step 5: Run all Agent tests and static checks**

```bash
uv run pytest tests/unit/agents/test_planning_agent_models.py tests/unit/agents/test_planning_agent.py tests/unit/agents/test_planning_tools.py -q
uv run ruff check src/skillforge_kb/agents tests/unit/agents
uv run mypy src
```

- [ ] **Step 6: Run full regression**

Run: `uv run pytest tests/unit -q`

Expected: existing 217 tests plus all new Agent tests pass.

- [ ] **Step 7: Commit Task 4**

```bash
git add src/skillforge_kb/agents/planning_agent.py src/skillforge_kb/agents/__init__.py tests/unit/agents/test_planning_agent.py
git commit -m "feat: expose checkpointed course planning agent"
```

### Task 5: Final Verification and Review

**Files:**
- Verify all files changed in Tasks 1-4.

- [ ] **Step 1: Run final gates**

```bash
uv run pytest tests/unit -q
uv run pytest --collect-only -q
uv run ruff check .
uv run mypy src
git diff --check HEAD~4..HEAD
```

- [ ] **Step 2: Review invariants**

Confirm failures preserve valid state, duplicates do not re-run planning, event conflicts are detected, reset enables reinitialization, adaptation excludes finished nodes, and no external integration entered the diff.

- [ ] **Step 3: Review dependency delta**

Confirm only LangGraph and its required transitive packages changed in `uv.lock`, and no API-key-dependent package or model client was added.

- [ ] **Step 4: Record branch state**

Run `git status --short` and `git log --oneline -8`; the tracked worktree must be clean.
