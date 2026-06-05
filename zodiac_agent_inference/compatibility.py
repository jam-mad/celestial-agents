"""
compatibility.py

Loads the compatibility chart from compatibility.json and exposes a clean
query interface. The chart itself lives in the JSON file — swap it out to
use a different astrological tradition without touching this code.

Usage:
    from compatibility import get_score, get_relationship, get_affinities

    score = get_score("aries", "libra")         # int, 0-7
    rel   = get_relationship("aries", "libra")  # RelationshipType enum
    top   = get_affinities("scorpio", n=3)      # [(name, score), ...] descending
"""

import json
import os
from enum import Enum
from functools import lru_cache
from typing import NamedTuple


# ---------------------------------------------------------------------------
# Relationship classification
# Thresholds are intentionally generous at the top — 6-7 is a strong bond,
# not reserved only for 7s. Adjust here without touching downstream code.
# ---------------------------------------------------------------------------

class RelationshipType(Enum):
    HARMONIOUS  = "harmonious"   # score 6-7: drawn together, friendly encounter
    NEUTRAL     = "neutral"      # score 3-5: indifferent, passing interaction
    DISCORDANT  = "discordant"   # score 0-2: friction, avoidant behavior


_THRESHOLDS = {
    RelationshipType.HARMONIOUS:  (6, 7),
    RelationshipType.NEUTRAL:     (3, 5),
    RelationshipType.DISCORDANT:  (0, 2),
}


def _classify(score: int) -> RelationshipType:
    for rel, (lo, hi) in _THRESHOLDS.items():
        if lo <= score <= hi:
            return rel
    raise ValueError(f"Score {score} is outside the 0-7 range")


# ---------------------------------------------------------------------------
# Data loading — one read at import time, then cached
# ---------------------------------------------------------------------------

_CHART_PATH = os.path.join(os.path.dirname(__file__), "compatibility.json")


@lru_cache(maxsize=1)
def _load() -> dict:
    with open(_CHART_PATH, "r") as f:
        data = json.load(f)
    # Build a fast (from, to) → score lookup
    signs  = data["signs"]
    chart  = data["chart"]
    lookup = {}
    for from_sign, row in chart.items():
        for to_idx, score in enumerate(row):
            lookup[(from_sign, signs[to_idx])] = score
    data["_lookup"] = lookup
    return data


def _lookup(a: str, b: str) -> int:
    return _load()["_lookup"][(a.lower(), b.lower())]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_score(a: str, b: str) -> int:
    """
    Return the compatibility score from sign a toward sign b (0-7).
    Note: not necessarily symmetric. get_score("aries","libra") may differ
    from get_score("libra","aries").
    """
    return _lookup(a, b)


def get_relationship(a: str, b: str) -> RelationshipType:
    """Classify the relationship from a toward b."""
    return _classify(get_score(a, b))


def get_mutual_score(a: str, b: str) -> float:
    """
    Average of both directions — useful when you want a single symmetric value,
    e.g. for deciding encounter behavior between two agents approaching each other.
    """
    return (get_score(a, b) + get_score(b, a)) / 2.0


def get_mutual_relationship(a: str, b: str) -> RelationshipType:
    """Classify using the mutual (averaged) score."""
    return _classify(round(get_mutual_score(a, b)))


def get_affinities(sign: str, n: int = 12) -> list[tuple[str, int]]:
    """
    Return all signs ranked by their compatibility score toward `sign`,
    descending. Excludes self. Useful for social clustering logic.

    get_affinities("scorpio", n=3) → [("virgo", 7), ("taurus", 6), ...]
    """
    sign = sign.lower()
    signs = _load()["signs"]
    results = [
        (other, get_score(sign, other))
        for other in signs
        if other != sign
    ]
    results.sort(key=lambda x: x[1], reverse=True)
    return results[:n]


def get_row_total(sign: str) -> int:
    """Total outward compatibility of a sign across all others (from the JSON totals)."""
    return _load()["totals"][sign.lower()]


class EncounterContext(NamedTuple):
    sign_a:            str
    sign_b:            str
    score_a_to_b:      int
    score_b_to_a:      int
    mutual_score:      float
    relationship:      RelationshipType
    dominant:          str | None   # whichever sign has the higher directional score, or None if tied


def get_encounter(a: str, b: str) -> EncounterContext:
    """
    Full encounter context between two agents. This is what the behavior engine
    reads when two agents enter each other's interaction_radius.
    """
    a, b       = a.lower(), b.lower()
    ab         = get_score(a, b)
    ba         = get_score(b, a)
    mutual     = (ab + ba) / 2.0
    rel        = _classify(round(mutual))
    dominant   = a if ab > ba else (b if ba > ab else None)
    return EncounterContext(
        sign_a       = a,
        sign_b       = b,
        score_a_to_b = ab,
        score_b_to_a = ba,
        mutual_score = mutual,
        relationship = rel,
        dominant     = dominant,
    )


# ---------------------------------------------------------------------------
# Sanity check / demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from zodiac_schema import SIGNS

    print("=== Compatibility Chart (mutual scores) ===\n")
    names = [s.name for s in SIGNS]

    # header
    print(f"{'':13s}", end="")
    for n in names:
        print(f"{n[:4]:5s}", end="")
    print()

    for a in names:
        print(f"{a:12s} ", end="")
        for b in names:
            if a == b:
                print(f"{'--':5s}", end="")
            else:
                print(f"{get_score(a, b):<5d}", end="")
        print(f"  total={get_row_total(a)}")

    print("\n=== Top 3 affinities ===")
    for sign in names:
        top = get_affinities(sign, n=3)
        top_str = ", ".join(f"{n}({s})" for n, s in top)
        print(f"  {sign:12s} → {top_str}")

    print("\n=== Sample encounter: Aries vs Scorpio ===")
    enc = get_encounter("aries", "scorpio")
    print(f"  {enc.sign_a} → {enc.sign_b}: {enc.score_a_to_b}")
    print(f"  {enc.sign_b} → {enc.sign_a}: {enc.score_b_to_a}")
    print(f"  mutual: {enc.mutual_score}  relationship: {enc.relationship.value}  dominant: {enc.dominant}")