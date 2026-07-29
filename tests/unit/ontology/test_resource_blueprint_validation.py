from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from skillforge_kb.ontology.resource_blueprints import load_resource_blueprints


def _write_manifest(tmp_path: Path, defaults: dict[str, object]) -> Path:
    path = tmp_path / "resource_blueprints.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "version": "resource-blueprints-v1",
                "graph_version": "ai-course-v1",
                "defaults": defaults,
                "overrides": {},
            }
        ),
        encoding="utf-8",
    )
    return path


def test_resource_blueprints_reject_malformed_depth_keys(tmp_path, catalog) -> None:
    path = _write_manifest(
        tmp_path,
        {
            "resource_types": ["lecture"],
            "estimated_minutes": 60,
            "levels": {"expert": {"estimated_minutes": 90}},
        },
    )

    with pytest.raises(ValidationError):
        load_resource_blueprints(catalog, path)


def test_resource_blueprints_reject_empty_override_items(tmp_path, catalog) -> None:
    path = _write_manifest(
        tmp_path,
        {
            "resource_types": ["lecture"],
            "estimated_minutes": 60,
            "levels": {"intro": {"learning_outcomes": [""]}},
        },
    )

    with pytest.raises(ValidationError):
        load_resource_blueprints(catalog, path)


def test_resource_blueprints_reject_invalid_effort_range(tmp_path, catalog) -> None:
    path = _write_manifest(
        tmp_path,
        {
            "resource_types": ["lecture"],
            "estimated_minutes": 0,
            "levels": {},
        },
    )

    with pytest.raises(ValidationError):
        load_resource_blueprints(catalog, path)
