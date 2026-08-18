import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]


def _row(chunk_id: str, content_kind: str, text: str) -> dict[str, object]:
    return {
        "chunk_id": chunk_id,
        "source_id": "dl_ch09_cnn",
        "source_title": "DeepLearning Chapter 9 Convolutional Networks",
        "source_url": "https://github.com/MingchaoZhu/DeepLearning",
        "license_status": "allowed",
        "license": "MIT",
        "language": "zh",
        "content_kind": content_kind,
        "concept_ids": ["dl.cnn.convolution"],
        "locator": "page 1",
        "page": 1,
        "text": text,
        "content_hash": chunk_id.ljust(64, "0")[:64],
    }


def test_review_queue_cli_writes_candidate_only_report(tmp_path: Path) -> None:
    input_path = tmp_path / "input.jsonl"
    output_path = tmp_path / "queue.json"
    rows = [
        _row("cnn-definition", "definition", "卷积运算与卷积核。"),
        _row("cnn-code", "code", "Conv2d stride padding output shape。"),
    ]
    input_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "build_cnn_evidence_review_queue.py"),
            "--input-file",
            str(input_path),
            "--output-file",
            str(output_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["review_status"] == "candidate"
    assert report["publishable"] is False
    assert report["missing_content_kinds"] == ["exercise"]
    assert report["missing_requirements"] == ["pytorch_nn_conv2d", "exercise"]
    assert len(report["candidates"]) == 2
    assert json.loads(input_path.read_text(encoding="utf-8").splitlines()[0]) == rows[0]
