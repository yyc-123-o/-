from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from retrieval_agent import DomainRetrievalAgent, LearnerProfile


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the domain retrieval agent.")
    parser.add_argument("query", help="Question or retrieval request.")
    parser.add_argument("--config", default="configs/pipeline_config.yaml", help="Config file path.")
    parser.add_argument("--index-prefix", default=None, help="Hybrid index prefix.")
    parser.add_argument("--learner-id", default="demo_learner", help="Learner profile id.")
    parser.add_argument("--profile-id", default="demo_profile", help="Learner profile record id.")
    parser.add_argument("--level", default="intermediate", choices=["beginner", "intermediate", "advanced"])
    parser.add_argument("--weak-concepts", default="", help="Comma-separated weak concepts.")
    parser.add_argument("--goals", default="", help="Comma-separated learning goals.")
    parser.add_argument("--concept-id", default=None, help="Optional concept filter id, e.g. concept:rag.")
    parser.add_argument("--depth", type=int, default=None, help="Optional concept graph depth.")
    parser.add_argument("--top-k", type=int, default=5, help="Number of evidence items to return.")
    parser.add_argument("--json", action="store_true", help="Print the full result as JSON.")
    parser.add_argument("--output", default=None, help="Optional path to save the full JSON result.")
    return parser


def parse_csv_values(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def main() -> None:
    args = build_parser().parse_args()
    agent = DomainRetrievalAgent(config_path=args.config)
    profile = LearnerProfile(
        learner_id=args.learner_id,
        profile_id=args.profile_id,
        level=args.level,
        weak_concepts=parse_csv_values(args.weak_concepts),
        goals=parse_csv_values(args.goals),
    )
    if args.index_prefix:
        agent.load_resources(args.index_prefix)

    result = agent.ask(
        args.query,
        learner_profile=profile,
        top_k=args.top_k,
        concept_id=args.concept_id,
        depth=args.depth,
    )
    payload = asdict(result)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print(f"[intent] {result.intent}")
    print(f"[query] {result.query}")
    print(f"[rewritten_query] {result.rewritten_query}")
    print(f"[learner_id] {result.learner_id}")
    print(f"[profile_id] {result.profile_id}")
    print(f"[difficulty_filter] {result.difficulty_filter}")
    print(f"[concept_id] {result.concept_id}")
    print(f"[depth] {result.depth}")
    print("\n[published_evidence]")
    if not result.evidence:
        print("0 published evidence items")
    for idx, item in enumerate(result.evidence, start=1):
        print(f"{idx}. {item.source_title} | {' / '.join(item.heading_path)} | score={item.score:.4f}")
    print("\n[candidate_evidence]")
    for idx, item in enumerate(result.candidate_evidence, start=1):
        print(f"{idx}. {item.source_title} | {' / '.join(item.heading_path)} | score={item.score:.4f} | status={item.evidence_status}")
    if result.evidence_gap:
        print("\n[evidence_gap]")
        for key, value in result.evidence_gap.items():
            print(f"- {key}: {value}")
    if result.agent_notes:
        print("\n[agent_notes]")
        for note in result.agent_notes:
            print(f"- {note}")


if __name__ == "__main__":
    main()
