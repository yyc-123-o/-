from skillforge_kb.agents.candidate_evidence_review import (
    CandidateEvidenceReviewAgent,
    ReviewerDecision,
)


def _candidate(evidence_id: str, kind: str) -> dict:
    return {
        "chunk_id": evidence_id,
        "concept_id": "dl.cnn.convolution",
        "depth": "intro",
        "content_kind": kind,
        "source_title": "CNN 教材",
        "excerpt": "可审核片段",
        "license_status": "allowed",
    }


def test_candidates_require_explicit_human_review() -> None:
    report = CandidateEvidenceReviewAgent().review(
        (_candidate("d1", "definition"), _candidate("c1", "code"), _candidate("e1", "exercise")),
        concept_id="dl.cnn.convolution",
        depth="intro",
    )

    assert report.status == "review_required"
    assert report.missing_publishable_kinds == ("code", "definition", "exercise")
    assert all(item.review_status == "review_required" for item in report.items)


def test_explicit_review_can_make_all_required_kinds_publishable() -> None:
    candidates = (
        _candidate("d1", "definition"),
        _candidate("c1", "code"),
        _candidate("e1", "exercise"),
    )
    decisions = tuple(
        ReviewerDecision(
            evidence_id=evidence_id,
            approved=True,
            license_confirmed=False,
            reviewer="reviewer-01",
        )
        for evidence_id in ("d1", "c1", "e1")
    )

    report = CandidateEvidenceReviewAgent().review(
        candidates,
        concept_id="dl.cnn.convolution",
        depth="intro",
        decisions=decisions,
    )

    assert report.status == "ready_for_publication"
    assert report.missing_publishable_kinds == ()
    assert all(item.publishable for item in report.items)


def test_only_ready_review_can_build_publication_manifest() -> None:
    agent = CandidateEvidenceReviewAgent()
    candidates = (
        _candidate("d1", "definition"),
        _candidate("c1", "code"),
        _candidate("e1", "exercise"),
    )
    decisions = tuple(
        ReviewerDecision(
            evidence_id=evidence_id,
            approved=True,
            license_confirmed=False,
            reviewer="reviewer-01",
        )
        for evidence_id in ("d1", "c1", "e1")
    )
    report = agent.review(
        candidates,
        concept_id="dl.cnn.convolution",
        depth="intro",
        decisions=decisions,
    )

    manifest = agent.build_publication_manifest(report, candidates)

    assert manifest["concept_id"] == "dl.cnn.convolution"
    assert len(manifest["records"]) == 3
