import json
from pathlib import Path

from skillforge_kb.fusion.runner import run_dry_run
from skillforge_kb.ingestion.normalize import sha256_text


def _pilot_row(source_path: str) -> dict[str, object]:
    text = "矩阵乘法把输入特征映射到新的表示空间，并保持线性结构。"
    return {
        "chunk_id": "pilot-1",
        "source_id": "source-1",
        "source_title": "Linear Algebra Notes",
        "source_path": source_path,
        "source_url": "https://example.edu/linear-algebra",
        "language": "zh",
        "text": text,
        "content_hash": sha256_text(text),
        "locator": "page 1",
        "concept_ids": ["ml.linear_algebra.matrix"],
        "content_kind": "definition",
        "difficulty": 2,
        "license": "MIT",
        "review_status": "candidate",
    }


def _legacy_row(chunk_id: str, text: str) -> dict[str, object]:
    return {
        "chunk_id": chunk_id,
        "doc_id": "legacy-doc",
        "source_title": "faiss_intro",
        "heading_path": ["FAISS", "IndexFlatIP"],
        "text": text,
        "page_no": None,
        "domain_tag": "ai-knowledge",
        "difficulty": "进阶",
        "token_count": len(text),
    }


def test_dry_run_accounts_for_every_line_and_is_deterministic(tmp_path: Path) -> None:
    knowledge_root = tmp_path / "knowledge"
    legacy_root = tmp_path / "processed"
    output_dir = tmp_path / "reports"
    knowledge_root.mkdir()
    legacy_root.mkdir()
    (knowledge_root / "source.pdf").write_bytes(b"source")
    pilot_path = knowledge_root / "pilot.jsonl"
    pilot_path.write_text(
        json.dumps(_pilot_row("knowledge/source.pdf"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    legacy_text = "IndexFlatIP performs exact inner-product retrieval over normalized vectors."
    legacy_path = legacy_root / "index_chunks.jsonl"
    legacy_path.write_text(
        json.dumps(_legacy_row("legacy-1", legacy_text), ensure_ascii=False)
        + "\n"
        + json.dumps(_legacy_row("legacy-2", legacy_text), ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )

    first = run_dry_run(
        knowledge_root=knowledge_root,
        legacy_root=legacy_root,
        pilot_jsonl=pilot_path,
        legacy_jsonl=legacy_path,
        workspace_root=tmp_path,
        output_dir=output_dir,
    )
    first_bytes = {
        path.name: path.read_bytes() for path in sorted(output_dir.iterdir()) if path.is_file()
    }
    second = run_dry_run(
        knowledge_root=knowledge_root,
        legacy_root=legacy_root,
        pilot_jsonl=pilot_path,
        legacy_jsonl=legacy_path,
        workspace_root=tmp_path,
        output_dir=output_dir,
    )

    assert first == second
    assert first.input_rows == 3
    assert sum(first.outcome_counts.values()) == 3
    assert first.source_count == 2
    assert first_bytes == {
        path.name: path.read_bytes() for path in sorted(output_dir.iterdir()) if path.is_file()
    }
    outcomes = [
        json.loads(line)
        for line in (output_dir / "fusion_outcomes.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(outcomes) == 3
    assert all(outcome["publishable"] is False for outcome in outcomes)
