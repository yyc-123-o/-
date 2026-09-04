"""Small durable store for learner-facing platform preferences."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

Theme = Literal["light", "dark", "system"]


class LearnerPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reminders_enabled: bool = True
    theme: Theme = "light"
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class LearnerPreferencesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reminders_enabled: bool
    theme: Theme


class PreferencesStore(Protocol):
    def get(self, learner_id: str) -> LearnerPreferences: ...

    def update(self, learner_id: str, update: LearnerPreferencesUpdate) -> LearnerPreferences: ...


class JsonPreferencesStore:
    """Persist preferences without coupling them to the learning run schema."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    def _read(self) -> dict[str, dict[str, object]]:
        try:
            value = json.loads(self._path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def _write(self, value: dict[str, dict[str, object]]) -> None:
        temporary = self._path.with_suffix(self._path.suffix + ".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self._path)

    def get(self, learner_id: str) -> LearnerPreferences:
        with self._lock:
            raw = self._read().get(learner_id)
            return LearnerPreferences.model_validate(raw) if raw else LearnerPreferences()

    def update(self, learner_id: str, update: LearnerPreferencesUpdate) -> LearnerPreferences:
        with self._lock:
            preferences = LearnerPreferences(
                **update.model_dump(),
                updated_at=datetime.now(UTC),
            )
            values = self._read()
            values[learner_id] = preferences.model_dump(mode="json")
            self._write(values)
            return preferences


class InMemoryPreferencesStore:
    """Test-friendly implementation used when no persistence path is supplied."""

    def __init__(self) -> None:
        self._values: dict[str, LearnerPreferences] = {}

    def get(self, learner_id: str) -> LearnerPreferences:
        return self._values.get(learner_id, LearnerPreferences())

    def update(self, learner_id: str, update: LearnerPreferencesUpdate) -> LearnerPreferences:
        value = LearnerPreferences(**update.model_dump(), updated_at=datetime.now(UTC))
        self._values[learner_id] = value
        return value
