from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def test_external_cross_check_cli_writes_json_report(tmp_path: Path) -> None:
    root = Path(__file__).parents[2]
    primary_file = tmp_path / "primary.jsonl"
    external_file = tmp_path / "external.jsonl"
    output_file = tmp_path / "cross_check_report.json"

    _write_jsonl(
        primary_file,
        [
            {
                "chunk_id": "p-1",
                "doc_id": "p-doc-1",
                "source_title": "CNN 卷积基础",
                "heading_path": ["CNN", "卷积运算"],
                "text": "卷积运算会在输入上滑动并生成输出特征图。",
                "page_no": 1,
                "domain_tag": "ai-knowledge",
                "difficulty": "进阶",
                "token_count": 12,
            }
        ],
    )
    _write_jsonl(
        external_file,
        [
            {
                "chunk_id": "p-1",
                "doc_id": "e-doc-1",
                "source_title": "CNN Intro",
                "heading_path": ["CNN", "卷积运算"],
                "text": "卷积运算会在输入上滑动并生成输出特征图。",
                "page_no": 1,
                "domain_tag": "ai-knowledge",
                "difficulty": "进阶",
                "token_count": 12,
                "content_kind": "definition",
            }
        ],
    )

    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "build_external_cross_check_report.py"),
            "--primary-file",
            str(primary_file),
            "--external-file",
            str(external_file),
            "--output-file",
            str(output_file),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert payload["summary"]["duplicate_overlap_count"] == 1
    assert payload["gate_decision"]["allowed_for_published_resource"] is False
