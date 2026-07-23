import json
from pathlib import Path

from typer.testing import CliRunner

from skillforge_kb.cli import app
from skillforge_kb.ingestion.normalize import sha256_text

runner = CliRunner()


def test_fusion_dry_run_cli_writes_summary(tmp_path: Path) -> None:
    knowledge = tmp_path / "knowledge"
    processed = tmp_path / "processed"
    output = tmp_path / "output"
    knowledge.mkdir()
    processed.mkdir()
    source = knowledge / "source.pdf"
    source.write_bytes(b"source")
    text = "梯度下降沿损失函数下降方向更新模型参数。"
    pilot_row = {
        "chunk_id": "pilot-1",
        "source_id": "source-1",
        "source_title": "Optimization Notes",
        "source_path": "knowledge/source.pdf",
        "source_url": "https://example.edu/optimization",
        "language": "zh",
        "text": text,
        "content_hash": sha256_text(text),
        "locator": "page 1",
        "concept_ids": ["ml.optimization.gradient_descent"],
        "content_kind": "definition",
        "difficulty": 2,
        "license": "MIT",
        "review_status": "candidate",
    }
    pilot = knowledge / "pilot.jsonl"
    pilot.write_text(json.dumps(pilot_row, ensure_ascii=False) + "\n", encoding="utf-8")
    legacy = processed / "index_chunks.jsonl"
    legacy.write_text("", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "fusion-dry-run",
            "--knowledge-root",
            str(knowledge),
            "--legacy-root",
            str(processed),
            "--pilot-jsonl",
            str(pilot),
            "--legacy-jsonl",
            str(legacy),
            "--workspace-root",
            str(tmp_path),
            "--output-dir",
            str(output),
        ],
    )

    assert result.exit_code == 0
    assert "Processed 1 rows" in result.stdout
    summary = json.loads((output / "fusion_summary.json").read_text(encoding="utf-8"))
    assert summary["input_rows"] == 1
