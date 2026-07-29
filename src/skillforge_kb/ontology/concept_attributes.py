from math import isclose
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .catalog import OntologyCatalog


class AbilityDemand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    theoretical_understanding: float = Field(ge=0, le=1)
    coding_ability: float = Field(ge=0, le=1)
    mathematical_foundation: float = Field(ge=0, le=1)
    problem_solving: float = Field(ge=0, le=1)

    def values(self) -> tuple[float, float, float, float]:
        return (
            self.theoretical_understanding,
            self.coding_ability,
            self.mathematical_foundation,
            self.problem_solving,
        )

    def __getitem__(self, dimension: str) -> float:
        value = getattr(self, dimension, None)
        if not isinstance(value, float):
            raise KeyError(dimension)
        return value

    @model_validator(mode="after")
    def validate_sum(self) -> "AbilityDemand":
        if not isclose(sum(self.values()), 1.0, abs_tol=1e-9):
            raise ValueError("ability demand weights must sum to 1")
        return self


class ConceptAttributes(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    graph_version: str = Field(min_length=1)
    concept_id: str = Field(min_length=1)
    chapter_id: str = Field(min_length=1)
    difficulty_prior: float = Field(ge=0, le=1)
    chapter_core: bool
    ability_demand: AbilityDemand


class ConceptAttributeCatalog(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str = Field(min_length=1)
    graph_version: str = Field(min_length=1)
    attributes: tuple[ConceptAttributes, ...]


class _AttributeManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str = Field(min_length=1)
    graph_version: str = Field(min_length=1)
    chapter_defaults: dict[str, AbilityDemand]
    concept_overrides: dict[str, AbilityDemand] = Field(default_factory=dict)


def load_concept_attributes(
    catalog: OntologyCatalog,
    path: Path,
) -> ConceptAttributeCatalog:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    manifest = _AttributeManifest.model_validate(raw)
    if manifest.graph_version != catalog.course_document.version:
        raise ValueError("concept attribute graph version does not match catalog")
    chapters = {chapter.id: chapter for chapter in catalog.chapters()}
    if set(manifest.chapter_defaults) != set(chapters):
        raise ValueError("concept attributes require one default for every chapter")
    for concept_id in manifest.concept_overrides:
        catalog.get_concept(concept_id)
    rows: list[ConceptAttributes] = []
    for concept in catalog.concepts():
        section = catalog.section_for(concept.id)
        chapter = chapters[section.chapter_id]
        rows.append(
            ConceptAttributes(
                graph_version=manifest.graph_version,
                concept_id=concept.id,
                chapter_id=chapter.id,
                difficulty_prior=concept.difficulty / 4,
                chapter_core=chapter.core,
                ability_demand=manifest.concept_overrides.get(
                    concept.id, manifest.chapter_defaults[chapter.id]
                ),
            )
        )
    return ConceptAttributeCatalog(
        version=manifest.version,
        graph_version=manifest.graph_version,
        attributes=tuple(rows),
    )


def concept_attributes(
    catalog: ConceptAttributeCatalog,
    concept_id: str,
) -> ConceptAttributes:
    for attributes in catalog.attributes:
        if attributes.concept_id == concept_id:
            return attributes
    raise KeyError(f"concept attributes not found: {concept_id}")
