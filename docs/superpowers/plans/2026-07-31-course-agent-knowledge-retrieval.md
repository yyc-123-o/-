# Course Agent Knowledge Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Load the verified JSONL knowledge corpus with a safe deterministic BM25 retriever and connect candidate context to the current node of `CoursePlanningAgent` without changing path decisions.

**Architecture:** A new `retrieval` package owns strict JSONL models, all-or-nothing loading, tokenization, BM25 ranking, and a LangChain `StructuredTool` adapter. The LangGraph planning graph calls the tool only after choosing the current node. Retrieval is auxiliary: failures and no-results are structured context, never planning failures.

**Tech Stack:** Python 3.12, Pydantic v2, LangChain Core, LangGraph, pytest, Ruff, mypy, and standard-library JSON/regex/hashlib.

## Global Constraints

- Runtime input is only `data/index_chunks.jsonl`; never load the uploaded pickle or FAISS artifacts.
- Candidate chunks never become `EvidenceRecord` or `EvidenceBundle` and never bypass publication gates.
- Retrieval cannot modify path ID, node membership, node order, node depth, adaptations, or planning audit digests.
- `CoursePlanningAgent.create(...)` remains unchanged when no retriever is supplied.
- No API key, embedding model, Qdrant service, Docker service, or new runtime dependency is required.
- Preserve all user-owned files and local corpora outside the tracked JSONL intake.
- Use red-green-refactor for every production behavior change.

---

### Task 1: Add Candidate Corpus Models and Safe JSONL Intake

**Files:**
- Create: `src/skillforge_kb/retrieval/__init__.py`
- Create: `src/skillforge_kb/retrieval/models.py`
- Create: `src/skillforge_kb/retrieval/corpus.py`
- Create: `tests/unit/retrieval/__init__.py`
- Create: `tests/unit/retrieval/test_corpus.py`
- Copy: `data/index_chunks.jsonl` from `processed/index_chunks.jsonl`
- Modify: `data/README.md`

**Interfaces:**
- `KnowledgeDifficulty`: exact values `入门`, `进阶`, `高阶`.
- `KnowledgeRetrievalStatus`: `ok`, `no_results`, `unavailable`.
- `KnowledgeChunk`: frozen, extra-forbid Pydantic model for the nine JSONL fields.
- `KnowledgeQuery(query: str, top_k: int = 5, concept_id: str | None = None)` with non-empty query and `1 <= top_k <= 20`.
- `KnowledgeCorpus.load(path: Path) -> KnowledgeCorpus` validates every line, rejects duplicate IDs, and reports the failing line number.
- `build_corpus_digest(chunks: tuple[KnowledgeChunk, ...]) -> str` returns a stable SHA-256 digest.

- [ ] **Step 1: Write the failing tests.**

```python
def test_load_validates_rows_and_digest(tmp_path):
    path = tmp_path / "chunks.jsonl"
    path.write_text(json.dumps(valid_row(), ensure_ascii=False) + "\n", encoding="utf-8")
    corpus = KnowledgeCorpus.load(path)
    assert corpus.chunks[0].difficulty is KnowledgeDifficulty.INTERMEDIATE
    assert corpus.digest == KnowledgeCorpus.load(path).digest


def test_loader_rejects_duplicate_ids_and_reports_bad_line(tmp_path):
    path = tmp_path / "chunks.jsonl"
    path.write_text(json.dumps(valid_row()) + "\n{bad}\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"line 2"):
        KnowledgeCorpus.load(path)


def test_query_rejects_invalid_top_k():
    with pytest.raises(ValueError):
        KnowledgeQuery(query="RAG", top_k=0)
```

The fixture row must contain `chunk_id`, `doc_id`, `source_title`, `heading_path`, `text`, `page_no`, `domain_tag`, `difficulty`, and `token_count`.

- [ ] **Step 2: Run the focused tests and verify RED.**

Run: `uv run pytest tests/unit/retrieval/test_corpus.py -q`

Expected: collection fails because `skillforge_kb.retrieval` does not exist.

- [ ] **Step 3: Implement the models and loader.**

Use `ConfigDict(frozen=True, extra="forbid")`. Normalize `heading_path` to a tuple of non-empty strings. Require positive `page_no` when present and non-negative `token_count`. Parse UTF-8 lines with `json.loads`, validate each row with `KnowledgeChunk.model_validate`, track IDs, and wrap JSON/Pydantic errors as `ValueError("invalid knowledge chunk at line N: ...")`. Do not return a partial corpus. Compute the digest from the ordered tuple of JSON-mode model dumps using sorted-key compact JSON and SHA-256; an empty file is a valid empty corpus.

- [ ] **Step 4: Run the focused tests and verify GREEN.**

Run: `uv run pytest tests/unit/retrieval/test_corpus.py -q`

Expected: all corpus tests pass.

- [ ] **Step 5: Add the verified intake file and update its policy.**

Run:

```powershell
Copy-Item -LiteralPath "D:\张维揭榜挂帅\processed\index_chunks.jsonl" -Destination "data\index_chunks.jsonl"
git hash-object -- data/index_chunks.jsonl processed/index_chunks.jsonl
```

Expected: both hashes are `5657a46477ccb6917ac5c9d959db03822625fb9e`. Update `data/README.md` to identify this as a candidate-only intake snapshot and explicitly state that serialized BM25/FAISS artifacts are not loaded.

- [ ] **Step 6: Commit.**

```powershell
git add src/skillforge_kb/retrieval tests/unit/retrieval data/index_chunks.jsonl data/README.md
git commit -m "feat: add safe knowledge corpus intake"
```

### Task 2: Implement Deterministic BM25 and LangChain Tooling

**Files:**
- Create: `src/skillforge_kb/retrieval/bm25.py`
- Create: `src/skillforge_kb/retrieval/tool.py`
- Modify: `src/skillforge_kb/retrieval/__init__.py`
- Create: `tests/unit/retrieval/test_bm25.py`
- Create: `tests/unit/retrieval/test_tool.py`

**Interfaces:**
- `KnowledgeRetriever` protocol: `retrieve(query: KnowledgeQuery) -> KnowledgeRetrievalResult`.
- `Bm25KnowledgeRetriever(corpus: KnowledgeCorpus, k1: float = 1.5, b: float = 0.75)`.
- `KnowledgeRetrievalTool(retriever: KnowledgeRetriever)` with `invoke(request: KnowledgeQuery | Mapping[str, object]) -> KnowledgeRetrievalResult` and `as_langchain_tool() -> StructuredTool`.
- `KnowledgeHit` carries IDs, source title, heading path, text, difficulty, score, and fixed `evidence_state="candidate"`.
- `KnowledgeRetrievalResult` requires hits for `ok`, no hits for `no_results`, and an error code/message for `unavailable`.

- [ ] **Step 1: Write failing ranking and wrapper tests.**

```python
def test_bm25_ranks_keyword_match_and_is_stable(corpus):
    retriever = Bm25KnowledgeRetriever(corpus)
    first = retriever.retrieve(KnowledgeQuery(query="LoRA 参数", top_k=2))
    second = retriever.retrieve(KnowledgeQuery(query="LoRA 参数", top_k=2))
    assert first.status is KnowledgeRetrievalStatus.OK
    assert first.hits[0].chunk_id == "lora"
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_unknown_terms_return_no_results(corpus):
    result = Bm25KnowledgeRetriever(corpus).retrieve(
        KnowledgeQuery(query="不存在的术语")
    )
    assert result.status is KnowledgeRetrievalStatus.NO_RESULTS
    assert result.hits == ()


def test_tool_exposes_structured_langchain_tool(corpus):
    wrapper = KnowledgeRetrievalTool(Bm25KnowledgeRetriever(corpus))
    assert wrapper.as_langchain_tool().name == "retrieve_knowledge"
    assert wrapper.invoke({"query": "RAG", "top_k": 1}).hits


def test_tool_converts_backend_exception_to_unavailable():
    class Broken:
        def retrieve(self, query):
            raise RuntimeError("index unavailable")
    result = KnowledgeRetrievalTool(Broken()).invoke({"query": "RAG"})
    assert result.status is KnowledgeRetrievalStatus.UNAVAILABLE
    assert result.error_code == "retrieval_error"
```

- [ ] **Step 2: Run the focused tests and verify RED.**

Run: `uv run pytest tests/unit/retrieval/test_bm25.py tests/unit/retrieval/test_tool.py -q`

Expected: collection fails because the retriever and tool modules are absent.

- [ ] **Step 3: Implement BM25.**

Tokenize `source_title + heading_path + text` with `re.findall(r"[A-Za-z0-9_]+|[\\u3400-\\u9fff]", text.casefold())`. Precompute document term frequencies, lengths, document frequencies, average length, and IDF. Use the standard BM25 formula with `k1=1.5`, `b=0.75`. Omit zero-score hits, sort by descending score then ascending `chunk_id`, and truncate to `top_k`. Return the corpus digest and candidate evidence state.

- [ ] **Step 4: Implement the LangChain adapter.**

Validate mapping inputs through `KnowledgeQuery`. Call the injected backend inside `try/except Exception`; convert backend exceptions to `KnowledgeRetrievalResult.unavailable("retrieval_error", str(exc))`. Build a `StructuredTool.from_function` named `retrieve_knowledge`, use `KnowledgeQuery` as `args_schema`, set `infer_schema=False`, and return JSON-mode dictionaries.

- [ ] **Step 5: Run tests and commit.**

Run: `uv run pytest tests/unit/retrieval -q`

Expected: all retrieval tests pass without external services. Then run `git add src/skillforge_kb/retrieval tests/unit/retrieval` and `git commit -m "feat: add deterministic knowledge retrieval tool"`.

### Task 3: Connect the Tool to CoursePlanningAgent

**Files:**
- Modify: `src/skillforge_kb/agents/planning_agent_models.py`
- Modify: `src/skillforge_kb/agents/planning_agent.py`
- Modify: `src/skillforge_kb/agents/__init__.py`
- Modify: `tests/unit/agents/test_planning_agent.py`

**Interfaces:**
- Add optional `knowledge_context: KnowledgeRetrievalResult | None` to `CoursePlanningAgentState` and `CoursePlanningAgentResult`.
- Extend `CoursePlanningAgent.create(..., knowledge_tool: KnowledgeRetrievalTool | None = None)` and `build_course_planning_graph(..., knowledge_tool: KnowledgeRetrievalTool | None = None)`.
- Add `build_knowledge_query(catalog: OntologyCatalog, node: PathNode) -> KnowledgeQuery`.
- Add a graph node `retrieve_current_node_knowledge` after current-node selection; it runs only for `READY` with an injected tool.

- [ ] **Step 1: Write failing Agent tests.**

Use a fake tool that records the query and returns one valid `KnowledgeRetrievalResult`. Add these behaviors:

```python
def test_connected_agent_retrieves_without_changing_path(agent, profile, fake_tool):
    plain = CoursePlanningAgent.create(agent.catalog, agent.attributes)
    expected = plain.invoke(initialize_event(profile), thread_id="plain")
    connected = CoursePlanningAgent.create(
        agent.catalog, agent.attributes, knowledge_tool=fake_tool
    )
    actual = connected.invoke(initialize_event(profile), thread_id="connected")
    assert fake_tool.calls == 1
    assert actual.knowledge_context.status is KnowledgeRetrievalStatus.OK
    assert actual.path.path_id == expected.path.path_id
    assert actual.path.nodes == expected.path.nodes
    assert actual.adaptations == expected.adaptations


def test_retrieval_failure_keeps_agent_ready(agent, profile):
    result = CoursePlanningAgent.create(
        agent.catalog, agent.attributes,
        knowledge_tool=KnowledgeRetrievalTool(BrokenRetriever()),
    ).invoke(initialize_event(profile), thread_id="broken")
    assert result.status is PlanningAgentStatus.READY
    assert result.knowledge_context.status is KnowledgeRetrievalStatus.UNAVAILABLE
    assert result.failure is None


def test_reset_clears_context(agent, profile, fake_tool):
    connected = CoursePlanningAgent.create(
        agent.catalog, agent.attributes, knowledge_tool=fake_tool
    )
    connected.invoke(initialize_event(profile), thread_id="student")
    result = connected.invoke(reset_event(), thread_id="student")
    assert result.knowledge_context is None
```

- [ ] **Step 2: Run the focused Agent tests and verify RED.**

Run: `uv run pytest tests/unit/agents/test_planning_agent.py -q`

Expected: failures identify the missing context field, constructor parameter, and graph node.

- [ ] **Step 3: Implement the optional context and query builder.**

Keep all existing result validation rules. Build the query from the current concept's Chinese/English names, aliases, summary, section and chapter titles, learning outcomes, and `delivery_depth`; do not include raw profile text. Add `knowledge_context=None` when committing a new candidate and when resetting.

- [ ] **Step 4: Add the retrieval graph node.**

Route from `select_current_node` to `retrieve_current_node_knowledge` only when status is `READY` and `knowledge_tool` is present; otherwise preserve the existing `END` route. The node validates the current path and node, calls the tool once, stores its result, and never constructs a planning failure. Duplicate events reuse checkpointed context; profile refresh and completion retrieve for the new current node; completed paths have no context.

- [ ] **Step 5: Run the focused and regression unit suites.**

Run `uv run pytest tests/unit/agents/test_planning_agent.py -q` and then `uv run pytest tests/unit -q`. Expected: new Agent tests pass and the existing 350 unit tests remain green. Commit with `git add src/skillforge_kb/agents tests/unit/agents` followed by `git commit -m "feat: connect knowledge retrieval to planning agent"`.

### Task 4: Add Full-Corpus Acceptance Coverage and Quality Gates

**Files:**
- Create: `tests/acceptance/test_course_agent_knowledge_retrieval.py`
- Modify: `data/README.md` only if the final checksum or intake wording needs recording

- [ ] **Step 1: Add the full-corpus smoke test.**

```python
def test_verified_candidate_corpus_retrieves_without_services():
    corpus = KnowledgeCorpus.load(Path("data/index_chunks.jsonl"))
    result = Bm25KnowledgeRetriever(corpus).retrieve(
        KnowledgeQuery(query="RAG 向量检索 BM25", top_k=5)
    )
    assert len(corpus.chunks) == 710
    assert result.status is KnowledgeRetrievalStatus.OK
    assert result.hits
    assert all(hit.evidence_state == "candidate" for hit in result.hits)
```

- [ ] **Step 2: Run the acceptance test.**

Run: `uv run pytest tests/acceptance/test_course_agent_knowledge_retrieval.py -q`

Expected: it passes with the tracked JSONL and does not contact Docker, Qdrant, or the network.

- [ ] **Step 3: Run final quality gates.**

Run `uv run pytest tests/unit tests/acceptance -q`, `uv run ruff check src tests`, `uv run mypy src/skillforge_kb`, `git diff --check`, and `git status --short`. Expected: unit and acceptance tests pass, Ruff and mypy exit 0, and the diff is clean. Full `uv run pytest -q` may still show the five pre-existing Docker daemon errors when Docker Desktop is unavailable; record that environment limitation separately.

- [ ] **Step 4: Commit acceptance coverage.**

Run `git add tests/acceptance data/README.md` and `git commit -m "test: verify full candidate corpus retrieval"`.

### Task 5: Final Review and Handoff

- [ ] **Step 1: Review the branch diff and history.**

Run `git log --oneline --decorate -8`, `git diff publish/knowledge-base-v1...HEAD --stat`, and `git diff publish/knowledge-base-v1...HEAD -- data/README.md src/skillforge_kb/retrieval src/skillforge_kb/agents tests/unit/retrieval tests/unit/agents tests/acceptance`. Confirm no user-owned files, local corpora, pickle/FAISS artifacts, API keys, or unrelated refactors are included.

- [ ] **Step 2: Verify the intake hash.**

Run `git hash-object -- data/index_chunks.jsonl`. Expected: `5657a46477ccb6917ac5c9d959db03822625fb9e`.

- [ ] **Step 3: Report the ready-to-merge branch, commits, tests, Docker limitation, and the fact that only candidate JSONL retrieval is connected.**
