# Planner Policy Calibration Design

## 1. Purpose

Extend offline evaluation from a single fixed `PlannerPolicy` to an auditable search
over the planner parameters that are still hand-set: evidence confidence, mastery
skip thresholds, readiness weights, delivery-depth thresholds, and four-dimensional
ability weights.

The output is a calibration report, not an automatic production-policy update. The
first reports use synthetic oracles and therefore measure rule consistency and
sensitivity rather than real educational effectiveness.

## 2. Scope and Constraints

- Reuse `SyntheticPlanningDataset` and its independent expected-node decisions.
- Never change the catalog, hard-prerequisite edges, required concept set, or stable
  course order.
- Never write a candidate policy into production configuration.
- Preserve the strict existing `evaluate_course_paths()` behavior for normal
  regression reports; calibration uses a separate candidate-evaluation entry point.
- Require no API key, model, database, network service, or external Agent.
- Keep every candidate deterministic and explain which single coordinate changed.
- Mark reports and claims as synthetic.

## 3. Approaches Considered

### 3.1 Add planner fields to node-weight calibration

This would combine two different decisions. `NodeWeightPolicy` controls resource
support intensity, while `PlannerPolicy` controls skip and delivery depth. A shared
search model would blur ownership and permit invalid parameter combinations.

### 3.2 Full Cartesian grid

A Cartesian product is exhaustive over the supplied values, but seven axes quickly
produce thousands of candidates. Most differ in several dimensions, making
regressions difficult to attribute and reports expensive to reproduce.

### 3.3 Deterministic coordinate sensitivity search

The selected approach varies one policy coordinate from the baseline at a time.
Readiness weights vary as a complementary pair, and ability weights vary as a
complete normalized vector. This yields direct attribution, bounded runtime, and a
clear baseline comparison. Multi-coordinate optimization remains a later step once
expert-labelled or observed data exists.

## 4. Architecture

Add `evaluation/planner_calibration.py` with four responsibilities:

1. frozen search-space and evaluation/report contracts;
2. legal candidate generation in stable coordinate/value order;
3. candidate evaluation against the dataset's stored oracle;
4. deterministic ranking, digests, and atomic JSON report writing.

Refactor `evaluation/path_evaluation.py` to expose
`evaluate_course_path_cases(catalog, dataset, policy)`. This function compares any
explicit policy to the same stored oracle and returns validated case results. The
existing `evaluate_course_paths()` remains the strict wrapper that additionally
requires the dataset's baseline policy metadata to match.

## 5. Search Space

`PlannerPolicySearchSpace` contains strictly increasing numeric axes:

- `minimum_confidences`;
- `skip_masteries`;
- `skip_confidences`;
- `mastery_weights`, with `ability_weight = 1 - mastery_weight`;
- `intermediate_thresholds`;
- `advanced_thresholds`.

It also contains complete `AbilityWeights` alternatives. Every ability vector must
sum to one, which the production model already validates.

Candidate generation starts from the complete baseline and changes exactly one
coordinate. It rejects duplicate tunable tuples, invalid threshold order, and
baseline-equivalent candidates. Candidate versions use
`planner-policy.candidate.v1.<four-digit-index>` in deterministic generation order.

The default search space includes the current baseline values and conservative
values immediately around them. It produces a small sensitivity set suitable for
the default 60-case dataset.

## 6. Evaluation and Ranking

Each `PlannerPolicyEvaluation` stores:

- the complete policy and its digest;
- the changed coordinate and baseline/candidate values;
- the standard `PathEvaluationMetrics`;
- case IDs with skip mismatches;
- case IDs with delivery-depth mismatches;
- case IDs with coverage, order, or prerequisite invariant failures.

Ranking uses this stable key:

1. invariant-failure case count, ascending;
2. skip accuracy, descending;
3. delivery-depth accuracy, descending;
4. low-confidence conservative rate, descending;
5. normalized L1 distance from the baseline, ascending;
6. policy digest, ascending.

The baseline is evaluated separately and cannot appear among ranked candidates.
`best_fitting_candidate` is the first ranked candidate, but the report never claims
that it is better than the baseline and never promotes it automatically.

## 7. Report and CLI

`PlannerPolicyCalibrationReport` carries dataset, graph, search-space, baseline, and
candidate provenance plus a report digest. Validators reject duplicate policies,
incorrect ranking, mismatched case coverage, baseline leakage, and digest mutation.

Add:

```text
skillforge-kb planning-calibrate-policy \
  --dataset-file <synthetic-dataset.json> \
  --output-file <planner-policy-calibration.json>
```

The first CLI version uses the reviewed default coordinate search space. The Python
API accepts an explicit `PlannerPolicySearchSpace` for controlled experiments.
Writes are atomic and outputs that overwrite a graph or dataset input are rejected.

## 8. Error Handling

- Reject unordered or duplicate numeric axes.
- Reject a search space that yields no baseline-distinct legal candidate.
- Reject graph and baseline-policy mismatch before candidate evaluation.
- Reject candidate policies that violate normalized weights or threshold order.
- Treat any invariant failure as a ranking penalty, never as an exception hidden
  from the report.
- Convert expected file/model errors into concise CLI parameter errors.

## 9. Testing and Acceptance

- Candidate generation is deterministic, legal, unique, and one-coordinate-only.
- The default space covers all seven tunable coordinate groups.
- Baseline evaluation matches the strict offline evaluation report.
- Candidate ranking reconstructs exactly from stored evaluation values.
- Report JSON round trips and rejects metric, ordering, identity, and digest changes.
- The CLI creates a synthetic-labelled report without external services.
- The current catalog retains zero prerequisite violations, full concept coverage,
  and stable path order for every legal default candidate.
- All unit tests, Ruff, mypy, and lock checks pass.
