# Node Weight Calibration Design

## 1. Purpose

Build the paper-independent algorithm layer needed to evaluate and tune the existing
`NodeWeightPolicy`. The feature produces deterministic candidate generation, labelled-case
evaluation, baseline comparison, factor ablation, and descriptive sensitivity summaries.

The feature does not estimate learner mastery, train BKT or IRT models, select adaptive test
items, change course ordering, or claim real teaching effectiveness.

## 2. Current Baseline

`NodeWeightEngine` currently computes support need from three bounded factors:

```text
0.55 * mastery_gap + 0.25 * error_risk + 0.20 * ability_gap
```

It then applies a conservative support floor and maps the score to compact, standard, or
scaffolded support. A blocked node always receives remediation. The current implementation is
deterministic and auditable, but the coefficients and thresholds are hand-authored defaults.

## 3. Approaches Considered

### 3.1 Full-profile end-to-end calibration

Run every candidate policy through `CoursePlanner` and `NodeWeightEngine` using complete learner
profiles. This exercises the entire stack but couples calibration to graph fixtures, repeats
expensive profile processing, and makes a small scoring experiment difficult to audit.

### 3.2 Feature-snapshot calibration (selected)

Extract a public pure scoring function shared by production and calibration. Its input is a
frozen snapshot containing `mastery_gap`, `error_risk`, `ability_gap`, `support_floor`, and
`blocked`. Calibration data adds expected intensity and an optional target score.

This approach prevents formula drift because production and experiments execute the same
function. It also makes it structurally impossible for the calibration module to add, remove, or
reorder course nodes.

### 3.3 Standalone CSV script

Implement the formula and grid search in a one-off script. This is quick, but it duplicates the
production formula, lacks strong validation, and produces weak audit records. It is rejected.

## 4. Architecture

### 4.1 Production scoring contract

`planning/adaptation.py` adds:

- `NodeWeightFeatures`: the five frozen inputs required to score support.
- `NodeSupportScore`: support score, intensity, and reproducible factor contributions.
- `score_node_support(features, policy)`: the only implementation of the weighted formula,
  conservative floor, and support-intensity thresholds.
- `build_node_weight_policy_digest(policy)`: the public canonical policy digest function.

`NodeWeightEngine.evaluate()` remains responsible for deriving feature values from the graph,
profile, and path node. It delegates scoring to `score_node_support()` and then builds the existing
`NodeAdaptationDecision`. Existing output contracts and path behavior remain unchanged.

### 4.2 Calibration data

`planning/calibration.py` defines a frozen `NodeWeightCalibrationDataset` with:

- a dataset ID and data version;
- an explicit data kind: `synthetic`, `expert_labelled`, or `observed`;
- one or more uniquely identified examples;
- for each example, a `NodeWeightFeatures` snapshot, expected support intensity, and optional
  target support score.

Blocked examples must be labelled `remediation`; non-blocked examples cannot use that label.
The dataset digest covers identity, provenance kind, features, and labels.

### 4.3 Candidate grid

`NodeWeightSearchSpace` contains ordered, unique candidate values for the three factor weights and
the compact/scaffolded thresholds. Candidate generation takes the Cartesian product and retains
only policies where:

- all values are within `[0, 1]`;
- the three factor weights do not exceed `1` and may undershoot it by at most `1e-9`;
- `compact_threshold < scaffolded_threshold`.

Generation order and candidate versions are stable. Empty or invalid grids fail explicitly.

### 4.4 Evaluation and ranking

Each policy is evaluated with the shared scoring function. A case result records predicted score,
predicted intensity, label match, and optional absolute score error. A policy evaluation records:

- exact intensity match count and rate;
- target score case count;
- mean absolute error when target scores exist;
- the complete ordered case results;
- the canonical policy digest.

Search evaluates the current baseline separately and excludes a numerically identical candidate.
Alternative candidates are ranked by:

1. higher exact intensity match rate;
2. lower mean absolute error when score targets exist;
3. smaller L1 parameter distance from the baseline;
4. canonical policy digest as the final deterministic tie-break.

The first result is named `best_fitting_candidate`, not an approved or production policy. Search
never mutates engine configuration or writes policy files.

Deserialized evaluations require unique case IDs. Reports require every evaluation to use the
same ordered case IDs and target coverage, exclude baseline-equivalent and duplicate candidates,
and preserve the documented complete ranking order.

### 4.5 Ablation and sensitivity

Weight ablation creates one candidate per positive factor by setting that factor to zero and
proportionally renormalizing the remaining factors. It evaluates each candidate using the same
dataset and returns the removed factor with the complete policy evaluation.

Sensitivity summaries group grid evaluations by each of the three factor values and report mean
match rate plus mean score error when available. These marginal summaries are descriptive and are
not presented as causal effects.

## 5. Safety and Claims

- Calibration never receives or returns a `PathDecision`.
- Hard prerequisites, graph order, delivery depth, and completion state cannot be modified.
- Every report includes dataset kind, dataset digest, policy values, policy versions, and policy
  digests.
- Synthetic data results must remain labelled synthetic.
- A best-fitting candidate is not automatically promoted to production.
- No API key, model call, database, network service, or external Agent is required.

## 6. Failure Behaviour

- Invalid datasets fail during model validation.
- Invalid search axes fail during model validation.
- A policy whose factor sum exceeds `1`, even within the lower-bound tolerance, fails validation.
- A grid with no mathematically valid policy raises `ValueError`.
- A grid containing no alternative to the baseline raises `ValueError` during search.
- An ablation that leaves no positive remaining weight raises `ValueError`.
- Evaluation is pure: failures cannot change the baseline or any production state.

## 7. Testing

Tests cover:

- production scoring equivalence before and after extraction;
- conservative floors and blocked remediation;
- dataset label and identity validation;
- deterministic candidate generation and invalid-grid rejection;
- exact-match and score-error metrics;
- stable ranking and conservative tie-breaking;
- baseline exclusion;
- three default-policy ablations and renormalization;
- deterministic sensitivity summaries;
- JSON round-trip of machine-readable reports;
- complete planning and Agent regression suites.

## 8. Deliverables

- `src/skillforge_kb/planning/calibration.py`
- additions to `src/skillforge_kb/planning/adaptation.py`
- public exports in `src/skillforge_kb/planning/__init__.py`
- `tests/unit/planning/test_calibration.py`
- regression additions to `tests/unit/planning/test_adaptation.py`
- a detailed TDD implementation plan
