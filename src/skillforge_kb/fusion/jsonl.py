import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class JsonlRecord:
    line_number: int
    raw: str
    value: dict[str, Any] | None
    error: str | None


def iter_jsonl(path: Path) -> Iterator[JsonlRecord]:
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, raw in enumerate(handle, start=1):
            value_text = raw.rstrip("\r\n")
            try:
                value = json.loads(value_text)
                if not isinstance(value, dict):
                    raise ValueError("JSONL value must be an object")
            except (json.JSONDecodeError, ValueError) as exc:
                yield JsonlRecord(line_number, value_text, None, str(exc))
            else:
                yield JsonlRecord(line_number, value_text, value, None)
