from skillforge_kb.domain.models import SourceRecord


class InMemorySourceRepository:
    def __init__(self) -> None:
        self._sources: dict[str, SourceRecord] = {}

    def get(self, source_id: str) -> SourceRecord | None:
        return self._sources.get(source_id)

    def save(self, source: SourceRecord) -> None:
        self._sources[source.source_id] = source

    def list_all(self) -> list[SourceRecord]:
        return sorted(self._sources.values(), key=lambda item: item.source_id)
