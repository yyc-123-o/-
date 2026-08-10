from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple


@dataclass
class EvalCase:
    query: str
    generated_statements: List[str]
    learner_mastery: Dict[str, float]
    expected_difficulty: str


def hallucination_rate(statements_with_concepts: Sequence[Tuple[str, str]], kg) -> float:
    if not statements_with_concepts:
        return 0.0

    unsupported = 0
    for _, concept in statements_with_concepts:
        if not kg.get_evidence_chunks(concept):
            unsupported += 1
    return unsupported / len(statements_with_concepts)


def difficulty_match_accuracy(cases: List[EvalCase], system) -> float:
    if not cases:
        return 0.0

    correct = 0
    for case in cases:
        results = system.retrieve(case.query, top_k=3)
        if results and results[0].difficulty == case.expected_difficulty:
            correct += 1
    return correct / len(cases)


def concept_coverage_rate(kg, syllabus_concepts: List[str]) -> float:
    if not syllabus_concepts:
        return 0.0

    covered = 0
    for concept in syllabus_concepts:
        if kg.get_evidence_chunks(concept):
            covered += 1
    return covered / len(syllabus_concepts)
