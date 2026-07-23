from pathlib import Path

from skillforge_kb.fusion.inventory import inventory_tree, sha256_file
from skillforge_kb.fusion.models import (
    CorpusId,
    FusionDisposition,
    FusionOutcome,
    InputDataset,
    ReasonCode,
)


def test_inventory_tree_is_sorted_and_hashes_file_bytes(tmp_path: Path) -> None:
    (tmp_path / "nested").mkdir()
    (tmp_path / "z.txt").write_bytes(b"z")
    (tmp_path / "nested" / "a.txt").write_bytes(b"alpha")

    entries = inventory_tree(tmp_path)

    assert [entry.relative_path for entry in entries] == ["nested/a.txt", "z.txt"]
    assert entries[0].size_bytes == 5
    assert entries[0].sha256 == sha256_file(tmp_path / "nested" / "a.txt")
    assert all(entry.root == str(tmp_path.resolve()) for entry in entries)


def test_fusion_outcome_defaults_to_non_publishable() -> None:
    outcome = FusionOutcome(
        input_dataset=InputDataset.PILOT,
        input_line=7,
        raw_line_sha256="a" * 64,
        disposition=FusionDisposition.ACCEPTED,
        corpus_id=CorpusId.LEARNING_EVIDENCE,
        reason_codes=[ReasonCode.HUMAN_REVIEW_REQUIRED],
    )

    assert outcome.publishable is False
    assert outcome.candidate is None
