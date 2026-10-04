#!/usr/bin/env python3
"""
Generate the "Ingest call" voice clips with an OPEN model from Hugging Face:
AI4Bharat Indic Parler-TTS (natural Telugu, Tamil, Kannada, Malayalam, Gujarati, Odia + Indian English).

Setup (once, on a machine with a GPU - e.g. a free Google Colab T4 - and ffmpeg):
    pip install git+https://github.com/huggingface/parler-tts.git soundfile
    huggingface-cli login            # accept the terms on https://huggingface.co/ai4bharat/indic-parler-tts

Usage
    python generate_voices_hf.py --demo te      # 2 quick test clips -> ./audio_demo  (listen first!)
    python generate_voices_hf.py                # all languages -> ./audio/<lang>/<n>.mp3 and ./audio/<lang>/fc/<n>.mp3
    python generate_voices_hf.py ta te          # only some languages
    python generate_voices_hf.py --resume       # skip clips that already exist (after a disconnect)

Two sets per language, same layout the page already uses:
    audio/<lang>/<n>.mp3      agent = female, customer = male
    audio/<lang>/fc/<n>.mp3   agent = male,   customer = female   (used when the viewer's name is female)
Odia now has real voices too. This overwrites clips made by generate_voices.py (Edge).
"""
import pathlib
import sys
import time

from generate_voices import LINES
import parler_engine as pe


def main(argv):
    demo = "--demo" in argv
    resume = "--resume" in argv
    langs = [a for a in argv if not a.startswith("--")] or list(LINES)
    bad = [l for l in langs if l not in LINES or l not in pe.SPEAKERS]
    if bad:
        sys.exit(f"unknown language(s): {bad}. choose from {sorted(pe.SPEAKERS)}")
    out = pathlib.Path(__file__).resolve().parent / ("audio_demo" if demo else "audio")
    pe.load()
    total = ok = 0
    for lang in langs:
        sets = (("", False),) if demo else (("", False), ("fc", True))
        for sub, alt in sets:
            for i, text in enumerate(LINES[lang]):
                if demo and i > 1:
                    break
                path = out / lang / sub / f"{i}.mp3"
                total += 1
                if resume and path.exists() and path.stat().st_size > 0:
                    ok += 1
                    print(f"skip {path.relative_to(out)}")
                    continue
                role = "agent" if i % 2 == 0 else "customer"
                t0 = time.time()
                try:
                    data = pe.to_mp3(pe.synth_wav(lang, role, text, alt))
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
                    ok += 1
                    print(f"ok   {path.relative_to(out)}  {role:8s} {'F' if pe.is_female(role, alt) else 'M'}  {time.time() - t0:4.1f}s")
                except Exception as e:
                    print(f"FAIL {lang}/{sub}/{i}.mp3  ({e})")
    print(f"\nDone: {ok}/{total} clips in {out}")


if __name__ == "__main__":
    main(sys.argv[1:])