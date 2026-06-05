"""
zodiac_schema.py

Static per-sign traits for the Zodiac Behavior Engine.
Derived from the original C# Zodiac fighting-game codebase.

These traits form the STATIC layer of the two-layer behavior model.
Every agent reads this once at startup; the daily horoscope decoder
modulates on top of it, never replaces it.

Usage:
    from zodiac_schema import SIGNS, get_sign, Element, Modality, Polarity

    aries = get_sign("aries")
    print(aries.base_speed)         # float, derived from element
    print(aries.core_drive)         # str, the element's energy type
    print(aries.behavioral_mode)    # str, how the modality expresses that energy
    print(aries.temperament)        # str, the combined (element + modality) personality label
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Enumerations — mirror the C# enums, Python-style
# ---------------------------------------------------------------------------

class Element(Enum):
    FIRE  = "fire"
    EARTH = "earth"
    AIR   = "air"
    WATER = "water"


class Modality(Enum):
    CARDINAL = "cardinal"
    FIXED    = "fixed"
    MUTABLE  = "mutable"


class Polarity(Enum):
    POSITIVE = "positive"   # outward, expressive, active
    NEGATIVE = "negative"   # inward, receptive, reflective


class Planet(Enum):
    SUN     = "sun"
    MERCURY = "mercury"
    VENUS   = "venus"
    MOON    = "moon"
    MARS    = "mars"
    JUPITER = "jupiter"
    SATURN  = "saturn"
    NEPTUNE = "neptune"
    URANUS  = "uranus"
    PLUTO   = "pluto"
    NEUTRAL = "neutral"


class Star(Enum):
    HAMAL          = "hamal"
    ALDEBARAN      = "aldebaran"
    POLLUX         = "pollux"
    AL_TARAF       = "al_taraf"
    REGULUS        = "regulus"
    SPICA          = "spica"
    ZUBENESCHAMALI = "zubeneschamali"
    ANTARES        = "antares"
    KAUS_AUSTRALIS = "kaus_australis"
    DENEB_ALGEDI   = "deneb_algedi"
    SADALSUUD      = "sadalsuud"
    ETA_PISCIUM    = "eta_piscium"


# ---------------------------------------------------------------------------
# Element-derived physical constants
# Sourced from: Zodiac.cs MovementCost switch block.
# In the original game, lower MovementCost = more mobile.
# We invert and normalize so higher base_speed = faster agent.
#
# Original costs: AIR=2, WATER=4, FIRE=8, EARTH=16
# Normalized speed:
#   AIR   → 1.00   (most mobile)
#   WATER → 0.50
#   FIRE  → 0.75   (bursty — fast but erratic)
#   EARTH → 0.20   (slowest, most grounded)
#
# core_drive:   what KIND of energy the element is (not a full personality).
#               Element alone is insufficient to describe temperament — modality
#               determines how that energy manifests. core_drive feeds into the
#               combined (element + modality) temperament lookup below.
# orbit_radius: how far an agent drifts from its anchor point at rest.
# restlessness: how often it changes direction unprompted (0.0-1.0).
# ---------------------------------------------------------------------------

_ELEMENT_TRAITS = {
    Element.AIR: {
        "base_speed":    1.00,
        "orbit_radius":  2.5,
        "restlessness":  0.85,
        "core_drive":    "connection",
        "domain_weight": {"communication": 1.4, "travel": 1.3, "creativity": 1.2,
                          "career": 1.0, "love": 1.0, "health": 0.8, "family": 0.7},
    },
    Element.WATER: {
        "base_speed":    0.50,
        "orbit_radius":  1.8,
        "restlessness":  0.55,
        "core_drive":    "feeling",
        "domain_weight": {"love": 1.5, "family": 1.4, "health": 1.2,
                          "creativity": 1.1, "career": 0.8, "travel": 0.7, "communication": 0.9},
    },
    Element.FIRE: {
        "base_speed":    0.75,
        "orbit_radius":  2.0,
        "restlessness":  0.80,
        "core_drive":    "action",
        "domain_weight": {"career": 1.4, "love": 1.3, "travel": 1.2,
                          "creativity": 1.1, "health": 1.0, "family": 0.8, "communication": 0.9},
    },
    Element.EARTH: {
        "base_speed":    0.20,
        "orbit_radius":  0.8,
        "restlessness":  0.20,
        "core_drive":    "stability",
        "domain_weight": {"career": 1.4, "family": 1.3, "health": 1.2,
                          "love": 1.0, "creativity": 0.9, "communication": 0.8, "travel": 0.6},
    },
}

# ---------------------------------------------------------------------------
# Modality-derived behavioral constants
# behavioral_mode: how the element's energy is expressed — feeds the combined
#                  temperament lookup alongside core_drive.
# Cardinal: initiates — higher tendency to approach others, react quickly.
# Fixed:    sustains  — low variance day-to-day, resists change.
# Mutable:  adapts    — high variance, easily swayed by daily horoscope.
# ---------------------------------------------------------------------------

_MODALITY_TRAITS = {
    Modality.CARDINAL: {
        "behavioral_mode":  "initiating",
        "approach_bias":    0.75,   # likelihood to move toward another agent on encounter
        "mood_inertia":     0.30,   # how much yesterday's mood carries into today (0=none)
        "horoscope_weight": 0.80,   # how strongly the decoded vector overrides static traits
    },
    Modality.FIXED: {
        "behavioral_mode":  "sustaining",
        "approach_bias":    0.40,
        "mood_inertia":     0.80,
        "horoscope_weight": 0.40,
    },
    Modality.MUTABLE: {
        "behavioral_mode":  "adapting",
        "approach_bias":    0.55,
        "mood_inertia":     0.10,
        "horoscope_weight": 1.00,
    },
}

# ---------------------------------------------------------------------------
# Temperament — derived from (Element, Modality) pairs.
# This is the first place a sign gets a personality distinct from its element-
# siblings. All three Fire signs share core_drive="action", but:
#   Aries (Fire + Cardinal) = assertive   — action that initiates
#   Leo   (Fire + Fixed)    = expressive  — action that performs/sustains
#   Sagittarius (Fire+Mutable)= exploratory — action that wanders
# Labels are kept to one word to stay mechanically useful as horoscope weights.
# ---------------------------------------------------------------------------

_TEMPERAMENT: dict[tuple[Element, Modality], str] = {
    # Fire
    (Element.FIRE,  Modality.CARDINAL): "assertive",
    (Element.FIRE,  Modality.FIXED):    "expressive",
    (Element.FIRE,  Modality.MUTABLE):  "exploratory",
    # Earth
    (Element.EARTH, Modality.CARDINAL): "ambitious",
    (Element.EARTH, Modality.FIXED):    "reliable",
    (Element.EARTH, Modality.MUTABLE):  "analytical",
    # Air
    (Element.AIR,   Modality.CARDINAL): "diplomatic",
    (Element.AIR,   Modality.FIXED):    "idealistic",
    (Element.AIR,   Modality.MUTABLE):  "adaptable",
    # Water
    (Element.WATER, Modality.CARDINAL): "nurturing",
    (Element.WATER, Modality.FIXED):    "intense",
    (Element.WATER, Modality.MUTABLE):  "empathetic",
}

# ---------------------------------------------------------------------------
# Polarity-derived constants
# Positive (yang): outward energy — brighter base glow, wider interaction radius.
# Negative (yin):  inward energy  — subtler glow, tighter personal space.
# ---------------------------------------------------------------------------

_POLARITY_TRAITS = {
    Polarity.POSITIVE: {
        "base_glow":          0.75,
        "interaction_radius": 3.5,
        "social_bias":        0.70,   # prefers proximity to other agents
    },
    Polarity.NEGATIVE: {
        "base_glow":          0.35,
        "interaction_radius": 2.0,
        "social_bias":        0.35,
    },
}

# ---------------------------------------------------------------------------
# Planet traits — used to weight horoscope domain tables
# Brightness/influence scale 0.0-1.0 (subjective, based on astrological tradition
# and rough visual magnitude — can be tuned as a data file later)
# ---------------------------------------------------------------------------

_PLANET_TRAITS = {
    Planet.SUN:     {"influence": 1.00, "domain_affinity": "career"},
    Planet.MOON:    {"influence": 0.90, "domain_affinity": "family"},
    Planet.VENUS:   {"influence": 0.75, "domain_affinity": "love"},
    Planet.MARS:    {"influence": 0.80, "domain_affinity": "conflict"},
    Planet.MERCURY: {"influence": 0.65, "domain_affinity": "communication"},
    Planet.JUPITER: {"influence": 0.85, "domain_affinity": "travel"},
    Planet.SATURN:  {"influence": 0.70, "domain_affinity": "career"},
    Planet.NEPTUNE: {"influence": 0.55, "domain_affinity": "creativity"},
    Planet.URANUS:  {"influence": 0.60, "domain_affinity": "change"},
    Planet.PLUTO:   {"influence": 0.50, "domain_affinity": "transformation"},
    Planet.NEUTRAL: {"influence": 0.00, "domain_affinity": None},
}

# Star apparent magnitude (lower = brighter in astronomy convention).
# Used as a scalar on the sign's visual intensity / glow ceiling.
# Source: standard astronomical catalogs.
_STAR_MAGNITUDE = {
    Star.HAMAL:          2.00,   # Aries
    Star.ALDEBARAN:      0.85,   # Taurus  — very bright
    Star.POLLUX:         1.14,   # Gemini  — bright
    Star.AL_TARAF:       3.53,   # Cancer  — dim
    Star.REGULUS:        1.35,   # Leo     — bright
    Star.SPICA:          0.97,   # Virgo   — very bright
    Star.ZUBENESCHAMALI: 2.61,   # Libra
    Star.ANTARES:        1.06,   # Scorpio — very bright
    Star.KAUS_AUSTRALIS: 1.85,   # Sagittarius
    Star.DENEB_ALGEDI:   2.85,   # Capricorn
    Star.SADALSUUD:      2.87,   # Aquarius
    Star.ETA_PISCIUM:    3.62,   # Pisces  — dim
}

# Normalize magnitude to a 0-1 glow multiplier.
# Brightest star (Aldebaran, 0.85) → 1.0; dimmest (Eta Piscium, 3.62) → ~0.0
_MAG_MIN = min(_STAR_MAGNITUDE.values())
_MAG_MAX = max(_STAR_MAGNITUDE.values())

def _mag_to_glow(magnitude: float) -> float:
    """Invert and normalize: brighter star (lower magnitude) → higher glow."""
    return round(1.0 - (magnitude - _MAG_MIN) / (_MAG_MAX - _MAG_MIN), 3)


# ---------------------------------------------------------------------------
# Core dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ZodiacSign:
    # Identity
    name:        str
    index:       int            # matches C# Sign enum order (ARIES=0 .. PISCES=11)

    # Astrological attributes (from individual sign .cs files)
    element:     Element
    modality:    Modality
    polarity:    Polarity
    ruler:       Planet
    exaltation:  Planet
    detriment:   Planet
    fall:        Planet
    star:        Star
    solar_duration: int         # days the sun spends in this sign (from SolarDuration)

    # Derived static behavior values (computed at construction, not changed at runtime)
    base_speed:         float = field(init=False)
    orbit_radius:       float = field(init=False)
    restlessness:       float = field(init=False)
    core_drive:         str   = field(init=False)   # element's energy type
    behavioral_mode:    str   = field(init=False)   # modality's expression style
    temperament:        str   = field(init=False)   # combined (element + modality) label
    domain_weight:      dict  = field(init=False)
    approach_bias:      float = field(init=False)
    mood_inertia:       float = field(init=False)
    horoscope_weight:   float = field(init=False)
    base_glow:          float = field(init=False)
    interaction_radius: float = field(init=False)
    social_bias:        float = field(init=False)
    star_glow:          float = field(init=False)
    ruler_influence:    float = field(init=False)
    ruler_domain:       Optional[str] = field(init=False)

    def __post_init__(self):
        et = _ELEMENT_TRAITS[self.element]
        mt = _MODALITY_TRAITS[self.modality]
        pt = _POLARITY_TRAITS[self.polarity]
        rt = _PLANET_TRAITS[self.ruler]

        object.__setattr__(self, "base_speed",         et["base_speed"])
        object.__setattr__(self, "orbit_radius",        et["orbit_radius"])
        object.__setattr__(self, "restlessness",        et["restlessness"])
        object.__setattr__(self, "core_drive",          et["core_drive"])
        object.__setattr__(self, "behavioral_mode",     mt["behavioral_mode"])
        object.__setattr__(self, "temperament",         _TEMPERAMENT[(self.element, self.modality)])
        object.__setattr__(self, "domain_weight",       et["domain_weight"])
        object.__setattr__(self, "approach_bias",       mt["approach_bias"])
        object.__setattr__(self, "mood_inertia",        mt["mood_inertia"])
        object.__setattr__(self, "horoscope_weight",    mt["horoscope_weight"])
        object.__setattr__(self, "base_glow",           pt["base_glow"])
        object.__setattr__(self, "interaction_radius",  pt["interaction_radius"])
        object.__setattr__(self, "social_bias",         pt["social_bias"])
        object.__setattr__(self, "star_glow",           _mag_to_glow(_STAR_MAGNITUDE[self.star]))
        object.__setattr__(self, "ruler_influence",     rt["influence"])
        object.__setattr__(self, "ruler_domain",        rt["domain_affinity"])

    def to_dict(self) -> dict:
        """Flat dict for JSON serialization or WebSocket transmission."""
        return {
            "name":               self.name,
            "index":              self.index,
            "element":            self.element.value,
            "modality":           self.modality.value,
            "polarity":           self.polarity.value,
            "ruler":              self.ruler.value,
            "exaltation":         self.exaltation.value,
            "detriment":          self.detriment.value,
            "fall":               self.fall.value,
            "star":               self.star.value,
            "solar_duration":     self.solar_duration,
            "base_speed":         self.base_speed,
            "orbit_radius":       self.orbit_radius,
            "restlessness":       self.restlessness,
            "core_drive":         self.core_drive,
            "behavioral_mode":    self.behavioral_mode,
            "temperament":        self.temperament,
            "domain_weight":      self.domain_weight,
            "approach_bias":      self.approach_bias,
            "mood_inertia":       self.mood_inertia,
            "horoscope_weight":   self.horoscope_weight,
            "base_glow":          self.base_glow,
            "interaction_radius": self.interaction_radius,
            "social_bias":        self.social_bias,
            "star_glow":          self.star_glow,
            "ruler_influence":    self.ruler_influence,
            "ruler_domain":       self.ruler_domain,
        }


# ---------------------------------------------------------------------------
# Sign table — data verbatim from the 12 .cs files
# Order matches the C# Sign enum (ARIES=0 .. PISCES=11)
# ---------------------------------------------------------------------------

SIGNS: list[ZodiacSign] = [
    ZodiacSign(
        name="aries", index=0,
        element=Element.FIRE, modality=Modality.CARDINAL, polarity=Polarity.POSITIVE,
        ruler=Planet.MARS, exaltation=Planet.SUN, detriment=Planet.VENUS, fall=Planet.SATURN,
        star=Star.HAMAL, solar_duration=25,
    ),
    ZodiacSign(
        name="taurus", index=1,
        element=Element.EARTH, modality=Modality.FIXED, polarity=Polarity.NEGATIVE,
        ruler=Planet.VENUS, exaltation=Planet.MOON, detriment=Planet.MARS, fall=Planet.NEUTRAL,
        star=Star.ALDEBARAN, solar_duration=37,
    ),
    ZodiacSign(
        name="gemini", index=2,
        element=Element.AIR, modality=Modality.MUTABLE, polarity=Polarity.POSITIVE,
        ruler=Planet.MERCURY, exaltation=Planet.NEUTRAL, detriment=Planet.JUPITER, fall=Planet.NEUTRAL,
        star=Star.POLLUX, solar_duration=31,
    ),
    ZodiacSign(
        name="cancer", index=3,
        element=Element.WATER, modality=Modality.CARDINAL, polarity=Polarity.NEGATIVE,
        ruler=Planet.MOON, exaltation=Planet.JUPITER, detriment=Planet.SATURN, fall=Planet.MARS,
        star=Star.AL_TARAF, solar_duration=20,
    ),
    ZodiacSign(
        name="leo", index=4,
        element=Element.FIRE, modality=Modality.FIXED, polarity=Polarity.POSITIVE,
        ruler=Planet.SUN, exaltation=Planet.NEUTRAL, detriment=Planet.SATURN, fall=Planet.NEUTRAL,
        star=Star.REGULUS, solar_duration=37,
    ),
    ZodiacSign(
        name="virgo", index=5,
        element=Element.EARTH, modality=Modality.MUTABLE, polarity=Polarity.NEGATIVE,
        ruler=Planet.MERCURY, exaltation=Planet.NEUTRAL, detriment=Planet.JUPITER, fall=Planet.VENUS,
        star=Star.SPICA, solar_duration=45,
    ),
    ZodiacSign(
        name="libra", index=6,
        element=Element.AIR, modality=Modality.CARDINAL, polarity=Polarity.POSITIVE,
        ruler=Planet.VENUS, exaltation=Planet.SATURN, detriment=Planet.MARS, fall=Planet.SUN,
        star=Star.ZUBENESCHAMALI, solar_duration=23,
    ),
    ZodiacSign(
        name="scorpio", index=7,
        element=Element.WATER, modality=Modality.FIXED, polarity=Polarity.NEGATIVE,
        ruler=Planet.MARS, exaltation=Planet.NEUTRAL, detriment=Planet.VENUS, fall=Planet.MOON,
        star=Star.ANTARES, solar_duration=25,
    ),
    ZodiacSign(
        name="sagittarius", index=8,
        element=Element.FIRE, modality=Modality.MUTABLE, polarity=Polarity.POSITIVE,
        ruler=Planet.JUPITER, exaltation=Planet.NEUTRAL, detriment=Planet.MERCURY, fall=Planet.NEUTRAL,
        star=Star.KAUS_AUSTRALIS, solar_duration=32,
    ),
    ZodiacSign(
        name="capricorn", index=9,
        element=Element.EARTH, modality=Modality.CARDINAL, polarity=Polarity.NEGATIVE,
        ruler=Planet.SATURN, exaltation=Planet.MARS, detriment=Planet.MOON, fall=Planet.JUPITER,
        star=Star.DENEB_ALGEDI, solar_duration=28,
    ),
    ZodiacSign(
        name="aquarius", index=10,
        element=Element.AIR, modality=Modality.FIXED, polarity=Polarity.POSITIVE,
        ruler=Planet.SATURN, exaltation=Planet.NEUTRAL, detriment=Planet.SUN, fall=Planet.NEUTRAL,
        star=Star.SADALSUUD, solar_duration=24,
    ),
    ZodiacSign(
        name="pisces", index=11,
        element=Element.WATER, modality=Modality.MUTABLE, polarity=Polarity.NEGATIVE,
        ruler=Planet.JUPITER, exaltation=Planet.VENUS, detriment=Planet.NEUTRAL, fall=Planet.SATURN,
        star=Star.ETA_PISCIUM, solar_duration=38,
    ),
]

# Fast lookup by name
_BY_NAME: dict[str, ZodiacSign] = {s.name: s for s in SIGNS}


def get_sign(name: str) -> ZodiacSign:
    """Return a ZodiacSign by lowercase name. Raises KeyError if not found."""
    return _BY_NAME[name.lower()]


def get_sign_by_index(index: int) -> ZodiacSign:
    """Return a ZodiacSign by its enum index (0=Aries .. 11=Pisces)."""
    return SIGNS[index]


# ---------------------------------------------------------------------------
# Quick sanity check / demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    print("=== Zodiac Static Trait Schema ===\n")
    for sign in SIGNS:
        print(
            f"{sign.name.capitalize():12s}  "
            f"elem={sign.element.value:5s}  "
            f"mod={sign.modality.value:8s}  "
            f"drive={sign.core_drive:9s}  "
            f"mode={sign.behavioral_mode:10s}  "
            f"temperament={sign.temperament}"
        )

    print()
    for sign in SIGNS:
        print(
            f"{sign.name.capitalize():12s}  "
            f"speed={sign.base_speed:.2f}  "
            f"glow={sign.base_glow:.2f}  "
            f"star_glow={sign.star_glow:.3f}  "
            f"horoscope_wt={sign.horoscope_weight:.2f}  "
            f"solar_dur={sign.solar_duration}"
        )

    print("\n--- full dicts ---")
    for s in SIGNS:
        print(json.dumps(get_sign(s.name).to_dict(), indent=2))