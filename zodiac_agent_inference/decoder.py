"""
decoder.py

Runs a pretrained emotion classifier on horoscope text and maps the
resulting emotion scores into a behavior vector for Unity agents.

The model loads once on first call and is cached for the session.

Requires:
    pip install transformers torch

Model: j-hartmann/emotion-english-distilroberta-base
Emotions: anger, disgust, fear, joy, neutral, sadness, surprise

The behavior vector is the raw decoded output. Blending with a zodiac
sign's static traits (via horoscope_weight from zodiac_schema) is the
responsibility of the behavior engine, not this module.

Usage:
    from decoder import decode, BehaviorVector

    vec = decode("Mars lends its restless heat to the hours ahead...")
    print(vec.dominant_emotion)   # "anger"
    print(vec.speed_mod)          # float in [-1, 1]
    print(vec.to_dict())          # JSON-ready
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Optional dependency guard — fail clearly at decode time, not at import time,
# so the rest of the project can import this module even without torch installed.
#
# hf_pipeline is pre-declared Any so Pylance knows it is always defined.
# TextClassificationPipeline is only needed at type-check time, so it lives
# under TYPE_CHECKING and never runs at runtime.
# ---------------------------------------------------------------------------

hf_pipeline: Any = None
_TRANSFORMERS_AVAILABLE = False
_IMPORT_ERROR: Optional[str] = None

try:
    import torch
    from transformers import pipeline as hf_pipeline
    _TRANSFORMERS_AVAILABLE = True
except ImportError as e:
    _IMPORT_ERROR = str(e)


# ---------------------------------------------------------------------------
# Model config
# ---------------------------------------------------------------------------

_MODEL_ID = "j-hartmann/emotion-english-distilroberta-base"
_EMOTIONS = ["anger", "disgust", "fear", "joy", "neutral", "sadness", "surprise"]

# Lazy-loaded pipeline — None until first decode() call.
# Annotated Any so Pylance accepts the assignment inside _load_pipeline()
# without narrowing its type to None after initialization.
_pipeline: Any = None


def _load_pipeline() -> Any:
    global _pipeline
    if _pipeline is not None:
        return _pipeline
    if not _TRANSFORMERS_AVAILABLE:
        raise RuntimeError(
            f"transformers/torch not available: {_IMPORT_ERROR}\n"
            "Install with: pip install transformers torch"
        )
    _pipeline = hf_pipeline(
        "text-classification",
        model=_MODEL_ID,
        top_k=None,       # return all emotion scores, not just the top one
        device=-1,        # CPU; change to 0 for first CUDA GPU if available
        truncation=True,
        max_length=512,
    )
    return _pipeline


# ---------------------------------------------------------------------------
# Emotion → behavior weight matrix
#
# Each emotion has a signed influence on each behavior dimension.
# Because emotion scores form a probability distribution (sum = 1.0)
# and all weights are in [-1, 1], the weighted sum is bounded in [-1, 1]
# without needing explicit normalization.
#
# Columns:  speed  agit  appr  glow  social  aggr
# ---------------------------------------------------------------------------

_BEHAVIOR_DIMS = ["speed_mod", "agitation", "approach_mod", "glow_mod", "social_mod", "aggression"]

_WEIGHT_MATRIX: dict[str, list[float]] = {
    #              speed   agit   appr   glow   social  aggr
    "anger":    [  0.70,   0.80, -0.30,  0.40,  -0.20,  0.90 ],
    "disgust":  [ -0.20,   0.10, -0.40, -0.30,  -0.50,  0.30 ],
    "fear":     [ -0.50,   0.70, -0.60, -0.30,  -0.60, -0.20 ],
    "joy":      [  0.60,   0.20,  0.70,  0.80,   0.70, -0.50 ],
    "neutral":  [  0.00,   0.00,  0.00,  0.00,   0.00,  0.00 ],
    "sadness":  [ -0.60,  -0.30, -0.50, -0.60,  -0.40, -0.30 ],
    "surprise": [  0.40,   0.50,  0.30,  0.30,   0.20,  0.10 ],
}

# Valence weights — positive emotions push toward +1, negative toward -1.
# Used to compute a single summary axis for simple visualizations.
_VALENCE_WEIGHTS: dict[str, float] = {
    "anger":    -0.60,
    "disgust":  -0.50,
    "fear":     -0.70,
    "joy":       1.00,
    "neutral":   0.00,
    "sadness":  -0.80,
    "surprise":  0.20,
}


# ---------------------------------------------------------------------------
# Output dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BehaviorVector:
    # Raw emotion probability scores from the model (sum to ~1.0)
    emotions:         dict[str, float]
    dominant_emotion: str

    # Summary axis: -1 = strongly negative affect, +1 = strongly positive
    valence:          float

    # Per-dimension behavior modifiers, all in [-1, 1] (agitation and
    # aggression are [0, 1] by convention — clamped before storage)
    speed_mod:        float
    agitation:        float
    approach_mod:     float
    glow_mod:         float
    social_mod:       float
    aggression:       float

    # Source text for display in the Gradio dashboard
    source_text:      str

    def to_dict(self) -> dict:
        """Flat dict suitable for JSON serialization or WebSocket transmission."""
        return {
            "emotions":         self.emotions,
            "dominant_emotion": self.dominant_emotion,
            "valence":          self.valence,
            "speed_mod":        self.speed_mod,
            "agitation":        self.agitation,
            "approach_mod":     self.approach_mod,
            "glow_mod":         self.glow_mod,
            "social_mod":       self.social_mod,
            "aggression":       self.aggression,
            "source_text":      self.source_text,
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _run_model(text: str) -> dict[str, float]:
    """
    Run the emotion classifier and return a {label: score} dict.
    Scores are softmax probabilities and sum to ~1.0.
    """
    pipe = _load_pipeline()
    # With top_k=None, the pipeline returns list[list[dict]] for a single
    # input, so [0] gives list[dict]. Annotate explicitly — Pylance's stubs
    # type the single-input return as list[dict], making [0] a dict, which
    # would cause iteration to yield keys (str) rather than items (dict).
    items: list[dict[str, Any]] = pipe(text)[0]
    return {str(item["label"]): float(item["score"]) for item in items}


def _weighted_sum(scores: dict[str, float], dim_idx: int) -> float:
    """Dot product of emotion scores against one column of _WEIGHT_MATRIX."""
    return sum(
        scores.get(emotion, 0.0) * weights[dim_idx]
        for emotion, weights in _WEIGHT_MATRIX.items()
    )


def _clamp(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def decode(text: str) -> BehaviorVector:
    """
    Decode horoscope text into a behavior vector.

    Args:
        text: Any string — typically a generated horoscope, but can be
              real horoscope text from an external source.

    Returns:
        BehaviorVector with emotion scores and derived behavior parameters.
    """
    scores   = _run_model(text)
    dominant = max(scores, key=scores.__getitem__)

    valence = _clamp(
        sum(scores.get(e, 0.0) * w for e, w in _VALENCE_WEIGHTS.items())
    )

    dims = [_weighted_sum(scores, i) for i in range(len(_BEHAVIOR_DIMS))]

    return BehaviorVector(
        emotions          = {e: round(scores.get(e, 0.0), 4) for e in _EMOTIONS},
        dominant_emotion  = dominant,
        valence           = round(valence, 4),
        speed_mod         = round(_clamp(dims[0]), 4),
        agitation         = round(_clamp(dims[1], 0.0, 1.0), 4),
        approach_mod      = round(_clamp(dims[2]), 4),
        glow_mod          = round(_clamp(dims[3]), 4),
        social_mod        = round(_clamp(dims[4]), 4),
        aggression        = round(_clamp(dims[5], 0.0, 1.0), 4),
        source_text       = text,
    )


def decode_sign(sign_name: str, for_date=None, use_tarot: bool = True) -> BehaviorVector:
    """
    Convenience wrapper: generate today's horoscope for a sign and decode it.

    Args:
        sign_name: Any of the 12 zodiac sign names (case-insensitive).
        for_date:  Date to generate for. Defaults to today.
        use_tarot: Passed through to the horoscope generator.

    Returns:
        BehaviorVector for that sign on that date.
    """
    from horoscope_generator import generate
    text = generate(sign_name, for_date=for_date, use_tarot=use_tarot)
    return decode(text)


# ---------------------------------------------------------------------------
# Sanity check / demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    from datetime import date
    from zodiac_schema import SIGNS

    test_date = date(2026, 6, 4)

    print(f"=== Behavior Vectors for {test_date} ===\n")
    print(f"{'Sign':12s}  {'dominant':10s}  {'valence':>7s}  "
          f"{'speed':>6s}  {'agit':>5s}  {'appr':>5s}  "
          f"{'glow':>5s}  {'social':>6s}  {'aggr':>5s}")
    print("-" * 80)

    for sign in SIGNS:
        vec = decode_sign(sign.name, test_date)
        print(
            f"{sign.name:12s}  {vec.dominant_emotion:10s}  {vec.valence:+.3f}  "
            f"{vec.speed_mod:+.3f}  {vec.agitation:.3f}  {vec.approach_mod:+.3f}  "
            f"{vec.glow_mod:+.3f}  {vec.social_mod:+.3f}  {vec.aggression:.3f}"
        )

    print("\n--- Full vector: Scorpio ---")
    vec = decode_sign("scorpio", test_date)
    d = vec.to_dict()
    d.pop("source_text")
    print(json.dumps(d, indent=2))