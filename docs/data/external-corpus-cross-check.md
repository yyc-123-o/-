# External Corpus Cross-Check

`data/external/index_chunks(1).jsonl` is a read-only verification corpus.
It is compared against the primary `data/index_chunks.jsonl` corpus to detect:

- exact duplicate overlap
- concept-level agreement
- concept-level conflict
- primary-only coverage gaps
- external-only coverage gaps

The generated report is a JSON file with these top-level sections:

- `request`
- `summary`
- `concept_evidence`
- `rows`
- `evidence_gap`
- `gate_decision`

The external corpus is never promoted to formal evidence by this report.
