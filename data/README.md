# Data Handling

The working project uses two local teammate datasets:

- `知识库/`: source PDFs, code, manifests, and provenance-rich candidate chunks.
- `processed/`: a legacy JSONL search index plus BM25, pickle, and FAISS artifacts.

These paths are ignored by Git on purpose. The first fusion intake reported 2,133 input records, 69 source identities, and 50 inventoried files. The committed code can reproduce the classification when the same local inputs are supplied to `fusion-dry-run`.

## Publication Rules

Do not commit raw PDFs, pickle files, FAISS indexes, or unreviewed JSONL. Before a source is published, record its canonical URL, version, license status, locator, content hash, language, concept labels, and human review state in the governed storage layer.

The `learning_evidence`, `agent_engineering`, and `project_material` domains remain separate during retrieval. Project and agent-engineering materials are not part of the default teaching evidence query.
