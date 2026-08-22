from __future__ import annotations

import glob
import json
import os
from pathlib import Path
from typing import List

from configs_loader import load_config
from document_parser import parse_document
from hybrid_retriever import HybridIndex, Reranker
from semantic_chunker import Chunk, chunk_document, tag_difficulty_by_rule


def export_chunks_jsonl(chunks: List[Chunk], path_prefix: str) -> str:
    output_path = f"{path_prefix}_chunks.jsonl"
    with open(output_path, "w", encoding="utf-8") as fh:
        for chunk in chunks:
            record = {
                "chunk_id": chunk.chunk_id,
                "doc_id": chunk.doc_id,
                "source_title": chunk.source_title,
                "heading_path": chunk.heading_path,
                "text": chunk.text,
                "page_no": chunk.page_no,
                "domain_tag": chunk.domain_tag,
                "difficulty": chunk.difficulty,
                "token_count": chunk.token_count,
            }
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return output_path


def ingest_directory(raw_dir: str, max_tokens: int, overlap_sentences: int) -> List[Chunk]:
    all_chunks: List[Chunk] = []
    paths = sorted(glob.glob(os.path.join(raw_dir, "**", "*.*"), recursive=True))
    supported_paths = [
        path for path in paths if path.lower().endswith((".pdf", ".docx", ".md", ".markdown"))
    ]

    print(f"[rag-only] scanning raw directory: {raw_dir}")
    print(f"[rag-only] found {len(supported_paths)} supported files")

    for idx, path in enumerate(supported_paths, start=1):
        print(f"[rag-only] parsing file {idx}/{len(supported_paths)}: {path}")
        document = parse_document(path, domain_tag="ai-knowledge")
        chunks = chunk_document(
            document,
            max_tokens=max_tokens,
            overlap_sentences=overlap_sentences,
        )
        tag_difficulty_by_rule(chunks)
        all_chunks.extend(chunks)
        print(f"[rag-only] file {idx} produced {len(chunks)} chunks")

    print(f"[rag-only] processed {len(supported_paths)} files")
    print(f"[rag-only] generated {len(all_chunks)} chunks")
    return all_chunks


if __name__ == "__main__":
    print("[rag-only] loading config")
    cfg = load_config("configs/pipeline_config.yaml")
    raw_dir = cfg.get("data_raw_dir", "data/raw")
    save_prefix = cfg.get("index_save_prefix", "data/processed/index")
    Path(os.path.dirname(save_prefix)).mkdir(parents=True, exist_ok=True)

    chunks = ingest_directory(
        raw_dir=raw_dir,
        max_tokens=cfg.get("chunk_max_tokens", 400),
        overlap_sentences=cfg.get("chunk_overlap_sentences", 1),
    )
    if not chunks:
        raise ValueError("No supported documents found in data_raw_dir.")

    print(f"[rag-only] loading embedding model: {cfg['embed_model']}")
    print(f"[rag-only] embedding device: {cfg.get('device', 'cpu')}")
    index = HybridIndex(
        embed_model_name=cfg["embed_model"],
        device=cfg.get("device", "cpu"),
        use_dense=cfg.get("dense_enabled", True),
    )

    print("[rag-only] building hybrid index")
    index.build(chunks)

    print("[rag-only] saving index files")
    index.save(save_prefix)
    jsonl_path = export_chunks_jsonl(chunks, save_prefix)
    print(f"[rag-only] saved index to prefix: {save_prefix}")
    print(f"[rag-only] saved chunk jsonl: {jsonl_path}")

    reranker = None
    if cfg.get("use_reranker", True):
        print(f"[rag-only] loading reranker: {cfg['reranker_model']}")
        try:
            reranker = Reranker(
                model_name=cfg["reranker_model"],
                device=cfg.get("device", "cpu"),
            )
            print(f"[rag-only] reranker ready: {cfg['reranker_model']}")
        except Exception as exc:
            print(f"[rag-only] reranker unavailable, skip rerank: {exc}")

    demo_query = "What is the basic LoRA fine-tuning workflow?"
    print(f"[rag-only] running demo query: {demo_query}")
    results = index.search(demo_query, top_k=3)
    if reranker and results:
        print("[rag-only] reranking demo results")
        results = reranker.rerank(demo_query, results, top_k=3)

    print("[rag-only] demo results")
    for item in results:
        heading = " / ".join(item.heading_path) if item.heading_path else "<root>"
        print(
            f"[{item.retrieval_method} score={item.score:.4f}] "
            f"{item.source_title} | {heading} | {item.text[:80]}"
        )
