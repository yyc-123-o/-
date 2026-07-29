from enum import StrEnum
from pathlib import Path
from typing import Annotated

import yaml
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from .catalog import OntologyCatalog
from .models import ConceptLevel, DepthLevel

NonEmptyString = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


class ResourceType(StrEnum):
    LECTURE = "lecture"
    PRACTICAL_GUIDE = "practical_guide"
    ASSESSMENT = "assessment"
    PROJECT = "project"


class ResourceBlueprintLevelInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    learning_outcomes: tuple[NonEmptyString, ...] | None = Field(
        default=None,
        min_length=1,
    )
    assessment_kinds: tuple[NonEmptyString, ...] | None = Field(
        default=None,
        min_length=1,
    )
    resource_types: tuple[ResourceType, ...] | None = Field(
        default=None,
        min_length=1,
    )
    estimated_minutes: int | None = Field(default=None, strict=True, ge=1)


class ResourceBlueprintInput(ResourceBlueprintLevelInput):
    levels: dict[DepthLevel, ResourceBlueprintLevelInput] = Field(default_factory=dict)


class ResourceBlueprintManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: NonEmptyString
    graph_version: NonEmptyString
    defaults: ResourceBlueprintInput
    overrides: dict[NonEmptyString, ResourceBlueprintInput] = Field(default_factory=dict)


class ResourceBlueprint(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    graph_version: NonEmptyString
    concept_id: NonEmptyString
    depth: DepthLevel
    learning_outcomes: tuple[NonEmptyString, ...] = Field(min_length=1)
    assessment_kinds: tuple[NonEmptyString, ...] = Field(min_length=1)
    resource_types: tuple[ResourceType, ...] = Field(min_length=1)
    estimated_minutes: int = Field(strict=True, ge=1)


class ResourceBlueprintCatalog(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: NonEmptyString
    graph_version: NonEmptyString
    blueprints: tuple[ResourceBlueprint, ...] = ()


def load_resource_blueprints(
    catalog: OntologyCatalog,
    path: Path,
) -> ResourceBlueprintCatalog:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    manifest = ResourceBlueprintManifest.model_validate(raw)
    if manifest.graph_version != catalog.course_document.version:
        raise ValueError("resource blueprint graph version does not match catalog")
    for concept_id in manifest.overrides:
        catalog.get_concept(concept_id)
    blueprints: list[ResourceBlueprint] = []
    for concept in catalog.concepts():
        for level in concept.levels:
            blueprints.append(
                _build_blueprint(manifest, concept.id, level.level, level)
            )
    return ResourceBlueprintCatalog(
        version=manifest.version,
        graph_version=manifest.graph_version,
        blueprints=tuple(blueprints),
    )


def resource_blueprint(
    manifest: ResourceBlueprintCatalog,
    concept_id: str,
    depth: DepthLevel,
) -> ResourceBlueprint:
    for blueprint in manifest.blueprints:
        if blueprint.concept_id == concept_id and blueprint.depth is depth:
            return blueprint
    raise KeyError(f"resource blueprint not found: {concept_id}:{depth.value}")


def _build_blueprint(
    manifest: ResourceBlueprintManifest,
    concept_id: str,
    depth: DepthLevel,
    level: ConceptLevel,
) -> ResourceBlueprint:
    override = manifest.overrides.get(concept_id, ResourceBlueprintInput())
    default_level = manifest.defaults.levels.get(depth, ResourceBlueprintLevelInput())
    override_level = override.levels.get(depth, ResourceBlueprintLevelInput())
    outcomes = (
        override_level.learning_outcomes
        or override.learning_outcomes
        or default_level.learning_outcomes
        or manifest.defaults.learning_outcomes
        or tuple(level.learning_outcomes)
    )
    assessments = (
        override_level.assessment_kinds
        or override.assessment_kinds
        or default_level.assessment_kinds
        or manifest.defaults.assessment_kinds
        or tuple(level.assessment_kinds)
    )
    resource_types = (
        override_level.resource_types
        or override.resource_types
        or default_level.resource_types
        or manifest.defaults.resource_types
        or (
            ResourceType.LECTURE,
            ResourceType.PRACTICAL_GUIDE,
            ResourceType.ASSESSMENT,
        )
    )
    default_minutes = {
        DepthLevel.INTRO: 45,
        DepthLevel.INTERMEDIATE: 60,
        DepthLevel.ADVANCED: 75,
    }
    minutes = (
        override_level.estimated_minutes
        or override.estimated_minutes
        or default_level.estimated_minutes
        or manifest.defaults.estimated_minutes
        or default_minutes[depth]
    )
    return ResourceBlueprint(
        graph_version=manifest.graph_version,
        concept_id=concept_id,
        depth=depth,
        learning_outcomes=outcomes,
        assessment_kinds=assessments,
        resource_types=resource_types,
        estimated_minutes=minutes,
    )
