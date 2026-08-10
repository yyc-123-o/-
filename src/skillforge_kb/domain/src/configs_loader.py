from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

try:
    import yaml
except ModuleNotFoundError:
    yaml = None


DEFAULT_CONFIG: Dict[str, Any] = {
    "embed_model": "BAAI/bge-large-zh-v1.5",
    "reranker_model": "BAAI/bge-reranker-large",
    "device": "cpu",
    "use_reranker": True,
    "chunk_max_tokens": 400,
    "chunk_overlap_sentences": 1,
    "llm_api_base": "http://127.0.0.1:8000",
    "llm_model": "qwen2.5-7b-instruct",
    "neo4j_uri": "bolt://127.0.0.1:7687",
    "neo4j_user": "neo4j",
    "neo4j_password": "please_change_me",
    "data_raw_dir": "data/raw",
    "index_save_prefix": "data/processed/index",
}


def load_config(config_path: str) -> Dict[str, Any]:
    path = Path(config_path)
    if yaml is None or not path.exists():
        return dict(DEFAULT_CONFIG)

    with path.open("r", encoding="utf-8") as fh:
        loaded = yaml.safe_load(fh) or {}

    cfg = dict(DEFAULT_CONFIG)
    cfg.update(loaded)
    return cfg
