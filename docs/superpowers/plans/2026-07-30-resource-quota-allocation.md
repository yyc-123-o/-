# Resource Quota Allocation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce deterministic, versioned learning-time and resource-count quotas from each reviewed resource blueprint and node adaptation, then embed them in every v2 `ResourceBrief`.

**Architecture:** Add a pure `resources/allocation.py` policy engine with frozen, digest-validated contracts. Keep `ResourceBriefBuilder` responsible only for obtaining the matching blueprint/adaptation and attaching the allocation; brief validation enforces cross-contract identity.

**Tech Stack:** Python 3.12, Pydantic 2, pytest, Ruff, mypy

## Global Constraints

- Do not change course concepts, path order, node status, or delivery depth.
- Use blueprint minutes and existing adaptation facts; do not infer learner state again.
- Keep all quotas non-negative, bounded by explicit policy values, and monotonic.
- Gate practical, assessment, and project counts by requested resource types.
- Version and hash the policy and every allocation.
- Mark constants as engineering defaults, not measured learning-effect estimates.
- Require no model, API key, database, network, or external Agent.

---

### Task 1: Pure Allocation Policy and Engine

**Files:**
- Create: `src/skillforge_kb/resources/allocation.py`
- Create: `tests/unit/resources/test_allocation.py`
- Modify: `src/skillforge_kb/resources/__init__.py`

**Interfaces:**
- Consumes: `ResourceBlueprint` and `NodeAdaptationDecision`.
- Produces: `QuotaVector`, `ResourceAllocationPolicy`, `ResourceAllocation`, `build_resource_allocation_policy_digest()`, `build_resource_allocation_digest()`, and `allocate_resources()`.

- [ ] **Step 1: Write failing policy and allocation tests**

Use a helper that builds a valid `NodeAdaptationDecision` with controlled depth,
support score, intensity, and effort multiplier. Require deterministic equality,
digest round trips, 5-minute upward rounding, exact default count tables,
resource-type gating, concept/depth mismatch rejection, and monotonicity.

```python
def test_intro_standard_allocation_uses_depth_plus_support_quota() -> None:
    allocation = allocate_resources(
        _blueprint(DepthLevel.INTRO, estimated_minutes=45),
        _adaptation(DepthLevel.INTRO, 0.40, SupportIntensity.STANDARD),
    )
    assert allocation.estimated_minutes == 65
    assert allocation.worked_example_count == 2
    assert allocation.guided_exercise_count == 4
    assert allocation.assessment_item_count == 5


def test_resource_types_gate_unavailable_quotas() -> None:
    allocation = allocate_resources(
        _blueprint(DepthLevel.ADVANCED, resource_types=(ResourceType.LECTURE,)),
        _adaptation(DepthLevel.ADVANCED, 0.70, SupportIntensity.SCAFFOLDED),
    )
    assert allocation.worked_example_count == 0
    assert allocation.guided_exercise_count == 0
    assert allocation.assessment_item_count == 0
    assert allocation.project_checkpoint_count == 0
```

- [ ] **Step 2: Run tests and verify RED**

Run `uv run pytest tests/unit/resources/test_allocation.py -q`. Expected: allocation module import failure.

- [ ] **Step 3: Implement policy contracts**

`QuotaVector` contains four non-negative integers. `ResourceAllocationPolicy` contains version, minute rounding, three depth vectors, and four support-addition vectors. Validate component-wise monotonicity across intro/intermediate/advanced and compact/standard/scaffolded/remediation.

- [ ] **Step 4: Implement allocation and digests**

Validate blueprint/adaptation identity. Add depth and support vectors, apply resource-type gates, and compute:

```python
estimated_minutes = ceil(
    blueprint.estimated_minutes * adaptation.effort_multiplier
    / policy.minute_rounding
) * policy.minute_rounding
```

Construct `ResourceAllocation` with source facts, reason codes, policy digest, and content digest. Model validators reproduce gates, duration bounds, and both digests.

- [ ] **Step 5: Verify and commit Task 1**

```powershell
uv run pytest tests/unit/resources/test_allocation.py -q
uv run ruff check src/skillforge_kb/resources tests/unit/resources
uv run mypy src/skillforge_kb/resources
git add src/skillforge_kb/resources tests/unit/resources/test_allocation.py
git commit -m "feat: allocate personalized resource quotas"
```

### Task 2: Embed Allocation in ResourceBrief v2

**Files:**
- Modify: `src/skillforge_kb/resources/models.py`
- Modify: `src/skillforge_kb/resources/briefs.py`
- Modify: `tests/unit/resources/test_briefs.py`

**Interfaces:**
- Consumes: Task 1 `allocate_resources()`.
- Produces: required `ResourceBriefPayload.resource_allocation` and new-build default `request_version="resource-brief.v2"`.

- [ ] **Step 1: Write failing brief integration tests**

Require every built brief to contain an allocation matching concept, depth, resource types, support intensity, effort multiplier, and blueprint minutes. Mutate allocation support/depth/resource types, recompute allocation and brief digests, and require cross-contract validation failure.

- [ ] **Step 2: Run tests and verify RED**

Run `uv run pytest tests/unit/resources/test_briefs.py -q`. Expected: missing `resource_allocation` assertions fail.

- [ ] **Step 3: Add the required brief field and validation**

Import `ResourceAllocation`, set the new-build request default to `resource-brief.v2`, and validate allocation identity against `concept_id`, `delivery_depth`, `required_resource_types`, and `node_adaptation`.

- [ ] **Step 4: Build allocation from the selected blueprint**

In `ResourceBriefBuilder.build()`, call `allocate_resources(blueprint, adaptation)` once and pass the result into `ResourceBriefPayload`. Do not recalculate any profile or graph facts in the allocator.

- [ ] **Step 5: Verify and commit Task 2**

```powershell
uv run pytest tests/unit/resources tests/unit/agents/test_resource_tools.py tests/unit/integration/test_personalized_resource_flow.py -q
uv run ruff check src/skillforge_kb/resources tests/unit/resources
uv run mypy src
git add src/skillforge_kb/resources tests/unit/resources/test_briefs.py
git commit -m "feat: attach quotas to resource briefs"
```

### Task 3: Documentation and Complete Regression Gates

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document allocation semantics**

Explain that v2 briefs contain rounded total minutes and resource-type-gated counts, that counts are engineering defaults, and that downstream Agents must consume the frozen allocation rather than recalculate it.

- [ ] **Step 2: Run scenario checks**

Use intro/intermediate/advanced and compact/standard/scaffolded/remediation tests to confirm component-wise monotonicity. Confirm blocked remediation remains intro depth and receives remediation additions.

- [ ] **Step 3: Commit documentation**

```powershell
git add README.md
git commit -m "docs: explain resource quota allocation"
```

- [ ] **Step 4: Run fresh final gates**

```powershell
uv run pytest tests/unit -q
uv run pytest --collect-only -q
uv run ruff check .
uv run mypy src
uv lock --check --offline
git diff --check
```

Expected: all commands exit `0`; five collected external-service integration tests remain outside the unit-test run.
