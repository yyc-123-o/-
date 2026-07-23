# SkillForge Knowledge Base

SkillForge Knowledge Base is a governed, bilingual evidence foundation for an AI learning system. It provides deterministic source ingestion, provenance-aware chunk candidates, review gates, and the storage contracts that will later support PostgreSQL, Qdrant, Neo4j, LangChain, and LangGraph integrations.

## Current Status

The repository currently contains:

- Domain contracts for sources, citations, evidence chunks, and retrieval packages.
- Governed source acquisition and PDF/HTML loaders.
- Deterministic normalization and pedagogical chunking.
- A read-only fusion intake pipeline for the two teammate-built knowledge bases.
- Unit and integration tests for ingestion, governance, storage, and fusion intake.
- Versioned design documents and implementation plans under `docs/`.

The first fusion dry run processed 2,133 JSONL records without changing the input files. The records remain candidates; licensing and human review are still required before publication.

## Repository Layout

```text
src/skillforge_kb/       Core Python package and fusion intake pipeline
tests/                   Unit and service-backed integration tests
docs/                    Design specs, implementation plans, and audit summaries
data/                    Public data-handling and reproducibility notes
compose.yaml             Local PostgreSQL, Qdrant, and Neo4j services
pyproject.toml           Python dependencies and developer commands
```

## Quick Start

Requirements: Python 3.12 and `uv`.

```powershell
uv sync --frozen
uv run pytest tests/unit -q
uv run ruff check src tests/unit
uv run mypy src/skillforge_kb
```

The fusion CLI is read-only with respect to source directories:

```powershell
uv run skillforge-kb fusion-dry-run `
  --knowledge-root 'D:\path\to\知识库' `
  --legacy-root 'D:\path\to\processed' `
  --pilot-jsonl 'D:\path\to\ai_learning_pilot_chunks.jsonl' `
  --legacy-jsonl 'D:\path\to\index_chunks.jsonl' `
  --workspace-root 'D:\path\to\project' `
  --output-dir 'reports/generated/fusion-v1'
```

It writes deterministic inventory, source-candidate, outcome, and summary files to the chosen output directory. The output directory must be outside both input roots.

## Data Policy

Raw PDFs, source repositories, teammate JSONL files, pickle indexes, FAISS indexes, and generated reports are intentionally excluded from Git. They may have separate licensing, size, or reproducibility constraints. See [`data/README.md`](data/README.md) and the source manifest kept with the local data copy.

No candidate is considered publishable until its source, license, locator, normalized hash, concept labels, and human review state satisfy the governance policy.

## License

The project code is released under the repository's chosen license. External papers, teaching materials, and teammate-provided documents retain their original rights and must be checked independently before redistribution.
