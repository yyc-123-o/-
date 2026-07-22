import json
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .inventory import inventory_tree
from .legacy import adapt_legacy
from .models import DryRunSummary, FusionOutcome, SourceCandidate
from .pilot import adapt_pilot


def _atomic_write(path: Path, text: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def _json_line(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _write_jsonl(path: Path, values: Iterable[Any]) -> None:
    lines = [_json_line(value) for value in values]
    _atomic_write(path, "".join(f"{line}\n" for line in lines))


def _source_score(source: SourceCandidate) -> tuple[int, int, int]:
    return (
        int(source.provenance_complete),
        int(source.canonical_url is not None),
        int(source.source_path is not None),
    )


def _sources(outcomes: list[FusionOutcome]) -> list[SourceCandidate]:
    selected: dict[str, SourceCandidate] = {}
    for outcome in outcomes:
        if outcome.candidate is None:
            continue
        source = outcome.candidate.source
        current = selected.get(source.source_key)
        if current is None or _source_score(source) > _source_score(current):
            selected[source.source_key] = source
    return [selected[key] for key in sorted(selected)]


def _counter(values: Iterable[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def _assert_output_outside_inputs(
    output_dir: Path, knowledge_root: Path, legacy_root: Path
) -> None:
    resolved_output = output_dir.resolve()
    if any(
        resolved_output.is_relative_to(input_root.resolve())
        for input_root in (knowledge_root, legacy_root)
    ):
        raise ValueError("output directory must be outside input roots")


def run_dry_run(
    *,
    knowledge_root: Path,
    legacy_root: Path,
    pilot_jsonl: Path,
    legacy_jsonl: Path,
    workspace_root: Path,
    output_dir: Path,
) -> DryRunSummary:
    _assert_output_outside_inputs(output_dir, knowledge_root, legacy_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    inventory = inventory_tree(knowledge_root) + inventory_tree(legacy_root)
    inventory.sort(key=lambda entry: (entry.root, entry.relative_path))
    outcomes = adapt_pilot(pilot_jsonl, workspace_root) + adapt_legacy(legacy_jsonl)
    sources = _sources(outcomes)
    summary = DryRunSummary(
        input_rows=len(outcomes),
        source_count=len(sources),
        input_file_count=len(inventory),
        outcome_counts=_counter(outcome.disposition.value for outcome in outcomes),
        reason_counts=_counter(
            reason.value for outcome in outcomes for reason in outcome.reason_codes
        ),
        corpus_counts=_counter(
            outcome.corpus_id.value for outcome in outcomes if outcome.corpus_id is not None
        ),
    )
    _write_jsonl(output_dir / "input_inventory.jsonl", inventory)
    _write_jsonl(output_dir / "source_candidates.jsonl", sources)
    _write_jsonl(output_dir / "fusion_outcomes.jsonl", outcomes)
    _atomic_write(
        output_dir / "fusion_summary.json",
        json.dumps(
            summary.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    return summary
