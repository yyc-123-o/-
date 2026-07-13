import re

from langchain_text_splitters import RecursiveCharacterTextSplitter

HEADING = re.compile(r"(?m)(?=^#{1,6}\s)")


def _split_sections(text: str) -> list[str]:
    boundaries = [0]
    in_fence = False
    offset = 0
    for line in text.splitlines(keepends=True):
        if line.startswith("```"):
            in_fence = not in_fence
        elif not in_fence and offset and HEADING.match(line):
            boundaries.append(offset)
        offset += len(line)
    boundaries.append(len(text))

    sections: list[str] = []
    for start, end in zip(boundaries, boundaries[1:], strict=False):
        section = text[start:end].strip()
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
            if section.startswith("```") and section.endswith("```") and len(section) <= 2_000:
                candidates = [section]
            else:
                candidates = self.splitter.split_text(section)
            chunks.extend(candidate for candidate in candidates if len(candidate) >= 80)
        return chunks
