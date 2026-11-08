"""Pure feature and concern calculations for the authenticity review panel."""

from __future__ import annotations

import hashlib
import math
import re
import statistics
from collections.abc import Sequence

WORD_RE = re.compile(r"[A-Za-z']+")
EMBEDDING_DIMENSIONS = 256
SENTENCE_RE = re.compile(r"[.!?]+")
TRANSITIONS = {
    "however",
    "therefore",
    "moreover",
    "furthermore",
    "consequently",
    "in addition",
    "on the other hand",
    "for example",
    "in conclusion",
}
FUNCTION_WORDS = (
    "the",
    "and",
    "to",
    "of",
    "a",
    "in",
    "that",
    "is",
    "it",
    "for",
    "on",
    "with",
    "as",
    "are",
    "was",
    "be",
    "by",
    "this",
    "which",
    "or",
    "from",
    "at",
    "an",
    "not",
    "have",
    "has",
    "but",
    "they",
    "we",
    "you",
    "can",
    "if",
    "then",
    "than",
    "when",
)


def hashing_embedding(text: str, dimensions: int = EMBEDDING_DIMENSIONS) -> list[float]:
    """Stable, local word/phrase hashing vector used with pgvector cosine distance."""
    tokens = [word.lower() for word in WORD_RE.findall(text)]
    features = tokens + [f"{a}_{b}" for a, b in zip(tokens, tokens[1:], strict=False)]
    vector = [0.0] * dimensions
    for feature in features:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest[:4], "big")
        bucket = value % dimensions
        vector[bucket] += 1.0 if digest[4] & 1 else -1.0
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm else vector


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    denominator = math.sqrt(sum(v * v for v in left) * sum(v * v for v in right))
    return (
        sum(a * b for a, b in zip(left, right, strict=True)) / denominator if denominator else 0.0
    )


def criterion_signature(description: str, question_type: str) -> str:
    normalized = " ".join(description.lower().split())
    return hashlib.sha256(f"{question_type}:{normalized}".encode()).hexdigest()


def style_features(text: str) -> dict[str, float]:
    words = [word.lower() for word in WORD_RE.findall(text)]
    sentences = [part for part in SENTENCE_RE.split(text) if part.strip()]
    sentence_lengths = [len(WORD_RE.findall(sentence)) for sentence in sentences]
    paragraphs = [part for part in re.split(r"\n\s*\n", text) if part.strip()]
    paragraph_lengths = [len(WORD_RE.findall(paragraph)) for paragraph in paragraphs]
    n = max(1, len(words))
    features = {
        "mean_sentence_length": statistics.mean(sentence_lengths) if sentence_lengths else 0.0,
        "std_sentence_length": statistics.pstdev(sentence_lengths)
        if len(sentence_lengths) > 1
        else 0.0,
        "type_token_ratio": len(set(words)) / n,
        "mean_word_length": statistics.mean([len(word) for word in words]) if words else 0.0,
        "comma_rate": text.count(",") / n,
        "semicolon_rate": text.count(";") / n,
        "emdash_rate": text.count("—") / n,
        "parenthesis_rate": (text.count("(") + text.count(")")) / n,
        "paragraph_length_variance": statistics.pvariance(paragraph_lengths)
        if len(paragraph_lengths) > 1
        else 0.0,
        "passive_voice_rate": len(
            re.findall(r"\b(?:am|is|are|was|were|be|been|being)\s+\w+ed\b", text.lower())
        )
        / n,
        "transition_rate": sum(words.count(term) for term in TRANSITIONS if " " not in term) / n,
    }
    for word in FUNCTION_WORDS:
        features[f"function:{word}"] = words.count(word) / n
    return features


def style_drift(features: dict[str, float], baseline: dict[str, dict[str, float]]) -> float | None:
    if not baseline:
        return None
    values = []
    for name, value in features.items():
        prior = baseline.get(name)
        if not prior:
            continue
        stddev = max(float(prior.get("std", 0.0)), 0.1)
        values.append(min(3.0, abs(value - float(prior.get("mean", 0.0))) / stddev))
    return max(values) if values else None


def concern_level(signals: Sequence[dict], followup_passed: bool = False) -> str:
    available = sum(signal.get("status") in {"raised", "neutral"} for signal in signals)
    score = sum(
        float(signal.get("weight", 0)) for signal in signals if signal.get("status") == "raised"
    )
    if available < 2:
        level = "insufficient_evidence"
    elif score >= 6:
        level = "high"
    elif score >= 3:
        level = "medium"
    else:
        level = "low"
    if followup_passed and level == "high":
        return "medium"
    return level


def trigram_jaccard(left: str, right: str) -> float:
    def grams(text: str) -> set[tuple[str, ...]]:
        tokens = [word.lower() for word in WORD_RE.findall(text)]
        return set(zip(tokens, tokens[1:], tokens[2:], strict=False))

    a, b = grams(left), grams(right)
    return len(a & b) / len(a | b) if a and b else 0.0


def raised_signal(signal_id: str, detail: str, weight: float) -> dict:
    return {"id": signal_id, "status": "raised", "detail": detail, "weight": weight}


def neutral_signal(signal_id: str, detail: str, weight: float) -> dict:
    return {"id": signal_id, "status": "neutral", "detail": detail, "weight": weight}


def unavailable_signal(signal_id: str, detail: str, weight: float) -> dict:
    return {"id": signal_id, "status": "not_available", "detail": detail, "weight": weight}
