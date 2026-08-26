# Learning Workbench Visualization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the existing SkillForge console visibly support the complete personalized learning loop from profile upload through chapter-aware path navigation, resource study, assessment, and progress refresh.

**Architecture:** Keep the existing FastAPI and platform contracts unchanged. Extend the static console with a path overview, node learning workspace, explicit resource/evidence states, and assessment actions that call the existing `/start-node`, `/complete-node`, and `/assessment` endpoints and re-render the returned `PlatformRunResult`.

**Tech Stack:** FastAPI static assets, semantic HTML, vanilla ES modules, CSS Grid, existing pytest frontend contract tests.

## Global Constraints

- The course graph remains the source of truth for path order, chapter/section IDs, node status, and delivery depth.
- Candidate evidence and candidate resources must remain visibly marked as preview and never appear as formally published.
- Node actions must use the existing platform endpoints; the browser must not recalculate mastery or path order.
- Keep the existing Swiss visual direction and responsive layout.

### Task 1: Extend the console structure

**Files:**
- Modify: `src/skillforge_kb/api/static/index.html`
- Test: `tests/unit/api/test_frontend.py`

- [ ] Add visible path metrics, a study-workbench region, and status containers while preserving existing IDs and tabs.
- [ ] Add semantic labels for the node resource, evidence gate, and assessment states.
- [ ] Extend the contract test with assertions for `learning-workbench`, `path-progress`, `node-resource`, and `assessment-form`.

### Task 2: Implement node study and assessment interactions

**Files:**
- Modify: `src/skillforge_kb/api/static/app.js`
- Test: `tests/unit/api/test_frontend.py`

- [ ] Render path totals and status counts from `planning.path.nodes`.
- [ ] Render a selected node's learning objectives, prerequisites, status, depth, and resource gate.
- [ ] Add `startNode`, `completeNode`, and `submitAssessment` handlers using existing API routes.
- [ ] Render lecture, practical guide, assessment, and evidence content from the returned result with preview/published labels.
- [ ] Refresh the entire result after each transition and preserve the selected node where possible.

### Task 3: Polish responsive states

**Files:**
- Modify: `src/skillforge_kb/api/static/app.css`

- [ ] Add stable styles for metrics, study workspace, resource content, code blocks, gate notices, and assessment feedback.
- [ ] Keep controls at accessible touch sizes and preserve the existing mobile single-column layout.
- [ ] Add reduced-motion behavior for transitions.

### Task 4: Verify the browser contract

**Files:**
- Test: `tests/unit/api/test_frontend.py`

- [ ] Run the frontend contract tests.
- [ ] Run Node syntax checking on `app.js`.
- [ ] Start the API and exercise profile upload/run through the console endpoints, confirming path rendering and transition responses.

