import argparse
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from skillforge_kb.evidence.review_queue import build_cnn_review_queue


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a candidate-only CNN evidence review queue."
    )
    parser.add_argument("--input-file", type=Path, required=True)
    parser.add_argument("--output-file", type=Path, required=True)
    return parser.parse_args()


def _read_rows(path: Path) -> Iterator[dict[str, Any]]:
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON at line {line_number}: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"JSONL row {line_number} must be an object")
        yield row


def main() -> int:
    args = parse_args()
    input_path = args.input_file.expanduser().resolve()
    output_path = args.output_file.expanduser().resolve()
    if input_path == output_path:
        raise ValueError("output file must not overwrite input file")
    payload = build_cnn_review_queue(_read_rows(input_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
