#!/usr/bin/env python3
"""
Tiny TTS endpoint for the Samvaad demo's personalised lines (the ones that contain the viewer's name).

    pip install fastapi uvicorn edge-tts
    uvicorn tts_server:app --host 0.0.0.0 --port 8000

Then set  var TTS_ENDPOINT = 'https://your-host/tts';  in index.html.
(An https site needs an https endpoint, otherwise the browser blocks the request.)
Optional: ALLOWED_ORIGINS="https://yoursite.com" to lock CORS down (default: any origin).

Keep this file next to generate_voices.py - it reuses the same voices and EMI pronunciation fix,
so the name lines sound like the rest of the pre-recorded call.
"""
import asyncio
import os
import edge_tts
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from generate_voices import VOICES, get_style, get_tts_text, polish

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",")],
    allow_methods=["GET"],
    allow_headers=["*"],
)
CACHE: dict = {}  # same voice + same sentence is only synthesised once


@app.get("/health")
async def health():
    """The page pings this when the name form opens, so a sleeping host is awake by the time the call starts."""
    return {"ok": True}


@app.get("/tts")
async def tts(lang: str, text: str = Query(..., min_length=1, max_length=300), role: str = "agent", alt: int = 0):
    """alt=1 swaps the voices (male agent / female customer) - used when the viewer's name is female."""
    if lang not in VOICES:
        raise HTTPException(404, "no voice for this language")
    idx = 0 if role == "agent" else 1
    voice = VOICES[lang][idx ^ 1] if alt else VOICES[lang][idx]
    st = get_style(voice)
    key = (voice, text)
    if key not in CACHE:
        buf = bytearray()
        for attempt in range(3):  # Edge TTS occasionally hiccups; retry before giving up
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
        if len(CACHE) > 500:
            CACHE.clear()
        CACHE[key] = await asyncio.to_thread(polish, bytes(buf))
    return Response(CACHE[key], media_type="audio/mpeg", headers={"Cache-Control": "public, max-age=86400"})