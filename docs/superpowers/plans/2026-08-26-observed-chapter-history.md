# Observed Chapter History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Derive evidence-backed prior chapter history in the learner diagnosis profile.

**Architecture:** `core/profile_builder.py` will aggregate existing `TestRecord` values using each earlier chapter's primary and co-requisite knowledge-point IDs. The output remains the existing `PriorChapter` schema, preserving a strict distinction between observed evidence and an explicit course completion event.

**Tech Stack:** Python 3, Pydantic, pytest.

## Global Constraints

- Do not change the public learner upload schema.
- Do not treat prerequisite-only records as chapter completion or chapter evidence.
- Preserve an empty history for learners without matching test records.
- Do not alter unrelated root-worktree files.

---

### Task 1: Add evidence-backed chapter history

**Files:**
- Modify: `学情诊断Agent/test_regressions.py`
- Modify: `学情诊断Agent/core/profile_builder.py`

**Interfaces:**
- Consumes: `KnowledgeGraph.chapters`, `Learner.test_records`, `current_chapter_id`.
- Produces: `_build_prior_chapters(kg, learner, current_chapter_id) -> List[PriorChapter]`.

- [ ] **Step 1: Write failing tests**

```python
profile = build_profile(learner, KG, current_chapter_id="ch03_cnn")
assert [item.chapter_id for item in profile.prior_chapters] == ["ch01_foundation"]
assert profile.prior_chapters[0].accuracy == 0.5
assert profile.prior_chapters[0].completed_at is None
```

- [ ] **Step 2: Run the regression test and verify it fails because `_build_prior_chapters()` always returns an empty list**

Run: `pytest test_regressions.py -q`

- [ ] **Step 3: Implement minimal aggregation**

```python
def _build_prior_chapters(kg, learner, current_chapter_id):
    current_order = kg.get_chapter(current_chapter_id).chapter_order
    for chapter in kg.chapters:
        if chapter.chapter_order >= current_order:
            continue
        chapter_kp_ids = {chapter.primary_kp_id, *chapter.co_requisite_kp_ids}
        records = [record for record in learner.test_records if record.knowledge_point_id in chapter_kp_ids]
        if not records:
            continue
        # Aggregate evidence and keep completed_at=None.
```

- [ ] **Step 4: Run the regression test and verify it passes**

Run: `pytest test_regressions.py -q`

- [ ] **Step 5: Run full Agent verification**

Run: `pytest test_verify.py test_simulation.py test_security_contract.py test_regressions.py test_e2e.py test_api_hardening.py test_adaptive_hardening.py -q`

