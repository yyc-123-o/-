# Concept Resource Binding

This workflow connects the tracked teammate knowledge snapshot to the existing course
graph as a candidate resource layer. It does not modify chapters, concepts,
prerequisites, or the published evidence manifest.

## Generate Candidate Bindings

From the repository root:

```powershell
uv run python scripts/build_concept_resource_bindings.py
```

The default command reads:

- `resources/ontology/ai_course_v1.yaml`
- `resources/ontology/ai_relations_v1.yaml`
- `data/index_chunks.jsonl`

It writes:

- `reports/generated/concept-resource-bindings/concept_resource_candidates.jsonl`
- `reports/generated/concept-resource-bindings/concept_resource_binding_report.json`

Pass `--course-file`, `--relations-file`, `--knowledge-file`, and `--output-dir` to use
explicit compatible paths.

## Matching Policy

The matcher uses reviewed Chinese names, English names, and aliases from the course
catalog. Source-title and heading matches receive higher scores than body matches.
Short generic terms require repeated body mentions; distinctive acronyms and longer
phrases may produce a candidate from one body mention. Safe title-prefix matches are
allowed for focused headings such as a shortened curriculum name.

One chunk may bind to more than one concept. This is intentional: the generated rows
are review candidates, and a document discussing a method may also explicitly discuss
its prerequisite or parent concept.

## Review And Publication Boundary

Every row has `review_status=candidate` and `evidence_state=candidate`. Before promotion,
a reviewer must verify the source URL, license, locator, content hash, concept relevance,
and teaching suitability. Promotion must occur through the governed evidence manifest;
editing the candidate JSONL does not publish an edge.

Candidate bindings must not be used to create prerequisite relations. A prerequisite is
a curriculum decision and remains governed by `ai_relations_v1.yaml`.

## Evidence Governance Queue

For rich teammate rows that already contain source, license, locator, hash, concept and
content-kind metadata, build the candidate-only governance queue:

```powershell
python scripts/build_evidence_review_queue.py `
  --input-file 'D:\path\to\ai_learning_pilot_review_300.jsonl' `
  --output-file 'reports/generated/evidence-governance-pilot-v1.json' `
  --core-concept-id 'dl.cnn.convolution' `
  --core-concept-id 'dl.feedforward.mlp'
```

The queue checks graph membership, provenance fields, HTTP(S) source URLs, content
hashes, license state, language, content kind and difficulty. It reports missing
`definition`, `code` and `exercise` kinds per core concept. Its output is always
`publishable=false` and `review_status=candidate`; it must not be copied directly into
`resources/evidence/evidence_manifest_v1.yaml`.

The human review step must independently confirm professional correctness, source
traceability, license applicability and concept scope. Only after that review may a
separate publication change create `EvidenceRecord` entries with `review_status=published`
and `license_status=allowed`.
