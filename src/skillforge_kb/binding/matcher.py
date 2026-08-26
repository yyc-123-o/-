import hashlib
import re
from dataclasses import dataclass

from skillforge_kb.ingestion.normalize import normalize_text
from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.retrieval.corpus import KnowledgeCorpus
from skillforge_kb.retrieval.models import KnowledgeChunk

from .models import ConceptResourceBinding


@dataclass(frozen=True)
class _Term:
    value: str
    is_alias: bool


_RANKS = {
    "title_exact_name": (0, 0.99),
    "title_alias": (1, 0.96),
    "title_partial_name": (2, 0.90),
    "body_exact_name": (3, 0.80),
    "body_alias": (4, 0.76),
}


def build_candidate_bindings(
    catalog: OntologyCatalog, corpus: KnowledgeCorpus
) -> tuple[ConceptResourceBinding, ...]:
    """Match explicit concept names in candidate chunks without publishing edges."""
    chapters = {chapter.id: chapter for chapter in catalog.chapters()}
    concepts = tuple(catalog.concepts())
    bindings: list[ConceptResourceBinding] = []

    for chunk in corpus.chunks:
        best_by_concept: dict[str, tuple[tuple[int, float, str], ConceptResourceBinding]] = {}
        title_parts = tuple(
            _compact(part) for part in (chunk.source_title, *chunk.heading_path)
        )
        body_text = _compact(chunk.text)
        for concept in concepts:
            section = catalog.section_for(concept.id)
            chapter = chapters[section.chapter_id]
            terms = (
                _Term(concept.names.zh, False),
                _Term(concept.names.en, False),
                *(_Term(alias, True) for alias in concept.aliases),
            )
            for term in terms:
                normalized_term = _compact(term.value)
                if not normalized_term:
                    continue
                match_type = _match_type(
                    title_parts,
                    body_text,
                    normalized_term,
                    term.value,
                    term.is_alias,
                )
                if match_type is None:
                    continue
                rank, score = _RANKS[match_type]
                key = (rank, -score, normalized_term)
                binding = _make_binding(
                    chunk=chunk,
                    concept_id=concept.id,
                    section_id=section.id,
                    chapter_id=chapter.id,
                    matched_term=term.value,
                    match_type=match_type,
                    score=score,
                )
                previous = best_by_concept.get(concept.id)
                if previous is None or key < previous[0]:
                    best_by_concept[concept.id] = (key, binding)
        bindings.extend(binding for _, binding in best_by_concept.values())

    return tuple(sorted(bindings, key=lambda item: (item.chunk_id, item.concept_id)))


def _match_type(
    title_parts: tuple[str, ...],
    body_text: str,
    term: str,
    original_term: str,
    is_alias: bool,
) -> str | None:
    if any(_contains(part, term) for part in title_parts):
        return "title_alias" if is_alias else "title_exact_name"
    if not is_alias and any(_is_safe_partial(part, term) for part in title_parts):
        return "title_partial_name"
    occurrences = _count_occurrences(body_text, term)
    if occurrences >= 2 or (occurrences == 1 and _is_distinctive(original_term)):
        return "body_alias" if is_alias else "body_exact_name"
    return None


def _is_safe_partial(title_text: str, term: str) -> bool:
    """Allow a longer formal name to match a focused title phrase."""
    if len(term) < 5:
        return False
    compact_title = title_text.replace(" ", "")
    compact_term = term.replace(" ", "")
    if compact_term in compact_title or compact_title in compact_term:
        shorter = min(len(compact_title), len(compact_term))
        return shorter >= 5 and shorter / max(len(compact_title), len(compact_term)) >= 0.5
    return False


def _contains(text: str, term: str) -> bool:
    return _count_occurrences(text, term) > 0


def _count_occurrences(text: str, term: str) -> int:
    if re.fullmatch(r"[a-z0-9][a-z0-9 ._+/-]*", term):
        pattern = rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])"
        return len(re.findall(pattern, text))
    return text.count(term)


def _is_distinctive(term: str) -> bool:
    compact = re.sub(r"\s+", "", term)
    if any("\u3400" <= character <= "\u9fff" for character in compact):
        return len(compact) >= 4
    uppercase_count = sum(character.isupper() for character in compact)
    return uppercase_count >= 2 or " " in term or "-" in term


def _compact(value: str) -> str:
    return re.sub(r"\s+", " ", normalize_text(value)).casefold().strip()


def _make_binding(
    *,
    chunk: KnowledgeChunk,
    concept_id: str,
    section_id: str,
    chapter_id: str,
    matched_term: str,
    match_type: str,
    score: float,
) -> ConceptResourceBinding:
    identity = f"{chunk.chunk_id}\n{concept_id}".encode()
    return ConceptResourceBinding(
        binding_id=hashlib.sha256(identity).hexdigest(),
        chunk_id=chunk.chunk_id,
        doc_id=chunk.doc_id,
        source_title=chunk.source_title,
        heading_path=chunk.heading_path,
        domain_tag=chunk.domain_tag,
        concept_id=concept_id,
        section_id=section_id,
        chapter_id=chapter_id,
        matched_term=matched_term,
        match_type=match_type,  # type: ignore[arg-type]
        score=score,
    )
