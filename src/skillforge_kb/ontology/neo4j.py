from neo4j import Driver, Session

from .catalog import OntologyCatalog
from .models import Relation, RelationKind


class Neo4jConceptGraph:
    """Publish a validated course ontology and traverse prerequisite edges."""

    def __init__(self, driver: Driver) -> None:
        self._driver = driver

    def publish(self, catalog: OntologyCatalog) -> None:
        version = catalog.course_document.version
        course = catalog.course_document.course
        chapters = catalog.chapters()
        sections = catalog.course_document.sections
        concepts = catalog.concepts()
        teaches = catalog.course_document.teaches

        with self._driver.session() as session:
            self._create_constraints(session)
            session.run(
                "MERGE (node:Course {id: $id}) "
                "SET node.zh = $zh, node.en = $en, node.audience = $audience, "
                "node.version = $version, node.review_status = $review_status",
                id=course.id,
                zh=course.title.zh,
                en=course.title.en,
                audience=course.audience,
                version=version,
                review_status=course.review_status.value,
            ).consume()
            session.run(
                "UNWIND $rows AS row MERGE (node:Chapter {id: row.id}) "
                "SET node.zh = row.zh, node.en = row.en, node.order = row.order, "
                "node.summary = row.summary, node.core = row.core, "
                "node.review_status = row.review_status, node.graph_version = $version",
                rows=[
                    {
                        "id": chapter.id,
                        "zh": chapter.title.zh,
                        "en": chapter.title.en,
                        "order": chapter.order,
                        "summary": chapter.summary,
                        "core": chapter.core,
                        "review_status": chapter.review_status.value,
                    }
                    for chapter in chapters
                ],
                version=version,
            ).consume()
            session.run(
                "UNWIND $rows AS row MERGE (node:Section {id: row.id}) "
                "SET node.zh = row.zh, node.en = row.en, node.order = row.order, "
                "node.review_status = row.review_status, node.graph_version = $version",
                rows=[
                    {
                        "id": section.id,
                        "zh": section.title.zh,
                        "en": section.title.en,
                        "order": section.order,
                        "review_status": section.review_status.value,
                    }
                    for section in sections
                ],
                version=version,
            ).consume()
            session.run(
                "UNWIND $rows AS row MERGE (node:Concept {id: row.id}) "
                "SET node.zh = row.zh, node.en = row.en, node.aliases = row.aliases, "
                "node.summary = row.summary, node.difficulty = row.difficulty, "
                "node.required = row.required, node.evidence_status = row.evidence_status, "
                "node.review_status = row.review_status, node.graph_version = $version",
                rows=[
                    {
                        "id": concept.id,
                        "zh": concept.names.zh,
                        "en": concept.names.en,
                        "aliases": concept.aliases,
                        "summary": concept.summary,
                        "difficulty": concept.difficulty,
                        "required": concept.required,
                        "evidence_status": concept.evidence_status.value,
                        "review_status": concept.review_status.value,
                    }
                    for concept in concepts
                ],
                version=version,
            ).consume()
            session.run(
                "UNWIND $rows AS row MERGE (node:ConceptLevel {id: row.id}) "
                "SET node.concept_id = row.concept_id, node.level = row.level, "
                "node.learning_outcomes = row.learning_outcomes, "
                "node.mastery_threshold = row.mastery_threshold, "
                "node.assessment_kinds = row.assessment_kinds, node.graph_version = $version",
                rows=[
                    {
                        "id": f"{concept.id}:{level.level.value}",
                        "concept_id": concept.id,
                        "level": level.level.value,
                        "learning_outcomes": level.learning_outcomes,
                        "mastery_threshold": level.mastery_threshold,
                        "assessment_kinds": level.assessment_kinds,
                    }
                    for concept in concepts
                    for level in concept.levels
                ],
                version=version,
            ).consume()
            session.run(
                "UNWIND $rows AS row MATCH (course:Course {id: $course_id}) "
                "MATCH (chapter:Chapter {id: row.id}) "
                "MERGE (course)-[edge:HAS_CHAPTER]->(chapter) "
                "SET edge.order = row.order, edge.graph_version = $version",
                course_id=course.id,
                rows=[{"id": chapter.id, "order": chapter.order} for chapter in chapters],
                version=version,
            ).consume()
            session.run(
                "UNWIND $rows AS row MATCH (chapter:Chapter {id: row.chapter_id}) "
                "MATCH (section:Section {id: row.id}) "
                "MERGE (chapter)-[edge:HAS_SECTION]->(section) "
                "SET edge.order = row.order, edge.graph_version = $version",
                rows=[
                    {"id": section.id, "chapter_id": section.chapter_id, "order": section.order}
                    for section in sections
                ],
                version=version,
            ).consume()
            session.run(
                "UNWIND $rows AS row MATCH (section:Section {id: row.section_id}) "
                "MATCH (concept:Concept {id: row.concept_id}) "
                "MERGE (section)-[edge:TEACHES]->(concept) "
                "SET edge.order = row.order, edge.required = row.required, "
                "edge.review_status = row.review_status, edge.graph_version = $version",
                rows=[
                    {
                        "section_id": assignment.section_id,
                        "concept_id": assignment.concept_id,
                        "order": assignment.order,
                        "required": assignment.required,
                        "review_status": assignment.review_status.value,
                    }
                    for assignment in teaches
                ],
                version=version,
            ).consume()
            session.run(
                "UNWIND $rows AS row MATCH (concept:Concept {id: row.concept_id}) "
                "MATCH (level:ConceptLevel {id: row.level_id}) "
                "MERGE (concept)-[edge:HAS_LEVEL]->(level) "
                "SET edge.graph_version = $version",
                rows=[
                    {"concept_id": concept.id, "level_id": f"{concept.id}:{level.level.value}"}
                    for concept in concepts
                    for level in concept.levels
                ],
                version=version,
            ).consume()
            self._publish_relations(session, catalog.relations(), version)

    def prerequisites(self, concept_id: str, max_depth: int = 2) -> list[str]:
        if max_depth not in {1, 2}:
            raise ValueError("max_depth must be 1 or 2")
        query = (
            f"MATCH (start:Concept {{id: $concept_id}})"
            f"<-[:PREREQUISITE_OF*1..{max_depth}]-(prerequisite:Concept) "
            "RETURN DISTINCT prerequisite.id AS id ORDER BY id"
        )
        with self._driver.session() as session:
            result = session.run(query, concept_id=concept_id)
            return [str(record["id"]) for record in result]

    @staticmethod
    def _create_constraints(session: Session) -> None:
        for label in ("Course", "Chapter", "Section", "Concept", "ConceptLevel"):
            session.run(
                f"CREATE CONSTRAINT {label.lower()}_id IF NOT EXISTS "
                f"FOR (node:{label}) REQUIRE node.id IS UNIQUE"
            ).consume()

    @staticmethod
    def _publish_relations(session: Session, relations: list[Relation], version: str) -> None:
        prerequisites = [
            relation
            for relation in relations
            if relation.kind
            in {RelationKind.HARD_PREREQUISITE, RelationKind.SOFT_PREREQUISITE}
        ]
        part_of = [relation for relation in relations if relation.kind is RelationKind.PART_OF]
        contrasts = [
            relation for relation in relations if relation.kind is RelationKind.CONTRASTS_WITH
        ]
        confused = [
            relation for relation in relations if relation.kind is RelationKind.CONFUSED_WITH
        ]
        Neo4jConceptGraph._publish_directed(
            session,
            "PREREQUISITE_OF",
            prerequisites,
            version,
            include_mastery=True,
        )
        Neo4jConceptGraph._publish_directed(session, "PART_OF", part_of, version)
        Neo4jConceptGraph._publish_symmetric(session, "CONTRASTS_WITH", contrasts, version)
        Neo4jConceptGraph._publish_symmetric(session, "CONFUSED_WITH", confused, version)

    @staticmethod
    def _publish_directed(
        session: Session,
        relation_type: str,
        relations: list[Relation],
        version: str,
        include_mastery: bool = False,
    ) -> None:
        if not relations:
            return
        mastery_set = "edge.min_mastery = row.min_mastery, " if include_mastery else ""
        session.run(
            f"UNWIND $rows AS row MATCH (source:Concept {{id: row.source}}) "
            f"MATCH (target:Concept {{id: row.target}}) "
            f"MERGE (source)-[edge:{relation_type}]->(target) "
            f"SET edge.kind = row.kind, {mastery_set}"
            "edge.review_status = row.review_status, edge.graph_version = $version",
            rows=[
                {
                    "source": relation.source,
                    "target": relation.target,
                    "kind": relation.kind.value,
                    "min_mastery": relation.min_mastery,
                    "review_status": relation.review_status.value,
                }
                for relation in relations
            ],
            version=version,
        ).consume()

    @staticmethod
    def _publish_symmetric(
        session: Session,
        relation_type: str,
        relations: list[Relation],
        version: str,
    ) -> None:
        if not relations:
            return
        rows = [
            {
                "source": relation.source,
                "target": relation.target,
                "kind": relation.kind.value,
                "review_status": relation.review_status.value,
            }
            for relation in relations
        ]
        for source_key, target_key in (("source", "target"), ("target", "source")):
            session.run(
                f"UNWIND $rows AS row MATCH (source:Concept {{id: row.{source_key}}}) "
                f"MATCH (target:Concept {{id: row.{target_key}}}) "
                f"MERGE (source)-[edge:{relation_type}]->(target) "
                "SET edge.kind = row.kind, edge.review_status = row.review_status, "
                "edge.graph_version = $version",
                rows=rows,
                version=version,
            ).consume()
