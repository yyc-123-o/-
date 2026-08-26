# Course Path Offline Evaluation Design

## 1. Purpose

Build a deterministic, synthetic-data evaluation harness for the existing course
planner. The harness must expose planning regressions and policy trade-offs without
claiming that synthetic results measure real learning outcomes.

This phase covers synthetic learner profiles and course-path metrics only. It does
not implement BKT, IRT, forgetting models, adaptive item selection, or learning-gain
estimation.

## 2. Fixed Constraints

- The course path contains every required concept in the catalog's stable teaching
  order.
- Hard prerequisites may never be removed, reordered, or bypassed.
- A planner policy may change skip decisions and delivery depth, but not the path's
  concept set or order.
- The default dataset contains exactly 60 cases and is reproducible from an integer
  seed.
- Every dataset and report is explicitly labelled `synthetic`.
- Generated timestamps are derived from fixed input metadata, not wall-clock time.
- Reports carry the graph version, policy version, policy digest, dataset digest,
  seed, and per-case reason data.

## 3. Approaches Considered

### 3.1 Hand-authored fixtures

Hand-authoring all profiles gives clear intent but is repetitive, difficult to
maintain, and weak at exercising numeric boundaries.

### 3.2 Unconstrained random generation

Sampling all profile fields from distributions provides variety but makes expected
skip and depth decisions hard to define independently. It can also produce many
semantically redundant cases.

### 3.3 Stratified templates with seeded variation

The selected approach defines explicit scenario families and applies bounded,
seeded variation within each family. Each generated case includes an oracle for
expected skipped concepts and expected delivery depth. This preserves auditability
while covering more combinations than fixed fixtures.

## 4. Architecture

Add an `evaluation` package with three focused modules:

1. `models.py` defines immutable, versioned dataset, case-result, metric, and report
   contracts.
2. `synthetic.py` generates valid learner profiles and their expected planning
   outcomes from scenario templates and a local `random.Random` instance.
3. `path_evaluation.py` runs `CoursePlanner`, checks graph invariants, calculates
   per-case values, and aggregates the report.

The generator and evaluator are pure with respect to external services. File I/O
is isolated in JSON read/write helpers and CLI commands.

## 5. Synthetic Dataset

### 5.1 Scenario families

The default 60 cases are distributed deterministically across these eight cohorts:

- `beginner`: missing or low mastery with low-to-moderate ability;
- `intermediate`: reliable middle-band mastery and ability;
- `advanced`: reliable high mastery and ability;
- `uneven`: chapter- or dimension-specific strength and weakness;
- `low_confidence`: plausible scores whose confidence is below the planning floor;
- `missing_evidence`: absent mastery, abilities, or both;
- `conflicting_evidence`: high mastery with low ability, or the reverse;
- `boundary`: values immediately below, at, and above policy thresholds.

Every cohort must appear at least once. Counts differ by at most one when the
requested case count is not divisible by eight.

### 5.2 Expected outcomes

Each case stores:

- a complete `LearnerProfileSnapshot` accepted by the production planner;
- the expected set of concepts that may be skipped;
- the expected delivery depth for every non-skipped concept;
- scenario tags explaining the intended condition.

Expected values are produced by the scenario template, not copied from planner
output. Semantically invalid Pydantic payloads are excluded because schema
validation is already tested separately.

### 5.3 Determinism and identity

Case IDs use the cohort and a stable ordinal. Dataset identity is a SHA-256 digest
of canonical JSON excluding no behaviorally relevant fields. The same catalog,
policy, case count, seed, and data version must produce byte-equivalent JSON.

## 6. Evaluation Metrics

The report includes these aggregate metrics:

- `hard_prerequisite_violation_rate`: violating prerequisite edges divided by
  evaluated in-path hard-prerequisite edges; required target is `0`;
- `required_concept_coverage_rate`: required concepts returned by the planner
  divided by required concepts in the catalog; required target is `1`;
- `skip_accuracy`: correct skip/non-skip decisions over all required concepts;
- `delivery_depth_accuracy`: expected depth matches over non-skipped concepts;
- `mean_learning_node_count`: mean number of nodes that remain to be learned;
- `mean_skipped_node_count`: mean number of skipped nodes;
- `low_confidence_conservative_rate`: low-confidence cases whose learning nodes
  remain at intro depth and are not skipped;
- `path_order_stability_rate`: cases whose concept order equals the catalog's
  stable required order; required target is `1`.

The evaluator also emits per-case counts, mismatched concept IDs, prerequisite
violations, `path_id`, and the planner's policy digest. Aggregate rates are computed
from integer numerators and denominators retained in the report.

Learning gain, Brier Score, log loss, Expected Calibration Error, and adaptive-test
question count are intentionally absent. They require an outcome or probabilistic
student model that this phase does not provide.

## 7. CLI and Files

Add two commands:

```text
skillforge-kb planning-generate-synthetic --output-file <path> --case-count 60 --seed 20260730
skillforge-kb planning-evaluate --dataset-file <path> --output-file <path>
```

Both commands use the default course and relation files unless explicitly
overridden. They reject output paths that overwrite an input. The evaluator rejects
dataset graph or policy mismatches rather than silently adapting them.

JSON writes use a temporary sibling file followed by replacement, matching the
existing coverage-report pattern. CLI failures become concise `typer.BadParameter`
messages.

## 8. Error Handling

- Reject case counts below eight so every cohort is represented.
- Reject unknown graph versions, duplicate case IDs, digest mismatches, and policy
  mismatches.
- Reject reports whose stored aggregates do not reproduce from per-case results.
- Treat a planner exception as a failed command; do not emit a partial success
  report.
- Keep all generated scores and confidence values in `[0, 1]` before model
  construction.

## 9. Testing

Use test-driven development for each public behavior:

- deterministic generation for identical inputs;
- seed-sensitive variation without changing cohort allocation;
- exactly 60 default cases with all eight cohorts;
- immutable dataset and digest validation;
- zero hard-prerequisite violations on the default catalog;
- full required-concept coverage and stable order;
- correct aggregate reconstruction and mismatch reporting;
- low-confidence conservative behavior;
- JSON round trip and atomic report writing;
- CLI success, invalid input, and input-overwrite rejection.

Run focused tests during development, followed by all unit tests, Ruff, and mypy.
External Neo4j and PostgreSQL integration tests remain separate.

## 10. Acceptance Criteria

- The default command produces 60 deterministic synthetic cases across all eight
  cohorts.
- Re-running generation and evaluation with identical inputs produces identical
  dataset and report content.
- The current default planner reports zero hard-prerequisite violations, complete
  required-concept coverage, and stable path order.
- Every mismatch is attributable to explicit concept IDs and case IDs.
- The output visibly states that it is synthetic and contains no claim about real
  student learning effectiveness.
- All unit tests, Ruff, and mypy pass.
