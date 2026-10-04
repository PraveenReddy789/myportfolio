"""
Indic Parler-TTS (open model by AI4Bharat + Hugging Face, Apache-2.0) - shared by
generate_voices_hf.py (pre-recorded clips) and tts_server.py (the lines with the viewer's name).

    pip install git+https://github.com/huggingface/parler-tts.git soundfile
    (and ffmpeg on the machine)

Model card: https://huggingface.co/ai4bharat/indic-parler-tts   (you may need to log in with
`huggingface-cli login` and accept the terms on that page once).
A GPU is strongly recommended - on CPU every sentence takes a minute or more.
"""
import io
import os
import threading

from generate_voices import FFMPEG, get_tts_text, polish

MODEL_ID = os.getenv("PARLER_MODEL", "ai4bharat/indic-parler-tts")
SEED = int(os.getenv("PARLER_SEED", "7"))

# (female speaker, male speaker) per language, taken from the model card's recommended speakers.
# Tamil has no recommended male speaker, so the male Tamil voice is described instead of named.
SPEAKERS = {
    "en": ("Mary", "Thoma"),
    "te": ("Lalitha", "Prakash"),
    "ta": ("Jaya", None),
    "ml": ("Anjali", "Harish"),
    "gu": ("Neha", "Yash"),
    "kn": ("Anu", "Suresh"),
    "or": ("Debjani", "Manas"),
}

# How each speaker should sound. Plain English; edit freely and re-generate.
# (Card tips: "very clear audio" gives the best quality, commas in the text add small breaths.)
DELIVERY = {
    "agent": "speaks at a natural, moderate pace in a warm, polite and professional tone, with gentle expressiveness",
    "customer": "speaks at a calm, relaxed, moderate pace in a natural, conversational tone",
}
QUALITY = ("The recording is of very high quality, very clear audio with no background noise, "
           "and the voice sounds very close up.")

_state = {}
_lock = threading.Lock()  # one generation at a time (a single GPU)


def is_female(role: str, alt: bool) -> bool:
    """Normal set: agent female / customer male.  alt (female viewer): agent male / customer female."""
    return (role == "agent") != bool(alt)


def describe(lang: str, female: bool, role: str) -> str:
    name = SPEAKERS[lang][0 if female else 1]
    who = name or ("A female speaker" if female else "A male speaker with a deep, steady voice")
    return f"{who} {DELIVERY[role]}. {QUALITY}"


def load():
    if _state:
        return _state
    import torch
    from parler_tts import ParlerTTSForConditionalGeneration
    from transformers import AutoTokenizer

    dev = "cuda:0" if torch.cuda.is_available() else "cpu"
    # bf16 only where the GPU supports it natively (Ampere+); otherwise full precision
    dtype = torch.bfloat16 if dev.startswith("cuda") and torch.cuda.get_device_capability()[0] >= 8 else torch.float32
    model = ParlerTTSForConditionalGeneration.from_pretrained(MODEL_ID, torch_dtype=dtype).to(dev)
    tok = AutoTokenizer.from_pretrained(MODEL_ID)
    dtok = AutoTokenizer.from_pretrained(model.config.text_encoder._name_or_path)
    _state.update(model=model, tok=tok, dtok=dtok, dev=dev, torch=torch)
    print(f"Indic Parler-TTS ready on {dev} ({str(dtype).split('.')[-1]})")
    return _state


def synth_wav(lang: str, role: str, text: str, alt: bool = False) -> bytes:
    """One sentence -> WAV bytes. The same (lang, voice) always uses the same seed so a speaker stays consistent."""
    import soundfile as sf

    s = load()
    torch, dev = s["torch"], s["dev"]
    female = is_female(role, alt)
    desc = describe(lang, female, role)
    prompt = get_tts_text(lang, text)
    with _lock:
        torch.manual_seed(SEED + 10 * sorted(SPEAKERS).index(lang) + int(female))
        d = s["dtok"](desc, return_tensors="pt").to(dev)
        p = s["tok"](prompt, return_tensors="pt").to(dev)
        with torch.inference_mode():
            gen = s["model"].generate(input_ids=d.input_ids, attention_mask=d.attention_mask,
                                      prompt_input_ids=p.input_ids, prompt_attention_mask=p.attention_mask)
        audio = gen.float().cpu().numpy().squeeze()
        buf = io.BytesIO()
        sf.write(buf, audio, s["model"].config.sampling_rate, format="WAV")
    return buf.getvalue()


def to_mp3(wav: bytes) -> bytes:
    """Trim silence, level the volume and encode - higher bitrate than the Edge clips since this is the quality path."""
    if not FFMPEG:
        raise RuntimeError("ffmpeg is required to turn the generated audio into mp3 (install ffmpeg)")
    out = polish(wav, ar=32000, br="96k")
    if out[:4] == b"RIFF":
        raise RuntimeError("ffmpeg could not encode the audio")
    return out