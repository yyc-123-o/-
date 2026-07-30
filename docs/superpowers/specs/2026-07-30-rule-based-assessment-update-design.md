# Rule-Based Assessment Update Design

## 1. Purpose

Implement the first non-paper learning-state baseline: convert structured answer
events into an updated `LearnerProfileSnapshot`, mastery evidence, confidence, and
error-pattern records. This is a deterministic engineering baseline and is
explicitly replaceable by BKT/IRT later.

## 2. Scope and Boundaries

- Update learner profile state only; never modify the knowledge graph, planner path,
  resource blueprint, or ResourceBrief.
- Accept only structured events with concept IDs already present in the catalog.
- Require profile ID and graph version to match the event and catalog.
- Keep all mastery/confidence/ratio values in `[0, 1]`.
- Make replay of an event ID an idempotent no-op through an explicit assessment
  ledger; do not overload `assessment_runs` with event IDs.
- No model, API key, network service, database, or external Agent is required.
- Mark the policy as `rule-based-assessment.v1`; results are not real teaching
  effectiveness measurements.

## 3. Approaches Considered

### 3.1 Mutate `LearnerProfileSnapshot` directly

This would hide replay state and make duplicate events impossible to distinguish
from new evidence. It also makes audit history ambiguous.

### 3.2 Add event IDs to `assessment_runs`

This preserves some identity but conflates a measurement run with an individual
response and can break existing profile adapter semantics.

### 3.3 Explicit immutable assessment ledger

The selected approach wraps a profile with `processed_event_ids`. Applying an event
returns a new ledger and a result. The ledger owns idempotency; the profile keeps
only semantic assessment facts and event references.

## 4. Contracts

### 4.1 `AssessmentEvent`

Fields:

- `event_id`, `profile_id`, `graph_version`;
- one or more unique `concept_ids`;
- `correct`, `response_time_ms`, `hint_count`, `attempt_count`, and aware
  `timestamp`;
- optional explicit `error_kind` and evidence references.

An explicitly supplied error kind is allowed only for incorrect answers. Correct
answers cannot carry an error kind.

### 4.2 `AssessmentPolicy`

Versioned bounded parameters:

- prior mastery `0.50` and prior confidence `0.25`;
- correct mastery gain `0.12` and incorrect mastery loss `0.15`;
- hint penalty `0.03` per hint, capped at three hints;
- retry penalty `0.02` per retry beyond the first;
- confidence gain `0.12` and minimum observed confidence `0.25`.

The policy is frozen, validates all values in `[0, 1]`, and has a content digest.

### 4.3 `AssessmentLedger` and result

The ledger contains a `LearnerProfileSnapshot` and unique processed event IDs. The
result contains the updated ledger, event digest, `applied` flag, affected concept
IDs, mastery before/after pairs, classified error kind, and reason codes.

## 5. Deterministic Update Rules

For each event concept:

```text
current mastery = recorded score, otherwise prior mastery
if correct:
    raw score = current + correct_gain * (1 - current)
else:
    raw score = current - incorrect_loss * current
adjusted score = raw score - hint_penalty * min(hints, 3)
                - retry_penalty * max(attempts - 1, 0)
mastery = clamp(adjusted score, 0, 1)
```

Confidence starts at the policy minimum and moves toward one by `confidence_gain`
per new event. `KnowledgeMastery` becomes `ASSESSED`, uses the event timestamp, and
appends the event ID to its evidence references.

Error classification for an incorrect event is deterministic:

1. explicit `error_kind` if supplied;
2. `concept_confusion` when hints >= 2;
3. `logic_gap` when response time >= 120000 ms;
4. `calculation_error` when attempts >= 2;
5. `missed_condition` otherwise.

For each concept, error patterns aggregate counts by kind and recompute ratios as
`kind_count / total_error_count_for_concept`. Existing unrelated profile patterns
are preserved. Correct answers create no error pattern.

## 6. Error Handling and Idempotency

- Unknown concept IDs, graph mismatch, profile mismatch, duplicate concept IDs, and
  naive timestamps fail before profile mutation.
- A duplicate event ID returns the original ledger, `applied=False`, and a
  `duplicate_event` reason code; it never increments counts twice.
- Event digest is content-sensitive and included in the result.
- Ledger and result models are frozen and validate all derived fields.

## 7. Testing and Acceptance

- First correct/incorrect events create assessed mastery from the configured prior.
- Correct answers raise mastery; incorrect answers lower mastery.
- Hints and retries cannot improve the score relative to the same answer without
  those penalties.
- Confidence is bounded and increases with new evidence.
- All five classifier branches and explicit error-kind override are covered.
- Multiple concepts update deterministically in input order while preserving unique
  IDs.
- Duplicate events are no-ops and preserve ledger/profile digests.
- Invalid events fail atomically and leave the original ledger unchanged.
- Outputs carry policy/event digests and do not contain path or resource decisions.
- All existing unit tests, Ruff, mypy, and lock checks pass.
