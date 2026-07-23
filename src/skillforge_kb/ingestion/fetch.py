from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx

ACCEPTED_TYPES = {"text/html", "application/xhtml+xml", "application/pdf"}


@dataclass(frozen=True)
class FetchedResource:
    body: bytes
    final_url: str
    content_type: str


class SourceFetcher:
    def __init__(
        self,
        allowed_hosts: set[str],
        max_bytes: int = 20_000_000,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.allowed_hosts = {host.casefold() for host in allowed_hosts}
        self.max_bytes = max_bytes
        self.timeout_seconds = timeout_seconds

    def _validate_url(self, url: str, redirect: bool = False) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https":
            raise ValueError("source URL must use HTTPS")
        if parsed.hostname is None or parsed.hostname.casefold() not in self.allowed_hosts:
            label = "redirect host" if redirect else "source host"
            raise ValueError(f"{label} is not registered")

    def fetch(self, url: str) -> FetchedResource:
        current = url
        self._validate_url(current)
        with httpx.Client(timeout=self.timeout_seconds, follow_redirects=False) as client:
            for redirect_count in range(4):
                with client.stream("GET", current) as response:
                    if response.is_redirect:
                        if redirect_count == 3:
                            raise ValueError("redirect limit exceeded")
                        location = response.headers.get("location")
                        if location is None:
                            raise ValueError("redirect missing location")
                        current = urljoin(current, location)
                        self._validate_url(current, redirect=True)
                        continue

                    response.raise_for_status()
                    declared = response.headers.get("content-length")
                    if declared is not None and int(declared) > self.max_bytes:
                        raise ValueError("response exceeds size limit")

                    body = bytearray()
                    for chunk in response.iter_bytes():
                        if len(body) + len(chunk) > self.max_bytes:
                            raise ValueError("response exceeds size limit")
                        body.extend(chunk)

                    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
                    if content_type not in ACCEPTED_TYPES:
                        raise ValueError(f"unsupported content type: {content_type}")
                    return FetchedResource(bytes(body), str(response.url), content_type)
        raise ValueError("redirect loop did not terminate")
