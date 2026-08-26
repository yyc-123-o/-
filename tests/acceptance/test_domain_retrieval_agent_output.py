import json
from pathlib import Path

ROOT = Path(__file__).parents[2]
OUTPUT = (
    ROOT
    / "examples"
    / "simulations"
    / "profile-2026-0001-demo"
    / "domain_retrieval_agent_output_cnn_0804.json"
)
HANDOFF = OUTPUT.parent / "resource_agent_handoff_cnn_0803.json"


def test_domain_retrieval_output_has_governed_cnn_candidates() -> None:
    payload = json.loads(OUTPUT.read_text(encoding="utf-8"))
    handoff = json.loads(HANDOFF.read_text(encoding="utf-8"))
    request = payload["request"]
    candidates = payload["candidate_evidence"]
    required_fields = {
        "chunk_id",
        "source_id",
        "source_title",
        "heading_path",
        "score",
        "retrieval_method",
        "concept_id",
        "depth",
        "content_kind",
        "review_status",
        "license_status",
        "evidence_status",
    }

    assert request == {
        "query": "卷积运算 CNN Conv2d 图像张量 padding stride 输出尺寸",
        "rewritten_query": (
            "学生 PROFILE-2026-0001-DEMO 的 intro 卷积运算："
            "卷积、互相关、CNN、Conv2d、图像张量、padding、stride、输出尺寸"
        ),
        "profile_id": "PROFILE-2026-0001-DEMO",
        "concept_id": "dl.cnn.convolution",
        "depth": "intro",
        "top_k": 5,
    }
    assert request["profile_id"] == handoff["profile_id"]
    assert request["concept_id"] == handoff["concept_id"]
    assert request["depth"] == handoff["depth"]
    assert payload["evidence"] == []
    assert len(candidates) == request["top_k"]
    assert {item["content_kind"] for item in candidates} == {
        "definition",
        "code",
        "exercise",
    }
    assert all(required_fields <= item.keys() for item in candidates)
    assert all(item.get("text") or item.get("excerpt") for item in candidates)
    assert all(
        item["concept_id"] == request["concept_id"]
        and item["depth"] == request["depth"]
        and item["review_status"] == "candidate"
        and item["evidence_status"] == "candidate_only"
        for item in candidates
    )
    forbidden = ("GAN", "DCGAN", "TextCNN", "ConvTranspose2d", "转置卷积")
    candidate_text = json.dumps(candidates, ensure_ascii=False).lower()
    assert not any(term.lower() in candidate_text for term in forbidden)

    summary = payload["evidence_summary"]
    assert summary["published_count"] == 0
    assert summary["candidate_count"] == len(candidates)
    assert summary["content_kinds_found_in_candidates"] == [
        "definition",
        "code",
        "exercise",
    ]
    assert summary["formal_evidence_is_empty"] is True
    assert payload["concept_evidence"][request["concept_id"]]["published"] == []
    assert payload["concept_evidence"][request["concept_id"]]["evidence_status"] == (
        "candidate_only"
    )
    assert payload["evidence_gap"]["formal_evidence"]
    assert payload["evidence_gap"]["definition"]
    assert payload["evidence_gap"]["code"]
    assert payload["evidence_gap"]["exercise"]
