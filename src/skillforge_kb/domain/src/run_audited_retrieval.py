from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any


CONTENT_KINDS = ("definition", "code", "exercise")
SUPPORTED_SUFFIXES = {".md", ".markdown"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run an auditable retrieval over the existing raw Markdown corpus."
    )
    parser.add_argument("query")
    parser.add_argument("--concept-id", required=True)
    parser.add_argument("--depth", type=int, required=True)
    parser.add_argument("--learner-id", default="demo_learner")
    parser.add_argument("--profile-id", default=None)
    parser.add_argument("--level", choices=("beginner", "intermediate", "advanced"), default="intermediate")
    parser.add_argument("--weak-concepts", default="")
    parser.add_argument("--goals", default="")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--raw-dir", default="data/raw")
    parser.add_argument("--output", default="data/audited_retrieval_result.json")
    return parser.parse_args()


def csv_values(raw: str) -> list[str]:
    return [value.strip() for value in raw.split(",") if value.strip()]


def rewrite_query(query: str, weak_concepts: list[str], goals: list[str]) -> str:
    extras: list[str] = []
    if goals:
        extras.append("goals:" + ", ".join(goals[:3]))
    if weak_concepts:
        extras.append("weak_concepts:" + ", ".join(weak_concepts[:5]))
    return query.strip() + (" ; " + " ; ".join(extras) if extras else "")


def infer_intent(query: str) -> str:
    if any(word in query for word in ("路径", "前置", "先学", "路线")):
        return "learning_path"
    if any(word in query for word in ("证据", "出处", "来源", "依据")):
        return "evidence_lookup"
    if any(word in query for word in ("怎么", "如何", "步骤", "实践")):
        return "task_guidance"
    return "knowledge_retrieval"


def normalize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9_+#.-]+|[\u4e00-\u9fff]", text.lower())


def classify_content_kind(path: Path, text: str) -> str:
    name = path.name.lower()
    lowered = text.lower()
    if any(token in name for token in ("task", "exercise", "练习", "习题", "作业")):
        return "exercise"
    if any(token in lowered for token in ("练习题", "习题", "作业要求", "请完成", "exercise")):
        return "exercise"
    if any(token in name for token in ("workflow", "pipeline", "experiment", "project", "实践", "实训")):
        return "code"
    if any(token in lowered for token in ("```", "python", "pip install", "代码", "实现", "运行")):
        return "code"
    return "definition"


def heading_path(lines: list[str], index: int) -> list[str]:
    levels: dict[int, str] = {}
    for line in lines[: index + 1]:
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if not match:
            continue
        level = len(match.group(1))
        levels[level] = match.group(2).strip()
        for stale in [key for key in levels if key > level]:
            del levels[stale]
    return [levels[key] for key in sorted(levels)]


def split_sections(text: str) -> list[tuple[int, list[str], str]]:
    lines = text.splitlines()
    starts = [index for index, line in enumerate(lines) if re.match(r"^#{1,6}\s+", line)]
    sections: list[tuple[int, list[str], str]] = []
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(lines)
        body = "\n".join(lines[start:end]).strip()
        if body:
            sections.append((start, heading_path(lines, start), body))
    if not sections and text.strip():
        sections.append((0, [], text.strip()))
    return sections


def token_score(query_tokens: list[str], text: str, concept_id: str) -> float:
    text_tokens = normalize(text)
    if not query_tokens or not text_tokens:
        return 0.0
    query_set = set(query_tokens)
    text_set = set(text_tokens)
    overlap = len(query_set & text_set) / len(query_set)
    concept_terms = [term for term in normalize(concept_id.replace("concept:", "")) if len(term) > 1]
    concept_hit = sum(term in text.lower() for term in concept_terms) / max(1, len(concept_terms))
    return round(0.8 * overlap + 0.2 * concept_hit, 6)


def excerpt(text: str, limit: int = 500) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact if len(compact) <= limit else compact[:limit].rstrip() + "..."


def build_candidate(
    path: Path,
    raw_dir: Path,
    section_index: int,
    headings: list[str],
    text: str,
    score: float,
    concept_id: str,
    depth: int,
) -> dict[str, Any]:
    relative = path.relative_to(raw_dir).as_posix()
    chunk_id = f"candidate:{relative}:s{section_index:04d}"
    source_id = f"raw:{relative}"
    content_kind = classify_content_kind(path, text)
    return {
        "chunk_id": chunk_id,
        "source_id": source_id,
        "source_title": path.stem,
        "heading_path": headings,
        "text": text,
        "excerpt": excerpt(text),
        "page_no": None,
        "code_location": f"{relative}:section:{section_index}",
        "score": score,
        "retrieval_method": "audited_keyword_scan",
        "concept_id": concept_id,
        "depth": depth,
        "content_kind": content_kind,
        "review_status": "unreviewed",
        "license_status": "unregistered",
        "evidence_status": "candidate_only"
    }


def main() -> None:
    args = parse_args()
    raw_dir = Path(args.raw_dir).resolve()
    profile_id = args.profile_id or args.learner_id
    weak_concepts = csv_values(args.weak_concepts)
    goals = csv_values(args.goals)
    rewritten = rewrite_query(args.query, weak_concepts, goals)
    query_tokens = normalize(args.query + " " + args.concept_id + " " + " ".join(weak_concepts))

    candidates: list[dict[str, Any]] = []
    for path in sorted(raw_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for section_index, headings, section_text in split_sections(text):
            score = token_score(query_tokens, section_text, args.concept_id)
            if score <= 0:
                continue
            candidates.append(
                build_candidate(
                    path,
                    raw_dir,
                    section_index,
                    headings,
                    section_text,
                    score,
                    args.concept_id,
                    args.depth,
                )
            )

    candidates.sort(key=lambda item: (-item["score"], item["chunk_id"]))
    candidates = candidates[: max(args.top_k * 3, 30)]
    formal_evidence: list[dict[str, Any]] = []

    kinds_present = sorted({item["content_kind"] for item in candidates})
    missing_kinds = [kind for kind in CONTENT_KINDS if kind not in kinds_present]
    evidence_gap = {
        "code": "Formal published evidence is unavailable because source review_status/license_status metadata is not present in the current corpus." if formal_evidence == [] else None,
        "exercise": "No exercise candidate was found for this query/concept/depth." if "exercise" in missing_kinds else None,
        "definition": "No definition candidate was found for this query/concept/depth." if "definition" in missing_kinds else None
    }
    evidence_gap = {key: value for key, value in evidence_gap.items() if value}
    if not formal_evidence:
        evidence_gap["formal_evidence"] = "No evidence was promoted from candidate_only to published evidence. Candidate fragments must be reviewed and licensed before publication."

    result = {
        "request": {
            "query": args.query,
            "rewritten_query": rewritten,
            "learner_id": args.learner_id,
            "profile_id": profile_id,
            "learner_profile": {
                "learner_id": args.learner_id,
                "level": args.level,
                "weak_concepts": weak_concepts,
                "goals": goals
            },
            "difficulty_filter": args.level,
            "concept_id": args.concept_id,
            "depth": args.depth,
            "top_k": args.top_k
        },
        "capability_check": {
            "hybrid_retrieval_in_source": True,
            "concept_id_filter_in_current_agent": False,
            "depth_filter_in_current_agent": False,
            "content_kind_metadata_in_current_agent": False,
            "review_status_metadata_in_current_agent": False,
            "license_status_metadata_in_current_agent": False,
            "published_evidence_available": False
        },
        "evidence": formal_evidence,
        "candidate_evidence": candidates[: args.top_k],
        "concept_evidence": {
            args.concept_id: {
                "depth": args.depth,
                "published": [],
                "candidates": [item["chunk_id"] for item in candidates[: args.top_k]],
                "evidence_status": "candidate_only"
            }
        },
        "evidence_summary": {
            "published_count": len(formal_evidence),
            "candidate_count": len(candidates[: args.top_k]),
            "content_kinds_found_in_candidates": kinds_present,
            "required_content_kinds": list(CONTENT_KINDS),
            "missing_required_content_kinds": missing_kinds,
            "formal_evidence_is_empty": not formal_evidence,
            "note": "candidate_evidence is not published knowledge and must not be used as formal evidence before review and license confirmation."
        },
        "evidence_gap": evidence_gap
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(output))


if __name__ == "__main__":
    main()
