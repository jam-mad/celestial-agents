"""
horoscope_generator.py

Procedural daily horoscope generator for the Zodiac Behavior Engine.

Each horoscope is deterministic for a given (sign, date) pair — the same
sign gets the same horoscope all day, a different one each day, and the
result is fully reproducible. Pass real horoscope text later if you want,
but this module has no external dependency.

The astrology IS the generation ruleset:
  - Element    → which domains are weighted, atmospheric voice
  - Modality   → advice posture (Cardinal acts, Fixed holds, Mutable waits)
  - Polarity   → sentence energy (outward vs inward framing)
  - Ruler      → which domain gets a secondary boost
  - Temperament → colors event vocabulary selection

Output is 3-5 sentences (~80-180 words), structured as:
  [opener] [domain + event] [elaboration] [advice] [timing]

Usage:
    from horoscope_generator import generate, generate_for_today

    text = generate("scorpio", date(2026, 6, 4))
    text = generate_for_today("gemini")          # uses today's date
    text = generate("leo", use_tarot=False)      # skip tarot flavor layer
"""

import hashlib
import random
from datetime import date, datetime
from typing import Optional

from zodiac_schema import get_sign, ZodiacSign, Element, Modality, Polarity


# ===========================================================================
# SEEDING
# ===========================================================================

def _make_rng(sign: str, d: date) -> random.Random:
    """
    Deterministic RNG seeded from sign name + date.
    Same sign + same date → same sequence every time, guaranteed.
    """
    key = f"{sign.lower()}:{d.isoformat()}"
    seed_int = int(hashlib.sha256(key.encode()).hexdigest(), 16)
    return random.Random(seed_int)


# ===========================================================================
# VALENCE
# Three tones a horoscope can take. Drawn once per sign per day.
# Mutable signs have equal probability across all three (they swing more).
# Fixed signs are weighted away from turbulent (they resist extremes).
# Cardinal signs skew toward active/engaged tones.
# ===========================================================================

class Valence:
    BRIGHT    = "bright"     # opportunity, ease, forward motion
    SHADOWED  = "shadowed"   # caution, complexity, a cost to pay
    TURBULENT = "turbulent"  # tension, disruption, forced change


_VALENCE_WEIGHTS = {
    Modality.CARDINAL: {Valence.BRIGHT: 0.45, Valence.SHADOWED: 0.35, Valence.TURBULENT: 0.20},
    Modality.FIXED:    {Valence.BRIGHT: 0.35, Valence.SHADOWED: 0.45, Valence.TURBULENT: 0.20},
    Modality.MUTABLE:  {Valence.BRIGHT: 0.33, Valence.SHADOWED: 0.34, Valence.TURBULENT: 0.33},
}

def _pick_valence(sign: ZodiacSign, rng: random.Random) -> str:
    weights = _VALENCE_WEIGHTS[sign.modality]
    return rng.choices(
        list(weights.keys()),
        weights=list(weights.values()),
        k=1
    )[0]


# ===========================================================================
# DOMAIN SELECTION
# Base weights come from zodiac_schema domain_weight.
# Ruler gets an additive boost on its affinity domain.
# ===========================================================================

_ALL_DOMAINS = [
    "love", "career", "money", "health", "family",
    "creativity", "travel", "communication", "spirituality", "transformation"
]

# Domains not in the schema's domain_weight get a default weight of 1.0
_DOMAIN_DEFAULTS = {d: 1.0 for d in _ALL_DOMAINS}

def _pick_domain(sign: ZodiacSign, rng: random.Random) -> str:
    weights = dict(_DOMAIN_DEFAULTS)
    # Apply element-based domain weights from the schema
    for domain, w in sign.domain_weight.items():
        if domain in weights:
            weights[domain] = w
    # Ruler gives a secondary boost to its affinity domain
    if sign.ruler_domain and sign.ruler_domain in weights:
        weights[sign.ruler_domain] = weights[sign.ruler_domain] * (1.0 + sign.ruler_influence * 0.5)
    domains = list(weights.keys())
    ws      = [weights[d] for d in domains]
    return rng.choices(domains, weights=ws, k=1)[0]


# ===========================================================================
# TAROT ARCHETYPES
# Optional event-vocabulary layer. One card is "drawn" per sign per day
# (from the seed, so it's consistent). The card contributes a short phrase
# woven into the domain sentence. Cards are tagged by valence affinity so
# the draw is filtered to match the day's tone.
# ===========================================================================

_TAROT = {
    Valence.BRIGHT: [
        ("The Star",            "a renewal you didn't dare hope for is closer than it appears"),
        ("The Sun",             "clarity arrives where confusion has held you back"),
        ("The World",           "a long arc finally reaches its completion"),
        ("The Fool",            "a leap of faith lands on surprisingly solid ground"),
        ("The Lovers",          "a significant connection deepens or a meaningful choice clarifies"),
        ("Wheel of Fortune",    "fortune rotates in your favor"),
        ("The Empress",         "abundance in an unexpected form finds its way to you"),
        ("The Magician",        "the tools you need are already in your hands"),
        ("Judgement",           "an old chapter closes and a truer path opens"),
        ("Ace of Cups",         "an emotional opening you had quietly given up on returns"),
        ("Ace of Pentacles",    "a practical foundation you've been laying begins to bear weight"),
        ("Six of Wands",        "recognition arrives for work done without applause"),
        ("Ten of Pentacles",    "the longer-term picture grows more stable and reassuring"),
        ("The Chariot",         "momentum, once gathered, carries you further than expected"),
    ],
    Valence.SHADOWED: [
        ("The Hermit",          "a period of deliberate withdrawal yields something important"),
        ("The High Priestess",  "what is unspoken carries more weight than what is said"),
        ("The Hanged Man",      "a pause you resist turns out to be necessary"),
        ("Temperance",          "balance is achievable but requires more patience than you'd like"),
        ("The Moon",            "something half-hidden shapes events more than you realize"),
        ("Seven of Cups",       "not every option before you is what it appears to be"),
        ("Four of Swords",      "rest is not avoidance — it is the work"),
        ("Eight of Pentacles",  "diligence in the details produces results that feel slow but hold"),
        ("Two of Swords",       "a decision you've been deferring can no longer wait"),
        ("Five of Cups",        "acknowledging what was lost makes room for what remains"),
        ("Page of Swords",      "information surfaces that reframes an assumption you've held"),
        ("The Justice",         "an imbalance that has gone unaddressed draws itself to your attention"),
    ],
    Valence.TURBULENT: [
        ("The Tower",           "a sudden disruption clears ground that needed clearing"),
        ("The Devil",           "a pattern you've outgrown pulls at you one more time"),
        ("Death",               "something must end before what is next can begin"),
        ("Five of Swords",      "a conflict reveals where the real disagreement lies"),
        ("Ten of Swords",       "a difficult conclusion arrives, but it does arrive — the uncertainty ends"),
        ("Three of Swords",     "grief or disappointment asks to be felt rather than managed"),
        ("Seven of Wands",      "pressure mounts, but so does your capacity to meet it"),
        ("The Tower (reversed)","the disruption that was coming takes a quieter but no less significant form"),
        ("Eight of Swords",     "the constraints feel absolute, but at least one is self-imposed"),
        ("Five of Pentacles",   "scarcity — of resources, of support, or of time — asks for creative response"),
    ],
}

def _pick_tarot(valence: str, rng: random.Random) -> tuple[str, str]:
    """Return (card_name, card_phrase) for today's draw."""
    return rng.choice(_TAROT[valence])


# ===========================================================================
# GRAMMAR TABLES
# Each table entry is a template string or a tuple of alternatives.
# The RNG picks among them; the caller fills any {placeholders}.
# ===========================================================================

# ---------------------------------------------------------------------------
# Atmospheric openers — element-flavored, one sentence
# ---------------------------------------------------------------------------

_OPENERS: dict[Element, list[str]] = {
    Element.FIRE: [
        "The celestial fires burn high in your chart today.",
        "Mars lends its restless heat to the hours ahead.",
        "An ember of ambition you thought extinguished flares back to life.",
        "The sky carries a charge today, and you are the conductor.",
        "Something in the atmosphere accelerates what has been gathering.",
        "Momentum is the theme, and it belongs to those willing to meet it.",
        "The planetary currents favor action over deliberation today.",
        "A surge of vital energy runs beneath everything you touch.",
        "The sky tilts toward the bold, and you are not short on that quality.",
        "Whatever has been building in you finds an outlet today.",
        "The hour is an accelerant — use it with intention.",
        "A fire lit weeks ago finally has the air it needs to spread.",
    ],
    Element.EARTH: [
        "The ground beneath your feet is more solid than it has been in weeks.",
        "Saturn's steady influence rewards those who have done the quiet work.",
        "The sky asks nothing dramatic of you today — only precision.",
        "A certain seriousness settles over the day, and it is useful.",
        "The planetary picture favors material concerns and practical decisions.",
        "What is built carefully today will be standing when others' quick structures have settled.",
        "The stars are in a patient mood, and patience is exactly what is required.",
        "Taurus energy runs through the day like a slow current — strong, quiet, purposeful.",
        "The hours reward attention to detail and distrust of shortcuts.",
        "A deliberate pace is not a slow pace; it is a thorough one.",
        "The sky is not flashy today, but it is dependable.",
        "What accumulates quietly is often what endures.",
    ],
    Element.AIR: [
        "Mercury sharpens the mind and quickens the exchange of ideas.",
        "A current of new information moves through your world today.",
        "The sky is talkative, and so, likely, are you.",
        "The atmosphere carries a restless intellectual charge.",
        "Something you read, hear, or say today lands with more consequence than expected.",
        "The planetary winds favor connection, communication, and the well-timed question.",
        "Ideas that have been circling finally find a surface to land on.",
        "The day is porous — let what needs to reach you, reach you.",
        "A social current runs through the hours, carrying useful information.",
        "The sky rewards those who pay attention to what is being said between the words.",
        "Insight arrives through conversation rather than solitude today.",
        "The atmosphere hums with possibility — most of it social in origin.",
    ],
    Element.WATER: [
        "The tides of feeling run deeper than usual today.",
        "The moon draws hidden currents to the surface.",
        "Something below the waterline of daily life stirs and asks to be acknowledged.",
        "The atmosphere is permeable today — your intuition is working overtime.",
        "Neptune's influence blurs the line between what is known and what is felt.",
        "The sky is more interior than exterior today; the inner world has useful intelligence.",
        "A dream-like quality moves through the hours, soft but not without substance.",
        "Emotion is not noise today — it is signal.",
        "What the logic of recent weeks has not resolved, the feeling-sense may.",
        "The planetary picture asks for receptivity rather than force.",
        "The most important data today arrives through feeling, not analysis.",
        "The sky is quiet but not still — much moves beneath the surface.",
    ],
}

# ---------------------------------------------------------------------------
# Domain introductions — frame the life area, by domain
# ---------------------------------------------------------------------------

_DOMAIN_INTROS: dict[str, list[str]] = {
    "love": [
        "In matters of the heart,",
        "Where love and connection are concerned,",
        "Your closest relationships come into focus today,",
        "The romantic and emotional sphere draws your attention,",
        "Something between you and another person shifts,",
        "A relationship — new, old, or yet to begin — enters a decisive phase,",
        "The territory of intimacy and feeling demands honesty today,",
        "The heart has its own intelligence, and today it speaks clearly,",
    ],
    "career": [
        "On the professional front,",
        "In your working life,",
        "Career matters take center stage,",
        "The ambitions you carry into your daily work come under review,",
        "Your public role and what it costs you privately becomes visible today,",
        "Something in your professional sphere that has been pending resolves,",
        "The work you have been doing quietly begins to produce a visible result,",
        "A shift in the professional landscape changes what is optimal,",
    ],
    "money": [
        "On financial matters,",
        "The practical territory of money and resources deserves attention today,",
        "A question of value — personal or financial — surfaces,",
        "Where your resources are concerned,",
        "The economic dimension of your life shifts in a way worth noticing,",
        "A financial decision you've been circling becomes more urgent,",
        "Something to do with money, property, or material security moves,",
        "The question of what you own — and what owns you — is worth examining today,",
    ],
    "health": [
        "The body has been keeping score, and today it presents the tally,",
        "Your physical wellbeing deserves more direct attention than it's been getting,",
        "A health matter you've been deferring becomes easier to address,",
        "The connection between how you feel and how you've been living becomes clear,",
        "Energy levels today tell a story worth listening to,",
        "The body is a good reporter — what is it reporting today,",
        "A small adjustment to how you move through your days yields disproportionate benefit,",
        "Physical vitality and mental clarity are linked today in an unusually direct way,",
    ],
    "family": [
        "Within your family or closest circle,",
        "A domestic matter that has been simmering comes to the surface,",
        "The people you call home — wherever home is — need something from you today,",
        "A family dynamic that has been stable enters a period of renegotiation,",
        "Something in your roots — family, home, origin — calls for attention,",
        "The ties of blood and history feel closer today,",
        "A conversation about shared life or shared history becomes possible,",
        "The domestic sphere and what sustains it becomes a point of focus,",
    ],
    "creativity": [
        "The creative current runs strong today,",
        "Something you've been trying to make finds the shape it's been waiting for,",
        "An artistic or expressive impulse demands more space than you've been giving it,",
        "The imagination is unusually fertile today — give it room,",
        "A project, idea, or creative vision reaches a productive turning point,",
        "The part of you that makes things is ready to be heard,",
        "Creative work that felt stalled begins to move again,",
        "A flash of inspiration arrives — it is more solid than it first appears,",
    ],
    "travel": [
        "Distance — physical or metaphorical — enters your picture today,",
        "A journey or the idea of one becomes more pressing,",
        "The urge to move, expand, or seek broader horizons intensifies,",
        "Something on the horizon — a place, a perspective, or a horizon itself — beckons,",
        "A plan involving travel or relocation clarifies,",
        "The wider world calls, and the call is worth answering,",
        "A question about where to go next has more than one good answer today,",
        "Movement — of self, of plans, of location — is the theme,",
    ],
    "communication": [
        "The exchange of words, ideas, and information carries unusual weight today,",
        "Something said — or left unsaid — shapes the hours ahead,",
        "A conversation you've been putting off becomes both possible and necessary,",
        "The written or spoken word is your most effective tool today,",
        "Information arrives that changes the shape of a decision,",
        "A message — sent or received — opens something that was closed,",
        "The quality of your attention in conversation today is the variable,",
        "What is communicated, and how, matters more than usual,",
    ],
    "spirituality": [
        "The deeper current beneath ordinary life surfaces today,",
        "A question about meaning or purpose that you've been carrying quietly comes forward,",
        "Something in the invisible architecture of your life shifts,",
        "The spiritual dimension — however you define it — is unusually close today,",
        "An encounter with the numinous, unexpected and brief, leaves something behind,",
        "The part of you that watches rather than acts has useful things to say today,",
        "A sense of alignment — or its absence — becomes hard to ignore,",
        "What cannot be measured still exerts a measurable influence today,",
    ],
    "transformation": [
        "Something in you that has resisted change is finally ready to move,",
        "A process of becoming — slow and largely invisible until now — breaks the surface,",
        "The person you are becoming and the person you have been negotiate today,",
        "A chapter ends — not dramatically, but definitively,",
        "Something you've been holding onto loosens its grip,",
        "A threshold that has been near becomes crossable,",
        "The kind of change that cannot be undone is underway,",
        "What you are letting go of is making room for something you haven't named yet,",
    ],
}

# ---------------------------------------------------------------------------
# Events — the core of the horoscope, tagged by (valence, element_affinity)
# "general" events work across all elements.
# ---------------------------------------------------------------------------

_EVENTS: dict[str, dict[str | Element, list[str]]] = {

    Valence.BRIGHT: {
        "general": [
            "an opportunity you nearly missed returns with better timing",
            "a long-held wish takes its first concrete form",
            "someone whose judgment you trust offers support you hadn't thought to ask for",
            "a door you had given up on opens from the inside",
            "a delayed reward arrives — and it has gathered interest",
            "two things you've been keeping separate discover they belong together",
            "a piece of information you've needed arrives through an unexpected channel",
            "an obstacle that seemed fixed has quietly moved",
            "something you gave without expectation returns multiplied",
            "the resistance you've been pushing against dissolves",
            "a conversation changes the shape of what seemed fixed",
            "a figure from your past brings something useful forward",
            "the path ahead clears in the area that matters most",
            "a quiet victory becomes visible to others for the first time",
            "what you've been preparing for finally arrives",
            "a creative solution emerges to a problem that had seemed purely logistical",
            "a new alliance forms in territory you'd been navigating alone",
            "a piece clicks into place that makes the whole picture legible",
        ],
        Element.FIRE: [
            "a burst of energy arrives that, if directed, can accomplish what months of steady effort could not",
            "an opponent or obstacle is revealed to be less formidable than it appeared",
            "the initiative you've been hesitating to take becomes the clearly right move",
            "a competitive situation resolves in your favor",
            "a long fight reaches its natural conclusion, and the conclusion is yours",
            "the courage you've been borrowing from your future self turns out to have been your own all along",
        ],
        Element.EARTH: [
            "the investment — of time, effort, or actual resources — begins to pay out",
            "a material concern that has been uncertain stabilizes",
            "the practical plan that seemed overly cautious is vindicated",
            "a physical or financial foundation solidifies under circumstances that might have shaken it",
            "the slow accumulation of small right decisions produces a result you couldn't have forced",
            "what you've been building piece by piece is visible as a whole for the first time",
        ],
        Element.AIR: [
            "the right idea arrives at exactly the right moment",
            "a social connection produces an opening you'd been trying to engineer through other means",
            "a piece of communication that was misread gets correctly understood",
            "an intellectual problem that has been circling finally resolves",
            "the network you've been quietly building proves its worth",
            "a collaboration produces something neither party could have reached alone",
        ],
        Element.WATER: [
            "an emotional risk taken quietly pays off in the currency of real intimacy",
            "a feeling you'd been unable to name finds its word",
            "a relationship that has been uncertain moves toward clarity, and the clarity is welcome",
            "the intuitive call you nearly talked yourself out of turns out to be correct",
            "a healing that has been in progress becomes, for the first time, perceptible",
            "what was hidden from you — because you were not yet ready — is now revealable",
        ],
    },

    Valence.SHADOWED: {
        "general": [
            "a tension that has been building reaches a point of release",
            "someone close reveals a truth that complicates, but ultimately clarifies",
            "a commitment made in haste now requires renegotiation",
            "a pattern you hoped had resolved resurfaces for closer examination",
            "progress in one direction requires accepting a cost in another",
            "what seemed like a setback is, at a different angle, a course correction",
            "a gap between what you said and what was heard becomes apparent",
            "the shorter path and the right path turn out to be different paths",
            "a support you had counted on proves less reliable than expected",
            "a choice must be made between two things that cannot both be kept",
            "an old wound, thought healed, announces it has further work to do",
            "the thing you've been avoiding has grown only slightly larger in the waiting",
            "a relationship that has been in a holding pattern demands a decision",
            "what appeared to be agreement conceals a significant unresolved difference",
            "a plan that worked in previous conditions requires adaptation to current ones",
            "the effort required is more than estimated; the value is also more than estimated",
        ],
        Element.FIRE: [
            "the impulse toward action is strong, but the timing is the variable",
            "a fight worth having still carries a cost worth calculating",
            "the energy available is real, but so is the risk of burning through it ahead of the right moment",
            "an ambition you've been pursuing begins to reveal what it actually costs",
        ],
        Element.EARTH: [
            "the careful plan meets an external variable it had not accounted for",
            "security, real or imagined, is tested in a way that is ultimately useful",
            "the material foundation is sound, but a crack in it that has been ignored demands attention",
            "what was built for one set of conditions must be adapted for another",
        ],
        Element.AIR: [
            "information arrives that makes a previous conclusion less certain",
            "a social dynamic you had read correctly shifts and must be re-read",
            "a conversation that seemed resolved leaves something important unsaid",
            "the idea is good, but the execution has a gap in it",
        ],
        Element.WATER: [
            "a feeling that has been managed rather than felt asserts its need to be felt",
            "an emotional assumption — about a relationship, a person, or yourself — is challenged",
            "the care you've extended without acknowledgment runs lower than you'd like to admit",
            "something you've been carrying for another person is ready to be set down",
        ],
    },

    Valence.TURBULENT: {
        "general": [
            "a disruption you didn't see coming clears ground that, in retrospect, needed clearing",
            "a system or structure that has been under strain finally gives way",
            "a sudden reversal demands rapid adjustment",
            "a conversation escalates in ways that, however uncomfortable, cannot be walked back",
            "something you were counting on is no longer available in the form you needed it",
            "an ending arrives without warning, though its causes have been in place for some time",
            "a confrontation — welcome or not — accelerates a resolution",
            "the illusion that things would remain as they were is no longer sustainable",
            "a loss is real, and it is also the precondition for something that could not have coexisted with what was lost",
            "what you hoped was settled turns out to have been merely postponed",
            "a pressure that has been external internalizes; a boundary was crossed",
            "the crisis is real, but crises have a way of surfacing what calmer conditions keep submerged",
        ],
        Element.FIRE: [
            "an explosion of energy — your own or someone else's — lands with force",
            "a conflict reaches the kind of heat that forges something new, if survived",
            "an impulsive action sets a chain of events in motion that cannot be recalled",
            "the fire that drove you forward burns a bridge you may later need",
        ],
        Element.EARTH: [
            "the ground shifts under a structure you had considered stable",
            "a material loss or disruption forces a practical reckoning",
            "what felt permanent reveals its conditionality",
            "the security that was real was also more narrow than it appeared",
        ],
        Element.AIR: [
            "a piece of information, once known, cannot be unknown",
            "a public or social situation fractures along a line that was always there",
            "a communication failure cascades into something larger than its origin",
            "an idea released too early — or too late — has consequences",
        ],
        Element.WATER: [
            "an emotional collapse is also a clearing",
            "what has been held below the surface breaks through, and the timing was not chosen",
            "the feeling that was being carefully managed can no longer be managed",
            "a relationship rupture, however painful, has the shape of an honest thing",
        ],
    },
}

# ---------------------------------------------------------------------------
# Elaborations — a second sentence expanding on the event
# Keyed by valence; these follow the event clause
# ---------------------------------------------------------------------------

_ELABORATIONS: dict[str, list[str]] = {
    Valence.BRIGHT: [
        "What seemed to require more preparation than you had is workable with what's already in hand.",
        "The conditions will not remain this favorable indefinitely — move when the opening presents itself.",
        "This is not luck arriving uninvited; it is the result of something you put in motion and then forgot about.",
        "The opening is real, but it has a window — do not let the analysis run past the opportunity.",
        "Allow the good news to land rather than immediately scanning it for the catch.",
        "More is available in this area than your recent experience would have suggested.",
        "The momentum is yours to direct; the question is only where.",
        "Trust the feeling that this is the right moment, because it is.",
        "Something that appeared to be a ceiling turns out to be a floor.",
        "The progress here is real even if it doesn't yet feel conclusive.",
        "Receive this one fully before moving on to what comes next.",
        "The breakthrough is quiet and, for that reason, more durable than a dramatic one would have been.",
    ],
    Valence.SHADOWED: [
        "There is a way through this, but it requires you to be honest about where the difficulty actually lives.",
        "The complication is not a sign that you were wrong — it is a sign that you were in motion.",
        "Sitting with the tension, rather than resolving it prematurely, is the most useful thing available.",
        "Not all of this is yours to carry; identifying what belongs to others is the first useful step.",
        "The adjustment required is real, but so is your capacity to make it.",
        "Clarity, even uncomfortable clarity, is worth more than the comfort of continued ambiguity.",
        "The cost is visible now; so, if you look, is what it is buying.",
        "This is a moment that asks for honesty over strategy.",
        "What cannot be changed can sometimes be accepted in a way that changes what it costs you.",
        "The work is not finished, but you are further along than the current friction suggests.",
        "Something that looked like a problem is more accurately described as a choice.",
        "The longer view — even a week longer — changes what this looks like considerably.",
    ],
    Valence.TURBULENT: [
        "The disruption is real; the finality of it is not yet as certain as it feels.",
        "What is broken may need to stay broken for a while before you know what to build in its place.",
        "Ground lost here often turns out to be ground that was quietly costing you to hold.",
        "The impulse to stabilize quickly is understandable; resist it long enough to see what actually needs to go.",
        "Not every fire is destruction — some fires are clearing burns.",
        "The situation does not require that you be fine with it; it requires that you be in it.",
        "Allow the collapse to be complete before deciding what comes next.",
        "What feels like the end of something is often the most accurate-feeling thing that has happened in a while.",
        "The intensity is information — not all of it is bad information.",
        "Seek support rather than containment; containment will fail and support will not.",
        "The hardest part of this is often the not-knowing, not the knowing.",
        "Something true is being revealed, even if its truth is unwelcome at the moment of revelation.",
    ],
}

# ---------------------------------------------------------------------------
# Advice — modality-voiced, comes after the elaboration
# Cardinal: act, decide, initiate
# Fixed:    hold, commit, don't compromise for ease
# Mutable:  stay open, don't force, let things evolve
# ---------------------------------------------------------------------------

_ADVICE: dict[Modality, list[str]] = {
    Modality.CARDINAL: [
        "Decide, and then act on the decision — half-measures will cost more than the whole one.",
        "The initiative is yours to take; take it before the window narrows.",
        "Name what you want with enough specificity that others know what to bring you.",
        "The move that feels premature is, in this case, simply early.",
        "Bring the conversation to a point rather than letting it continue to circle.",
        "Lead in the area where others are waiting for someone to go first.",
        "The decision that keeps being deferred is costing more than making it would.",
        "Act from your current understanding rather than waiting for perfect information.",
        "The obstacle yields to direct address more readily than to patience alone.",
        "Claim what is available rather than waiting for it to be offered.",
    ],
    Modality.FIXED: [
        "Hold to what you know is true, even where the pressure to reconsider is significant.",
        "Consistency is not stubbornness if what you are being consistent toward is real.",
        "The commitment holds; let it hold, and let the doubt be noise.",
        "Resist the easy revision — what you built carefully deserves the same careful defense.",
        "Stay with the original plan long enough to distinguish a genuine flaw from temporary difficulty.",
        "The people trying to move you quickly may not have your patience — and your patience may be correct.",
        "Your endurance here is its own form of intelligence.",
        "What you maintain through difficulty becomes the foundation that others eventually rely on.",
        "Do not confuse loyalty to a situation with loyalty to a person or principle — they are different things.",
        "The long game continues to be the right game.",
    ],
    Modality.MUTABLE: [
        "Stay soft on the how while remaining clear on the what.",
        "The route is negotiable; the destination is not.",
        "Let the situation tell you what it needs before deciding what to give it.",
        "Flexibility here is not weakness — it is the appropriate response to actual conditions.",
        "Follow what is alive rather than what was planned.",
        "The version that is emerging may be better than the version that was intended — let it.",
        "Do not force a conclusion before the process has finished offering its information.",
        "The answer is not yet fixed; your openness to several possible answers is an advantage.",
        "Allow yourself to not know for a little longer — the knowing will come.",
        "Read the room again before deciding the room is what you originally thought it was.",
    ],
}

# ---------------------------------------------------------------------------
# Timing closes — element-flavored
# ---------------------------------------------------------------------------

_TIMING: dict[Element, list[str]] = {
    Element.FIRE: [
        "The moment for action is closer than it is far.",
        "Before the week burns through, you will know what to do with this.",
        "The window is open now and may not be as wide by month's end.",
        "Act while the energy is with you — it won't be indefinitely.",
        "What you set in motion today will have legs by the end of the week.",
        "The spark catches if you apply it; don't wait for a better moment.",
    ],
    Element.EARTH: [
        "Give it the time it needs — not less, but also not more.",
        "By the end of the month, what is stable now will be load-bearing.",
        "Patience through the next two weeks produces results that haste would have prevented.",
        "The pace is right even when it doesn't feel urgent.",
        "The longer arc here bends toward solidity — stay with it.",
        "What takes root slowly, holds.",
    ],
    Element.AIR: [
        "The answer comes through conversation, sooner than you think.",
        "By the end of this exchange — this day, this week — something useful will have been said.",
        "Stay in contact; the information you need is traveling toward you.",
        "The next few days are unusually good for clarifying what has been ambiguous.",
        "What is in the air now lands somewhere specific very soon.",
        "The communication channel that opens today is worth keeping open.",
    ],
    Element.WATER: [
        "By the time the feeling settles, the direction will be clear.",
        "Give it the emotional time it actually requires — the logic can follow.",
        "Within the week, the current will have moved enough to show you where it's going.",
        "Let it work in you for a few days before deciding what it means.",
        "The clarity arrives from below, not from above, and it arrives in its own time.",
        "Before the next full moon, what is murky will have found its surface.",
    ],
}

# ---------------------------------------------------------------------------
# Polarity-based sentence framing
# Positive (outward): active subject, external orientation
# Negative (inward):  reflective, interior orientation
# Applied subtly to advice and elaboration selection
# ---------------------------------------------------------------------------

def _polarity_seed_offset(polarity: Polarity, rng: random.Random, lst: list) -> int:
    """
    Returns an index biased toward the first or second half of lst based on
    polarity. Positive signs get earlier indices (more outward phrasing),
    Negative get later (more interior). Split is derived from the actual list
    length so no magic numbers are needed.
    """
    half = len(lst) // 2
    base = rng.randint(0, half - 1)
    if polarity == Polarity.POSITIVE:
        return base
    else:
        return half + base


def _pick(lst: list, rng: random.Random) -> str:
    return rng.choice(lst)


def _pick_polarity(lst: list, polarity: Polarity, rng: random.Random) -> str:
    """Pick from lst biased toward first half (Positive) or second half (Negative)."""
    idx = _polarity_seed_offset(polarity, rng, lst)
    # clamp in case list length is odd and half + base overshoots
    return lst[min(idx, len(lst) - 1)]


# ===========================================================================
# ASSEMBLY
# ===========================================================================

def generate(
    sign_name: str,
    for_date: Optional[date] = None,
    use_tarot: bool = True,
) -> str:
    """
    Generate a deterministic horoscope for the given sign and date.

    Args:
        sign_name:  Any of the 12 zodiac sign names (case-insensitive).
        for_date:   The date to generate for. Defaults to today.
        use_tarot:  Whether to weave a tarot archetype into the domain sentence.

    Returns:
        A horoscope string of 3-5 sentences.
    """
    if for_date is None:
        for_date = date.today()

    sign = get_sign(sign_name)
    rng  = _make_rng(sign.name, for_date)

    # --- Core draws ---
    valence = _pick_valence(sign, rng)
    domain  = _pick_domain(sign, rng)
    tarot_card, tarot_phrase = _pick_tarot(valence, rng) if use_tarot else (None, None)

    # --- Select event from element-specific pool with fallback to general ---
    element_events = _EVENTS[valence].get(sign.element, [])
    general_events = _EVENTS[valence]["general"]
    # Weight toward element-specific events (2:1) if available
    if element_events and rng.random() < 0.65:
        event = _pick(element_events, rng)
    else:
        event = _pick(general_events, rng)

    elaboration = _pick_polarity(_ELABORATIONS[valence], sign.polarity, rng)
    advice      = _pick_polarity(_ADVICE[sign.modality], sign.polarity, rng)
    timing      = _pick(_TIMING[sign.element], rng)
    opener      = _pick(_OPENERS[sign.element], rng)
    domain_intro = _pick(_DOMAIN_INTROS[domain], rng)

    # --- Assemble domain sentence ---
    # With tarot: "In matters of love, The Star suggests a renewal... as [event]."
    # Without:    "In matters of love, [event]."
    if use_tarot and tarot_phrase:
        intro = domain_intro.rstrip(",")
        domain_sentence = (
            f"{intro}. {tarot_card} moves through today's picture — "
            f"{tarot_phrase} — and with it {event}."
        )
    else:
        domain_sentence = f"{domain_intro} {event}."

    # --- Final assembly ---
    # Structure: opener. domain+event. elaboration. advice. timing.
    horoscope = " ".join([
        opener,
        domain_sentence,
        elaboration,
        advice,
        timing,
    ])

    return horoscope


def generate_for_today(sign_name: str, use_tarot: bool = True) -> str:
    """Convenience wrapper — generates for today's date."""
    return generate(sign_name, date.today(), use_tarot)


# ===========================================================================
# SANITY CHECK / DEMO
# ===========================================================================

if __name__ == "__main__":
    from datetime import date

    test_date = date(2026, 6, 4)
    signs = [
        "aries", "taurus", "gemini", "cancer", "leo", "virgo",
        "libra", "scorpio", "sagittarius", "capricorn", "aquarius", "pisces"
    ]

    print(f"=== Daily Horoscopes for {test_date} ===\n")
    for sign_name in signs:
        sign = get_sign(sign_name)
        text = generate(sign_name, test_date)
        print(f"--- {sign_name.upper()} ({sign.element.value} / {sign.modality.value} / {sign.temperament}) ---")
        print(text)
        print()

    # Demonstrate determinism: same sign + date always produces the same output
    print("--- Determinism check: Scorpio generated 3 times ---")
    for _ in range(3):
        print(generate("scorpio", test_date))
    print()

    # Demonstrate day variance: same sign across 5 consecutive days
    print("--- Day variance: Gemini across 5 days ---")
    from datetime import timedelta
    for i in range(5):
        d = test_date + timedelta(days=i)
        first_sentence = generate("gemini", d).split(". ")[0] + "."
        print(f"  {d}: {first_sentence}")

# ===========================================================================
# EMOTION SEED
#
# Short, emotionally direct phrases keyed by (valence, element).
# These are never displayed -- they are prepended to the horoscope text
# before it is passed to the emotion classifier so the model has a clear
# signal to work with. Literary horoscope prose reads as "neutral" to a
# model trained on social-media text; a one-sentence anchor fixes that
# without changing what Gradio shows or what the generator produces.
#
# The seed is deterministic: it uses the same (sign, date) RNG and makes
# the same _pick_valence draw as generate(), so both always agree on the
# day's tone.
# ===========================================================================

_EMOTION_SEEDS: dict[str, dict[Element, str]] = {
    Valence.BRIGHT: {
        Element.FIRE:  "Joy and fierce excitement surge powerfully forward today.",
        Element.EARTH: "Deep contentment and satisfaction fill this abundant moment.",
        Element.AIR:   "Delight and wonder spark through every thought and connection.",
        Element.WATER: "Warmth and happiness flow through deep emotional fulfillment.",
    },
    Valence.SHADOWED: {
        Element.FIRE:  "Frustration and anger smolder beneath the surface, mounting.",
        Element.EARTH: "Sadness and heaviness weigh on what feels uncertain and hard.",
        Element.AIR:   "Grief and worry cloud everything, a quiet sadness settles in.",
        Element.WATER: "Grief and sorrow move below the surface, sadness pools deeply.",
    },
    Valence.TURBULENT: {
        Element.FIRE:  "Rage erupts and fury breaks violently through every restraint.",
        Element.EARTH: "Dread and panic rise sharply as solid ground gives way.",
        Element.AIR:   "Shock and surprise shatter every assumption, nothing is as expected.",
        Element.WATER: "Terror and anguish surge as dark depths erupt without warning.",
    },
}


def get_emotion_seed(sign_name: str, for_date: Optional[date] = None) -> str:
    """
    Return the short emotion-anchor phrase for this sign on this date.
    Deterministic -- uses the same seed and first RNG draw as generate().
    Prepend this to the horoscope text before calling decode().
    """
    if for_date is None:
        for_date = date.today()
    sign    = get_sign(sign_name)
    rng     = _make_rng(sign.name, for_date)
    valence = _pick_valence(sign, rng)
    return _EMOTION_SEEDS[valence][sign.element]