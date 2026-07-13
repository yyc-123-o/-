from dataclasses import dataclass

import fitz  # type: ignore[import-untyped]
import trafilatura

from skillforge_kb.domain.enums import Language


@dataclass(frozen=True)
class RawDocument:
    source_id: str
    language: Language
    text: str
    locator_prefix: str


def load_html(source_id: str, language: Language, content: bytes, url: str) -> RawDocument:
    text = trafilatura.extract(content, include_links=False, include_tables=True)
    if text is None or len(text.strip()) < 100:
        raise ValueError("HTML extraction produced insufficient content")
    return RawDocument(source_id, language, text.strip(), url)


def load_pdf(source_id: str, language: Language, content: bytes, url: str) -> list[RawDocument]:
    pages: list[RawDocument] = []
    with fitz.open(stream=content, filetype="pdf") as pdf:
        for page_number, page in enumerate(pdf, start=1):
            text = page.get_text("text").strip()
            if text:
                pages.append(RawDocument(source_id, language, text, f"{url}#page={page_number}"))
    if not pages:
        raise ValueError("PDF extraction produced no text")
    return pages
