from __future__ import annotations

import glob
import os
from pathlib import Path
from typing import Dict, List, Optional

from configs_loader import load_config
from document_parser import parse_document
from hybrid_retriever import Evidence, HybridIndex, RetrievalBundle, Reranker
from kg_extraction import extract_and_normalize
from kg_schema_neo4j import KGBuilder
from semantic_chunker import Chunk, chunk_document, tag_difficulty_by_rule


class DomainKnowledgeSystem:
    def __init__(self, config_path: str = "configs/pipeline_config.yaml"):
        self.cfg = load_config(config_path)
        self.index = HybridIndex(
            embed_model_name=self.cfg["embed_model"],
            device=self.cfg["device"],
            use_dense=self.cfg.get("dense_enabled", True),
        )
        self.reranker: Optional[Reranker] = None
        self.kg: Optional[KGBuilder] = None
        self.all_chunks: List[Chunk] = []

    def ingest_directory(self, raw_dir: str, domain_tag: str = "人工智能/大模型") -> None:
        paths = sorted(glob.glob(os.path.join(raw_dir, "**", "*.*"), recursive=True))
        supported_paths = [
            path for path in paths if path.lower().endswith((".pdf", ".docx", ".md", ".markdown"))
        ]

        for path in supported_paths:
            document = parse_document(path, domain_tag=domain_tag)
            chunks = chunk_document(
                document,
                max_tokens=self.cfg["chunk_max_tokens"],
                overlap_sentences=self.cfg.get("chunk_overlap_sentences", 1),
            )
            tag_difficulty_by_rule(chunks)
            self.all_chunks.extend(chunks)

        print(f"[ingest] processed {len(supported_paths)} files, generated {len(self.all_chunks)} chunks")

    def build_kg(self) -> None:
        if not self.all_chunks:
            raise ValueError("No chunks found. Run ingest_directory() first.")

        self.kg = KGBuilder(
            self.cfg["neo4j_uri"],
            self.cfg["neo4j_user"],
            self.cfg["neo4j_password"],
        )
        self.kg.init_schema()

        for chunk in self.all_chunks:
            triples = extract_and_normalize(
                chunk,
                api_base=self.cfg["llm_api_base"],
                model_name=self.cfg["llm_model"],
            )
            for triple in triples:
                self.kg.upsert_triple(triple)
                for entity_name, entity_label in ((triple.head, triple.head_label), (triple.tail, triple.tail_label)):
                    if entity_label == "Concept":
                        self.kg.link_concept_to_chunk(
                            entity_name,
                            chunk.chunk_id,
                            chunk.source_title,
                            chunk.page_no,
                        )

        print("[kg] graph build completed")

    def build_index(self, save_prefix: Optional[str] = None) -> None:
        if not self.all_chunks:
            raise ValueError("No chunks found. Run ingest_directory() first.")

        self.index.build(self.all_chunks)
        if self.cfg.get("use_reranker", True):
            self.reranker = Reranker(
                model_name=self.cfg["reranker_model"],
                device=self.cfg["device"],
            )
        if save_prefix:
            self.index.save(save_prefix)

        print(f"[index] hybrid index built for {len(self.all_chunks)} chunks")

    def load_index(self, load_prefix: str) -> None:
        self.index.load(load_prefix)
        if self.cfg.get("use_reranker", True):
            self.reranker = Reranker(
                model_name=self.cfg["reranker_model"],
                device=self.cfg["device"],
            )
        self.kg = KGBuilder(
            self.cfg["neo4j_uri"],
            self.cfg["neo4j_user"],
            self.cfg["neo4j_password"],
        )

    def _promote_published(self, evidences: List[Evidence]) -> List[Evidence]:
        published: List[Evidence] = []
        for evidence in evidences:
            if evidence.review_status == "reviewed" and evidence.license_status == "approved":
                evidence.evidence_status = "published"
                published.append(evidence)
        return published

    def retrieve(
        self,
        query: str,
        learner_id: Optional[str] = None,
        top_k: int = 5,
        difficulty_filter: Optional[str] = None,
        concept_id: Optional[str] = None,
        depth: Optional[int] = None,
    ) -> RetrievalBundle:
        learner_mastery = None
        if learner_id and self.kg:
            try:
                weak_concepts = self.kg.get_weak_concepts(learner_id)
                learner_mastery = {concept: 0.2 for concept in weak_concepts}
            except Exception:
                learner_mastery = None

        candidates = self.index.search(
            query,
            top_k=top_k * 4,
            learner_mastery=learner_mastery,
            difficulty_filter=difficulty_filter,
            concept_id=concept_id,
            depth=depth,
        )
        if self.reranker:
            candidates = self.reranker.rerank(query, candidates, top_k=top_k * 4)

        published = self._promote_published(candidates)
        top_candidates = candidates[:top_k]

        found_kinds = {evidence.content_kind for evidence in top_candidates}
        evidence_gap: Dict[str, str] = {}
        for kind in ("definition", "code", "exercise"):
            if kind not in found_kinds:
                evidence_gap[kind] = f"No {kind} candidate was found for this query/concept/depth."
        if not published:
            evidence_gap["formal_evidence"] = (
                "No evidence was promoted from candidate_only to published evidence. "
                "Candidate fragments must be reviewed and licensed before publication."
            )

        return RetrievalBundle(
            published_evidence=published[:top_k],
            candidate_evidence=top_candidates,
            evidence_gap=evidence_gap,
        )

    def kg_query_learning_path(self, target_concept: str) -> List[str]:
        if not self.kg:
            raise ValueError("KG has not been initialized.")
        return self.kg.get_learning_path(target_concept)

    def kg_query_evidence(self, concept_name: str) -> List[dict]:
        if not self.kg:
            raise ValueError("KG has not been initialized.")
        return self.kg.get_evidence_chunks(concept_name)


if __name__ == "__main__":
    system = DomainKnowledgeSystem()
    raw_dir = system.cfg.get("data_raw_dir", "data/raw")
    save_prefix = system.cfg.get("index_save_prefix", "data/processed/index")
    Path(os.path.dirname(save_prefix)).mkdir(parents=True, exist_ok=True)

    system.ingest_directory(raw_dir)
    system.build_kg()
    system.build_index(save_prefix=save_prefix)

    examples = system.retrieve("如何使用 LoRA 微调 Qwen2.5-7B 完成角色扮演任务", top_k=3)
    for evidence in examples.candidate_evidence:
        heading = " / ".join(evidence.heading_path) if evidence.heading_path else "未分类"
        print(
            f"[{evidence.retrieval_method} score={evidence.score:.3f}] "
            f"{evidence.source_title} | {heading} | {evidence.text[:80]}"
        )
