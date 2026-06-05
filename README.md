# Zodiac Behavior Engine

A system where each zodiac sign is an autonomous agent in a 3D Unity scene whose daily behavior is driven by a procedurally generated horoscope. A pretrained emotion classifier decodes the horoscope text into a behavior vector; Unity reads that vector and drives each agent's movement, glow, and social interactions.

This repo is a code snapshot shared for reference. Only scripts are included — no scenes, art assets, prefabs, or Unity metadata. The project is in active development.

---

## How it works

Each agent has two layers of behavior.

The **static layer** is permanent personality derived from classical astrological attributes: element, modality, polarity, ruling planet, and fixed star. An Earth sign moves slowly and resists daily mood swings. An Air sign covers ground quickly and shifts more easily. This layer never changes at runtime.

The **dynamic layer** is a daily behavior vector produced by running a procedurally generated horoscope through a pretrained emotion classifier. The same Scorpio is always intense; today's horoscope decides whether that intensity is directed inward or outward. The two layers are blended by a per-sign `horoscope_weight` that reflects how fixed or mutable the sign is by nature.

The novel framing: the ML model is used as an **interpreter** (text to behavior vector), not as a task performer. The system works with any off-the-shelf emotion classifier because its job is simply to translate fortune-text into structured signal.

### Emotion seeding

Horoscope prose is literary and measured, which causes the classifier to default toward neutral. Before decoding, the horoscope is prefixed with a short emotion-anchoring phrase derived from the sign's astrological valence for that day. The phrase is deterministic (seeded by sign and date), so the anchored text is reproducible. The prefix is never displayed; only the clean horoscope reaches the Gradio dashboard.

### Star glow

Each sign's constellation star sets a brightness ceiling for its glow. Star brightness is normalized from apparent magnitude to a `[0.25, 1.0]` range — Aldebaran (Taurus) at 1.0, Eta Piscium (Pisces) at 0.25. The floor is 0.25 because all constellation stars are visible to the naked eye; none should read as absent. In Unity, a separate minimum floor constant ensures every agent emits at least a faint glow regardless of star or mood.

---

## Architecture

```
zodiac_agent_inference/           Python project
  zodiac_schema.py                static per-sign traits and behavior constants
  compatibility.py                12x12 compatibility chart from compatibility.json
  horoscope_generator.py          procedural daily horoscope, seeded by (sign + date)
  decoder.py                      emotion classifier -> behavior vector
  server.py                       WebSocket server, caches and pushes daily vectors
  gradio_app.py                   dashboard: horoscope display, emotion bars, overrides

zodiac_agent_engine/              Unity project
  Assets/Scripts/
    ZodiacAgent.cs                base MonoBehaviour, static traits + effective blending
    ZodiacAgentPrimitive.cs       v1 visual driver: movement, rotation, glow, social drift
    ZodiacWebSocketClient.cs      WebSocket client, routes vectors to agents
    ZodiacMessages.cs             JsonUtility-compatible message wrapper classes
    BehaviorVectorData.cs         serializable behavior vector class
    ZodiacData/
      ZodiacData.cs               ScriptableObject holding per-sign static trait data
    Editor/
      ZodiacDataGenerator.cs      editor utility: generates ZodiacData assets from JSON
  Assets/ZodiacData/SignData/     generated ScriptableObject assets (one per sign)
  Assets/zodiac_signs.json        data bridge: exported from zodiac_schema.py
```

The WebSocket server runs on localhost. Unity and the Gradio dashboard both connect as clients. On connect, the server decodes all 12 signs for the current date, caches the result, and pushes it to every connected client. The emotion model runs once per calendar day; subsequent connections are served from cache. Sign requests and overrides from the Gradio dashboard broadcast to all connected clients in real time.

### Wire format

Emotion scores are sent as flat top-level float fields (`emotion_anger`, `emotion_fear`, etc.) rather than a nested object. Unity's `JsonUtility` cannot deserialize `Dictionary<string, float>`; flat fields with matching C# property names are the reliable alternative. The horoscope source text is stripped from the wire entirely since it contains characters that break `JsonUtility`'s parser.

---

## Behavior vector

The emotion classifier outputs a probability distribution across seven emotions. Those scores are projected through a weight matrix into six behavior dimensions, each blended with the agent's static baseline via `horoscope_weight`:

| Dimension | Range | Drives |
|---|---|---|
| `speed_mod` | -1 to 1 | movement speed |
| `agitation` | 0 to 1 | jitter, direction-change rate |
| `approach_mod` | -1 to 1 | tendency to move toward others |
| `glow_mod` | -1 to 1 | emission intensity |
| `social_mod` | -1 to 1 | attraction or repulsion in encounters |
| `aggression` | 0 to 1 | encounter hostility |

A Fixed sign (Taurus, Leo, Scorpio, Aquarius) has `horoscope_weight=0.40`, so the daily vector barely moves it from baseline. A Mutable sign (Gemini, Virgo, Sagittarius, Pisces) has `horoscope_weight=1.00` and swings fully with the day's decoded emotion.

Each agent's point light and emission blend continuously between its material color and a weighted combination of all seven emotion colors, driven by the decoded probability scores. The blending cycle period is tunable per agent in the Inspector.

---

## Running it

Requires Python 3.11+ and Unity 6 (or later).

Install dependencies:

```bash
cd zodiac_agent_inference
pip install -r requirements.txt
```

Start the behavior server:

```bash
python server.py
```

Start the Gradio dashboard:

```bash
python gradio_app.py
```

Then open the Unity project and enter Play mode. The server logs connections from both clients and prints a decode confirmation when the emotion model finishes its first pass.

### Unity setup

Static trait data lives in ScriptableObject assets under `Assets/ZodiacData/SignData/`. To regenerate these from `zodiac_schema.py` after any schema change:

1. Export the schema to JSON from the Python project root:

```bash
python -c "
import json
from zodiac_schema import SIGNS
out = []
for s in SIGNS:
    d = s.to_dict()
    out.append({
        'name': d['name'], 'index': d['index'],
        'element': d['element'], 'modality': d['modality'],
        'polarity': d['polarity'], 'ruler': d['ruler'],
        'star': d['star'], 'temperament': d['temperament'],
        'core_drive': d['core_drive'], 'behavioral_mode': d['behavioral_mode'],
        'base_speed': d['base_speed'], 'base_glow': d['base_glow'],
        'orbit_radius': d['orbit_radius'], 'restlessness': d['restlessness'],
        'approach_bias': d['approach_bias'], 'social_bias': d['social_bias'],
        'interaction_radius': d['interaction_radius'],
        'horoscope_weight': d['horoscope_weight'],
        'star_glow': d['star_glow'], 'ruler_influence': d['ruler_influence'],
    })
print(json.dumps(out, indent=2))
" > zodiac_signs.json
```

2. Copy `zodiac_signs.json` into `zodiac_agent_engine/Assets/`.

3. In the Unity menu: `Zodiac > Generate Sign Data Assets`. Re-running overwrites existing assets safely.

### Gradio override panel

Override sliders hold desired values and never auto-update from the server. A live delta panel updates every second showing the current server state vs your set position. **Apply** broadcasts the slider values to Unity. **Reset to Live** pulls the current server state into the sliders.

The optional animated emotion bars use a custom Gradio component ([gradio-confidence-chart](https://github.com/jam-mad/gradio-confidence-chart)). The dashboard falls back to standard Gradio label bars if the component is not installed.

---

## What is not in this repo

This is a script-only snapshot. The following are excluded intentionally:

- Unity scene files and prefabs
- Materials, textures, and any art assets
- Unity `.meta` files and project configuration
- The `Library/`, `Temp/`, and other Unity-generated folders

The codebase gives a full picture of the logic and architecture. The missing pieces are either Unity boilerplate or art that is not ready to share. The scripts are self-contained enough to read and understand the system without them.

---

## Status

v1 is in progress. The current build uses primitive shapes as stand-in agents. The full vision involves rigged character models and a richer inter-agent social layer driven by the compatibility chart. Those are deferred until the engine is solid.

---

## License

Source code is shared for reference. All rights reserved.