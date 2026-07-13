import hashlib
import re
import unicodedata


def normalize_text(text: str) -> str:
    value = unicodedata.normalize("NFKC", text).replace("\r\n", "\n").replace("\r", "\n")
    value = value.replace("\u00a0", " ")
    value = "\n".join(line.rstrip() for line in value.split("\n"))
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def sha256_text(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def ngrams(text: str, width: int = 5) -> set[str]:
    value = normalize_text(text).casefold()
    return {value[index : index + width] for index in range(max(0, len(value) - width + 1))}


def jaccard_similarity(left: str, right: str) -> float:
    left_grams = ngrams(left)
    right_grams = ngrams(right)
    union = left_grams | right_grams
    if not union:
        return 1.0
    return len(left_grams & right_grams) / len(union)


def is_near_duplicate(left: str, right: str, threshold: float = 0.92) -> bool:
    return jaccard_similarity(left, right) >= threshold
