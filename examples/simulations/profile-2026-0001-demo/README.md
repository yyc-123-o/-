# PROFILE-2026-0001-DEMO CNN Path Simulation

This directory contains a reproducible course-planning simulation derived from
`D:\张维揭榜挂帅\学情画像输出-最终版.json` (SHA-256
`10113557a047260d0a465189c929561b8b52d651442582bc10fb3ec5317df0c3`). The raw
profile remains outside Git.

## Inputs

- `01_initialize_event.json` is the canonical `PlanningAgentEvent` consumed by the
  course-planning Agent. It contains only normalized learner facts.
- `02_cnn_progress_event.json` is a separate simulation-control event. It marks the 56
  concepts before `chapter.05.cnn-representation` complete so the run begins at the
  CNN stage claimed by the source profile.

The second event aligns two different chapter taxonomies. It does not claim that the
56 fine-grained concepts received fresh mastery assessments.

## Normalization Rules

- `learner_ref` is SHA-256 of `LRN-2026-AI02`:
  `55b246fc71fa05f2d826495e671442167e13151a77c7859c4bc6230a796d7a94`.
- `graph_version=ai-course-v1` is explicit simulation configuration.
- Assessed mastery confidence is `min(0.90, 0.50 + 0.10 * test_count)` because the
  source provides test counts but not per-concept confidence.
- All four ability dimensions inherit the source profile's global IRT confidence of
  `0.90`. This shared confidence is a simulation assumption, not a new diagnosis.
- `observed_at` uses the source diagnosis timestamp because per-concept observation
  timestamps are absent.
- One-to-one mappings included in the canonical profile are:

| Source ID | Canonical concept |
| --- | --- |
| `kp_004` | `math.linear-algebra.matrix-operations` |
| `kp_005` | `math.calculus.derivative-gradient` |
| `kp_006` | `ml.supervised.learning` |
| `kp_009` | `ml.model-selection.cross-validation` |
| `kp_016` | `ml.optimization.gradient-descent` |
| `kp_017` | `dl.backpropagation` |
| `kp_018` | `dl.optimization.adam` |
| `kp_029` | `ml.objective.loss-function` |

Composite or absent concepts are intentionally not forced into canonical mastery. This
includes `kp_001`, `kp_002`, `kp_003`, `kp_007`, `kp_008`, `kp_010`-`kp_015`,
`kp_019`-`kp_028`, and `kp_030` where the label is composite, broader than one node,
unassessed, or absent from the current graph.

The source file's `learning_path_context`, `resource_generation_hints`, depth labels,
and diagnosis recommendations are not copied into the canonical profile. They are
downstream results from another taxonomy and would create a circular planner input.

## Run

From the repository root, remove any previous local simulation database, then run:

```powershell
Remove-Item .skillforge/profile-2026-0001-demo.sqlite3 -ErrorAction SilentlyContinue

uv run skillforge-kb agent-run `
  --event-file examples/simulations/profile-2026-0001-demo/01_initialize_event.json `
  --thread-id profile-2026-0001-demo `
  --state-db .skillforge/profile-2026-0001-demo.sqlite3

uv run skillforge-kb agent-run `
  --event-file examples/simulations/profile-2026-0001-demo/02_cnn_progress_event.json `
  --thread-id profile-2026-0001-demo `
  --state-db .skillforge/profile-2026-0001-demo.sqlite3 `
  --output-file examples/simulations/profile-2026-0001-demo/planning_result.json
```

## Outputs

- `planning_result.json` is the complete validated Agent state after both events.
- `resource_agent_handoff.json` is the reduced next-step input for the resource Agent.

The handoff reuses the project's existing blueprint and allocation contracts. It is not
a formal `ResourceBrief`: the governed evidence manifest currently contains zero
published records for `dl.vision.image-tensor:intro`, so the handoff explicitly reports
`blocked_missing_published_evidence`. Candidate retrieval is not promoted to evidence.

The expected current concept is `dl.vision.image-tensor`, the first node in the current
ontology's CNN chapter. Its delivery depth and support decision come from the new Agent
run rather than the old profile's embedded path.

## Input Summary

| Field | Normalized input |
| --- | --- |
| Profile | `PROFILE-2026-0001-DEMO` |
| Graph | `ai-course-v1` |
| Ability | theory `0.55`, coding `0.70`, math `0.62`, problem solving `0.55` |
| Reliable mapped mastery | 8 canonical concepts |
| Primary error pattern | concept confusion, ratio `0.42` |
| Preferred stack | Python, PyTorch, Jupyter Notebook |
| Preferred order | intuition, derivation, code practice, interview review |
| Weekly pace | 10 hours |
| Scenario progress | 56 pre-CNN concepts completed |

## Planning Output Summary

| Field | Agent output |
| --- | --- |
| Status | `ready` |
| Path ID | `path_6d09613775f5b15f501f0f4433d3e4003e6a04144b41e1e2053c6dc5162d9af9` |
| Total path nodes | 140 |
| Completed baseline | 56 |
| Current node | `dl.vision.image-tensor` (Image Tensor) |
| Delivery depth | `intro` |
| Ability readiness | `0.613` |
| Readiness score | `0.2452` |
| Support need | `1.0` |
| Support intensity | `scaffolded` |
| Estimated resource time | 90 minutes |
| Candidate knowledge | `no_results` |

The Agent chooses `intro` even though the learner has intermediate overall ability:
there is no reviewed concept-level mastery for image tensors. The ability contribution
raises readiness, while the evidence floor keeps support at `scaffolded`. This is the
intended conservative personalization behavior.

## Personalized CNN Path

| Sequence | Concept | Initial state | Depth |
| ---: | --- | --- | --- |
| 57 | `dl.vision.image-tensor` | available | intro |
| 58 | `dl.cnn.convolution` | blocked by image tensor | intro |
| 59 | `dl.cnn.cross-correlation` | pending | intro |
| 60 | `dl.cnn.kernel-filter` | blocked by convolution | intro |
| 61 | `dl.cnn.padding-stride` | blocked by convolution | intro |
| 62 | `dl.cnn.pooling` | blocked by convolution | intro |
| 63 | `dl.cnn.receptive-field` | blocked by kernel/filter | intro |
| 64 | `dl.cnn.architecture` | blocked by padding/stride and pooling | intro |
| 65 | `dl.cnn.flatten-fully-connected` | blocked by architecture | intro |
| 66 | `dl.cnn.backpropagation` | blocked by architecture | intro |

The resource Agent should consume `resource_agent_handoff.json` for sequence 57 first.
After reviewed evidence is published and the learner completes this node, the
course-planning Agent receives a new `concepts_completed` event and advances the same
path without changing its ID or order.
