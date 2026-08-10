from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from build_pipeline import DomainKnowledgeSystem
from hybrid_retriever import Evidence, RetrievalBundle


DEFAULT_DOMAIN_TAG = "ai_llm"
DEFAULT_LEARNER_LEVELS = {
    "beginner": "beginner",
    "intermediate": "intermediate",
    "advanced": "advanced",
}


@dataclass
class LearnerProfile:
    learner_id: str = "default_learner"
    profile_id: str = "default_profile"
    level: str = "intermediate"
    weak_concepts: List[str] = field(default_factory=list)
    goals: List[str] = field(default_factory=list)


@dataclass
class RetrievalAgentResponse:
    query: str
    rewritten_query: str
    intent: str
    learner_id: str
    profile_id: str
    difficulty_filter: Optional[str]
    concept_id: Optional[str]
    depth: Optional[int]
    evidence: List[Evidence]
    candidate_evidence: List[Evidence]
    evidence_summary: Dict[str, object]
    concept_evidence: Dict[str, Dict[str, object]]
    learning_path: List[str]
    answer_outline: List[str]
    agent_notes: List[str]
    evidence_gap: Dict[str, str]


class DomainRetrievalAgent:
    """Agent layer on top of the existing hybrid retriever and KG APIs."""

    def __init__(self, config_path: str = "configs/pipeline_config.yaml"):
        self.system = DomainKnowledgeSystem(config_path=config_path)
        self._index_loaded = False

    def load_resources(self, index_prefix: Optional[str] = None) -> None:
        if self._index_loaded:
            return

        prefix = index_prefix or self.system.cfg.get("index_save_prefix", "data/processed/index")
        self.system.load_index(prefix)
        self._index_loaded = True

    def ask(
        self,
        query: str,
        learner_profile: Optional[LearnerProfile] = None,
        top_k: int = 5,
        with_learning_path: bool = True,
        concept_id: Optional[str] = None,
        depth: Optional[int] = None,
    ) -> RetrievalAgentResponse:
        self.load_resources()

        profile = learner_profile or LearnerProfile()
        difficulty_filter = self._resolve_difficulty_filter(profile.level)
        rewritten_query = self._rewrite_query(query, profile)
        intent = self._infer_intent(query)

        self._sync_profile_to_kg(profile)
        retrieval = self.system.retrieve(
            rewritten_query,
            learner_id=profile.learner_id,
            top_k=top_k,
            difficulty_filter=difficulty_filter,
            concept_id=concept_id,
            depth=depth,
        )

        concepts = self._extract_concepts(query, profile, retrieval.candidate_evidence)
        learning_path: List[str] = []
        concept_evidence: Dict[str, Dict[str, object]] = {}

        if with_learning_path and concepts:
            primary_concept = concepts[0]
            try:
                learning_path = self.system.kg_query_learning_path(primary_concept)
            except Exception:
                learning_path = []

        target_concepts = [concept_id] if concept_id else concepts[:3]
        for concept in target_concepts:
            if not concept:
                continue
            concept_key = concept
            try:
                concept_evidence[concept_key] = {
                    "depth": depth,
                    "published": [],
                    "candidates": [
                        evidence.chunk_id
                        for evidence in retrieval.candidate_evidence
                        if evidence.concept_id == concept_id or concept_id is None
                    ],
                    "graph_evidence": self.system.kg_query_evidence(concept.replace("concept:", "")),
                    "evidence_status": "candidate_only" if not retrieval.published_evidence else "mixed",
                }
            except Exception:
                concept_evidence[concept_key] = {
                    "depth": depth,
                    "published": [],
                    "candidates": [evidence.chunk_id for evidence in retrieval.candidate_evidence],
                    "graph_evidence": [],
                    "evidence_status": "candidate_only" if not retrieval.published_evidence else "mixed",
                }

        evidence_summary = self._build_evidence_summary(retrieval)
        answer_outline = self._build_answer_outline(intent, retrieval, learning_path)
        agent_notes = self._build_agent_notes(profile, retrieval, concepts, concept_id, depth)

        return RetrievalAgentResponse(
            query=query,
            rewritten_query=rewritten_query,
            intent=intent,
            learner_id=profile.learner_id,
            profile_id=profile.profile_id,
            difficulty_filter=difficulty_filter,
            concept_id=concept_id,
            depth=depth,
            evidence=retrieval.published_evidence,
            candidate_evidence=retrieval.candidate_evidence,
            evidence_summary=evidence_summary,
            concept_evidence=concept_evidence,
            learning_path=learning_path,
            answer_outline=answer_outline,
            agent_notes=agent_notes,
            evidence_gap=retrieval.evidence_gap,
        )

    def _resolve_difficulty_filter(self, level: str) -> Optional[str]:
        return DEFAULT_LEARNER_LEVELS.get(level.lower())

    def _rewrite_query(self, query: str, profile: LearnerProfile) -> str:
        extras: List[str] = []
        if profile.goals:
            extras.append("goals:" + ", ".join(profile.goals[:3]))
        if profile.weak_concepts:
            extras.append("weak_concepts:" + ", ".join(profile.weak_concepts[:5]))
        if extras:
            return query.strip() + " ; " + " ; ".join(extras)
        return query.strip()

    def _infer_intent(self, query: str) -> str:
        lowered = query.lower()
        if any(keyword in query for keyword in ["路径", "前置", "先学", "路线"]):
            return "learning_path"
        if any(keyword in query for keyword in ["证据", "出处", "来源", "依据"]):
            return "evidence_lookup"
        if any(keyword in query for keyword in ["怎么", "如何", "步骤", "实践"]):
            return "task_guidance"
        if any(keyword in lowered for keyword in ["path", "prerequisite", "evidence", "source", "how"]):
            if "path" in lowered or "prerequisite" in lowered:
                return "learning_path"
            if "evidence" in lowered or "source" in lowered:
                return "evidence_lookup"
            if "how" in lowered:
                return "task_guidance"
        return "knowledge_retrieval"

    def _sync_profile_to_kg(self, profile: LearnerProfile) -> None:
        if not self.system.kg:
            return

        for concept in profile.weak_concepts:
            try:
                self.system.kg.upsert_learner_mastery(profile.learner_id, concept, level=0.2)
            except Exception:
                continue

    def _extract_concepts(
        self,
        query: str,
        profile: LearnerProfile,
        evidence: List[Evidence],
    ) -> List[str]:
        concepts: List[str] = []
        if profile.weak_concepts:
            concepts.extend(profile.weak_concepts)

        normalized_query = query
        for char in ["，", "；", "。", ",", ";", "."]:
            normalized_query = normalized_query.replace(char, " ")
        for token in [part.strip() for part in normalized_query.split()]:
            if len(token) >= 2 and token not in concepts:
                concepts.append(token)

        for item in evidence[:3]:
            for heading in item.heading_path:
                heading = heading.strip()
                if len(heading) >= 2 and heading not in concepts:
                    concepts.append(heading)

        return concepts[:5]

    def _build_evidence_summary(self, retrieval: RetrievalBundle) -> Dict[str, object]:
        found_kinds = sorted({item.content_kind for item in retrieval.candidate_evidence})
        missing_kinds = [kind for kind in ("definition", "code", "exercise") if kind not in found_kinds]
        return {
            "published_count": len(retrieval.published_evidence),
            "candidate_count": len(retrieval.candidate_evidence),
            "content_kinds_found_in_candidates": found_kinds,
            "required_content_kinds": ["definition", "code", "exercise"],
            "missing_required_content_kinds": missing_kinds,
            "formal_evidence_is_empty": not retrieval.published_evidence,
            "note": "candidate_evidence is not published knowledge and must not be used as formal evidence before review and license confirmation.",
        }

    def _build_answer_outline(
        self,
        intent: str,
        retrieval: RetrievalBundle,
        learning_path: List[str],
    ) -> List[str]:
        outline: List[str] = []
        if intent == "learning_path" and learning_path:
            outline.append("Provide prerequisites first, then map each step to evidence.")
        elif intent == "task_guidance":
            outline.append("Explain the concept first, then give practical steps and caveats.")
        elif intent == "evidence_lookup":
            outline.append("List the source first, then quote the strongest evidence snippets.")
        else:
            outline.append("Answer the core question first, then add supporting knowledge and sources.")

        for item in retrieval.candidate_evidence[:3]:
            outline.append(f"Use evidence from {item.source_title}.")

        if learning_path:
            outline.append("Learning order: " + " -> ".join(learning_path[:5]))
        return outline

    def _build_agent_notes(
        self,
        profile: LearnerProfile,
        retrieval: RetrievalBundle,
        concepts: List[str],
        concept_id: Optional[str],
        depth: Optional[int],
    ) -> List[str]:
        notes: List[str] = []
        notes.append(f"Applied learner level filter: {profile.level}")
        notes.append(f"Published evidence count: {len(retrieval.published_evidence)}")
        notes.append(f"Candidate evidence count: {len(retrieval.candidate_evidence)}")
        if concept_id:
            notes.append(f"Applied concept filter: {concept_id}")
        if depth is not None:
            notes.append(f"Applied depth filter: {depth}")
        if profile.weak_concepts:
            notes.append("Applied weak concept boost: " + ", ".join(profile.weak_concepts[:5]))
        if concepts:
            notes.append("Candidate concepts: " + ", ".join(concepts[:5]))
        if not retrieval.published_evidence:
            notes.append("No published evidence found. Returning candidate evidence and evidence_gap only.")
        return notes
