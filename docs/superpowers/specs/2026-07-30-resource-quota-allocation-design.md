# Resource Quota Allocation Design

## 1. Purpose

Convert an existing resource blueprint and `NodeAdaptationDecision` into concrete,
auditable generation quotas: total learning minutes, worked examples, guided
exercises, assessment items, and project checkpoints.

The allocator is deterministic policy logic. It does not generate content, change
the course path, change delivery depth, or claim that the quotas are empirically
optimal.

## 2. Inputs and Fixed Boundaries

- `ResourceBlueprint.estimated_minutes` supplies the reviewed depth-specific base
  duration, currently 45/60/75 minutes for intro/intermediate/advanced defaults.
- `NodeAdaptationDecision.effort_multiplier` scales duration and is already bounded
  to `[0.5, 2.0]`; production decisions currently use `1 + support_need_score`.
- `NodeAdaptationDecision.support_intensity` selects the support quota addition.
- `ResourceBlueprint.resource_types` gates quotas that cannot be produced by the
  requested bundle.
- Blueprint concept/depth and adaptation concept/depth must match.

## 3. Approaches Considered

### 3.1 Inline arithmetic in `ResourceBriefBuilder`

This is short but makes constants unversioned, difficult to test independently,
and easy to duplicate in Agents or frontends.

### 3.2 Model-based allocation

A trained or LLM-based allocator would need observed completion-time and learning
outcome data that the project does not have. Synthetic outputs would not justify
learned quotas.

### 3.3 Versioned pure allocation policy

The selected approach adds `resources/allocation.py` with frozen policy contracts,
a pure allocation function, and content-derived digests. `ResourceBriefBuilder`
calls it once and embeds the result into the brief so every downstream consumer
uses the same decision.

## 4. Policy

`ResourceAllocationPolicy` contains a minute rounding interval, three depth quota
vectors, and four support-addition vectors. Every vector has non-negative counts
for worked examples, guided exercises, assessment items, and project checkpoints.

Default depth quotas:

| Depth | Examples | Exercises | Assessment items | Project checkpoints |
|---|---:|---:|---:|---:|
| Intro | 1 | 3 | 4 | 1 |
| Intermediate | 2 | 5 | 6 | 2 |
| Advanced | 3 | 7 | 8 | 3 |

Default support additions:

| Support | Examples | Exercises | Assessment items | Project checkpoints |
|---|---:|---:|---:|---:|
| Compact | 0 | 0 | 0 | 0 |
| Standard | 1 | 1 | 1 | 0 |
| Scaffolded | 2 | 3 | 2 | 1 |
| Remediation | 3 | 5 | 4 | 2 |

Policy validation requires every count to be monotonic across increasing depth and
support intensity. The policy version and all constants contribute to a stable
policy digest.

## 5. Allocation Formula

Duration is:

```text
raw_minutes = blueprint.estimated_minutes * adaptation.effort_multiplier
estimated_minutes = ceil(raw_minutes / minute_rounding) * minute_rounding
```

Each raw quota is `depth_quota + support_addition`. Resource-type gates then apply:

- without `PRACTICAL_GUIDE`, worked examples and guided exercises are zero;
- without `ASSESSMENT`, assessment items are zero;
- without `PROJECT`, project checkpoints are zero.

Lecture presence does not create a separate count. The blueprint base duration
still describes the whole requested node resource bundle.

## 6. Output Contract

`ResourceAllocation` stores:

- policy version and digest;
- concept ID, delivery depth, support intensity, and requested resource types;
- blueprint minutes, effort multiplier, and rounded estimated minutes;
- all four final quota counts;
- reason codes and an allocation digest.

Validators reproduce the duration bounds, resource-type gates, identity fields,
and allocation digest. `ResourceBriefPayload` requires this allocation and verifies
that it matches the brief's concept, depth, resource types, and node adaptation.
New briefs default to `resource-brief.v2`.

## 7. Failure Behavior

- Reject blueprint/adaptation concept or depth mismatch.
- Reject a non-monotonic allocation policy.
- Reject a brief whose allocation is missing, stale, or copied from another node.
- Reject allocation or policy digest mutation.
- Do not infer quotas for skipped or completed nodes because those nodes cannot
  produce resource briefs.

## 8. Testing and Acceptance

- Identical inputs produce identical allocations and digests.
- Estimated minutes are rounded up, never below blueprint minutes for production
  effort multipliers, and never exceed the allowed multiplier result plus rounding.
- Increasing depth or support intensity cannot reduce any ungated quota.
- Missing resource types force their quota fields to zero.
- Remediation produces at least scaffolded quotas and remains intro depth for a
  blocked node.
- Every newly built `ResourceBrief` contains a matching v2 allocation.
- Existing evidence, citation, path identity, and resource-generation tests remain
  valid.
- All unit tests, Ruff, mypy, and lock checks pass.
