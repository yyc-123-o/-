# Data Handling

The working project uses two local teammate datasets and one verified intake snapshot:

- `知识库/`: source PDFs, code, manifests, and provenance-rich candidate chunks.
- `processed/`: a legacy JSONL search index plus BM25, pickle, and FAISS artifacts.
- `data/index_chunks.jsonl`: the verified 710-row candidate snapshot consumed by the
  deterministic retrieval baseline. Its Git object hash is
  `5657a46477ccb6917ac5c9d959db03822625fb9e`.

The teammate paths remain ignored by Git on purpose. The first fusion intake reported
2,133 input records, 69 source identities, and 50 inventoried files. The committed code
can reproduce the classification when the same local inputs are supplied to
`fusion-dry-run`.

## Publication Rules

The tracked JSONL is an explicitly candidate-only intake snapshot. It is not a
published evidence manifest: it has no source URL, license decision, concept binding,
or human review record. The retrieval tool may quote its chunks as candidate context,
but it must not convert them into `EvidenceRecord` or `EvidenceBundle` objects.

Do not load or commit serialized pickle/FAISS indexes as a runtime dependency. Before a
source is published, record its canonical URL, version, license status, locator, content
hash, language, concept labels, and human review state in the governed storage layer.

The `learning_evidence`, `agent_engineering`, and `project_material` domains remain separate during retrieval. Project and agent-engineering materials are not part of the default teaching evidence query.

See the [standalone course-planning Agent runbook](../docs/runbooks/standalone-course-planning-agent.md)
for the candidate snapshot's local runtime usage and governance boundary.
