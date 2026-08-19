# Platform Usable Profile Integration Design

## Goal

Make the local platform safely consumable from the imported Learner Profile
Agent while preserving the canonical planner contract and evidence governance.

## Scope

This change has two independent boundaries:

1. Adapt the standalone `LearnerProfile` v2.1 JSON into a validated
   `LearnerProfileSnapshot` through a versioned, explicit knowledge-point map.
2. Prevent candidate retrieval from assigning `definition`, `code`, or
   `exercise` solely because a query was issued for that type.

Production persistence, authentication, and formal evidence publication remain
separate follow-up work. Strict generation must continue to block until human
reviewed evidence is published.

## Profile Adapter

`LearnerProfileAgentAdapter` consumes the v2.1 output shape and produces an
`AdaptedLearnerProfile` containing:

- the canonical `LearnerProfileSnapshot` used by the planner;
- skipped legacy knowledge-point IDs with explicit reasons;
- the source profile version and adapter version.

Only IDs listed in `resources/ontology/profile_agent_kp_map_v1.yaml` are
converted. A mapping is one-to-one and points to an existing atomic ontology
concept. CNN `kp_012` maps to `dl.cnn.convolution`, so the planner and retrieval
agent cannot fall back to `dl.vision.image-tensor` for this input. Composite or
unmapped IDs are omitted from mastery and reported as warnings; omission causes
the planner's existing conservative behavior for that concept.

Abilities, error patterns, and preferences are copied only into the canonical
fields. Chapter-level `resource_generation_hints`, path fields, and generated
resource decisions are never copied into the snapshot.

The API exposes `POST /api/v1/profiles/adapt` for this explicit conversion. The
existing `/api/v1/runs` endpoint remains unchanged and accepts only the
canonical snapshot, keeping the run contract deterministic and cacheable.

## Candidate Evidence Typing

`KnowledgeChunk` gains an optional declared `content_kind`. Candidate retrieval
uses that declaration when present. For legacy chunks without a declaration, a
conservative classifier recognizes code and exercise markers; ambiguous chunks
are definition candidates only when they do not contain code or exercise
markers. A hit is emitted only when its inferred type equals the requested type.

The candidate preview route therefore cannot proceed when a required type is
absent. This is intentional: a structured evidence gap is safer than a draft
that cites a code fragment as an exercise.

## Error Handling and Tests

- malformed v2.1 profile, graph-version mismatch, invalid score, duplicate
  mapping, and invalid canonical target return a typed adaptation error;
- unmapped legacy IDs are warnings, never silently discarded;
- candidate type mismatches are filtered before resource generation;
- API tests cover adaptation success/failure and strict/candidate-preview
  behavior with typed fixtures;
- existing planner identity and evidence gates remain unchanged.
