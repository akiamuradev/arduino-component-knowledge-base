"""Versioned, deterministic fuzzy score with bounded safe evidence."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from hashlib import sha256

ALGORITHM_VERSION = "fuzzy-v1"
CANDIDATE_THRESHOLD = 0.35
HIGH_SCORE_THRESHOLD = 0.70
_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)


@dataclass(frozen=True, slots=True)
class ComponentSignals:
    title: str
    aliases: tuple[str, ...] = ()
    manufacturer: str | None = None
    model: str | None = None
    specifications: tuple[tuple[str, str], ...] = ()
    text_hashes: frozenset[str] = frozenset()
    media_sha256: frozenset[str] = frozenset()
    media_phashes: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class ScoreResult:
    score: float
    evidence: dict[str, object]


def text_hashes(*values: str | None) -> frozenset[str]:
    return frozenset(
        sha256(normalized.encode()).hexdigest()
        for value in values
        if (normalized := normalize_text(value))
    )


def score_pair(left: ComponentSignals, right: ComponentSignals, trigram: float) -> ScoreResult:
    trigram_score = _bounded(trigram)
    token_score = _jaccard(_tokens(left), _tokens(right))
    identity_score = _identity_similarity(left, right)
    spec_score, spec_conflicts = _spec_similarity(left.specifications, right.specifications)
    text_score = _jaccard(left.text_hashes, right.text_hashes)
    media_sha_score = _jaccard(left.media_sha256, right.media_sha256)
    phash_score = _phash_similarity(left.media_phashes, right.media_phashes)
    penalties: dict[str, float] = {}
    if _conflicts(left.manufacturer, right.manufacturer):
        penalties["manufacturer_conflict"] = 0.15
    if _conflicts(left.model, right.model):
        penalties["model_conflict"] = 0.25
    if spec_conflicts:
        penalties["spec_conflicts"] = min(0.20, 0.05 * spec_conflicts)
    weighted_signals = {
        "title_trigram": (trigram_score, 0.25, True),
        "token_similarity": (token_score, 0.20, True),
        "identity_similarity": (
            identity_score,
            0.15,
            _has_comparable_identity(left, right),
        ),
        "spec_fingerprint": (
            spec_score,
            0.15,
            bool(left.specifications and right.specifications),
        ),
        "text_hashes": (text_score, 0.10, bool(left.text_hashes and right.text_hashes)),
        "media_sha256": (
            media_sha_score,
            0.10,
            bool(left.media_sha256 and right.media_sha256),
        ),
        "media_phash": (
            phash_score,
            0.05,
            bool(left.media_phashes and right.media_phashes),
        ),
    }
    active_weight = sum(weight for _, weight, active in weighted_signals.values() if active)
    weighted = (
        sum(value * weight for value, weight, active in weighted_signals.values() if active)
        / active_weight
    )
    final = _bounded(weighted - sum(penalties.values()))
    evidence: dict[str, object] = {
        "algorithm_version": ALGORITHM_VERSION,
        "signals": {
            "title_trigram": round(trigram_score, 4),
            "token_similarity": round(token_score, 4),
            "identity_similarity": round(identity_score, 4),
            "spec_fingerprint": round(spec_score, 4),
            "text_hashes": round(text_score, 4),
            "media_sha256": round(media_sha_score, 4),
            "media_phash": round(phash_score, 4),
        },
        "penalties": penalties,
        "spec_conflict_count": spec_conflicts,
        "active_weights": {
            name: weight for name, (_, weight, active) in weighted_signals.items() if active
        },
    }
    return ScoreResult(round(final, 4), evidence)


def normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(_TOKEN.findall(normalized))


def specification_fingerprint(values: tuple[tuple[str, str], ...]) -> frozenset[str]:
    return frozenset(
        sha256(f"{normalize_text(key)}\x00{normalize_text(value)}".encode()).hexdigest()
        for key, value in values
        if normalize_text(key) and normalize_text(value)
    )


def _tokens(signals: ComponentSignals) -> frozenset[str]:
    return frozenset(
        token
        for value in (
            signals.title,
            *signals.aliases,
            signals.manufacturer or "",
            signals.model or "",
        )
        for token in normalize_text(value).split()
    )


def _identity_similarity(left: ComponentSignals, right: ComponentSignals) -> float:
    comparisons = [
        normalize_text(left_value) == normalize_text(right_value)
        for left_value, right_value in (
            (left.manufacturer, right.manufacturer),
            (left.model, right.model),
        )
        if normalize_text(left_value) and normalize_text(right_value)
    ]
    return sum(comparisons) / len(comparisons) if comparisons else 0.0


def _has_comparable_identity(left: ComponentSignals, right: ComponentSignals) -> bool:
    return any(
        normalize_text(left_value) and normalize_text(right_value)
        for left_value, right_value in (
            (left.manufacturer, right.manufacturer),
            (left.model, right.model),
        )
    )


def _spec_similarity(
    left: tuple[tuple[str, str], ...], right: tuple[tuple[str, str], ...]
) -> tuple[float, int]:
    left_values = {normalize_text(key): normalize_text(value) for key, value in left}
    right_values = {normalize_text(key): normalize_text(value) for key, value in right}
    shared_keys = left_values.keys() & right_values.keys()
    conflicts = sum(left_values[key] != right_values[key] for key in shared_keys)
    return _jaccard(specification_fingerprint(left), specification_fingerprint(right)), conflicts


def _conflicts(left: str | None, right: str | None) -> bool:
    normalized_left = normalize_text(left)
    normalized_right = normalize_text(right)
    return bool(normalized_left and normalized_right and normalized_left != normalized_right)


def _phash_similarity(left: frozenset[str], right: frozenset[str]) -> float:
    similarities: list[float] = []
    for first in left:
        for second in right:
            if len(first) != 16 or len(second) != 16:
                continue
            try:
                distance = (int(first, 16) ^ int(second, 16)).bit_count()
            except ValueError:
                continue
            similarities.append(1.0 - (distance / 64))
    return max(similarities, default=0.0)


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _bounded(value: float) -> float:
    return max(0.0, min(1.0, value))
