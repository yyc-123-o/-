# Repository Structure and Engineering Governance Design

**Status:** Accepted for implementation planning

**Date:** 2026-07-30

**Scope:** The complete SkillForge-MA monorepo, including the Python backend,
learning algorithms, seven Agent roles, knowledge assets, a future web client,
deployment configuration, tests, and team documentation.

## 1. Purpose

The repository has grown from a knowledge-base package into the backend core of a
multi-Agent personalized learning system. The existing package has useful domain
boundaries and strong verification, but the current top-level layout does not yet
provide a durable home for the web client, API layer, seven Agent roles, deployment
files, team process documents, or local datasets.

This design standardizes where every project artifact belongs while preserving the
working Python package and its current behavior. The selected architecture is a
modular monolith in one monorepo. It avoids premature microservices and avoids a
large Python package rename.

## 2. Current Baseline

At the time of this decision, the repository has:

- one Python 3.12 package named `skillforge_kb`;
- 63 tracked source files and 69 tracked test files;
- 350 passing unit tests and 355 collected tests;
- strict mypy, Ruff, pytest, and uv lock checks;
- versioned ontology, evidence, resource-blueprint, and profile-mapping assets;
- deterministic planning, assessment, allocation, and offline evaluation code;
- LangChain/LangGraph-compatible course-planning adapters;
- local raw datasets and tool state that must remain outside Git.

The reorganization must not reduce this baseline without an explicit, reviewed
reason.

## 3. Approaches Considered

### 3.1 Minimal cleanup

Keep the existing Python directories and only reorganize root documents and data.
This has the smallest immediate diff, but it leaves no stable boundaries for seven
Agent roles, API workflows, and the future web client. The repository would need a
second structural rewrite later.

### 3.2 Modular-monolith monorepo

Keep one Python backend package, organize it by business domain, add the web client
as a separate app, and enforce one-way dependencies. This preserves the current uv
build while making ownership and future growth explicit.

This is the selected approach.

### 3.3 Multi-service workspace

Create separate API, worker, Agent, and shared-library packages immediately. This
provides independent deployment boundaries but adds package publication, service
discovery, distributed tracing, and cross-service contract costs that the current
team does not need.

## 4. Target Top-Level Layout

```text
SkillForge-MA/
|-- apps/
|   `-- web/                    # Future visualization client
|-- src/
|   `-- skillforge_kb/          # Python backend, algorithms, and Agent core
|-- tests/                      # Unit, contract, integration, acceptance
|-- resources/                  # Versioned runtime knowledge/configuration assets
|-- examples/                   # Sanitized example inputs and outputs
|-- data/
|   |-- README.md               # Data source, license, and handling policy
|   |-- raw/                    # Local only
|   |-- interim/                # Local only
|   `-- processed/              # Local only by default
|-- reports/                    # Local generated reports by default
|-- docs/
|   |-- product/
|   |-- architecture/
|   |-- designs/
|   |-- plans/
|   |-- development/
|   |-- team/
|   |-- reports/
|   `-- archive/
|-- deploy/
|   `-- compose.yaml
|-- scripts/                    # Developer automation only; no domain logic
|-- .github/
|   |-- workflows/
|   |-- CODEOWNERS
|   `-- pull_request_template.md
|-- pyproject.toml
|-- uv.lock
|-- .env.example
|-- .gitignore
|-- CONTRIBUTING.md
`-- README.md
```

The repository will not create empty directories. `apps/web` and other future
areas are added only when they contain real, reviewed files.

## 5. Python Package Boundaries

```text
src/skillforge_kb/
|-- api/                         # FastAPI routes, schemas, dependency injection
|-- application/                 # Cross-domain use cases and learning workflows
|   |-- assessment_flow.py
|   |-- planning_flow.py
|   |-- resource_flow.py
|   `-- learning_loop.py
|-- agents/                      # Agent shells, state, tools, and audit contracts
|   |-- shared/
|   |-- diagnosis/
|   |-- curriculum/
|   |-- retrieval/
|   |-- generation/
|   |-- review/
|   |-- judge/
|   `-- tutoring/
|-- learning/                    # Learner-state and curriculum algorithms
|   |-- profiles/
|   |-- assessment/
|   `-- planning/
|-- knowledge/                   # Knowledge lifecycle and retrieval
|   |-- sources/
|   |-- ingestion/
|   |-- fusion/
|   |-- governance/
|   |-- evidence/
|   |-- graph/
|   `-- retrieval/
|-- content/                     # Learning-resource contracts and allocation
|   |-- blueprints/
|   |-- allocation/
|   |-- briefs/
|   |-- evidence_bundle/
|   `-- contracts/
|-- evaluation/                  # Offline evaluation; never online policy state
|   |-- planning/
|   |-- retrieval/
|   |-- generation/
|   `-- debate/
|-- infrastructure/              # Implementations of external-system ports
|   |-- postgres/
|   |-- neo4j/
|   |-- qdrant/
|   |-- llm/
|   `-- checkpoints/
|-- config.py
`-- cli.py
```

### 5.1 Dependency direction

```text
API / CLI
    |
    v
Application workflows
    |
    +------> Agents / orchestration
    |              |
    v              v
Learning + Knowledge + Content
    |
    v
Abstract ports <------ Infrastructure implementations
```

The following rules are mandatory:

1. `learning`, `knowledge`, and `content` must not import `api`, `agents`, or
   concrete infrastructure adapters.
2. Agents call domain services and contracts. They do not query Neo4j, Qdrant, or
   PostgreSQL directly.
3. Infrastructure implements ports owned by the domain. It does not own business
   rules.
4. Evaluation reads domain outputs. Production decisions do not read evaluation
   reports and automatically promote policies.
5. Cross-domain business flows start in `application`.
6. Shared helpers are extracted only after at least two real consumers exist. A
   general-purpose `utils.py` is not allowed.
7. The seven Agent roles remain modules in one deployable backend until independent
   scaling or isolation is demonstrated.

### 5.2 Current-to-target mapping

| Current path | Target path |
| --- | --- |
| `domain/` | `knowledge/sources/` |
| `ingestion/` | `knowledge/ingestion/` |
| `fusion/` | `knowledge/fusion/` |
| `governance/` | `knowledge/governance/` |
| `evidence/` | `knowledge/evidence/` |
| `ontology/models.py`, `catalog.py`, `validation.py`, `coverage.py` | `knowledge/graph/` |
| `ontology/profile.py` | `learning/profiles/` |
| `ontology/neo4j.py` | `infrastructure/neo4j/` |
| `ontology/resource_blueprints.py` | `content/blueprints/` |
| `planning/` | `learning/planning/` |
| `assessment/` | `learning/assessment/` |
| `resources/` | `content/` |
| `storage/` | `infrastructure/postgres/` |
| `evaluation/` | `evaluation/planning/` |
| flat course-planning files in `agents/` | `agents/curriculum/` |

Files are split only when they hold distinct responsibilities. For example, a
large Agent module may become `models.py`, `service.py`, `graph.py`, and `tools.py`.
Line count alone is not a reason to split a file.

## 6. Test Taxonomy

```text
tests/
|-- unit/                         # Pure functions and one-module behavior
|   |-- learning/
|   |-- knowledge/
|   |-- content/
|   |-- agents/
|   `-- evaluation/
|-- contract/                     # Public module and adapter contracts
|   |-- api/
|   |-- agents/
|   `-- infrastructure/
|-- integration/                  # Real service-backed tests
|   |-- postgres/
|   |-- neo4j/
|   `-- qdrant/
|-- acceptance/                   # Complete offline workflows
|   |-- personalized_learning/
|   |-- resource_generation/
|   `-- agent_workflows/
`-- fixtures/
    |-- profiles/
    |-- ontology/
    |-- evidence/
    `-- acceptance/
```

Test rules:

- Unit tests mirror the source business domains.
- A test that runs a full workflow without external services belongs in
  `acceptance`, not `unit/integration`.
- Tests using real PostgreSQL, Neo4j, or Qdrant belong in `integration`.
- Cross-module tests use public APIs and do not import private underscore names.
- Every Agent covers event contracts, idempotency, invalid transitions, conflict
  handling, and recovery behavior.
- The deterministic personalized-flow matrix moves from `reports/generated` to
  `tests/fixtures/acceptance`.
- Test counts may change because of parametrization or consolidation, but any
  reduction must be explained in the pull request with equivalent coverage.

## 7. Documentation Taxonomy

```text
docs/
|-- product/
|   |-- vision.md
|   |-- system-scope.md
|   `-- acceptance-criteria.md
|-- architecture/
|   |-- overview.md
|   |-- dependency-rules.md
|   `-- decisions/
|       `-- ADR-0001-modular-monolith.md
|-- designs/                      # Accepted feature/system designs
|-- plans/                        # Active implementation plans
|-- development/
|   |-- setup.md
|   |-- coding-standards.md
|   |-- testing.md
|   |-- git-workflow.md
|   `-- data-policy.md
|-- team/
|   |-- ownership.md
|   |-- task-board.md
|   `-- weekly/
|-- reports/                      # Reproducible formal validation summaries
`-- archive/                      # Completed or superseded plans
```

The root-level final solution becomes `docs/product/vision.md`. Active designs and
plans remain easy to discover. Completed implementation plans move to `archive`
without deleting the historical audit trail.

## 8. Data and Naming Policy

### 8.1 Allowed in Git

- versioned ontology and relation documents;
- reviewed resource blueprints and evidence manifests;
- schemas and one-to-one mapping manifests;
- small, deterministic, sanitized test fixtures;
- sanitized example requests and outputs;
- source, license, locator, and content-hash metadata.

### 8.2 Excluded from Git

- raw PDFs and teammate JSONL corpora;
- vector indexes, embedding caches, database volumes, and model caches;
- `data/raw`, `data/interim`, and `data/processed` content;
- ad hoc generated reports and logs;
- `.claude`, `.agents`, `.superpowers`, and other local tool state;
- API keys, credentials, real learner identifiers, and unsanitized profiles.

Raw data should preferably live outside the Git checkout. If local tooling requires
repository-relative paths, it uses the ignored `data` stages above.

### 8.3 Naming conventions

All tracked paths use ASCII names:

- Python modules: `snake_case.py`;
- document and general directory names: `kebab-case`;
- classes: `PascalCase`;
- functions and variables: `snake_case`;
- constants: `UPPER_SNAKE_CASE`.

Chinese content is allowed inside documents and data fields, but not in tracked
file or directory names. Public identifiers and graph IDs remain versioned and
stable.

## 9. Git Workflow

`main` is the stable integration branch. Long-lived `publish/*` development
branches are retired after the current work is integrated.

Allowed branch prefixes:

```text
feature/course-planning
feature/retrieval-fusion
fix/profile-validation
docs/system-architecture
chore/repository-structure
```

Rules:

1. All work uses short-lived branches and pull requests.
2. Direct pushes to protected `main` are not allowed.
3. Commit subjects follow Conventional Commits: `feat`, `fix`, `test`, `docs`,
   `refactor`, and `chore`.
4. Each commit carries one logical change.
5. A pull request does not mix broad file movement with behavior changes.
6. Cross-domain changes require review from the relevant owners.
7. `.github/CODEOWNERS` records knowledge, algorithm, Agent, and frontend owners.
8. Branches synchronize with current `main` before merge.
9. Required CI checks must pass before squash merge.
10. Existing Git history is not rewritten as part of the reorganization.

## 10. CI Gates

The required pull-request pipeline is:

```text
Ruff lint and format check
        |
        v
mypy strict
        |
        v
unit + contract + acceptance tests
        |
        v
ontology and resource-schema validation
        |
        v
frontend lint + typecheck + tests (when apps/web exists)
```

PostgreSQL, Neo4j, and Qdrant tests run as separate service-backed jobs. Tests that
require an LLM API key are manual or scheduled and are not required for ordinary
pull requests. No required quality gate depends on an API key.

CI should cache uv and future frontend dependencies, but it must validate the lock
files rather than resolving unbounded dependency versions.

## 11. Migration Strategy

The migration is intentionally incremental.

### Phase 0: Freeze and measure

- create `chore/repository-structure-v1`;
- record the current test, build, CLI, and graph-validation baseline;
- freeze business behavior while structural moves are active.

### Phase 1: Root, documentation, and data governance

- create the accepted top-level documentation and governance files;
- classify root documents and local datasets;
- expand ignore rules without deleting user-owned data;
- do not move, rename, or delete local corpora automatically; produce an inventory
  and obtain explicit ownership confirmation before any filesystem relocation;
- make no Python import changes.

### Phase 2: Test taxonomy

- move tests with `git mv`;
- establish contract, integration, acceptance, and fixture locations;
- update pytest configuration and path helpers;
- preserve the behavioral baseline.

### Phase 3: Knowledge domain

- migrate sources, ingestion, fusion, governance, evidence, and graph code;
- move Neo4j implementation code to infrastructure;
- update one knowledge subdomain per independently verified change.

### Phase 4: Learning, content, and evaluation

- migrate profiles, assessment, planning, content contracts, and offline evaluation;
- preserve policy versions, digests, serialized schemas, CLI behavior, and errors.

### Phase 5: Agents, application, and API

- move the current planning Agent to `agents/curriculum`;
- split modules by responsibility where justified;
- introduce application workflows before adding API routes;
- ensure domain modules do not import FastAPI or concrete stores.

### Phase 6: Collaboration, deployment, and web

- add CI, CODEOWNERS, pull-request template, and contributing guide;
- move Compose configuration to `deploy` and update documented commands;
- add `apps/web` only with real frontend code.

Each phase is a separate pull request or a small sequence of reviewable pull
requests. No phase combines broad moves with algorithm changes.

## 12. Compatibility and Error Handling

- Use `git mv` to retain file history.
- Update source imports, tests, and documentation links in the same change.
- Old public imports may be re-exported through focused `__init__.py` compatibility
  modules for no more than one subsequent migration phase.
- Internal code must switch to the new imports immediately.
- Delete compatibility exports after `rg` confirms no internal or documented old
  consumers. Every structural compatibility export must be removed before Phase 6
  begins.
- Do not use symlinks, duplicated source trees, or permanent forwarding modules.
- Preserve CLI commands, Pydantic schemas, policy versions, digest inputs, error
  classes, and public result semantics.
- Validate data again at API, Agent, and infrastructure trust boundaries.
- Domain errors remain typed and are translated to transport errors only in API or
  CLI adapters.
- A failed structural phase is reverted as its own commit or repaired in its branch;
  it is not hidden by disabling tests.

Dependency-direction checks should be automated with architecture tests or an
import-contract tool. These checks are introduced before the compatibility layer is
removed.

## 13. Performance and Repository Health

Structural changes must not alter runtime complexity. Additional performance rules
are:

- large datasets and indexes stay outside Git;
- required pull-request tests remain API-key-free;
- service-backed tests run separately from the fast deterministic suite;
- repeated ontology, embedding, or model loading is not introduced by new module
  boundaries;
- CI caches dependencies but not mutable generated truth artifacts;
- generated reports are not imported by production code;
- frontend and backend dependency locks remain explicit when the web app exists.

The migration should measure test duration and package build duration at Phase 0
and after each major phase. A material regression requires explanation or repair.

## 14. Principal Failure Modes

| Codepath | Failure mode | Required control |
| --- | --- | --- |
| Source moves | Imports fail across the package | One-domain moves and immediate tests |
| Test moves | Relative fixture paths break | Repository-root or fixture-helper resolution |
| Documentation moves | Local links become stale | Markdown link scan |
| Data cleanup | Raw or personal data enters Git | Ignore rules, size checks, secret scan |
| Domain split | Circular dependencies appear | One-way import contracts |
| Compatibility | Old imports remain indefinitely | Milestone deadline and `rg` scan |
| Parallel team work | Move-heavy merge conflicts | Temporary ownership/freeze per domain |
| CI expansion | Feedback becomes too slow | Separate fast and service-backed jobs |
| Evaluation | Synthetic results are treated as real outcomes | Mandatory data-kind disclaimer |

## 15. Acceptance Criteria

The final structure is accepted when all relevant commands succeed:

```powershell
uv sync --locked
uv run pytest tests/unit tests/contract tests/acceptance -q
uv run pytest --collect-only -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run skillforge-kb --help
uv build
uv lock --check --offline
git diff --check
```

Additional requirements:

- ontology and resource-blueprint validation results remain unchanged;
- the root contains no unclassified project artifacts;
- internal code contains no old compatibility imports;
- raw data and real learner records remain outside Git;
- README and development guides match working commands;
- no unexplained test coverage or test-count reduction occurs;
- public policy, event, and artifact digests remain reproducible.

During early phases, commands are adjusted only for directories that already exist.
The final command set becomes mandatory after the test taxonomy is created.

## 16. Not in Scope

This reorganization does not:

- implement new Agent behavior or frontend features;
- change assessment, planning, retrieval, or allocation algorithms;
- change database schemas;
- split the backend into microservices;
- rename the `skillforge_kb` Python package;
- import local knowledge corpora, JSONL files, or real learner data;
- automatically promote policies from synthetic evaluation;
- rewrite existing Git history;
- require an LLM API key.
