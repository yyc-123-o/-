import json
import subprocess
import sys
from pathlib import Path


def test_cli_writes_queue_without_overwriting_input(tmp_path: Path) -> None:
    root = Path(__file__).parents[3]
    source = {
        "chunk_id": "cnn-definition-1",
        "source_id": "dl_ch09_cnn",
        "source_title": "DeepLearning Chapter 9 Convolutional Networks",
        "source_url": "https://github.com/MingchaoZhu/DeepLearning",
        "license_status": "allowed",
        "license": "MIT",
        "language": "zh",
        "content_kind": "definition",
        "concept_ids": ["dl.cnn.convolution"],
        "locator": "page 1",
        "difficulty": 1,
        "text": "卷积运算将输入窗口与卷积核逐元素相乘并求和。",
        "content_hash": "a" * 64,
    }
    input_path = tmp_path / "input.jsonl"
    output_path = tmp_path / "queue.json"
    input_path.write_text(json.dumps(source, ensure_ascii=False) + "\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "build_evidence_review_queue.py"),
            "--input-file",
            str(input_path),
            "--output-file",
            str(output_path),
            "--core-concept-id",
            "dl.cnn.convolution",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["candidate_count"] == 1
    assert payload["publishable"] is False
    assert input_path.read_text(encoding="utf-8").count("cnn-definition-1") == 1
