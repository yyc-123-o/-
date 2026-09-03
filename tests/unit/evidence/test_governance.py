from skillforge_kb.evidence.governance import build_review_queue


def _row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "chunk_id": "cnn-definition-1",
        "source_id": "dl_ch09_cnn",
        "source_title": "DeepLearning Chapter 9 Convolutional Networks",
        "source_url": "https://github.com/MingchaoZhu/DeepLearning",
        "license_status": "allowed",
        "license": "MIT",
        "tier": "S2",
        "language": "zh",
        "content_kind": "definition",
        "concept_ids": ["dl.cnn.convolution"],
        "locator": "page 1",
        "page": 1,
        "difficulty": 1,
        "text": "卷积运算将输入窗口与卷积核逐元素相乘并求和。",
        "content_hash": "a" * 64,
    }
    row.update(overrides)
    return row


def test_generic_queue_normalizes_candidates_and_reports_content_gaps(catalog) -> None:
    payload = build_review_queue(
        [
            _row(),
            _row(
                chunk_id="cnn-code-1",
                content_kind="code",
                locator="page 13",
                page=13,
                difficulty=3,
                text="torch.nn.Conv2d(3, 8, kernel_size=3, stride=1)",
                content_hash="b" * 64,
            ),
        ],
        catalog,
        core_concept_ids=("dl.cnn.convolution",),
    )

    assert payload["schema_version"] == "evidence-review-queue.v1"
    assert payload["publishable"] is False
    assert payload["candidate_count"] == 2
    assert payload["excluded_count"] == 0
    assert payload["candidates"][0]["review_status"] == "candidate"
    assert {item["proposed_depth"] for item in payload["candidates"]} == {
        "intro",
        "intermediate",
    }
    summary = payload["concepts"]["dl.cnn.convolution"]
    assert summary["available_content_kinds"] == ["definition", "code"]
    assert summary["missing_content_kinds"] == ["exercise"]
    assert summary["ready_for_human_review"] is True


def test_generic_queue_excludes_unknown_missing_and_duplicate_rows(catalog) -> None:
    payload = build_review_queue(
        [
            _row(),
            _row(chunk_id="cnn-definition-1"),
            _row(chunk_id="unknown-1", concept_ids=["not.in.graph"]),
            _row(chunk_id="missing-1", text=""),
            _row(chunk_id="license-1", license_status="pending"),
        ],
        catalog,
        core_concept_ids=("dl.cnn.convolution",),
    )

    assert payload["candidate_count"] == 1
    assert payload["excluded_count"] == 4
    reasons = {item["chunk_id"]: item["reason"] for item in payload["excluded"]}
    assert reasons["cnn-definition-1"] == "duplicate_chunk_id"
    assert reasons["unknown-1"] == "unknown_concept_id"
    unknown = next(item for item in payload["excluded"] if item["chunk_id"] == "unknown-1")
    assert unknown["concept_ids"] == ["not.in.graph"]
    assert reasons["missing-1"] == "missing_required_metadata"
    assert reasons["license-1"] == "license_not_allowed"


def test_generic_queue_uses_core_manifest_as_coverage_denominator(catalog) -> None:
    payload = build_review_queue(
        [_row()],
        catalog,
        core_concept_ids=("dl.cnn.convolution", "math.linear-algebra.scalar"),
    )

    coverage = payload["coverage_summary"]
    assert coverage["core_concept_count"] == 2
    assert coverage["covered_concept_count"] == 1
    assert coverage["coverage_rate"] == 0.5
    assert coverage["complete_three_kind_count"] == 0


def test_generic_queue_filters_candidates_to_the_declared_core_scope(catalog) -> None:
    payload = build_review_queue(
        [
            _row(
                concept_ids=["dl.cnn.convolution", "math.linear-algebra.scalar"],
            ),
            _row(
                chunk_id="scalar-1",
                concept_ids=["math.linear-algebra.scalar"],
            ),
        ],
        catalog,
        core_concept_ids=("dl.cnn.convolution",),
    )

    assert payload["candidate_count"] == 1
    assert payload["candidates"][0]["concept_id"] == "dl.cnn.convolution"
    assert payload["excluded"] == [
        {
            "chunk_id": "scalar-1",
            "reason": "outside_core_scope",
            "concept_ids": ["math.linear-algebra.scalar"],
        }
    ]
