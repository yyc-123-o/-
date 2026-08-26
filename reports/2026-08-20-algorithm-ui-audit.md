# Platform Algorithm and UI Audit

Date: 2026-08-20
Branch: `feature/course-agent-kb-retrieval`

## Algorithm Findings And Changes

The main functional gap was that `learning_scope.primary_kp_id` from the
Learner Profile Agent was discarded before planning. A profile could say that
CNN was the current objective while the platform still selected the first
unfinished course node.

The planning contract now accepts an optional `target_concept_id`:

- v2.1 profile adaptation returns a mapped `suggested_target_concept_id`;
- the run request and planning event can carry an explicit target;
- the planner keeps the full required path and records the target as the
  learner's focus;
- the target is persisted in `PathDecision` and included in targeted path IDs;
- path updates preserve the target and reject target changes mid-session;
- resource handoff validation recomputes targeted path identity;
- unknown target IDs fail with a typed planning error.

Full-course planning remains backward compatible. When no target is supplied,
the previous full required-concept path and path ID serialization are retained.

## UI Changes

The console now presents:

- a dedicated target concept input with automatic v2.1 profile suggestions;
- a four-card run overview for current node, depth, evidence, and next action;
- clearer pipeline states, including a distinct blocked state;
- path summaries showing full versus targeted planning;
- typed evidence labels and formal/candidate/missing counts;
- explicit next-step copy when generation is blocked;
- responsive two-column overview behavior on narrow screens;
- the existing Swiss visual system with tighter information hierarchy.

## Verification

- `458 passed` for unit and acceptance tests;
- Ruff passed;
- mypy passed for 88 source files;
- JavaScript syntax check passed;
- `git diff --check` passed;
- live health endpoint: HTTP `200`;
- live homepage: HTTP `200`, target input and overview present;
- live target run: HTTP `201`, current node `dl.cnn.convolution`, two-node
  prerequisite closure, candidate draft generated, all resource identity fields
  consistent.

## Remaining Product Boundary

The default evidence manifest is still empty by governance design. Strict mode
therefore blocks until definition, code, and exercise evidence are reviewed,
licensed, and published. Candidate preview is available for inspection but is
not publishable.

The in-app browser runtime was unavailable during this audit, so screenshot and
click-level responsive QA remain a follow-up blind spot. HTTP/API and static
asset checks were completed.
