from collections.abc import Callable
from typing import Any

import fitz
import pytest

from skillforge_kb.domain.enums import Language
from skillforge_kb.ingestion.loaders import load_html, load_pdf


def _pdf_bytes_with_text(*page_texts: str) -> bytes:
    with fitz.open() as document:
        for page_text in page_texts:
            page = document.new_page()
            page.insert_text((72, 72), page_text)
        return document.tobytes()


def _track_opened_documents(
    monkeypatch: pytest.MonkeyPatch,
) -> list[fitz.Document]:
    real_open: Callable[..., fitz.Document] = fitz.open
    opened: list[fitz.Document] = []

    def tracking_open(*args: Any, **kwargs: Any) -> fitz.Document:
        document = real_open(*args, **kwargs)
        opened.append(document)
        return document

    monkeypatch.setattr(fitz, "open", tracking_open)
    return opened


def test_pdf_loader_preserves_page_locators() -> None:
    content = _pdf_bytes_with_text(
        "Page 1 explains attention with enough content for parsing.",
        "Page 2 explains attention with enough content for parsing.",
    )

    pages = load_pdf("paper", Language.EN, content, "https://example.edu/paper.pdf")

    assert [page.locator_prefix for page in pages] == [
        "https://example.edu/paper.pdf#page=1",
        "https://example.edu/paper.pdf#page=2",
    ]


def test_html_loader_extracts_main_content() -> None:
    html = b"""
    <html><body><nav>Home About Contact</nav><main><h1>Logistic Regression</h1>
    <p>Logistic regression estimates conditional class probabilities using the sigmoid function.</p>
    <p>Its loss is binary cross entropy and its decision boundary is linear
    in the input features.</p>
    </main></body></html>
    """

    document = load_html("course", Language.EN, html, "https://example.edu/course")

    assert "conditional class probabilities" in document.text
    assert "Home About Contact" not in document.text


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"<html><body><main><p>Too short.</p></main></body></html>",
    ],
    ids=["empty", "insufficient"],
)
def test_html_loader_rejects_empty_or_insufficient_content(content: bytes) -> None:
    with pytest.raises(ValueError, match="HTML extraction produced insufficient content"):
        load_html("course", Language.EN, content, "https://example.edu/course")


def test_html_loader_rejects_long_plain_text_without_html_structure() -> None:
    malformed_content = b"</html>" + (
        b"Logistic regression estimates conditional class probabilities with a sigmoid function. "
        b"Binary cross entropy measures the prediction error for a labeled training example. "
        b"The resulting decision boundary is linear in the model input features."
    )

    with pytest.raises(ValueError, match="HTML extraction produced insufficient content"):
        load_html("course", Language.EN, malformed_content, "https://example.edu/course")


def test_pdf_loader_rejects_document_without_text_and_closes_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with fitz.open() as document:
        document.new_page()
        content = document.tobytes()
    opened = _track_opened_documents(monkeypatch)

    with pytest.raises(ValueError, match="PDF extraction produced no text"):
        load_pdf("paper", Language.EN, content, "https://example.edu/paper.pdf")

    assert len(opened) == 1
    assert opened[0].is_closed


def test_pdf_loader_rejects_malformed_pdf() -> None:
    with pytest.raises(fitz.FileDataError):
        load_pdf(
            "paper",
            Language.EN,
            b"not a PDF document",
            "https://example.edu/paper.pdf",
        )


def test_pdf_loader_closes_document_after_success(monkeypatch: pytest.MonkeyPatch) -> None:
    content = _pdf_bytes_with_text("A page with extractable text.")
    opened = _track_opened_documents(monkeypatch)

    load_pdf("paper", Language.EN, content, "https://example.edu/paper.pdf")

    assert len(opened) == 1
    assert opened[0].is_closed
