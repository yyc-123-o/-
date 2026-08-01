# Learner Profile CNN Path Simulation

## Goal

Use the final learner-profile export as a reproducible simulation input for the
deterministic course-planning Agent, produce a CNN-focused personalized path, and
prepare a structured handoff for the resource-generation Agent.

## Scope

The raw export at `D:\张维揭榜挂帅\学情画像输出-最终版.json` remains outside the
repository. The simulation stores only normalized canonical events and generated
outputs under `examples/simulations/profile-2026-0001-demo/`. The old
`learning_path_context` and `resource_generation_hints` sections are treated as
downstream reference data, never as planner output.

## Input Normalization

`01_initialize_event.json` contains a `PlanningAgentEvent` with a
`LearnerProfileSnapshot`:

- `profile_id` is copied from `profile_meta.profile_id`.
- `learner_ref` is SHA-256 of `basic_profile.learner_id`.
- `graph_version` is explicitly set to `ai-course-v1` for this simulation.
- Only unambiguous one-to-one `kp_*` mappings are included in canonical mastery.
- Composite labels such as “CNN”, “RNN/LSTM”, “Transformer/Attention”, and
  “L1/L2/Dropout” are retained only in the mapping notes and are not forced into a
  single graph concept.
- Per-concept confidence is a deterministic simulation normalization:
  `min(0.90, 0.50 + 0.10 * test_count)` for assessed entries. Evidence references
  point back to the source profile and `kp_*` identifier.
- The four ability scores use the profile's global IRT confidence (`0.90`) as a
  shared simulation confidence because the export has no per-dimension confidence.
  This is explicitly marked as a simulation assumption, not a new diagnosis.
- Error patterns and learning preferences are copied only after canonical ID
  filtering; no derived path or resource fields are copied into the profile.

## CNN Progress Baseline

`02_cnn_progress_event.json` is a separate `concepts_completed` event containing the
56 canonical concepts ordered before `chapter.05.cnn-representation`. This is a
scenario control derived from the profile's explicit `current_chapter=ch03_cnn`
claim, aligning the legacy chapter naming with the current graph's finer chapter
taxonomy. It is not presented as new mastery evidence. The resulting path begins at
the first CNN node and continues through the graph's CNN subpath.

## Outputs

- `planning_result.json`: full `CoursePlanningAgentResult` after both events.
- `resource_agent_handoff.json`: current node, current adaptation, profile preferences,
  error-pattern priorities, and the path audit needed by the resource Agent. Candidate
  knowledge context remains candidate-only.
- `README.md`: exact commands, assumptions, expected current node, and field-level
  input/output explanation.

## Acceptance Criteria

1. Both events validate against the canonical planning-event schema.
2. Running them with SQLite produces `status=ready` and a current node in
   `chapter.05.cnn-representation`.
3. The path order is stable and contains the CNN chapter nodes in graph order.
4. The resource handoff is valid JSON and contains no raw legacy `kp_*` IDs as
   canonical concept IDs.
5. No source profile, API key, LLM call, or formal evidence publication is added.
