from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import List

from document_parser import DocBlock, ParsedDocument

SENT_SPLIT_PATTERN = re.compile(r"(?<=[。！？；\n])")
ADVANCED_KEYWORDS = ["证明", "推导", "复杂度", "梯度", "海森", "收敛", "分布式训练", "CUDA"]
BASIC_KEYWORDS = ["简介", "概念", "定义", "举例", "入门", "什么是"]


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    source_id: str
    source_title: str
    source_path: str
    heading_path: List[str]
    text: str
    page_no: int | None = None
    domain_tag: str | None = None
    difficulty: str | None = None
    token_count: int = 0
    content_kind: str = "definition"
    review_status: str = "unreviewed"
    license_status: str = "unregistered"


def _split_sentences(text: str) -> List[str]:
    return [part for part in SENT_SPLIT_PATTERN.split(text) if part.strip()]


def _estimate_tokens(text: str) -> int:
    return len(text)


def _group_blocks(blocks: List[DocBlock]) -> List[List[DocBlock]]:
    groups: List[List[DocBlock]] = []
    for block in blocks:
        if groups and groups[-1][-1].heading_path == block.heading_path:
            groups[-1].append(block)
        else:
            groups.append([block])
    return groups


def _classify_content_kind(source_path: str, heading_path: List[str], text: str) -> str:
    joined = " ".join(heading_path).lower()
    lowered = text.lower()
    path_name = os.path.basename(source_path).lower()
    if any(token in path_name for token in ("task", "exercise", "练习", "习题", "作业")):
        return "exercise"
    if any(token in joined or token in lowered for token in ("练习", "习题", "作业", "exercise")):
        return "exercise"
    if any(token in path_name for token in ("workflow", "pipeline", "project", "experiment", "实训", "实践")):
        return "code"
    if any(token in lowered for token in ("```", "python", "代码", "运行", "命令", "安装")):
        return "code"
    return "definition"


def _append_chunk(
    chunks: List[Chunk],
    doc: ParsedDocument,
    source_id: str,
    heading_path: List[str],
    text: str,
    page_no: int | None,
    domain_tag: str | None,
    content_kind: str,
) -> None:
    clean = text.strip()
    if not clean:
        return
    chunks.append(
        Chunk(
            chunk_id=f"{doc.doc_id}-c{len(chunks)}",
            doc_id=doc.doc_id,
            source_id=source_id,
            source_title=doc.title,
            source_path=doc.source_path,
            heading_path=heading_path,
            text=clean,
            page_no=page_no,
            domain_tag=domain_tag,
            token_count=_estimate_tokens(clean),
            content_kind=content_kind,
        )
    )


def chunk_document(doc: ParsedDocument, max_tokens: int = 400, overlap_sentences: int = 1) -> List[Chunk]:
    chunks: List[Chunk] = []
    source_id = doc.source_path.replace("\\", "/")

    for group in _group_blocks(doc.blocks):
        merged_text = " ".join(block.text for block in group).strip()
        if not merged_text:
            continue
        heading_path = group[0].heading_path
        page_no = group[0].page_no
        domain_tag = group[0].domain_tag
        content_kind = _classify_content_kind(doc.source_path, heading_path, merged_text)

        if _estimate_tokens(merged_text) <= max_tokens:
            _append_chunk(chunks, doc, source_id, heading_path, merged_text, page_no, domain_tag, content_kind)
            continue

        sentences = _split_sentences(merged_text)
        buffer: List[str] = []
        buffer_len = 0
        index = 0
        while index < len(sentences):
            sentence = sentences[index]
            sentence_len = len(sentence)
            if buffer and buffer_len + sentence_len > max_tokens:
                _append_chunk(chunks, doc, source_id, heading_path, "".join(buffer), page_no, domain_tag, content_kind)
                overlap = buffer[-overlap_sentences:] if overlap_sentences else []
                if overlap and len(overlap[0]) + sentence_len > max_tokens:
                    overlap = []
                buffer = overlap
                buffer_len = sum(len(item) for item in buffer)
                continue
            if not buffer and sentence_len > max_tokens:
                _append_chunk(chunks, doc, source_id, heading_path, sentence, page_no, domain_tag, content_kind)
                index += 1
                continue
            buffer.append(sentence)
            buffer_len += sentence_len
            index += 1
        if buffer:
            _append_chunk(chunks, doc, source_id, heading_path, "".join(buffer), page_no, domain_tag, content_kind)

    return chunks


def tag_difficulty_by_rule(chunks: List[Chunk]) -> None:
    for chunk in chunks:
        if any(keyword in chunk.text for keyword in ADVANCED_KEYWORDS):
            chunk.difficulty = "advanced"
        elif any(keyword in chunk.text for keyword in BASIC_KEYWORDS):
            chunk.difficulty = "beginner"
        else:
            chunk.difficulty = "intermediate"
