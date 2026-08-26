## Scope

- Task ID:
- Change type: contract / algorithm / experiment / fix / documentation
- Base branch: `feature/course-agent-kb-retrieval`

## What Changed

<!-- Describe one reviewable outcome. -->

## Contract And Invariants

- [ ] Course concept IDs and graph version remain valid.
- [ ] Hard-prerequisite violation rate remains zero.
- [ ] Required path concept set and order remain stable.
- [ ] Candidate evidence was not promoted to published evidence.
- [ ] Existing deterministic baseline remains available for fallback/comparison.

## Algorithm Evidence

- Dataset kind: synthetic / expert-labelled / observed / not applicable
- Dataset version and digest:
- Baseline:
- Candidate method:
- Metrics and result:
- Random seed:
- Paper or method references:

## Verification

```powershell
uv run pytest tests/unit tests/acceptance -q
uv run ruff check src tests scripts
uv run mypy src/skillforge_kb
```

- [ ] Tests added for normal, cold-start, low-confidence, boundary, and invalid inputs.
- [ ] Reproduction command and machine-readable result are included.
- [ ] Synthetic results are not described as real teaching effectiveness.
- [ ] No secrets, personal student data, local databases, or cache artifacts are committed.

## Review Notes

<!-- Call out contract changes, limitations, follow-up work, and rollback path. -->
