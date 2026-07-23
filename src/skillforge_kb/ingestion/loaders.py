from dataclasses import dataclass
from html.parser import HTMLParser

import fitz  # type: ignore[import-untyped]
import trafilatura

from skillforge_kb.domain.enums import Language


class _HTMLStructureParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.has_element = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.has_element = True

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.has_element = True


def _has_html_structure(content: bytes) -> bool:
    parser = _HTMLStructureParser()
    parser.feed(content.decode("utf-8", errors="replace"))
    parser.close()
    return parser.has_element


@dataclass(frozen=True)
class RawDocument:
    source_id: str
    language: Language
    text: str
    locator_prefix: str


def load_html(source_id: str, language: Language, content: bytes, url: str) -> RawDocument:
    if not _has_html_structure(content):
        raise ValueError("HTML extraction produced insufficient content")
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
