# Learner Profile CNN Path Simulation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to execute this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate reproducible canonical inputs and outputs for a CNN-focused personalized-path simulation from the final learner profile export.

**Architecture:** Normalize only upstream profile facts into a canonical `initialize` event. Use a separate explicit progress event to align the old profile's current CNN chapter with the current graph's 56-node prefix. Run the existing CLI with SQLite, then derive a resource-Agent handoff from the validated Agent result.

**Tech Stack:** Existing Python 3.12 Agent runtime, Pydantic schemas, Typer CLI, SQLite checkpointer, PowerShell/JSON artifacts.

## Global Constraints

- Do not copy the raw profile export into Git.
- Do not treat `learning_path_context` or `resource_generation_hints` as new planner output.
- Do not force composite `kp_*` labels into one canonical concept.
- Do not call an LLM or publish candidate knowledge as formal evidence.
- Preserve the explicit simulation assumptions in a README beside the outputs.

---

### Task 1: Create Canonical Simulation Inputs

**Files:**
- Create: `examples/simulations/profile-2026-0001-demo/01_initialize_event.json`
- Create: `examples/simulations/profile-2026-0001-demo/02_cnn_progress_event.json`
- Create: `examples/simulations/profile-2026-0001-demo/README.md`

- [x] **Step 1: Write the normalized initialize event.**

Include the canonical `learner-profile.v1` profile, exact graph version `ai-course-v1`,
explicit assessment runs, conservative mastery mappings, four ability scores, filtered
error patterns, and canonical learning preferences.

- [x] **Step 2: Write the CNN progress event.**

Use event kind `concepts_completed` and the 56 ordered canonical IDs before
`chapter.05.cnn-representation`. This event is labeled as a simulation scenario
baseline in the README.

- [x] **Step 3: Document every normalization assumption.**

Record source fields, omitted composite IDs, confidence normalization, learner hash,
and the distinction between profile facts and scenario control.

### Task 2: Run the Existing Agent and Produce Outputs

**Files:**
- Create: `examples/simulations/profile-2026-0001-demo/planning_result.json`
- Create: `examples/simulations/profile-2026-0001-demo/resource_agent_handoff.json`

- [x] **Step 1: Run initialize with SQLite.**

```powershell
uv run skillforge-kb agent-run `
  --event-file examples/simulations/profile-2026-0001-demo/01_initialize_event.json `
  --thread-id profile-2026-0001-demo `
  --state-db .skillforge/profile-2026-0001-demo.sqlite3
```

- [x] **Step 2: Run the CNN progress event against the same thread.**

```powershell
uv run skillforge-kb agent-run `
  --event-file examples/simulations/profile-2026-0001-demo/02_cnn_progress_event.json `
  --thread-id profile-2026-0001-demo `
  --state-db .skillforge/profile-2026-0001-demo.sqlite3 `
  --output-file examples/simulations/profile-2026-0001-demo/planning_result.json
```

- [x] **Step 3: Extract the resource handoff from the validated JSON result.**

The handoff must include the current canonical node, adaptation decision, path ID,
profile preferences, error-pattern priorities, and candidate knowledge status. It must
not invent evidence records or include legacy IDs as graph IDs.

### Task 3: Verify the Simulation

- [x] **Step 1: Validate both events with Pydantic through the CLI.**
- [x] **Step 2: Assert the final result is `ready` and the current node belongs to CNN.**
- [x] **Step 3: Assert the output path and handoff contain stable canonical IDs.**
- [x] **Step 4: Run `git diff --check`, Ruff, and the focused runtime tests.**
- [x] **Step 5: Commit the simulation artifacts with `data: add CNN profile path simulation`.**
