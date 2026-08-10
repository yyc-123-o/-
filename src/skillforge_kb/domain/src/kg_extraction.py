from __future__ import annotations

import json
import re
from typing import List

import requests

from kg_schema_neo4j import Triple
from semantic_chunker import Chunk

ALLOWED_RELATIONS = [
    "PREREQUISITE_OF",
    "PART_OF",
    "IMPLEMENTS",
    "USES_TOOL",
    "APPLIES_TO",
    "REQUIRES_SKILL",
]
ALLOWED_LABELS = ["Concept", "Skill", "Algorithm", "Model", "Tool", "Task", "Course"]
EXTRACTION_PROMPT_TEMPLATE = """你是人工智能领域知识图谱抽取专家。请从下面的教学或技术文本中抽取结构化三元组。
要求：
1. 实体类型只能从以下集合中选择: {labels}
2. 关系类型只能从以下集合中选择: {relations}
3. 只抽取文本中明确表达的关系，不要推测
4. 严格输出 JSON，不要输出任何额外说明

{{"triples": [{{"head": "实体名", "head_label": "类型", "relation": "关系", "tail": "实体名", "tail_label": "类型"}}]}}

文本：
{text}
"""
SYNONYM_MAP = {
    "低秩适配": "LoRA",
    "Low-Rank Adaptation": "LoRA",
    "检索增强生成": "RAG",
    "向量检索": "Dense Retrieval",
    "BGE向量模型": "BGE",
}


def _call_llm(prompt: str, api_base: str, model_name: str) -> str:
    response = requests.post(
        f"{api_base.rstrip('/')}/v1/chat/completions",
        json={
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": 800,
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def _safe_parse_json(raw: str) -> dict:
    text = raw.strip()
    text = re.sub(r"^```json\s*|```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return {"triples": []}


def normalize_entity(name: str) -> str:
    normalized = SYNONYM_MAP.get(name.strip(), name.strip())
    return re.sub(r"\s+", " ", normalized).strip()


def _is_valid_entity(name: str) -> bool:
    if not name or len(name) < 2:
        return False
    if name in {"该方法", "该模型", "这个工具", "这种方式"}:
        return False
    return True


def extract_triples_from_chunk(chunk: Chunk, api_base: str, model_name: str) -> List[Triple]:
    prompt = EXTRACTION_PROMPT_TEMPLATE.format(
        labels=", ".join(ALLOWED_LABELS),
        relations=", ".join(ALLOWED_RELATIONS),
        text=chunk.text,
    )
    raw = _call_llm(prompt, api_base=api_base, model_name=model_name)
    parsed = _safe_parse_json(raw)

    triples: List[Triple] = []
    seen = set()
    for item in parsed.get("triples", []):
        relation = item.get("relation")
        head_label = item.get("head_label")
        tail_label = item.get("tail_label")
        head = normalize_entity(item.get("head", ""))
        tail = normalize_entity(item.get("tail", ""))

        if relation not in ALLOWED_RELATIONS:
            continue
        if head_label not in ALLOWED_LABELS or tail_label not in ALLOWED_LABELS:
            continue
        if not _is_valid_entity(head) or not _is_valid_entity(tail) or head == tail:
            continue

        key = (head, relation, tail)
        if key in seen:
            continue
        seen.add(key)
        triples.append(
            Triple(
                head=head,
                head_label=head_label,
                relation=relation,
                tail=tail,
                tail_label=tail_label,
            )
        )
    return triples


def extract_and_normalize(chunk: Chunk, api_base: str, model_name: str) -> List[Triple]:
    return extract_triples_from_chunk(chunk, api_base=api_base, model_name=model_name)
