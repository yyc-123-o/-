from collections.abc import Iterator

import httpx
import pytest
import respx

from skillforge_kb.ingestion.fetch import FetchedResource, SourceFetcher


class GuardedStream(httpx.SyncByteStream):
    def __init__(self) -> None:
        self.chunks_read = 0
        self.closed = False

    def __iter__(self) -> Iterator[bytes]:
        for chunk in (b"x" * 700, b"y" * 700):
            self.chunks_read += 1
            yield chunk
        raise AssertionError("fetcher read beyond the size limit")

    def close(self) -> None:
        self.closed = True


@respx.mock
def test_fetch_rejects_redirect_to_unregistered_host() -> None:
    respx.get("https://allowed.example/doc").mock(
        return_value=httpx.Response(
            302,
            headers={"location": "https://blocked.example/doc"},
        )
    )
    fetcher = SourceFetcher(allowed_hosts={"allowed.example"}, max_bytes=1024)

    with pytest.raises(ValueError, match="redirect host"):
        fetcher.fetch("https://allowed.example/doc")


@respx.mock
def test_fetch_rejects_oversized_response() -> None:
    respx.get("https://allowed.example/doc").mock(
        return_value=httpx.Response(200, content=b"x" * 2048)
    )
    fetcher = SourceFetcher(allowed_hosts={"allowed.example"}, max_bytes=1024)

    with pytest.raises(ValueError, match="size limit"):
        fetcher.fetch("https://allowed.example/doc")


@respx.mock
def test_fetch_stops_streaming_and_closes_response_at_size_limit() -> None:
    stream = GuardedStream()
    respx.get("https://allowed.example/doc").mock(
        return_value=httpx.Response(
            200,
            headers={"content-type": "text/html"},
            stream=stream,
        )
    )
    fetcher = SourceFetcher(allowed_hosts={"allowed.example"}, max_bytes=1024)

    with pytest.raises(ValueError, match="size limit"):
        fetcher.fetch("https://allowed.example/doc")

    assert stream.chunks_read == 2
    assert stream.closed


@respx.mock
def test_fetch_follows_allowed_redirect_and_returns_resource() -> None:
    respx.get("https://allowed.example/doc").mock(
        return_value=httpx.Response(302, headers={"location": "/final"})
    )
    respx.get("https://allowed.example/final").mock(
        return_value=httpx.Response(
            200,
            content=b"<main>governed content</main>",
            headers={"content-type": "text/html; charset=utf-8"},
        )
    )
    fetcher = SourceFetcher(allowed_hosts={"ALLOWED.EXAMPLE"}, max_bytes=1024)

    resource = fetcher.fetch("https://allowed.example/doc")

    assert resource == FetchedResource(
        body=b"<main>governed content</main>",
        final_url="https://allowed.example/final",
        content_type="text/html",
    )


@respx.mock
def test_fetch_rejects_unsupported_content_type() -> None:
    respx.get("https://allowed.example/doc").mock(
        return_value=httpx.Response(
            200,
            content=b"plain text",
            headers={"content-type": "text/plain"},
        )
    )
    fetcher = SourceFetcher(allowed_hosts={"allowed.example"})

    with pytest.raises(ValueError, match="unsupported content type: text/plain"):
        fetcher.fetch("https://allowed.example/doc")


@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("http://allowed.example/doc", "must use HTTPS"),
        ("https://blocked.example/doc", "source host"),
    ],
)
def test_fetch_rejects_ungoverned_source_urls(url: str, message: str) -> None:
    fetcher = SourceFetcher(allowed_hosts={"allowed.example"})

    with pytest.raises(ValueError, match=message):
        fetcher.fetch(url)
