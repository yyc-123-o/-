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

# Latin/digit runs and contiguous CJK runs are tokenized separately so the
# token stream keeps its original document order (needed by anchor scoring).
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u3400-\u9fff]+")


def tokenize(text: str) -> tuple[str, ...]:
    """Deterministic, dependency-free bilingual tokenizer.

    * Latin/digit runs become one casefolded token each (``Conv2d`` -> ``conv2d``).
    * Contiguous CJK runs become adjacent bigrams (``卷积运算`` -> ``卷积``, ``积运``,
      ``运算``). A single CJK character stays a single token.

    Bigrams give Chinese retrieval enough precision to distinguish ``卷积`` from
    unrelated single-character overlaps, while still letting ``卷积`` match a longer
    phrase such as ``卷积运算`` or ``转置卷积`` without an external segmenter.
    """
    tokens: list[str] = []
    for match in _TOKEN_PATTERN.finditer(text):
        token = match.group()
        if token[0].isascii():
            tokens.append(token.casefold())
        elif len(token) == 1:
            tokens.append(token)
        else:
            tokens.extend(token[index : index + 2] for index in range(len(token) - 1))
    return tuple(tokens)


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
            Counter(tokenize(_search_text(chunk))) for chunk in corpus.chunks
        )
        self._label_tokens = tuple(
            tokenize(_label_text(chunk)) for chunk in corpus.chunks
        )
        self._body_tokens = tuple(
            tokenize(chunk.text) for chunk in corpus.chunks
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

        query_terms = tokenize(query.query)
        if not query_terms or not self._idf:
            return KnowledgeRetrievalResult.no_results(
                query,
                corpus_digest=self._corpus.digest,
            )

        # Anchors are a relevance boost rather than a hard filter: a document is
        # still eligible when its body matches the query terms, but a document that
        # names the concept in its title/heading or body ranks higher. This keeps
        # retrieval useful for corpora that discuss a concept with slightly
        # different wording (e.g. ``卷积`` for ``卷积运算``).
        anchor_sequences = tuple(
            tokens for anchor in query.anchors if (tokens := tokenize(anchor))
        )

        scored: list[tuple[float, str, KnowledgeChunk]] = []
        for chunk, frequencies, document_length, label_tokens, body_tokens in zip(
            self._corpus.chunks,
            self._term_frequencies,
            self._document_lengths,
            self._label_tokens,
            self._body_tokens,
            strict=True,
        ):
            base = self._score(query_terms, frequencies, document_length)
            if base <= 0:
                continue
            score = base + self._anchor_bonus(
                label_tokens,
                body_tokens,
                anchor_sequences,
            )
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

    @staticmethod
    def _anchor_bonus(
        label_tokens: tuple[str, ...],
        body_tokens: tuple[str, ...],
        anchor_sequences: tuple[tuple[str, ...], ...],
    ) -> float:
        if not anchor_sequences:
            return 0.0
        label_terms = set(label_tokens)
        body_terms = set(body_tokens)
        bonus = 0.0
        for anchor_tokens in anchor_sequences:
            anchor_terms = set(anchor_tokens)
            if anchor_terms & label_terms:
                bonus += 3.0
            elif anchor_terms & body_terms:
                bonus += 1.0
        return bonus


def _search_text(chunk: KnowledgeChunk) -> str:
    return " ".join((chunk.source_title, *chunk.heading_path, chunk.text))


def _label_text(chunk: KnowledgeChunk) -> str:
    return " ".join((chunk.source_title, *chunk.heading_path))


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
