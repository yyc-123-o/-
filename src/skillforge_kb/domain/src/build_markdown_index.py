from __future__ import annotations

import argparse
import glob
import json
import os
from pathlib import Path

from configs_loader import load_config
from document_parser import parse_document
from hybrid_retriever import HybridIndex
from semantic_chunker import chunk_document, tag_difficulty_by_rule


def main() -> None:
    print("[markdown-index] start", flush=True)
    parser = argparse.ArgumentParser(description="Build a runnable BM25 index from Markdown knowledge sources.")
    parser.add_argument("--raw-dir", default=None)
    parser.add_argument("--output-prefix", default=None)
    args = parser.parse_args()

    cfg = load_config("configs/pipeline_config.yaml")
    raw_dir = args.raw_dir or cfg.get("data_raw_dir", "data/raw")
    output_prefix = args.output_prefix or cfg.get("index_save_prefix", "data/processed/index")
    paths = sorted(glob.glob(os.path.join(raw_dir, "**", "*.md"), recursive=True))
    print(f"[markdown-index] markdown files: {len(paths)}", flush=True)

    chunks = []
    for path in paths:
        print(f"[markdown-index] parsing {path}", flush=True)
        document = parse_document(path, domain_tag="ai-knowledge")
        file_chunks = chunk_document(
            document,
            max_tokens=cfg.get("chunk_max_tokens", 400),
            overlap_sentences=cfg.get("chunk_overlap_sentences", 1),
        )
        tag_difficulty_by_rule(file_chunks)
        chunks.extend(file_chunks)

    if not chunks:
        raise RuntimeError("No Markdown chunks were generated.")
    print(f"[markdown-index] chunks: {len(chunks)}", flush=True)

    index = HybridIndex(
        embed_model_name=cfg["embed_model"],
        device=cfg.get("device", "cpu"),
        use_dense=False,
    )
    index.build(chunks)
    Path(os.path.dirname(output_prefix)).mkdir(parents=True, exist_ok=True)
    index.save(output_prefix)
    with open(f"{output_prefix}_chunks.jsonl", "w", encoding="utf-8") as fh:
        for chunk in chunks:
            fh.write(json.dumps(chunk.__dict__, ensure_ascii=False) + "\n")
    print(json.dumps({"files": len(paths), "chunks": len(chunks), "output_prefix": output_prefix}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
