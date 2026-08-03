# Contributing to SkillForge

This repository uses short-lived branches, reviewed contracts, deterministic tests,
and reproducible algorithm reports. Do not commit directly to `main`.

## Development Baseline

Requirements:

- Python 3.12
- `uv`
- Git

Set up and verify the repository:

```powershell
uv sync --frozen --dev
uv run pytest tests/unit tests/acceptance -q
uv run ruff check src tests scripts
uv run mypy src/skillforge_kb
```

Service-backed tests under `tests/integration` require their documented PostgreSQL,
Neo4j, or Docker prerequisites. A missing service is not a reason to skip unit and
acceptance tests.

## Branch And Pull Request Workflow

Course-Agent algorithm work starts from the shared feature branch until that branch is
merged into `main`:

```powershell
git fetch origin
git switch -c alg/cp-01-bkt-mastery origin/feature/course-agent-kb-retrieval
```

Use one task ID per branch and pull request:

- `alg/<task-id>-<summary>` for algorithm implementations and experiments
- `feat/<summary>` for product behavior
- `fix/<summary>` for defects
- `docs/<summary>` for documentation-only changes

Commit messages use `type: imperative summary`, for example:

```text
feat: add bkt mastery estimator
test: compare hybrid retrieval baselines
docs: record node weight calibration limits
```

Open algorithm pull requests against `feature/course-agent-kb-retrieval`. Keep each PR
independently testable and small enough to review. Contract changes and algorithm
implementations should be separate PRs when both are required.

## Course-Agent Boundaries

The following are stable facts, not optimization targets:

- Course chapters, concept IDs, teaching order, and hard prerequisites come from the
  versioned ontology.
- Algorithms must not introduce a hard-prerequisite cycle or reorder the deterministic
  required path.
- Low-confidence or missing profile data must trigger conservative behavior.
- Candidate knowledge chunks are not published evidence.
- Resource-generation code cannot change path identity, node order, or delivery depth.
- Synthetic evaluation results are regression evidence, not claims about real students.

Algorithm implementations must keep the current deterministic baseline available for
comparison and fallback. Do not replace a baseline until a separate review accepts the
new algorithm, dataset, metrics, and versioned policy.

## Data And Artifact Rules

- Use `data/index_chunks.jsonl` for the candidate retrieval baseline.
- Do not deserialize `data/index_chunks.pkl`, `data/index_bm25.pkl`, or
  `data/index_faiss.index` in Agent runtime code. Their provenance and build settings are
  not governed runtime dependencies.
- Do not commit personal student data, API keys, local databases, cache directories, or
  ad hoc generated reports.
- Record dataset version, input digest, random seed, algorithm version, parameters, and
  metrics for every experiment.
- New external datasets require source, license, and privacy review before use.

## Algorithm Pull Request Requirements

Every algorithm PR must include:

1. A task ID from
   `docs/team/2026-08-03-course-agent-algorithm-collaboration.md`.
2. A written input/output contract and fallback behavior.
3. A baseline comparison using the same dataset split and metrics.
4. Unit tests for cold start, low confidence, boundaries, invalid input, and replay.
5. An invariant test proving hard-prerequisite violations remain zero.
6. A machine-readable result or a reproducible command that generates it.
7. An explicit statement distinguishing synthetic, expert-labelled, and observed data.

Use the repository Issue and Pull Request templates. A paper link or notebook without a
tested package integration is reference material, not a completed algorithm task.
