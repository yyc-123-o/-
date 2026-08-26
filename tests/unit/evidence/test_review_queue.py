from skillforge_kb.evidence.review_queue import build_cnn_review_queue


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
        "text": "卷积运算将输入窗口与卷积核逐元素相乘并求和。",
        "content_hash": "a" * 64,
    }
    row.update(overrides)
    return row


def test_queue_keeps_valid_definition_and_code_and_reports_exercise_gap() -> None:
    payload = build_cnn_review_queue(
        [
            _row(),
            _row(
                chunk_id="cnn-code-1",
                content_kind="code",
                locator="page 13",
                page=13,
                text="class Conv2D: stride=1, pad=0; return output",
                content_hash="b" * 64,
            ),
            _row(
                chunk_id="gan-code-1",
                source_id="gan_source",
                source_title="DCGAN training guide",
                text="Conv2d is used by a GAN discriminator.",
                content_hash="c" * 64,
            ),
        ]
    )

    assert payload["concept_id"] == "dl.cnn.convolution"
    assert payload["review_status"] == "candidate"
    assert payload["publishable"] is False
    assert [item["content_kind"] for item in payload["candidates"]] == [
        "code",
        "definition",
    ]
    assert payload["missing_content_kinds"] == ["exercise"]
    assert payload["missing_requirements"] == ["pytorch_nn_conv2d", "exercise"]
    assert all(item["tier"] == "S2" for item in payload["candidates"])
    assert payload["excluded_candidates"][0]["reason"] == "disallowed_source_family"


def test_queue_rejects_rows_without_exact_concept_anchor() -> None:
    payload = build_cnn_review_queue(
        [_row(concept_ids=["dl.cnn.pooling"], chunk_id="pooling-1")]
    )

    assert payload["candidates"] == []
    assert payload["missing_content_kinds"] == ["definition", "code", "exercise"]
    assert payload["excluded_candidates"][0]["reason"] == "concept_scope_mismatch"


def test_queue_rejects_weak_concept_binding_without_cnn_source_anchor() -> None:
    payload = build_cnn_review_queue(
        [
            _row(
                chunk_id="misbound-svm-1",
                source_title="DeepLearning Chapter 5 Machine Learning Basics",
                text="linear kernel and support vector machine implementation",
            )
        ]
    )

    assert payload["candidates"] == []
    assert payload["excluded_candidates"][0]["reason"] == "source_scope_mismatch"
