# AI Evidence Governance Pilot

## Run

The first pilot uses the teammate's rich candidate snapshot:

```text
知识库/processed/chunks/ai_learning_pilot_review_300.jsonl
```

The scope is the first 30 concepts in the graph's stable required-course order. The
output is:

```text
reports/generated/evidence-governance-pilot-30-v1.json
```

## Result

| Field | Value |
| --- | ---: |
| Core concepts in scope | 30 |
| Candidate records | 16 |
| Excluded input rows | 285 |
| Concepts with at least one candidate | 2 |
| Candidate concept coverage | 6.67% |
| Concepts with definition + code + exercise | 0 |
| Formal published evidence records | 0 |

Candidate content kinds in scope were `definition=6`, `code=8`, `derivation=1`, and
`exercise=1`. The queue excluded 249 rows because their legacy or composite concept IDs
are not present in `ai-course-v1`; it did not guess a mapping. The two covered concepts
were `dl.feedforward.mlp` and `ml.supervised.learning`.

## Interpretation

This is a governance status report, not a quality score. The corpus contains useful AI
teaching material, but only records with an exact graph binding and complete provenance
can enter the review queue. No record was promoted automatically, and
`resources/evidence/evidence_manifest_v1.yaml` remains unchanged with zero published
records until human review is completed.

## Required Human Review

For each candidate, reviewers must confirm:

1. The source URL, license and locator identify a real retrievable source.
2. The text is professionally correct and does not introduce a fact absent from the
   cited source.
3. The concept binding is exact; composite or legacy IDs are mapped only through an
   explicit reviewed mapping.
4. `definition`, `code` and `exercise` labels match the actual material.
5. The proposed depth is appropriate; a difficulty-to-depth inference is only a
   suggestion, not a publication decision.

After review, a separate publication step can create `EvidenceRecord` rows. Until then,
resources generated from these rows remain candidate previews and must not be presented
as formally verified teaching content.
