import re

from langchain_text_splitters import RecursiveCharacterTextSplitter

HEADING = re.compile(r"(?m)(?=^#{1,6}\s)")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")


def _fence_marker(line: str) -> tuple[str, int, str] | None:
    match = FENCE.match(line.rstrip("\r\n"))
    if match is None:
        return None
    delimiter = match.group(1)
    return delimiter[0], len(delimiter), match.group(2)


def _scan_structure(text: str) -> tuple[list[int], list[tuple[int, int]]]:
    boundaries = [0]
    fenced_spans: list[tuple[int, int]] = []
    active_fence: tuple[str, int, int] | None = None
    offset = 0
    for line in text.splitlines(keepends=True):
        marker = _fence_marker(line)
        if active_fence is None:
            if marker is not None:
                active_fence = marker[0], marker[1], offset
            elif offset and HEADING.match(line):
                boundaries.append(offset)
        elif marker is not None:
            delimiter, length, remainder = marker
            active_delimiter, active_length, start = active_fence
            if (
                delimiter == active_delimiter
                and length >= active_length
                and not remainder.strip()
            ):
                fenced_spans.append((start, offset + len(line)))
                active_fence = None
        offset += len(line)
    boundaries.append(len(text))
    return boundaries, fenced_spans


def _is_complete_fence(text: str) -> bool:
    _, fenced_spans = _scan_structure(text)
    return fenced_spans == [(0, len(text))]


def _split_sections(text: str) -> list[str]:
    boundaries, _ = _scan_structure(text)

    sections: list[str] = []
    for start, end in zip(boundaries, boundaries[1:], strict=False):
        raw_section = text[start:end]
        section = raw_section if _is_complete_fence(raw_section) else raw_section.strip()
        if section:
            sections.append(section)
    return sections


class PedagogicalChunker:
    def __init__(self, chunk_size: int = 900, overlap: int = 120) -> None:
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=overlap,
            separators=["\n\n", "\n", "。", ". ", " ", ""],
            length_function=len,
        )

    def split(self, text: str) -> list[str]:
        sections = _split_sections(text)
        chunks: list[str] = []
        for section in sections or [text.strip()]:
            if _is_complete_fence(section) and len(section) <= 2_000:
                candidates = [section]
            else:
                candidates = self.splitter.split_text(section)
            chunks.extend(candidate for candidate in candidates if len(candidate) >= 80)
        return chunks
