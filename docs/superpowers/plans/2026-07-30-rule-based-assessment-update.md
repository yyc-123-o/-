# Rule-Based Assessment Update Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic, idempotent answer-event baseline that updates learner mastery, confidence, and error patterns without modifying graph or course-path decisions.

**Architecture:** Create `assessment/update.py` with frozen event, policy, ledger, and result contracts. A pure `apply_assessment_event()` validates scope, classifies errors, updates profile facts, and records processed IDs. Export the API without coupling it to `CoursePlanner`, Agents, or resource generation.

**Tech Stack:** Python 3.12, Pydantic 2, pytest, Ruff, mypy

## Global Constraints

- Policy version is `rule-based-assessment.v1`.
- Keep all mastery, confidence, and error ratios in `[0, 1]`.
- Never modify graph, path order, depth decisions, resource briefs, or blueprints.
- Duplicate event IDs are explicit idempotent no-ops.
- Reject invalid events before mutating the ledger.
- Require no API key, model, database, network, or external Agent.
- Label this as a replaceable rule baseline, not a paper-based or real-outcome model.

---

### Task 1: Assessment Contracts and Event Digest

**Files:**
- Create: `src/skillforge_kb/assessment/__init__.py`
- Create: `src/skillforge_kb/assessment/update.py`
- Create: `tests/unit/assessment/__init__.py`
- Create: `tests/unit/assessment/conftest.py`
- Create: `tests/unit/assessment/test_update.py`

**Interfaces:**
- Consumes: `LearnerProfileSnapshot`, `OntologyCatalog`, and event primitives.
- Produces: `AssessmentErrorKind`, `AssessmentEvent`, `AssessmentPolicy`, `AssessmentLedger`, `AssessmentUpdateResult`, `build_assessment_policy_digest()`, and `build_assessment_event_digest()`.

- [ ] **Step 1: Write failing contract tests**

```python
def test_event_requires_aware_timestamp_and_unique_concepts() -> None:
    with pytest.raises(ValidationError, match="concept IDs"):
        AssessmentEvent(
            event_id="event-1",
            profile_id="profile-1",
            graph_version="ai-course-v1",
            concept_ids=("ml.optimization.gradient-descent",) * 2,
            correct=True,
            response_time_ms=1000,
            hint_count=0,
            attempt_count=1,
            timestamp=datetime(2026, 7, 30),
        )


def test_policy_digest_and_event_digest_are_stable() -> None:
    event = _event()
    assert build_assessment_event_digest(event) == build_assessment_event_digest(
        AssessmentEvent.model_validate(event.model_dump())
    )
```

- [ ] **Step 2: Run focused tests and verify RED**

Run `uv run pytest tests/unit/assessment/test_update.py -q`. Expected: import failure for `skillforge_kb.assessment`.

- [ ] **Step 3: Implement frozen contracts and validators**

Define the error enum values `concept_confusion`, `logic_gap`, `calculation_error`, `missed_condition`. Add event fields from the design, optional explicit error kind, and evidence references. `AssessmentPolicy` contains the exact v1 defaults from the design. `build_assessment_policy_digest()` and `build_assessment_event_digest()` use canonical JSON and SHA-256 with `assessment_policy_` and `assessment_event_` prefixes. `AssessmentLedger` stores a profile and unique processed IDs. `AssessmentUpdateResult` stores ledger, policy version/digest, event digest, applied flag, affected IDs, before/after mastery pairs, optional classified error kind, and reason codes.

- [ ] **Step 4: Verify contracts and commit Task 1**

```powershell
uv run pytest tests/unit/assessment/test_update.py -q
uv run ruff check src/skillforge_kb/assessment tests/unit/assessment
uv run mypy src/skillforge_kb/assessment
git add src/skillforge_kb/assessment tests/unit/assessment
git commit -m "feat: add assessment event contracts"
```

### Task 2: Deterministic Rule Update and Error Classification

**Files:**
- Modify: `src/skillforge_kb/assessment/update.py`
- Modify: `tests/unit/assessment/test_update.py`

**Interfaces:**
- Consumes: Task 1 event, policy, ledger, and catalog contracts.
- Produces: `apply_assessment_event()`.

- [ ] **Step 1: Write failing update tests**

Cover first correct/incorrect answers, hints/retries, confidence growth and bounds, the four fallback classifier branches, multi-concept events, unknown concept/profile/graph failures, explicit error override as the fifth classifier branch, and duplicate no-op:

```python
def test_correct_answer_raises_mastery_and_duplicate_is_noop(catalog, ledger) -> None:
    event = _event(correct=True)
    first = apply_assessment_event(catalog, ledger, event)
    second = apply_assessment_event(catalog, first.ledger, event)

    assert first.applied is True
    assert second.applied is False
    assert "duplicate_event" in second.reason_codes
    assert second.ledger == first.ledger
    assert first.mastery_after[0][1] > first.mastery_before[0][1]


@pytest.mark.parametrize(
    ("hints", "response_ms", "attempts", "expected"),
    [
        (2, 1000, 1, AssessmentErrorKind.CONCEPT_CONFUSION),
        (0, 120000, 1, AssessmentErrorKind.LOGIC_GAP),
        (0, 1000, 2, AssessmentErrorKind.CALCULATION_ERROR),
        (0, 1000, 1, AssessmentErrorKind.MISSED_CONDITION),
    ],
)
def test_incorrect_answer_classifies_deterministically(
    hints: int,
    response_ms: int,
    attempts: int,
    expected: AssessmentErrorKind,
    catalog: OntologyCatalog,
    ledger: AssessmentLedger,
) -> None:
    result = apply_assessment_event(
        catalog,
        ledger,
        _event(
            correct=False,
            hint_count=hints,
            response_time_ms=response_ms,
            attempt_count=attempts,
        ),
    )

    assert result.classified_error_kind is expected
```

- [ ] **Step 2: Run tests and verify RED**

Expected: `apply_assessment_event` is undefined.

- [ ] **Step 3: Implement scope validation and replay gate**

Validate catalog graph version, profile ID, event graph version, known concept IDs, unique event concepts, and aware timestamp before copying the ledger. If `event_id` is in `processed_event_ids`, return the original frozen ledger with `applied=False`, no changed profile, and `duplicate_event`.

- [ ] **Step 4: Implement mastery/confidence update**

For each concept use the design formula, clamp to `[0, 1]`, set `AssessmentStatus.ASSESSED`, timestamp the event, and append the event ID to evidence refs. Confidence starts at the policy minimum and moves toward one by `confidence_gain` for each new event. Preserve unrelated mastery records and profile fields.

- [ ] **Step 5: Implement error classification and aggregation**

Select explicit error kind, then hints >= 2, response time >= 120000, attempts >= 2, otherwise missed condition. For incorrect events, aggregate `ErrorPattern` counts per concept and kind and recompute ratios over total errors for that concept. Correct events create no new pattern.

- [ ] **Step 6: Verify Task 2 and commit**

```powershell
uv run pytest tests/unit/assessment/test_update.py -q
uv run ruff check src/skillforge_kb/assessment tests/unit/assessment
uv run mypy src
git add src/skillforge_kb/assessment tests/unit/assessment/test_update.py
git commit -m "feat: update learner state from answer events"
```

### Task 3: Public API, Documentation, and Final Gates

**Files:**
- Modify: `README.md`
- Modify: `src/skillforge_kb/assessment/__init__.py`

- [ ] **Step 1: Add public exports and documentation**

Export the contracts, policy digest, event digest, and update function. Document the rule baseline, idempotency, classifier priority, and explicit non-connection to path planning.

- [ ] **Step 2: Run scenario and regression tests**

Verify three profile states, multi-concept updates, repeated event replay, and that applying an assessment event leaves the original ledger/profile and a `CoursePlanner` decision created from that original profile unchanged. A later explicit planner call may consume the returned updated profile; this module must not invoke planning itself.

- [ ] **Step 3: Commit documentation**

```powershell
git add README.md src/skillforge_kb/assessment
git commit -m "docs: explain rule-based assessment baseline"
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
