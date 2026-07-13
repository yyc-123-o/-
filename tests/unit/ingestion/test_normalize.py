import re

from skillforge_kb.ingestion.normalize import (
    is_near_duplicate,
    jaccard_similarity,
    ngrams,
    normalize_text,
    sha256_text,
)


def test_normalization_is_stable_across_line_endings_and_unicode_spaces() -> None:
    left = "Logistic\r\nregression\u00a0model"
    right = "Logistic\nregression model"
    assert normalize_text(left) == normalize_text(right)
    assert sha256_text(left) == sha256_text(right)


def test_normalization_applies_nfkc_and_deterministic_whitespace_rules() -> None:
    text = "ＡＢＣ\t  model   \r\n\r\n\r\nNext\u00a0line  "

    assert normalize_text(text) == "ABC model\n\nNext line"


def test_sha256_text_returns_lowercase_digest_and_changes_with_content() -> None:
    digest = sha256_text("logistic regression")

    assert re.fullmatch(r"[0-9a-f]{64}", digest)
    assert digest != sha256_text("linear regression")


def test_ngrams_normalize_case_and_return_overlapping_windows() -> None:
    assert ngrams("ＡBCDE", width=3) == {"abc", "bcd", "cde"}


def test_jaccard_similarity_uses_character_ngram_intersection_over_union() -> None:
    assert jaccard_similarity("abcdef", "abcdef") == 1.0
    assert jaccard_similarity("abcdef", "uvwxyz") == 0.0
    assert jaccard_similarity("", "") == 1.0


def test_near_duplicate_classification_uses_inclusive_threshold() -> None:
    left = "Logistic regression estimates conditional class probability."
    right = "Logistic regression estimates conditional class probabilities."
    score = jaccard_similarity(left, right)

    assert 0.0 < score < 1.0
    assert is_near_duplicate(left, right, threshold=score)
    assert not is_near_duplicate(left, right, threshold=score + 0.01)


def test_near_duplicate_default_threshold_distinguishes_unrelated_text() -> None:
    canonical = "Logistic regression estimates conditional class probability."

    assert is_near_duplicate(canonical, canonical.upper())
    assert not is_near_duplicate(canonical, "Decision trees split features recursively.")
