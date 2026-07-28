from typing import Any

from neo4j import Driver

from .catalog import OntologyCatalog
from .models import RelationKind
from .validation import validate_catalog


class Neo4jConceptGraph:
    def __init__(self, driver: Driver, graph_version: str | None = None) -> None:
        self._driver = driver
        self._graph_version = graph_version

    def publish(self, catalog: OntologyCatalog) -> None:
        validate_catalog(catalog)
        course = catalog.course_document
        if self._graph_version is not None and self._graph_version != course.version:
            raise ValueError("adapter graph version does not match the catalog")
        nodes = [
            {
                "label": "Course",
                "id": course.course.id,
                "properties": {
                    "title_zh": course.course.title.zh,
                    "title_en": course.course.title.en,
                    "audience": course.course.audience,
                    "version": course.version,
                    "graph_version": course.version,
                    "review_status": course.course.review_status.value,
                },
            }
        ]
        nodes.extend(
            {
                "label": "Chapter",
                "id": chapter.id,
                "properties": {
                    "order": chapter.order,
                    "title_zh": chapter.title.zh,
                    "title_en": chapter.title.en,
                    "summary": chapter.summary,
                    "learning_outcomes": chapter.learning_outcomes,
                    "core": chapter.core,
                    "review_status": chapter.review_status.value,
                    "graph_version": course.version,
                },
            }
            for chapter in course.chapters
        )
        nodes.extend(
            {
                "label": "Section",
                "id": section.id,
                "properties": {
                    "chapter_id": section.chapter_id,
                    "order": section.order,
                    "title_zh": section.title.zh,
                    "title_en": section.title.en,
                    "learning_outcomes": section.learning_outcomes,
                    "review_status": section.review_status.value,
                    "graph_version": course.version,
                },
            }
            for section in course.sections
        )
        nodes.extend(
            {
                "label": "Concept",
                "id": concept.id,
                "properties": {
                    "name_zh": concept.names.zh,
                    "name_en": concept.names.en,
                    "aliases": concept.aliases,
                    "summary": concept.summary,
                    "difficulty": concept.difficulty,
                    "required": concept.required,
                    "evidence_status": concept.evidence_status.value,
                    "review_status": concept.review_status.value,
                    "graph_version": course.version,
                },
            }
            for concept in course.concepts
        )
        nodes.extend(
            {
                "label": "ConceptLevel",
                "id": f"{concept.id}:{level.level.value}",
                "properties": {
                    "concept_id": concept.id,
                    "level": level.level.value,
                    "learning_outcomes": level.learning_outcomes,
                    "mastery_threshold": level.mastery_threshold,
                    "assessment_kinds": level.assessment_kinds,
                    "graph_version": course.version,
                },
            }
            for concept in course.concepts
            for level in concept.levels
        )
        with self._driver.session() as session:
            _create_constraints(session)
            session.execute_write(
                _publish_transaction,
                version=course.version,
                nodes=nodes,
                course_id=course.course.id,
                chapters=[
                    {
                        "chapter": chapter.id,
                        "order": chapter.order,
                        "review_status": chapter.review_status.value,
                    }
                    for chapter in course.chapters
                ],
                sections=[
                    {
                        "chapter": section.chapter_id,
                        "section": section.id,
                        "order": section.order,
                        "review_status": section.review_status.value,
                    }
                    for section in course.sections
                ],
                teaches=[
                    {
                        "section": assignment.section_id,
                        "concept": assignment.concept_id,
                        "order": assignment.order,
                        "required": assignment.required,
                        "review_status": assignment.review_status.value,
                    }
                    for assignment in course.teaches
                ],
                levels=[
                    {
                        "concept": concept.id,
                        "level": f"{concept.id}:{level.level.value}",
                        "review_status": concept.review_status.value,
                    }
                    for concept in course.concepts
                    for level in concept.levels
                ],
                relations=[
                    {
                        "source": relation.source,
                        "target": relation.target,
                        "kind": relation.kind.value,
                        "min_mastery": relation.min_mastery,
                        "review_status": relation.review_status.value,
                    }
                    for relation in catalog.relations()
                ],
            )
        self._graph_version = course.version

    def prerequisites(self, concept_id: str, max_depth: int = 2) -> list[str]:
        if max_depth not in {1, 2}:
            raise ValueError("max_depth must be 1 or 2")
        version_expression = "target.graph_version"
        parameters: dict[str, Any] = {"concept_id": concept_id}
        if self._graph_version is not None:
            version_expression = "$graph_version"
            parameters["graph_version"] = self._graph_version
        query = (
            "MATCH path=(target:Concept {id: $concept_id})"
            f"<-[:PREREQUISITE_OF*1..{max_depth}]-(source:Concept) "
            "WHERE all(edge IN relationships(path) "
            f"WHERE coalesce(edge.graph_version, edge.version) = {version_expression}) "
            "RETURN DISTINCT source.id AS id ORDER BY id"
        )
        with self._driver.session() as session:
            return [record["id"] for record in session.run(query, **parameters)]


def _publish_transaction(
    tx: Any,
    *,
    version: str,
    nodes: list[dict[str, Any]],
    course_id: str,
    chapters: list[dict[str, Any]],
    sections: list[dict[str, Any]],
    teaches: list[dict[str, Any]],
    levels: list[dict[str, str]],
    relations: list[dict[str, Any]],
) -> None:
    for node in nodes:
        tx.run(
            f"MERGE (node:{node['label']} {{id: $id}}) SET node += $properties",
            id=node["id"],
            properties=node["properties"],
        ).consume()
    tx.run(
        "MATCH ()-[relation]->() WHERE relation.version = $version "
        "OR relation.graph_version = $version DELETE relation",
        version=version,
    ).consume()
    tx.run(
        "MATCH (course:Course {id: $course_id}) UNWIND $rows AS row "
        "MATCH (chapter:Chapter {id: row.chapter}) "
        "MERGE (course)-[:HAS_CHAPTER {version: $version, graph_version: $version, "
        "order: row.order, "
        "review_status: row.review_status}]->(chapter)",
        course_id=course_id,
        rows=chapters,
        version=version,
    ).consume()
    tx.run(
        "UNWIND $rows AS row MATCH (chapter:Chapter {id: row.chapter}) "
        "MATCH (section:Section {id: row.section}) "
        "MERGE (chapter)-[:HAS_SECTION {version: $version, graph_version: $version, "
        "order: row.order, "
        "review_status: row.review_status}]->(section)",
        rows=sections,
        version=version,
    ).consume()
    tx.run(
        "UNWIND $rows AS row MATCH (section:Section {id: row.section}) "
        "MATCH (concept:Concept {id: row.concept}) "
        "MERGE (section)-[edge:TEACHES {version: $version, "
        "graph_version: $version}]->(concept) "
        "SET edge.order = row.order, edge.required = row.required, "
        "edge.review_status = row.review_status",
        rows=teaches,
        version=version,
    ).consume()
    tx.run(
        "UNWIND $rows AS row MATCH (concept:Concept {id: row.concept}) "
        "MATCH (level:ConceptLevel {id: row.level}) "
        "MERGE (concept)-[:HAS_LEVEL {version: $version, graph_version: $version, "
        "review_status: row.review_status}]->(level)",
        rows=levels,
        version=version,
    ).consume()
    for relation_kind in RelationKind:
        rows = [row for row in relations if row["kind"] == relation_kind.value]
        if not rows:
            continue
        edge_type = (
            "PREREQUISITE_OF"
            if relation_kind in {
                RelationKind.HARD_PREREQUISITE,
                RelationKind.SOFT_PREREQUISITE,
            }
            else relation_kind.value.upper()
        )
        _publish_relation_group(
            tx,
            edge_type=edge_type,
            rows=rows,
            version=version,
            symmetric=relation_kind
            in {RelationKind.CONTRASTS_WITH, RelationKind.CONFUSED_WITH},
        )


def _create_constraints(session: Any) -> None:
    for label in ("Course", "Chapter", "Section", "Concept", "ConceptLevel"):
        session.run(
            f"CREATE CONSTRAINT {label.lower()}_id IF NOT EXISTS "
            f"FOR (node:{label}) REQUIRE node.id IS UNIQUE"
        ).consume()


def _publish_relation_group(
    tx: Any,
    *,
    edge_type: str,
    rows: list[dict[str, Any]],
    version: str,
    symmetric: bool,
) -> None:
    directions = (rows, _reverse_relation_rows(rows)) if symmetric else (rows,)
    for direction_rows in directions:
        tx.run(
            f"UNWIND $rows AS row MATCH (source:Concept {{id: row.source}}) "
            f"MATCH (target:Concept {{id: row.target}}) "
            f"MERGE (source)-[edge:{edge_type} {{version: $version, "
            "graph_version: $version}]->(target) "
            "SET edge.kind = row.kind, edge.min_mastery = row.min_mastery, "
            "edge.review_status = row.review_status",
            rows=direction_rows,
            version=version,
        ).consume()


def _reverse_relation_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {**row, "source": row["target"], "target": row["source"]}
        for row in rows
    ]
