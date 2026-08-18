from collections.abc import Iterable, Mapping
from typing import Any

CONCEPT_ID = "dl.cnn.convolution"
DEPTH = "intro"
REQUIRED_KINDS = ("definition", "code", "exercise")
_DISALLOWED_TERMS = (
    "gan",
    "dcgan",
    "textcnn",
    "diffusion",
    "convtranspose",
    "生成对抗",
    "转置卷积",
)
_SOURCE_ANCHORS = ("cnn", "convolution", "conv2d", "卷积")


def build_cnn_review_queue(
    rows: Iterable[Mapping[str, object]],
) -> dict[str, object]:
    candidates: list[dict[str, object]] = []
    excluded: list[dict[str, str]] = []
    seen_chunk_ids: set[str] = set()

    for row in rows:
        chunk_id = _text(row.get("chunk_id")) or "unknown"
        reason = _exclusion_reason(row, chunk_id in seen_chunk_ids)
        if reason is not None:
            excluded.append({"chunk_id": chunk_id, "reason": reason})
            continue
        seen_chunk_ids.add(chunk_id)
        candidates.append(_candidate(row, chunk_id))

    candidates.sort(
        key=lambda item: (
            str(item["content_kind"]),
            str(item["source_id"]),
            str(item["locator"]),
            str(item["chunk_id"]),
        )
    )
    excluded.sort(key=lambda item: (item["chunk_id"], item["reason"]))
    available = {str(item["content_kind"]) for item in candidates}
    code_excerpts = [
        str(item["excerpt"]).casefold()
        for item in candidates
        if item["content_kind"] == "code"
    ]
    missing_requirements: list[str] = []
    if not any("nn.conv2d" in excerpt for excerpt in code_excerpts):
        missing_requirements.append("pytorch_nn_conv2d")
    if "exercise" not in available:
        missing_requirements.append("exercise")
    return {
        "schema_version": "cnn-evidence-review-queue.v1",
        "concept_id": CONCEPT_ID,
        "depth": DEPTH,
        "review_status": "candidate",
        "publishable": False,
        "candidates": candidates,
        "excluded_candidates": excluded,
        "available_content_kinds": [
            kind for kind in REQUIRED_KINDS if kind in available
        ],
        "missing_content_kinds": [
            kind for kind in REQUIRED_KINDS if kind not in available
        ],
        "missing_requirements": missing_requirements,
    }


def _exclusion_reason(
    row: Mapping[str, object],
    duplicate_chunk_id: bool,
) -> str | None:
    concept_ids = row.get("concept_ids")
    if not isinstance(concept_ids, list) or CONCEPT_ID not in concept_ids:
        return "concept_scope_mismatch"
    if duplicate_chunk_id:
        return "duplicate_chunk_id"
    if _text(row.get("license_status")) != "allowed":
        return "license_not_allowed"
    if _text(row.get("content_kind")) not in REQUIRED_KINDS:
        return "unsupported_content_kind"
    required_fields = (
        "chunk_id",
        "source_id",
        "source_title",
        "source_url",
        "license",
        "language",
        "locator",
        "text",
        "content_hash",
    )
    if any(not _text(row.get(field)) for field in required_fields):
        return "missing_required_metadata"
    searchable = " ".join(
        (
            _text(row.get("source_title")),
            _heading_text(row.get("heading_path")),
            _text(row.get("text")),
        )
    ).casefold()
    if any(term in searchable for term in _DISALLOWED_TERMS):
        return "disallowed_source_family"
    source_scope = " ".join(
        (
            _text(row.get("source_title")),
            _heading_text(row.get("heading_path")),
        )
    ).casefold()
    if not any(anchor in source_scope for anchor in _SOURCE_ANCHORS):
        return "source_scope_mismatch"
    return None


def _candidate(row: Mapping[str, object], chunk_id: str) -> dict[str, object]:
    page = row.get("page")
    return {
        "chunk_id": chunk_id,
        "source_id": _text(row.get("source_id")),
        "source_title": _text(row.get("source_title")),
        "source_url": _text(row.get("source_url")),
        "license_status": "allowed",
        "license": _text(row.get("license")),
        "tier": _text(row.get("tier")) or None,
        "language": _text(row.get("language")),
        "content_kind": _text(row.get("content_kind")),
        "concept_id": CONCEPT_ID,
        "depth": DEPTH,
        "locator": _text(row.get("locator")),
        "page": page if isinstance(page, int) and page > 0 else None,
        "normalized_hash": _text(row.get("content_hash")),
        "excerpt": _text(row.get("text")),
        "review_status": "candidate",
    }


def _heading_text(value: object) -> str:
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return _text(value)


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
