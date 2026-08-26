# Standalone Course Planning Agent

This command runs the course-planning Agent locally from the governed course graph,
concept attributes, and the tracked candidate knowledge snapshot. It requires Python
3.12 and `uv`; it does not require an API key, LLM, FastAPI service, Qdrant, Neo4j,
Postgres, or Docker.

## Setup

From the repository root:

```powershell
uv sync --dev
```

## One-Shot Run

```powershell
uv run skillforge-kb agent-run `
  --event-file examples/agents/initialize_event.json `
  --thread-id demo-student
```

The command writes a single JSON result to stdout. A successful initialization returns
`status=ready`, a deterministic learning path, the current node and its adaptation, and
a `knowledge_context`. `knowledge_context.status=no_results` is a valid precision-safe
result when no candidate chunk contains the current concept's formal Chinese or English
name.

Use `--output-file` to atomically write the same JSON emitted to stdout:

```powershell
uv run skillforge-kb agent-run `
  --event-file examples/agents/initialize_event.json `
  --thread-id demo-student `
  --output-file .skillforge/results/demo-student.json
```

## Persistent Session

Pass a SQLite path to preserve LangGraph checkpoints across command invocations:

```powershell
uv run skillforge-kb agent-run `
  --event-file examples/agents/initialize_event.json `
  --thread-id demo-student `
  --state-db .skillforge/demo.sqlite3
```

Run the same event and thread ID again to receive `event_duplicate=true`. A requested
SQLite database is mandatory: database creation or access errors cause the command to
fail instead of falling back to in-memory state.

Without `--state-db`, state is in memory for that process only. Each CLI invocation is a
new process, so use SQLite for subsequent `profile_refreshed`, `concepts_completed`, or
`reset` events.

## Canonical Event Contract

Input must validate as `PlanningAgentEvent` (`planning-agent-event.v1`). Initialize and
profile-refresh events must contain a canonical `LearnerProfileSnapshot`
(`learner-profile.v1`) with an explicit `graph_version`. Assessed mastery entries require
confidence, observation time, and evidence references. The command does not infer
missing fields or translate composite legacy knowledge nodes.

The example file is [initialize_event.json](../../examples/agents/initialize_event.json).
Use `--course-file`, `--relations-file`, `--attributes-file`, and `--knowledge-file` only
when supplying explicit compatible assets.

## Governance Boundary

Knowledge hits remain `evidence_state=candidate`. Candidate retrieval is not formal
evidence publication and does not create `EvidenceRecord` or `EvidenceBundle` objects.
This command does not generate learning resources, invoke an LLM, or coordinate other
Agents.

Input/configuration errors exit with code 2. A valid Agent result whose status is
`failed` is still printed as JSON and exits with code 3.

The integrated platform service persists runs, assessment idempotency records, and
knowledge-tracing observations to `SKILLFORGE_PLATFORM_STATE_DB` (default:
`.skillforge/platform.sqlite3`). Keep this SQLite file outside source control; it is
runtime state, not a fixture or an evidence source.
