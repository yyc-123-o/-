import math
import re
from collections import Counter

from .corpus import KnowledgeCorpus
from .models import (
    KnowledgeChunk,
    KnowledgeHit,
    KnowledgeQuery,
    KnowledgeRetrievalResult,
    KnowledgeRetrievalStatus,
)

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u3400-\u9fff]")


class Bm25KnowledgeRetriever:
    def __init__(
        self,
        corpus: KnowledgeCorpus,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        if k1 < 0:
            raise ValueError("k1 must be non-negative")
        if not 0 <= b <= 1:
            raise ValueError("b must be between 0 and 1")
        self._corpus = corpus
        self._k1 = k1
        self._b = b
        self._term_frequencies = tuple(
            Counter(_tokenize(_search_text(chunk))) for chunk in corpus.chunks
        )
        self._label_tokens = tuple(
            _tokenize(_label_text(chunk)) for chunk in corpus.chunks
        )
        self._body_tokens = tuple(
            _tokenize(chunk.text) for chunk in corpus.chunks
        )
        self._document_lengths = tuple(
            sum(frequencies.values()) for frequencies in self._term_frequencies
        )
        self._average_length = (
            sum(self._document_lengths) / len(self._document_lengths)
            if self._document_lengths
            else 0.0
        )
        document_frequency: Counter[str] = Counter()
        for frequencies in self._term_frequencies:
            document_frequency.update(frequencies.keys())
        self._idf = {
            term: math.log1p(
                (len(self._term_frequencies) - frequency + 0.5) / (frequency + 0.5)
            )
            for term, frequency in document_frequency.items()
        }

    def retrieve(self, query: KnowledgeQuery) -> KnowledgeRetrievalResult:
        query = KnowledgeQuery.model_validate(query.model_dump())
        if not self._corpus.chunks:
            return KnowledgeRetrievalResult.no_results(
                query,
                corpus_digest=self._corpus.digest,
            )

        query_terms = _tokenize(query.query)
        if not query_terms or not self._idf:
            return KnowledgeRetrievalResult.no_results(
                query,
                corpus_digest=self._corpus.digest,
            )

        scored: list[tuple[float, str, KnowledgeChunk]] = []
        anchor_sequences = tuple(
            tokens for anchor in query.anchors if (tokens := _tokenize(anchor))
        )
        for chunk, frequencies, document_length, label_tokens, body_tokens in zip(
            self._corpus.chunks,
            self._term_frequencies,
            self._document_lengths,
            self._label_tokens,
            self._body_tokens,
            strict=True,
        ):
            if anchor_sequences and not any(
                _contains_sequence(label_tokens, anchor_tokens)
                or _count_sequence(body_tokens, anchor_tokens) >= 2
                for anchor_tokens in anchor_sequences
            ):
                continue
            score = self._score(query_terms, frequencies, document_length)
            if score > 0:
                scored.append((score, chunk.chunk_id, chunk))

        scored.sort(key=lambda item: (-item[0], item[1]))
        hits = tuple(
            _to_hit(score, chunk)
            for score, _, chunk in scored[: query.top_k]
        )
        if not hits:
            return KnowledgeRetrievalResult.no_results(
                query,
                corpus_digest=self._corpus.digest,
            )
        return KnowledgeRetrievalResult(
            status=KnowledgeRetrievalStatus.OK,
            query=query,
            concept_id=query.concept_id,
            corpus_digest=self._corpus.digest,
            hits=hits,
        )

    def _score(
        self,
        query_terms: tuple[str, ...],
        frequencies: Counter[str],
        document_length: int,
    ) -> float:
        if document_length == 0:
            return 0.0
        average_length = self._average_length or 1.0
        score = 0.0
        for term in query_terms:
            term_frequency = frequencies.get(term, 0)
            idf = self._idf.get(term)
            if term_frequency == 0 or idf is None:
                continue
            denominator = term_frequency + self._k1 * (
                1 - self._b + self._b * document_length / average_length
            )
            score += idf * term_frequency * (self._k1 + 1) / denominator
        return score


def _search_text(chunk: KnowledgeChunk) -> str:
    return " ".join((chunk.source_title, *chunk.heading_path, chunk.text))


def _label_text(chunk: KnowledgeChunk) -> str:
    return " ".join((chunk.source_title, *chunk.heading_path))


def _tokenize(text: str) -> tuple[str, ...]:
    return tuple(match.casefold() for match in _TOKEN_PATTERN.findall(text))


def _contains_sequence(tokens: tuple[str, ...], sequence: tuple[str, ...]) -> bool:
    return _count_sequence(tokens, sequence) > 0


def _count_sequence(tokens: tuple[str, ...], sequence: tuple[str, ...]) -> int:
    width = len(sequence)
    if width == 0:
        return 0
    return sum(
        tokens[index : index + width] == sequence
        for index in range(len(tokens) - width + 1)
    )


def _to_hit(score: float, chunk: KnowledgeChunk) -> KnowledgeHit:
    return KnowledgeHit(
        chunk_id=chunk.chunk_id,
        doc_id=chunk.doc_id,
        source_title=chunk.source_title,
        heading_path=chunk.heading_path,
        text=chunk.text,
        difficulty=chunk.difficulty,
        score=score,
    )
