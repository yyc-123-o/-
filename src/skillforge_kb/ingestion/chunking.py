import re

from langchain_text_splitters import RecursiveCharacterTextSplitter

HEADING = re.compile(r"(?m)(?=^#{1,6}\s)")


class PedagogicalChunker:
    def __init__(self, chunk_size: int = 900, overlap: int = 120) -> None:
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=overlap,
            separators=["\n\n", "\n", "。", ". ", " ", ""],
            length_function=len,
        )

    def split(self, text: str) -> list[str]:
        sections = [section.strip() for section in HEADING.split(text) if section.strip()]
        chunks: list[str] = []
        for section in sections or [text.strip()]:
            if section.startswith("```") and section.endswith("```") and len(section) <= 2_000:
                candidates = [section]
            else:
                candidates = self.splitter.split_text(section)
            chunks.extend(candidate for candidate in candidates if len(candidate) >= 80)
        return chunks
