"""
server.py

WebSocket server that decodes daily horoscopes into behavior vectors and
pushes them to connected clients (Unity scene, Gradio dashboard).

All 12 signs are decoded once per calendar day and cached. Any client that
connects after the first gets the cached result immediately.

Usage:
    python server.py

Clients connect to ws://localhost:8765. The protocol is JSON.
Each message has a "type" field that determines its shape.

Outbound message types (server -> client):
    daily_update  -- all 12 vectors for today, sent on connect
    sign_update   -- single sign, sent in response to a request or override

Inbound message types (client -> server):
    request_sign  -- ask for one sign, optionally on a specific date
    request_date  -- ask for all signs on a specific date
    override      -- push manual behavior values for one sign

Wire format notes:
    source_text is excluded from all outbound messages. It contains raw
    horoscope prose with apostrophes and special characters that break
    JsonUtility's parser on the Unity side. Gradio doesn't need it over
    the wire — it can regenerate it locally if needed.

    emotions is sent as a flat object with one float field per emotion
    label, matching the EmotionScores class in BehaviorVectorData.cs.
    JsonUtility cannot deserialize dict[str, float], so the nested dict
    from to_dict() is never sent directly.

Dependencies:
    pip install websockets
"""

from __future__ import annotations

import asyncio
import json
import logging
import signal
from datetime import date
from typing import Any

import websockets
from websockets.asyncio.server import ServerConnection

from horoscope_generator import generate, get_emotion_seed
from decoder import decode
from zodiac_schema import SIGNS

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

HOST = "localhost"
PORT = 8765

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Daily vector cache
# ---------------------------------------------------------------------------

_cache_date:    date | None = None
_cache_vectors: dict[str, dict[str, Any]] = {}
_cache_lock     = asyncio.Lock()


async def _get_daily_vectors(for_date: date) -> dict[str, dict[str, Any]]:
    global _cache_date, _cache_vectors

    async with _cache_lock:
        if _cache_date == for_date:
            return _cache_vectors

        log.info(f"Decoding all 12 signs for {for_date} ...")
        vectors = {}
        for sign in SIGNS:
            horoscope          = generate(sign.name, for_date)
            seed               = get_emotion_seed(sign.name, for_date)
            vec                = decode(f"{seed} {horoscope}")
            vectors[sign.name] = vec.to_dict()
        _cache_date    = for_date
        _cache_vectors = vectors
        log.info("Decode complete.")
        return vectors


# ---------------------------------------------------------------------------
# Wire-safe vector
#
# Strips source_text (horoscope prose with apostrophes/special chars that
# break JsonUtility) and flattens the emotions dict into a plain object so
# JsonUtility can deserialize it into the EmotionScores class.
# ---------------------------------------------------------------------------

def _wire_vector(vec: dict[str, Any]) -> dict[str, Any]:
    emotions_dict = vec.get("emotions", {})
    return {
        # Flat fields -- JsonUtility cannot deserialize dict[str, float].
        # BehaviorVectorData.cs and gradio_app.py both expect this shape.
        "emotion_anger":    emotions_dict.get("anger",    0.0),
        "emotion_disgust":  emotions_dict.get("disgust",  0.0),
        "emotion_fear":     emotions_dict.get("fear",     0.0),
        "emotion_joy":      emotions_dict.get("joy",      0.0),
        "emotion_neutral":  emotions_dict.get("neutral",  0.0),
        "emotion_sadness":  emotions_dict.get("sadness",  0.0),
        "emotion_surprise": emotions_dict.get("surprise", 0.0),
        "dominant_emotion": vec.get("dominant_emotion", "neutral"),
        "valence":          vec.get("valence",          0.0),
        "speed_mod":        vec.get("speed_mod",        0.0),
        "agitation":        vec.get("agitation",        0.0),
        "approach_mod":     vec.get("approach_mod",     0.0),
        "glow_mod":         vec.get("glow_mod",         0.0),
        "social_mod":       vec.get("social_mod",       0.0),
        "aggression":       vec.get("aggression",       0.0),
        # source_text deliberately omitted
    }


# ---------------------------------------------------------------------------
# Message builders
# ---------------------------------------------------------------------------

def _daily_update_msg(for_date: date, vectors: dict[str, dict]) -> str:
    return json.dumps({
        "type":    "daily_update",
        "date":    for_date.isoformat(),
        "vectors": [
            {"sign": sign, "vector": _wire_vector(vec)}
            for sign, vec in vectors.items()
        ],
    })


def _sign_update_msg(sign: str, for_date: date, vector: dict) -> str:
    return json.dumps({
        "type":   "sign_update",
        "sign":   sign,
        "date":   for_date.isoformat(),
        "vector": _wire_vector(vector),
    })


# ---------------------------------------------------------------------------
# Connected client registry
# ---------------------------------------------------------------------------

_clients: set[ServerConnection] = set()


async def _broadcast(message: str) -> None:
    if not _clients:
        return
    await asyncio.gather(
        *[ws.send(message) for ws in _clients],
        return_exceptions=True,
    )


# ---------------------------------------------------------------------------
# Message handler
# ---------------------------------------------------------------------------

async def _handle_message(websocket: ServerConnection, raw: str) -> None:
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("Received non-JSON message -- ignored.")
        return

    msg_type = msg.get("type")

    if msg_type == "request_sign":
        sign_name = msg.get("sign", "").lower()
        date_str  = msg.get("date", date.today().isoformat())
        try:
            for_date = date.fromisoformat(date_str)
        except ValueError:
            log.warning(f"Bad date string: {date_str!r}")
            return
        vectors = await _get_daily_vectors(for_date)
        if sign_name not in vectors:
            log.warning(f"Unknown sign in request_sign: {sign_name!r}")
            return
        await _broadcast(_sign_update_msg(sign_name, for_date, vectors[sign_name]))
        log.info(f"Broadcast sign_update -> {sign_name} for {for_date}")

    elif msg_type == "request_date":
        date_str = msg.get("date", date.today().isoformat())
        try:
            for_date = date.fromisoformat(date_str)
        except ValueError:
            log.warning(f"Bad date string: {date_str!r}")
            return
        vectors = await _get_daily_vectors(for_date)
        await _broadcast(_daily_update_msg(for_date, vectors))
        log.info(f"Broadcast daily_update for {for_date} on request")

    elif msg_type == "override":
        sign_name = msg.get("sign", "").lower()
        overrides = msg.get("overrides", {})
        vectors   = await _get_daily_vectors(date.today())
        if sign_name not in vectors:
            log.warning(f"Unknown sign in override: {sign_name!r}")
            return
        patched = {**vectors[sign_name], **overrides}
        await _broadcast(_sign_update_msg(sign_name, date.today(), patched))
        log.info(f"Broadcast override -> {sign_name}: {overrides}")

    else:
        log.warning(f"Unknown message type: {msg_type!r}")


# ---------------------------------------------------------------------------
# Connection handler
# ---------------------------------------------------------------------------

async def _handle_client(websocket: ServerConnection) -> None:
    addr = websocket.remote_address
    log.info(f"Client connected: {addr}")
    _clients.add(websocket)

    try:
        vectors = await _get_daily_vectors(date.today())
        await websocket.send(_daily_update_msg(date.today(), vectors))
        log.info(f"Sent daily_update to {addr}")

        async for raw in websocket:
            text = raw if isinstance(raw, str) else bytes(raw).decode()
            await _handle_message(websocket, text)

    except websockets.exceptions.ConnectionClosedOK:
        pass
    except websockets.exceptions.ConnectionClosedError as e:
        log.warning(f"Connection error from {addr}: {e}")
    finally:
        _clients.discard(websocket)
        log.info(f"Client disconnected: {addr}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    log.info(f"Starting Zodiac Behavior Server on ws://{HOST}:{PORT}")

    stop = asyncio.get_event_loop().create_future()
    for sig in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_event_loop().add_signal_handler(sig, stop.set_result, None)

    async with websockets.serve(_handle_client, HOST, PORT):
        log.info(f"Ready. Waiting for connections on ws://{HOST}:{PORT}")
        await stop

    log.info("Server shut down cleanly.")


if __name__ == "__main__":
    asyncio.run(main())