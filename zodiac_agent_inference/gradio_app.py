"""
gradio_app.py

Gradio dashboard for the Zodiac Behavior Engine.

Connects to the Python WebSocket server as a client, receives live
behavior vector pushes, and lets you inspect and override any sign's
behavior in real time. Overrides broadcast to Unity immediately.

Layout:
  Left  — sign selector, static trait summary, date picker, horoscope text
  Right — emotion confidence chart, behavior override sliders, apply/reset

The WebSocket listener runs in a background thread with its own event
loop. A gr.Timer polls shared state every second and updates the UI.
Sliders show current vector values and double as override controls.

Usage:
    python gradio_app.py

Requires the behavior server to be running:
    python server.py

Optional — install the custom confidence chart component for animated bars:
    pip install gradio_confidencechart
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from datetime import date

import gradio as gr
from gradio.themes import Soft

from websockets.asyncio.client import connect as ws_connect
from zodiac_schema import SIGNS, get_sign
from horoscope_generator import generate as generate_horoscope

# ---------------------------------------------------------------------------
# Optional custom component
#
# ConfidenceChart is bound in BOTH branches so it is never "possibly unbound":
# the real class on success, None on failure. The call site checks `is not None`
# so Pylance can narrow the type and know it is callable.
# ---------------------------------------------------------------------------

try:
    from gradio_confidencechart import ConfidenceChart
except ImportError:
    ConfidenceChart = None


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SERVER_URL   = "ws://localhost:8765"
TIMER_PERIOD = 1.0   # seconds between UI refreshes

ZODIAC_NAMES = [s.name.capitalize() for s in SIGNS]

BEHAVIOR_DIMS  = ["speed_mod", "agitation", "approach_mod",
                  "glow_mod", "social_mod", "aggression"]
EMOTION_LABELS = ["anger", "disgust", "fear", "joy",
                  "neutral", "sadness", "surprise"]


# ---------------------------------------------------------------------------
# WebSocket background client
#
# All async lives inside this class. The loop and queue are created in
# __init__ so they are never None — that removes the unchecked-None problem
# the module-global version had. The Gradio side only ever touches three
# sync, thread-safe methods: start(), latest(), send().
#
# For a Go reader: _run is `go func(){}()`, _send_queue is a channel,
# run_coroutine_threadsafe is sending on that channel from another goroutine,
# and `async for raw in ws` is `for msg := range ch`.
# ---------------------------------------------------------------------------

class BehaviorClient:
    def __init__(self, url: str, retry_delay: float = 5.0):
        self._url         = url
        self._retry_delay = retry_delay
        self._loop        = asyncio.new_event_loop()
        self._send_queue: asyncio.Queue[str] = asyncio.Queue()
        self._state: dict[str, dict] = {}
        self._lock        = threading.Lock()

    # --- public, sync, thread-safe -----------------------------------------

    def start(self) -> None:
        """Spin up the background thread that owns the event loop."""
        threading.Thread(target=self._run, daemon=True).start()

    def latest(self, zodiac: str) -> dict:
        """Return a copy of the most recent vector for a sign (never None)."""
        with self._lock:
            return dict(self._state.get(zodiac.lower(), {}))

    def send(self, msg: dict) -> None:
        """Queue a message for sending. Safe to call before the loop starts."""
        asyncio.run_coroutine_threadsafe(
            self._send_queue.put(json.dumps(msg)),
            self._loop,
        )

    # --- background thread internals ---------------------------------------

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._client_loop())

    async def _client_loop(self) -> None:
        """Connect, receive forever, reconnect on any failure."""
        while True:
            try:
                async with ws_connect(self._url) as ws:
                    sender = asyncio.create_task(self._send_loop(ws))
                    try:
                        async for raw in ws:
                            text = raw if isinstance(raw, str) else bytes(raw).decode()
                            self._ingest(text)
                    finally:
                        sender.cancel()
            except Exception:
                pass   # server down or dropped — retry below
            await asyncio.sleep(self._retry_delay)

    async def _send_loop(self, ws) -> None:
        """Drain the outbound queue onto the socket."""
        while True:
            text = await self._send_queue.get()
            try:
                await ws.send(text)
            except Exception:
                pass   # lost on disconnect; reconnect re-syncs state anyway

    def _ingest(self, text: str) -> None:
        """Parse one inbound message and update shared state under the lock."""
        try:
            msg = json.loads(text)
        except json.JSONDecodeError:
            return
        with self._lock:
            if msg.get("type") == "daily_update":
                for entry in msg.get("vectors", []):
                    z, v = entry.get("sign"), entry.get("vector")
                    if z and v:
                        self._state[z] = v
            elif msg.get("type") == "sign_update":
                z, v = msg.get("sign"), msg.get("vector")
                if z and v:
                    self._state[z] = v


# Module-level singleton — handlers reference this.
client = BehaviorClient(SERVER_URL)


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _sign_summary(zodiac_name: str) -> str:
    """Compact static trait summary for display below the dropdown."""
    s = get_sign(zodiac_name.lower())
    return (
        f"**{s.name.capitalize()}**  ·  "
        f"{s.element.value} / {s.modality.value} / {s.polarity.value}  ·  "
        f"*{s.temperament}*\n\n"
        f"Drive: **{s.core_drive}**  ·  "
        f"Mode: **{s.behavioral_mode}**  ·  "
        f"Ruler: **{s.ruler.value}**  ·  "
        f"Star: **{s.star.value}**\n\n"
        f"Base speed: `{s.base_speed:.2f}`  ·  "
        f"Glow: `{s.base_glow:.2f}`  ·  "
        f"Star glow: `{s.star_glow:.3f}`  ·  "
        f"Horoscope weight: `{s.horoscope_weight:.2f}`"
    )


def _emotion_bars(vec: dict) -> dict:
    return {
        "anger":    round(float(vec.get("emotion_anger",   0.0)), 4),
        "disgust":  round(float(vec.get("emotion_disgust", 0.0)), 4),
        "fear":     round(float(vec.get("emotion_fear",    0.0)), 4),
        "joy":      round(float(vec.get("emotion_joy",     0.0)), 4),
        "neutral":  round(float(vec.get("emotion_neutral", 0.0)), 4),
        "sadness":  round(float(vec.get("emotion_sadness", 0.0)), 4),
        "surprise": round(float(vec.get("emotion_surprise",0.0)), 4),
    }


def _slider_values(vec: dict) -> list[float]:
    return [round(float(vec.get(dim, 0.0)), 4) for dim in BEHAVIOR_DIMS]


def _build_display(vec: dict, zodiac: str = "", for_date: date = None) -> tuple:
    """Returns (horoscope, dominant_summary, emotion_bars).
    Never includes slider values -- sliders are not auto-updated."""
    if zodiac:
        horoscope = generate_horoscope(zodiac.lower(), for_date or date.today())
    else:
        horoscope = "Select a sign to load its horoscope."
    dominant = vec.get("dominant_emotion", "—")
    valence  = float(vec.get("valence", 0.0))
    summary  = f"**{dominant}**  (valence `{valence:+.3f}`)"
    emotions = _emotion_bars(vec)
    return (horoscope, summary, emotions)


def _delta_md(live_vec: dict, slider_vals: list) -> str:
    """
    Shows live server value vs current slider position for each behavior dim.
    Sliders never move on their own -- this tells the user what the server
    has vs what they are about to send with Apply.
    """
    rows = []
    for dim, set_val in zip(BEHAVIOR_DIMS, slider_vals):
        live_val = round(float(live_vec.get(dim, 0.0)), 4)
        delta    = round(set_val - live_val, 4)
        if abs(delta) < 0.005:
            rows.append(f"`{dim}` &nbsp; live `{live_val:+.3f}` ← matches")
        else:
            arrow = "▲" if delta > 0 else "▼"
            rows.append(
                f"`{dim}` &nbsp; live `{live_val:+.3f}` │ "
                f"set `{set_val:+.3f}` &nbsp;{arrow} Δ `{delta:+.3f}`"
            )
    return "\n\n".join(rows)


# ---------------------------------------------------------------------------
# Gradio event handlers
# ---------------------------------------------------------------------------

_N_DISPLAY = 3   # horoscope + dominant + emotion_bars (no sliders)
_N_SLIDERS = len(BEHAVIOR_DIMS)


def on_zodiac_change(zodiac: str) -> tuple:
    """Sign changed — update traits and pull live values into sliders."""
    traits  = _sign_summary(zodiac)
    vec     = client.latest(zodiac)
    sliders = _slider_values(vec)
    return (traits, *_build_display(vec, zodiac), *sliders, "")


def on_timer_tick(zodiac: str,
                  sp: float, ag: float, ap: float,
                  gl: float, so: float, aggr: float) -> list:
    """
    Tick every TIMER_PERIOD seconds.
    Updates display + delta only. Sliders are NEVER written by the timer.
    """
    vec = client.latest(zodiac)
    if not vec:
        return [gr.update()] * (_N_DISPLAY + 1)
    slider_vals = [sp, ag, ap, gl, so, aggr]
    return [*_build_display(vec, zodiac), _delta_md(vec, slider_vals)]


def on_apply_override(zodiac, speed, agitation, approach, glow, social, aggression) -> None:
    """Push current slider values to server and broadcast to Unity."""
    client.send({
        "type": "override",
        "sign": zodiac.lower(),
        "overrides": {
            "speed_mod":    speed,
            "agitation":    agitation,
            "approach_mod": approach,
            "glow_mod":     glow,
            "social_mod":   social,
            "aggression":   aggression,
        },
    })


def on_reset(zodiac: str) -> tuple:
    """Pull live server values into sliders and clear delta."""
    vec = client.latest(zodiac)
    return (*_build_display(vec, zodiac), *_slider_values(vec), "")


def on_load_date(zodiac: str, date_str: str) -> tuple:
    """Request a specific date, wait for response, update display and sliders."""
    try:
        for_date = date.fromisoformat(date_str)
    except ValueError:
        n = _N_DISPLAY + _N_SLIDERS + 1
        return tuple(gr.update() for _ in range(n))
    client.send({
        "type": "request_sign",
        "sign": zodiac.lower(),
        "date": date_str,
    })
    time.sleep(0.5)
    vec = client.latest(zodiac)
    return (*_build_display(vec, zodiac, for_date), *_slider_values(vec), "")


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

def _make_emotion_chart(label: str):
    if ConfidenceChart is not None:
        return ConfidenceChart(label=label)
    return gr.Label(label=label, num_top_classes=len(EMOTION_LABELS))


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="Zodiac Behavior Engine", theme=Soft()) as demo:

        gr.Markdown("# Zodiac Behavior Engine")
        gr.Markdown(
            "Live behavior vectors decoded daily from procedural horoscopes. "
            "Override any dimension to push a change directly to the Unity scene."
        )

        with gr.Row():

            # ----------------------------------------------------------------
            # Left column — identity + horoscope
            # ----------------------------------------------------------------
            with gr.Column(scale=1):

                zodiac_dd = gr.Dropdown(
                    choices=ZODIAC_NAMES,
                    value="Aries",
                    label="Zodiac Sign",
                )
                traits_md = gr.Markdown(_sign_summary("aries"))

                with gr.Row():
                    date_input = gr.Textbox(
                        value=date.today().isoformat(),
                        label="Date",
                        scale=3,
                    )
                    date_btn = gr.Button("Load", variant="secondary", scale=1)

                horoscope_box = gr.Textbox(
                    label="Today's Horoscope",
                    lines=7,
                    interactive=False,
                )
                dominant_box = gr.Textbox(
                    label="Dominant Emotion",
                    interactive=False,
                )

            # ----------------------------------------------------------------
            # Right column — emotion chart + behavior overrides
            # ----------------------------------------------------------------
            with gr.Column(scale=1):

                emotion_bars = _make_emotion_chart("Emotion Scores")

                gr.Markdown("### Behavior Override")
                gr.Markdown(
                    "Sliders hold your **desired** values and never auto-update from the server. "
                    "The delta panel shows live server state vs your set position. "
                    "**Apply** pushes to Unity. **Reset to Live** syncs sliders to server."
                )

                s_speed    = gr.Slider(-1.0,  1.0, value=0.0, step=0.01, label="speed_mod")
                s_agit     = gr.Slider( 0.0,  1.0, value=0.0, step=0.01, label="agitation")
                s_approach = gr.Slider(-1.0,  1.0, value=0.0, step=0.01, label="approach_mod")
                s_glow     = gr.Slider(-1.0,  1.0, value=0.0, step=0.01, label="glow_mod")
                s_social   = gr.Slider(-1.0,  1.0, value=0.0, step=0.01, label="social_mod")
                s_aggr     = gr.Slider( 0.0,  1.0, value=0.0, step=0.01, label="aggression")

                with gr.Row():
                    apply_btn = gr.Button("Apply Override",  variant="primary")
                    reset_btn = gr.Button("Reset to Live",   variant="secondary")

                delta_md = gr.Markdown(label="Live vs Set", value="")

        timer = gr.Timer(value=TIMER_PERIOD)

        # Component groups
        display_outputs = [horoscope_box, dominant_box, emotion_bars]
        slider_outputs  = [s_speed, s_agit, s_approach, s_glow, s_social, s_aggr]

        # Wiring
        zodiac_dd.change(
            fn=on_zodiac_change,
            inputs=[zodiac_dd],
            outputs=[traits_md, *display_outputs, *slider_outputs, delta_md],
        )

        # Timer reads slider values to compute delta, but never writes to sliders.
        timer.tick(
            fn=on_timer_tick,
            inputs=[zodiac_dd, *slider_outputs],
            outputs=[*display_outputs, delta_md],
        )

        apply_btn.click(
            fn=on_apply_override,
            inputs=[zodiac_dd, *slider_outputs],
            outputs=[],
        )

        reset_btn.click(
            fn=on_reset,
            inputs=[zodiac_dd],
            outputs=[*display_outputs, *slider_outputs, delta_md],
        )

        date_btn.click(
            fn=on_load_date,
            inputs=[zodiac_dd, date_input],
            outputs=[*display_outputs, *slider_outputs, delta_md],
        )

    return demo


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    client.start()
    build_ui().launch()