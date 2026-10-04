#!/usr/bin/env python3
"""
TTS endpoint for the Samvaad demo's personalised lines (the ones that contain the viewer's name).

Two engines, picked with the TTS_ENGINE environment variable:

  edge    (default)  Microsoft Edge neural voices. Fast, runs anywhere.
        pip install fastapi uvicorn edge-tts
        uvicorn tts_server:app --host 0.0.0.0 --port 8000

  parler             Open model from Hugging Face (AI4Bharat Indic Parler-TTS) - much more natural,
                     needs a GPU (see parler_engine.py for setup). Use the SAME engine you used to
                     make the pre-recorded clips, so the whole call has one consistent voice.
        pip install fastapi uvicorn git+https://github.com/huggingface/parler-tts.git soundfile
        TTS_ENGINE=parler uvicorn tts_server:app --host 0.0.0.0 --port 8000

Then set  var TTS_ENDPOINT = 'https://your-host/tts';  in index.html.
(An https site needs an https endpoint, otherwise the browser blocks the request.)
Optional: ALLOWED_ORIGINS="https://yoursite.com" to lock CORS down (default: any origin).
Keep this file next to generate_voices.py (and parler_engine.py for the parler engine).
"""
import asyncio
import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from generate_voices import STYLE, VOICES, get_tts_text, polish

ENGINE = os.getenv("TTS_ENGINE", "edge").lower()
if ENGINE not in ("edge", "parler"):
    raise SystemExit("TTS_ENGINE must be 'edge' or 'parler'")
if ENGINE == "edge":
    import edge_tts
else:
    import parler_engine

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",")],
    allow_methods=["GET"],
    allow_headers=["*"],
)
CACHE: dict = {}  # same voice + same sentence is only synthesised once
READY = {"ok": ENGINE == "edge"}


@app.on_event("startup")
async def _startup():
    if ENGINE == "parler":  # load the model (and run one short sentence) before the first visitor arrives
        await asyncio.to_thread(parler_engine.load)
        await asyncio.to_thread(parler_engine.synth_wav, "en", "agent", "Hello.", False)
    READY["ok"] = True


@app.get("/health")
async def health():
    """The page pings this when the name form opens, so a sleeping host is awake by the time the call starts."""
    return {"ok": READY["ok"], "engine": ENGINE}


async def _edge(lang: str, text: str, role: str, alt: int) -> bytes:
    if lang not in VOICES:
        raise HTTPException(404, "no voice for this language")
    idx = 0 if role == "agent" else 1
    voice = VOICES[lang][idx ^ 1] if alt else VOICES[lang][idx]
    st = STYLE["agent" if role == "agent" else "customer"]
    buf = bytearray()
    for _ in range(3):  # Edge TTS occasionally hiccups; retry before giving up
        buf = bytearray()
        try:
            async for chunk in edge_tts.Communicate(get_tts_text(lang, text), voice, rate=st["rate"], pitch=st["pitch"]).stream():
                if chunk["type"] == "audio":
                    buf += chunk["data"]
        except Exception:
            buf = bytearray()
        if buf:
            break
        await asyncio.sleep(0.6)
    if not buf:
        raise HTTPException(502, "speech synthesis failed")
    return await asyncio.to_thread(polish, bytes(buf))


async def _parler(lang: str, text: str, role: str, alt: int) -> bytes:
    if lang not in parler_engine.SPEAKERS:
        raise HTTPException(404, "no voice for this language")
    try:
        wav = await asyncio.to_thread(parler_engine.synth_wav, lang, role, text, bool(alt))
        return await asyncio.to_thread(parler_engine.to_mp3, wav)
    except Exception as e:
        raise HTTPException(502, f"speech synthesis failed: {e}")


@app.get("/tts")
async def tts(lang: str, text: str = Query(..., min_length=1, max_length=300), role: str = "agent", alt: int = 0):
    """alt=1 swaps the voices (male agent / female customer) - used when the viewer's name is female."""
    role = "agent" if role == "agent" else "customer"
    key = (ENGINE, lang, role, alt, text)
    if key not in CACHE:
        data = await (_edge if ENGINE == "edge" else _parler)(lang, text, role, alt)
        if len(CACHE) > 500:
            CACHE.clear()
        CACHE[key] = data
    return Response(CACHE[key], media_type="audio/mpeg", headers={"Cache-Control": "public, max-age=86400"})