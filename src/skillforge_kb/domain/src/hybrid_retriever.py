from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import faiss
import jieba
import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

from semantic_chunker import Chunk

BGE_MODEL_NAME = "BAAI/bge-large-zh-v1.5"
BGE_QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："


@dataclass
class Evidence:
    chunk_id: str
    source_id: str
    text: str
    source_title: str
    heading_path: List[str]
    page_no: Optional[int]
    difficulty: Optional[str]
    score: float
    retrieval_method: str
    concept_id: Optional[str] = None
    depth: Optional[int] = None
    content_kind: str = "definition"
    review_status: str = "unreviewed"
    license_status: str = "unregistered"
    code_location: Optional[str] = None
    evidence_status: str = "candidate_only"


@dataclass
class RetrievalBundle:
    published_evidence: List[Evidence]
    candidate_evidence: List[Evidence]
    evidence_gap: Dict[str, str]


def _tokenize_zh(text: str) -> List[str]:
    return [token for token in jieba.lcut(text) if token.strip()]


class HybridIndex:
    def __init__(self, embed_model_name: str = BGE_MODEL_NAME, device: str = "cpu", use_dense: bool = True):
        self.embed_model_name = embed_model_name
        self.device = device
        self.use_dense = use_dense
        self.embed_model: Optional[SentenceTransformer] = None
        self.chunks: List[Chunk] = []
        self.bm25: Optional[BM25Okapi] = None
        self.faiss_index: Optional[faiss.Index] = None
        self.dense_error: Optional[str] = None

    def _ensure_dense_model(self) -> bool:
        if not self.use_dense:
            return False
        if self.embed_model is not None:
            return True
        try:
            self.embed_model = SentenceTransformer(self.embed_model_name, device=self.device)
            return True
        except Exception as exc:
            self.dense_error = f"{type(exc).__name__}: {exc}"
            self.use_dense = False
            return False

    def build(self, chunks: List[Chunk]) -> None:
        if not chunks:
            raise ValueError("No chunks available to build the index.")

        self.chunks = chunks
        texts = [chunk.text for chunk in chunks]
        self.bm25 = BM25Okapi([_tokenize_zh(text) for text in texts])

        if not self._ensure_dense_model():
            return
        embeddings = self.embed_model.encode(
            texts,
            batch_size=32,
            normalize_embeddings=True,
            show_progress_bar=True,
        )
        embeddings = np.asarray(embeddings, dtype="float32")
        self.faiss_index = faiss.IndexFlatIP(embeddings.shape[1])
        self.faiss_index.add(embeddings)

    def save(self, path_prefix: str) -> None:
        prefix = Path(path_prefix)
        prefix.parent.mkdir(parents=True, exist_ok=True)
        with open(f"{path_prefix}_chunks.pkl", "wb") as fh:
            pickle.dump(self.chunks, fh)
        with open(f"{path_prefix}_bm25.pkl", "wb") as fh:
            pickle.dump(self.bm25, fh)
        if self.faiss_index is not None:
            faiss.write_index(self.faiss_index, f"{path_prefix}_faiss.index")

    def load(self, path_prefix: str) -> None:
        with open(f"{path_prefix}_chunks.pkl", "rb") as fh:
            self.chunks = pickle.load(fh)
        with open(f"{path_prefix}_bm25.pkl", "rb") as fh:
            self.bm25 = pickle.load(fh)
        faiss_path = Path(f"{path_prefix}_faiss.index")
        if self.use_dense and faiss_path.exists():
            self.faiss_index = faiss.read_index(str(faiss_path))

    def _bm25_search(self, query: str, top_k: int) -> List[Tuple[int, float]]:
        scores = self.bm25.get_scores(_tokenize_zh(query))
        order = np.argsort(scores)[::-1][:top_k]
        return [(int(i), float(scores[i])) for i in order if scores[i] > 0]

    def _dense_search(self, query: str, top_k: int) -> List[Tuple[int, float]]:
        if self.faiss_index is None or not self._ensure_dense_model():
            return []
        query_embedding = self.embed_model.encode(
            [f"{BGE_QUERY_INSTRUCTION}{query}"],
            normalize_embeddings=True,
        )
        scores, indices = self.faiss_index.search(np.asarray(query_embedding, dtype="float32"), top_k)
        return [(int(i), float(s)) for i, s in zip(indices[0], scores[0]) if i != -1]

    def _rrf_fuse(self, bm25_results: List[Tuple[int, float]], dense_results: List[Tuple[int, float]], k: int = 60) -> List[Tuple[int, float]]:
        fused: Dict[int, float] = {}
        for rank, (idx, _) in enumerate(bm25_results, start=1):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (k + rank)
        for rank, (idx, _) in enumerate(dense_results, start=1):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (k + rank)
        return sorted(fused.items(), key=lambda item: item[1], reverse=True)

    def _to_evidence(self, chunk: Chunk, score: float, retrieval_method: str, concept_id: Optional[str], depth: Optional[int]) -> Evidence:
        return Evidence(
            chunk_id=chunk.chunk_id,
            source_id=chunk.source_id,
            text=chunk.text,
            source_title=chunk.source_title,
            heading_path=chunk.heading_path,
            page_no=chunk.page_no,
            difficulty=chunk.difficulty,
            score=score,
            retrieval_method=retrieval_method,
            concept_id=concept_id,
            depth=depth,
            content_kind=chunk.content_kind,
            review_status=chunk.review_status,
            license_status=chunk.license_status,
            code_location=f"{chunk.source_id}#{chunk.chunk_id}",
            evidence_status="candidate_only",
        )

    def search(self, query: str, top_k: int = 5, recall_k: int = 30, learner_mastery: Optional[Dict[str, float]] = None, difficulty_filter: Optional[str] = None, concept_id: Optional[str] = None, depth: Optional[int] = None) -> List[Evidence]:
        bm25_results = self._bm25_search(query, recall_k)
        dense_results = self._dense_search(query, recall_k)
        if dense_results:
            fused = self._rrf_fuse(bm25_results, dense_results)[:recall_k]
            retrieval_method = "fused"
        else:
            fused = bm25_results[:recall_k]
            retrieval_method = "bm25_fallback"

        evidences: List[Evidence] = []
        for idx, score in fused:
            chunk = self.chunks[idx]
            if difficulty_filter and chunk.difficulty != difficulty_filter:
                continue
            evidences.append(self._to_evidence(chunk, score, retrieval_method, concept_id, depth))

        if learner_mastery:
            for evidence in evidences:
                for concept, level in learner_mastery.items():
                    if concept in evidence.text or any(concept in heading for heading in evidence.heading_path):
                        evidence.score += (1 - level) * 0.1
            evidences.sort(key=lambda item: item.score, reverse=True)
        return evidences[:top_k]


class Reranker:
    def __init__(self, model_name: str = "BAAI/bge-reranker-large", device: str = "cpu"):
        from FlagEmbedding import FlagReranker
        self.reranker = FlagReranker(model_name, use_fp16=device != "cpu", device=device)

    def rerank(self, query: str, evidences: List[Evidence], top_k: int = 5) -> List[Evidence]:
        if not evidences:
            return []
        pairs = [[query, evidence.text] for evidence in evidences]
        scores = self.reranker.compute_score(pairs, normalize=True)
        if isinstance(scores, float):
            scores = [scores]
        for evidence, score in zip(evidences, scores):
            evidence.score = float(score)
            evidence.retrieval_method = "reranked"
        evidences.sort(key=lambda item: item.score, reverse=True)
        return evidences[:top_k]
