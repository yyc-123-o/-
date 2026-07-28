from pathlib import Path

import yaml

from skillforge_kb.ingestion.normalize import normalize_text

from .models import (
    Chapter,
    Concept,
    CourseDocument,
    Relation,
    RelationDocument,
    RelationKind,
    Section,
)


class OntologyCatalog:
    def __init__(
        self,
        course_document: CourseDocument,
        relation_document: RelationDocument,
    ) -> None:
        self._course_document = course_document
        self._relation_document = relation_document
        self._concepts = {concept.id: concept for concept in course_document.concepts}
        self._sections = {section.id: section for section in course_document.sections}
        self._chapters = {chapter.id: chapter for chapter in course_document.chapters}
        self._teaching = {item.concept_id: item.section_id for item in course_document.teaches}
        if len(self._concepts) != len(course_document.concepts):
            raise ValueError("duplicate concept IDs")
        if len(self._sections) != len(course_document.sections):
            raise ValueError("duplicate section IDs")
        if len(self._chapters) != len(course_document.chapters):
            raise ValueError("duplicate chapter IDs")
        if len(self._teaching) != len(course_document.teaches):
            raise ValueError("concept must have one primary teaching section")
        self._aliases = self._build_aliases()

    @property
    def course_document(self) -> CourseDocument:
        return self._course_document

    @property
    def relation_document(self) -> RelationDocument:
        return self._relation_document

    @classmethod
    def load(cls, course_path: Path, relations_path: Path) -> "OntologyCatalog":
        course_raw = yaml.safe_load(course_path.read_text(encoding="utf-8"))
        relations_raw = yaml.safe_load(relations_path.read_text(encoding="utf-8"))
        return cls(
            CourseDocument.model_validate(course_raw),
            RelationDocument.model_validate(relations_raw),
        )

    @classmethod
    def from_documents(
        cls,
        course: CourseDocument,
        relations: RelationDocument,
    ) -> "OntologyCatalog":
        return cls(course, relations)

    def chapters(self) -> list[Chapter]:
        return sorted(self._chapters.values(), key=lambda item: item.order)

    def concepts(self) -> list[Concept]:
        return sorted(self._concepts.values(), key=lambda item: item.id)

    def get_concept(self, concept_id: str) -> Concept:
        return self._concepts[concept_id]

    def resolve_alias(self, value: str) -> str | None:
        return self._aliases.get(normalize_text(value).casefold())

    def section_for(self, concept_id: str) -> Section:
        return self._sections[self._teaching[concept_id]]

    def relations(self, kind: RelationKind | None = None) -> list[Relation]:
        rows = self._relation_document.relations
        if kind is not None:
            rows = [relation for relation in rows if relation.kind is kind]
        return sorted(rows, key=lambda item: (item.kind.value, item.source, item.target))

    def _build_aliases(self) -> dict[str, str]:
        aliases: dict[str, str] = {}
        for concept in self._concepts.values():
            for value in [concept.names.zh, concept.names.en, *concept.aliases]:
                key = normalize_text(value).casefold()
                owner = aliases.get(key)
                if owner is not None and owner != concept.id:
                    raise ValueError(f"duplicate alias: {value}")
                aliases[key] = concept.id
        return aliases
