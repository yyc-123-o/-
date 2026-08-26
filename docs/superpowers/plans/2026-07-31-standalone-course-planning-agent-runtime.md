# Standalone Course Planning Agent Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide a one-command standalone course-planning Agent with canonical event input, concept-safe candidate retrieval, and optional SQLite session persistence.

**Architecture:** A runtime factory loads validated course assets and the candidate JSONL corpus, then constructs the existing LangGraph Agent. The CLI owns JSON file boundaries and chooses either `InMemorySaver` or `SqliteSaver`; the Agent remains reusable as a Python library. BM25 receives formal bilingual concept anchors and only scores chunks containing a complete anchor phrase.

**Tech Stack:** Python 3.12, Pydantic v2, LangGraph, LangChain Core, `langgraph-checkpoint-sqlite>=3,<4`, Typer, pytest, Ruff, mypy, and the standard library.

## Global Constraints

- Only standard `PlanningAgentEvent` JSON and `LearnerProfileSnapshot` input are accepted.
- Do not infer missing graph versions, confidence, evidence references, or composite profile mappings.
- Runtime defaults are explicit repository paths; never scan `processed/` or silently fall back to another corpus.
- Candidate chunks remain `evidence_state=candidate` and never enter formal evidence publication.
- No LLM, API key, FastAPI service, Qdrant service, or Docker daemon is required for `agent-run`.
- SQLite is optional and must never silently fall back to memory when requested.
- Retrieval filtering may return `no_results`; it must not alter path ID, path order, node depth, or adaptation results.
- Existing Python API behavior remains backward compatible when no new arguments are supplied.

---

### Task 1: Add Concept Anchor Contracts and Precision-Gated BM25

**Files:**
- Modify: `src/skillforge_kb/retrieval/models.py`
- Modify: `src/skillforge_kb/retrieval/bm25.py`
- Modify: `src/skillforge_kb/agents/planning_agent.py`
- Modify: `tests/unit/retrieval/test_bm25.py`
- Modify: `tests/unit/retrieval/test_corpus.py`
- Modify: `tests/unit/agents/test_planning_agent.py`

**Interfaces:**
- `KnowledgeQuery.anchors: tuple[str, ...] = ()`; anchors are non-empty phrases and are deduplicated in input order.
- `build_knowledge_query(catalog, node)` sets anchors to the concept's formal Chinese and English names only; aliases remain scoring terms.
- `Bm25KnowledgeRetriever.retrieve()` applies anchor gating before scoring when anchors are present.

- [ ] **Step 1: Write failing anchor tests.**

```python
def test_rag_anchor_does_not_match_storage(corpus):
    result = Bm25KnowledgeRetriever(corpus).retrieve(
        KnowledgeQuery(query="RAG", anchors=("RAG",), top_k=5)
    )
    assert result.status is KnowledgeRetrievalStatus.OK
    assert all("rag" in hit.text.casefold() or hit.source_title == "RAG" for hit in result.hits)


def test_anchor_miss_returns_no_results(corpus):
    result = Bm25KnowledgeRetriever(corpus).retrieve(
        KnowledgeQuery(query="数学标量", anchors=("不存在的正式概念",))
    )
    assert result.status is KnowledgeRetrievalStatus.NO_RESULTS


def test_no_anchors_preserves_generic_bm25_behavior(corpus):
    result = Bm25KnowledgeRetriever(corpus).retrieve(KnowledgeQuery(query="LoRA"))
    assert result.status is KnowledgeRetrievalStatus.OK
```

Add an Agent test asserting `build_knowledge_query(catalog, node).anchors` contains the concept's formal bilingual names and excludes arbitrary aliases.

- [ ] **Step 2: Run focused tests and verify RED.**

Run: `uv run pytest tests/unit/retrieval tests/unit/agents/test_planning_agent.py -q`

Expected: Pydantic rejects the unknown `anchors` field or the anchor tests return the existing broad results.

- [ ] **Step 3: Implement the anchor contract and phrase matcher.**

Add a frozen tuple field and a validator that strips whitespace, rejects blank phrases, and removes duplicates while preserving order. Tokenize each anchor with the existing tokenization rules. Store document token tuples in the BM25 constructor. A document passes the gate when one anchor token sequence occurs contiguously in its document token tuple; this makes `RAG` a complete token and prevents matches inside `storage`, while Chinese phrases remain contiguous character sequences. Keep generic BM25 unchanged when `anchors` is empty.

- [ ] **Step 4: Generate formal anchors from the planning query.**

In `build_knowledge_query`, use `concept.names.zh` and `concept.names.en` as anchors, and keep the existing names, aliases, summaries, section/chapter titles, outcomes, and depth in the query text. Do not include raw learner profile text.

- [ ] **Step 5: Run focused tests and quality checks.**

Run:

```powershell
uv run pytest tests/unit/retrieval tests/unit/agents/test_planning_agent.py -q
uv run ruff check src/skillforge_kb/retrieval src/skillforge_kb/agents tests/unit/retrieval tests/unit/agents
uv run mypy src/skillforge_kb/retrieval src/skillforge_kb/agents
```

Expected: all focused tests pass, Ruff and mypy exit 0.

- [ ] **Step 6: Commit the precision gate.**

```powershell
git add src/skillforge_kb/retrieval src/skillforge_kb/agents tests/unit/retrieval tests/unit/agents
git commit -m "fix: gate knowledge retrieval by concept anchors"
```

### Task 2: Add a Reusable Standalone Runtime and SQLite Checkpointer Support

**Files:**
- Create: `src/skillforge_kb/agents/runtime.py`
- Modify: `src/skillforge_kb/agents/planning_agent.py`
- Modify: `src/skillforge_kb/agents/__init__.py`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `.gitignore`
- Create: `tests/unit/agents/test_runtime.py`

**Interfaces:**
- `StandaloneAgentPaths` frozen dataclass with `course_file`, `relations_file`, `attributes_file`, and `knowledge_file`.
- `StandaloneAgentPaths.from_project_root(root: Path) -> StandaloneAgentPaths` resolves the four default paths without reading environment state.
- `load_planning_event(path: Path) -> PlanningAgentEvent` parses UTF-8 JSON and validates the canonical event schema.
- `build_standalone_course_planning_agent(paths, *, checkpointer: BaseCheckpointSaver | None = None) -> CoursePlanningAgent` loads all assets and constructs the retrieval-backed Agent.
- `run_standalone_event(paths, event, thread_id, *, checkpointer=None) -> CoursePlanningAgentResult` invokes the Agent.

- [ ] **Step 1: Add failing runtime construction tests.**

```python
def test_runtime_loads_default_assets_and_runs_initialize(tmp_path):
    paths = StandaloneAgentPaths.from_project_root(Path.cwd())
    event = load_planning_event(Path("examples/agents/initialize_event.json"))

    result = run_standalone_event(paths, event, "runtime-test")

    assert result.status is PlanningAgentStatus.READY
    assert result.path is not None
    assert result.current_node is not None
    assert result.knowledge_context is not None


def test_loader_rejects_noncanonical_profile(tmp_path):
    path = tmp_path / "profile.json"
    path.write_text('{"profile_meta": {"profile_id": "legacy"}}', encoding="utf-8")

    with pytest.raises(ValueError, match="invalid planning event"):
        load_planning_event(path)
```

- [ ] **Step 2: Run tests and verify RED.**

Run: `uv run pytest tests/unit/agents/test_runtime.py -q`

Expected: import failure because `agents.runtime` and the canonical example do not exist.

- [ ] **Step 3: Add the SQLite dependency and generalize checkpointer typing.**

Add `langgraph-checkpoint-sqlite>=3,<4` to the main dependencies, run `uv lock`, and run `uv sync --dev`. Change `CoursePlanningAgent.create` and `build_course_planning_graph` to accept `BaseCheckpointSaver | None`; retain `InMemorySaver()` as the default. Do not change existing callers.

- [ ] **Step 4: Implement the runtime factory.**

Load `OntologyCatalog`, `ConceptAttributeCatalog`, `KnowledgeCorpus`, `Bm25KnowledgeRetriever`, and `KnowledgeRetrievalTool` from the paths object. Parse event files with `json.loads` followed by `PlanningAgentEvent.model_validate`; wrap `OSError`, JSON decode errors, and Pydantic validation errors as concise `ValueError` messages that include the input path. Never inspect `processed/` or construct a fallback profile.

- [ ] **Step 5: Add the canonical event example.**

Create `examples/agents/initialize_event.json` with:

```json
{
  "schema_version": "planning-agent-event.v1",
  "event_id": "event_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "kind": "initialize",
  "profile": {
    "schema_version": "learner-profile.v1",
    "profile_id": "standalone-demo",
    "learner_ref": "0000000000000000000000000000000000000000000000000000000000000000",
    "graph_version": "ai-course-v1",
    "assessment_runs": [],
    "knowledge_mastery": [],
    "abilities": {},
    "error_patterns": [],
    "preferences": {}
  },
  "completed_concept_ids": []
}
```

- [ ] **Step 6: Run tests and commit the runtime foundation.**

Run: `uv run pytest tests/unit/agents/test_runtime.py tests/unit/agents/test_planning_agent.py -q`.

Expected: runtime and existing Agent tests pass. Then run `git add src/skillforge_kb/agents pyproject.toml uv.lock .gitignore examples/agents tests/unit/agents/test_runtime.py` and commit with `feat: add standalone agent runtime`.

### Task 3: Add the `agent-run` CLI and Optional SQLite Sessions

**Files:**
- Modify: `src/skillforge_kb/cli.py`
- Modify: `tests/unit/test_cli.py`
- Create: `tests/acceptance/test_standalone_agent_cli.py`

**Interfaces:**
- `agent-run` accepts `--event-file`, `--thread-id`, optional `--state-db`, optional `--output-file`, and optional explicit asset paths.
- Success always writes JSON to stdout; `--output-file` writes the same JSON atomically.
- Input/configuration errors exit 2; Agent result status `failed` exits 3 after printing the result.

- [ ] **Step 1: Write failing CLI and SQLite tests.**

```python
def test_agent_run_prints_json(capsys):
    result = runner.invoke(
        app,
        ["agent-run", "--event-file", "examples/agents/initialize_event.json", "--thread-id", "cli-demo"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ready"
    assert payload["current_node"] is not None


def test_agent_run_persists_duplicate_event(tmp_path):
    state_db = tmp_path / "agent.sqlite3"
    args = [
        "agent-run",
        "--event-file", "examples/agents/initialize_event.json",
        "--thread-id", "sqlite-demo",
        "--state-db", str(state_db),
    ]
    first = runner.invoke(app, args)
    second = runner.invoke(app, args)
    assert first.exit_code == 0
    assert second.exit_code == 0
    assert json.loads(second.stdout)["event_duplicate"] is True
```

- [ ] **Step 2: Run focused CLI tests and verify RED.**

Run: `uv run pytest tests/unit/test_cli.py tests/acceptance/test_standalone_agent_cli.py -q`

Expected: the command is not registered or the runtime cannot be constructed.

- [ ] **Step 3: Implement `agent-run`.**

Add Typer options with explicit defaults from `StandaloneAgentPaths.from_project_root(PROJECT_ROOT)`. Validate all input files before creating a checkpointer. When `--state-db` is present, create its parent directory and use `SqliteSaver.from_conn_string(str(path))` as a context manager; do not catch its failures as memory fallback. Invoke `run_standalone_event`, serialize `model_dump(mode="json")` with `ensure_ascii=False`, and write stdout/result file as specified. Use `typer.BadParameter` for input errors and `typer.Exit(code=3)` for a valid failed Agent result. Reject an output file or state DB path that resolves to any input asset.

- [ ] **Step 4: Run focused CLI and acceptance tests.**

Run: `uv run pytest tests/unit/test_cli.py tests/acceptance/test_standalone_agent_cli.py -q`.

Expected: CLI output is parseable JSON, the in-memory run returns `ready`, and the second SQLite run returns `event_duplicate=true`.

- [ ] **Step 5: Commit the CLI.**

```powershell
git add src/skillforge_kb/cli.py tests/unit/test_cli.py tests/acceptance/test_standalone_agent_cli.py
git commit -m "feat: add standalone agent run command"
```

### Task 4: Add End-to-End Precision Tests and Runbook

**Files:**
- Create: `tests/acceptance/test_standalone_agent_runtime.py`
- Create: `docs/runbooks/standalone-course-planning-agent.md`
- Modify: `data/README.md` only to link the runbook if needed

- [ ] **Step 1: Write the failing end-to-end assertions.**

```python
def test_math_node_does_not_return_unrelated_project_context():
    paths = StandaloneAgentPaths.from_project_root(Path.cwd())
    event = load_planning_event(Path("examples/agents/initialize_event.json"))
    result = run_standalone_event(paths, event, "precision-demo")
    assert result.status is PlanningAgentStatus.READY
    assert result.current_node is not None
    assert result.knowledge_context is not None
    assert result.knowledge_context.status is KnowledgeRetrievalStatus.NO_RESULTS
```

- [ ] **Step 2: Run the test and verify RED before the anchor gate exists.**

Run: `uv run pytest tests/acceptance/test_standalone_agent_runtime.py -q`.

Expected before Task 1: the result contains the previous broad BM25 candidates, so the `NO_RESULTS` assertion fails.

- [ ] **Step 3: Implement runbook and exact command examples.**

Document environment setup with `uv sync`, the one-shot command, the SQLite command, canonical event requirements, expected `ready/no_results` behavior, and the explicit statement that candidate retrieval is not formal evidence or resource generation.

- [ ] **Step 4: Run all relevant quality gates.**

Run:

```powershell
uv run pytest tests/unit tests/acceptance -q
uv run ruff check src tests
uv run mypy src/skillforge_kb
git diff --check
uv run skillforge-kb --help
uv run skillforge-kb agent-run --event-file examples/agents/initialize_event.json --thread-id smoke
```

Expected: all 365+ unit/acceptance tests pass, Ruff/mypy/diff checks pass, help lists `agent-run`, and the smoke command emits JSON with `status=ready`.

- [ ] **Step 5: Commit acceptance and documentation.**

```powershell
git add tests/acceptance/test_standalone_agent_runtime.py docs/runbooks/standalone-course-planning-agent.md data/README.md
git commit -m "test: verify standalone planning agent runtime"
```

### Task 5: Final Review and Handoff

- [ ] **Step 1: Review all changed files and confirm boundaries.**

Run `git diff publish/knowledge-base-v1...HEAD --stat` and `git diff --check`. Confirm no user-owned files, legacy profile sample, serialized indexes, API keys, or Docker-only runtime requirements were added.

- [ ] **Step 2: Verify data and example hashes/paths.**

Run `git hash-object -- data/index_chunks.jsonl` and `Test-Path examples/agents/initialize_event.json`. Expected: the data hash remains `5657a46477ccb6917ac5c9d959db03822625fb9e` and the example exists.

- [ ] **Step 3: Report the exact run command, test results, SQLite behavior, and remaining formal-evidence/LLM boundaries.**
