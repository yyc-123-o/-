from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from .catalog import OntologyCatalog
from .models import ConceptLevel, DepthLevel


class ResourceBlueprint(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    graph_version: str = Field(min_length=1)
    concept_id: str = Field(min_length=1)
    depth: DepthLevel
    learning_outcomes: tuple[str, ...] = Field(min_length=1)
    assessment_kinds: tuple[str, ...] = Field(min_length=1)
    resource_types: tuple[str, ...] = Field(min_length=1)
    estimated_minutes: int = Field(ge=1)


class ResourceBlueprintCatalog(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str = Field(min_length=1)
    graph_version: str = Field(min_length=1)
    defaults: dict[str, Any] = Field(default_factory=dict)
    overrides: dict[str, dict[str, Any]] = Field(default_factory=dict)
    blueprints: dict[str, ResourceBlueprint] = Field(default_factory=dict)


def load_resource_blueprints(
    catalog: OntologyCatalog,
    path: Path,
) -> ResourceBlueprintCatalog:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    manifest = ResourceBlueprintCatalog.model_validate(raw)
    if manifest.graph_version != catalog.course_document.version:
        raise ValueError("resource blueprint graph version does not match catalog")
    for concept_id in manifest.overrides:
        catalog.get_concept(concept_id)
    blueprints: dict[str, ResourceBlueprint] = {}
    for concept in catalog.concepts():
        for level in concept.levels:
            key = _key(concept.id, level.level)
            blueprints[key] = _build_blueprint(manifest, concept.id, level.level, level)
    return manifest.model_copy(update={"blueprints": blueprints})


def resource_blueprint(
    manifest: ResourceBlueprintCatalog,
    concept_id: str,
    depth: DepthLevel,
) -> ResourceBlueprint:
    try:
        return manifest.blueprints[_key(concept_id, depth)]
    except KeyError as exc:
        raise KeyError(f"resource blueprint not found: {concept_id}:{depth.value}") from exc


def _build_blueprint(
    manifest: ResourceBlueprintCatalog,
    concept_id: str,
    depth: DepthLevel,
    level: ConceptLevel,
) -> ResourceBlueprint:
    override = manifest.overrides.get(concept_id, {})
    values = {**manifest.defaults, **override}
    levels = values.pop("levels", {})
    level_values = levels.get(depth.value, {})
    values.update(level_values)
    outcomes = tuple(values.pop("learning_outcomes", level.learning_outcomes))
    assessments = tuple(values.pop("assessment_kinds", level.assessment_kinds))
    resource_types = tuple(
        values.pop("resource_types", ("lecture", "practical_guide", "assessment"))
    )
    default_minutes = {"intro": 45, "intermediate": 60, "advanced": 75}
    minutes = int(values.pop("estimated_minutes", default_minutes[depth.value]))
    return ResourceBlueprint(
        graph_version=manifest.graph_version,
        concept_id=concept_id,
        depth=depth,
        learning_outcomes=outcomes,
        assessment_kinds=assessments,
        resource_types=resource_types,
        estimated_minutes=minutes,
    )


def _key(concept_id: str, depth: DepthLevel) -> str:
    return f"{concept_id}:{depth.value}"
