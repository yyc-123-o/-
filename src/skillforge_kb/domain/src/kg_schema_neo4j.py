from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from neo4j import GraphDatabase


@dataclass
class Triple:
    head: str
    head_label: str
    relation: str
    tail: str
    tail_label: str
    props: Dict | None = field(default_factory=dict)


CONSTRAINTS = [
    "CREATE CONSTRAINT concept_name IF NOT EXISTS FOR (c:Concept) REQUIRE c.name IS UNIQUE",
    "CREATE CONSTRAINT skill_name IF NOT EXISTS FOR (s:Skill) REQUIRE s.name IS UNIQUE",
    "CREATE CONSTRAINT algo_name IF NOT EXISTS FOR (a:Algorithm) REQUIRE a.name IS UNIQUE",
    "CREATE CONSTRAINT model_name IF NOT EXISTS FOR (m:Model) REQUIRE m.name IS UNIQUE",
    "CREATE CONSTRAINT tool_name IF NOT EXISTS FOR (t:Tool) REQUIRE t.name IS UNIQUE",
    "CREATE CONSTRAINT task_name IF NOT EXISTS FOR (t:Task) REQUIRE t.name IS UNIQUE",
    "CREATE CONSTRAINT course_name IF NOT EXISTS FOR (c:Course) REQUIRE c.name IS UNIQUE",
    "CREATE CONSTRAINT chunk_id IF NOT EXISTS FOR (c:Chunk) REQUIRE c.chunk_id IS UNIQUE",
    "CREATE CONSTRAINT learner_id IF NOT EXISTS FOR (l:Learner) REQUIRE l.learner_id IS UNIQUE",
]


class KGBuilder:
    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self) -> None:
        self.driver.close()

    def init_schema(self) -> None:
        with self.driver.session() as session:
            for stmt in CONSTRAINTS:
                session.run(stmt)

    def upsert_triple(self, triple: Triple) -> None:
        cypher = f"""
        MERGE (h:{triple.head_label} {{name: $head}})
        MERGE (t:{triple.tail_label} {{name: $tail}})
        MERGE (h)-[r:{triple.relation}]->(t)
        SET r += $props
        """
        with self.driver.session() as session:
            session.run(cypher, head=triple.head, tail=triple.tail, props=triple.props or {})

    def link_concept_to_chunk(
        self,
        concept_name: str,
        chunk_id: str,
        source_title: str,
        page_no: Optional[int] = None,
    ) -> None:
        cypher = """
        MERGE (c:Concept {name: $concept_name})
        MERGE (ch:Chunk {chunk_id: $chunk_id})
        ON CREATE SET ch.source_title = $source_title, ch.page_no = $page_no
        MERGE (c)-[:EVIDENCED_BY]->(ch)
        """
        with self.driver.session() as session:
            session.run(
                cypher,
                concept_name=concept_name,
                chunk_id=chunk_id,
                source_title=source_title,
                page_no=page_no,
            )

    def upsert_learner_mastery(
        self,
        learner_id: str,
        concept_name: str,
        level: float,
        weak_threshold: float = 0.4,
    ) -> None:
        cypher = """
        MERGE (l:Learner {learner_id: $learner_id})
        MERGE (c:Concept {name: $concept_name})
        MERGE (l)-[r:MASTERS]->(c)
        SET r.level = $level
        WITH l, c
        OPTIONAL MATCH (l)-[w:WEAK_IN]->(c)
        FOREACH (_ IN CASE WHEN $level < $weak_threshold THEN [1] ELSE [] END |
            MERGE (l)-[:WEAK_IN]->(c)
        )
        FOREACH (_ IN CASE WHEN $level >= $weak_threshold AND w IS NOT NULL THEN [1] ELSE [] END |
            DELETE w
        )
        """
        with self.driver.session() as session:
            session.run(
                cypher,
                learner_id=learner_id,
                concept_name=concept_name,
                level=level,
                weak_threshold=weak_threshold,
            )

    def get_prerequisite_edges(self, concept_name: str, depth: int = 3) -> List[Tuple[str, str]]:
        cypher = f"""
        MATCH path=(pre:Concept)-[:PREREQUISITE_OF*1..{depth}]->(target:Concept {{name: $name}})
        UNWIND relationships(path) AS rel
        RETURN DISTINCT startNode(rel).name AS src, endNode(rel).name AS dst
        """
        with self.driver.session() as session:
            return [(row["src"], row["dst"]) for row in session.run(cypher, name=concept_name)]

    def get_weak_concepts(self, learner_id: str) -> List[str]:
        cypher = """
        MATCH (l:Learner {learner_id: $learner_id})-[:WEAK_IN]->(c:Concept)
        RETURN c.name AS name
        """
        with self.driver.session() as session:
            return [row["name"] for row in session.run(cypher, learner_id=learner_id)]

    def get_evidence_chunks(self, concept_name: str) -> List[dict]:
        cypher = """
        MATCH (c:Concept {name: $name})-[:EVIDENCED_BY]->(ch:Chunk)
        RETURN ch.chunk_id AS chunk_id, ch.source_title AS source_title, ch.page_no AS page_no
        """
        with self.driver.session() as session:
            return [dict(row) for row in session.run(cypher, name=concept_name)]

    def get_learning_path(self, target_concept: str) -> List[str]:
        edges = self.get_prerequisite_edges(target_concept)
        return _topo_sort(edges, target_concept)


def _topo_sort(edges: List[Tuple[str, str]], target: str) -> List[str]:
    graph = defaultdict(list)
    indegree = defaultdict(int)
    nodes = {target}

    for src, dst in edges:
        graph[src].append(dst)
        indegree[dst] += 1
        nodes.add(src)
        nodes.add(dst)
        indegree.setdefault(src, indegree.get(src, 0))

    queue = deque(sorted(node for node in nodes if indegree[node] == 0))
    order: List[str] = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for nxt in graph[node]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)

    if target not in order:
        order.append(target)
    return order
