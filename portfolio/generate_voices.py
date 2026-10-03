#!/usr/bin/env python3
"""
Generate natural-sounding voice clips for the "Ingest call" demo (Microsoft Edge neural TTS).

Usage
    pip install edge-tts
    python generate_voices.py            # creates ./audio/<lang>/<line>.mp3
    python generate_voices.py ta te      # only some languages
    python generate_voices.py --voices   # list the Indian voices your install can see

Then put the "audio" folder next to index.html. Even-numbered lines (0, 2, 4, 6)
are the AGENT; odd-numbered lines (1, 3, 5, 7) are the CUSTOMER.

Two sets are generated per language:
    audio/<lang>/<n>.mp3      agent = female voice, customer = male voice     (male / no name)
    audio/<lang>/fc/<n>.mp3   agent = male voice,   customer = female voice   (female viewer name)
Re-run this script whenever you change the call lines.
"""
import asyncio, pathlib, re, shutil, subprocess, sys
import edge_tts

# language -> (agent voice, customer voice)
VOICES = {
    "en": ("en-IN-NeerjaNeural",   "en-IN-PrabhatNeural"),
    "ta": ("ta-IN-PallaviNeural",  "ta-IN-ValluvarNeural"),
    "te": ("te-IN-ShrutiNeural",   "te-IN-MohanNeural"),
    "ml": ("ml-IN-SobhanaNeural",  "ml-IN-MidhunNeural"),
    "gu": ("gu-IN-DhwaniNeural",   "gu-IN-NiranjanNeural"),
    "kn": ("kn-IN-SapnaNeural",    "kn-IN-GaganNeural"),
    # "or" (Odia): Edge TTS has no Odia voice. The demo falls back to captions only.
}

# Phone-call pacing: natural relaxed pacing for both agent and customer (-7% rate, +0Hz pitch)
STYLE = {"agent": {"rate": "-7%", "pitch": "+0Hz"}, "customer": {"rate": "-7%", "pitch": "+0Hz"}}

LINES = {
    "en": [
        "Hello Mr. Praveen, this is Samvaad calling about your loan EMI.",
        "Yes, please go ahead.",
        "Mr. Praveen, your EMI of INR 12,500 was due on 20 September.",
        "Yes, my salary came late this month.",
        "I understand, Mr. Praveen. When can you make the payment?",
        "I will pay the full amount of INR 12,500 by 7 October.",
        "Thank you, Mr. Praveen. I have noted the full payment of INR 12,500 by 7 October.",
        "Okay, thank you."
    ],
    "ta": [
        "வணக்கம் பிரவீன் அவர்களே, நான் சம்வாத் அழைக்கிறேன், உங்கள் கடன் EMI பற்றி.",
        "ஆமாம், சொல்லுங்கள்.",
        "பிரவீன் அவர்களே, உங்கள் ₹12,500 EMI செப்டம்பர் 20 அன்று செலுத்த வேண்டியது.",
        "ஆமாம், இந்த மாதம் சம்பளம் தாமதமாக வந்தது.",
        "புரிகிறது, பிரவீன் அவர்களே. எப்போது செலுத்த முடியும்?",
        "அக்டோபர் 7க்குள் முழுத் தொகையான ₹12,500 செலுத்துகிறேன்.",
        "நன்றி, பிரவீன் அவர்களே. அக்டோபர் 7க்குள் ₹12,500 முழுத் தொகை செலுத்துவதாகக் குறித்துக்கொண்டேன்.",
        "சரி, நன்றி."
    ],
    "te": [
        "నమస్కారం ప్రవీణ్ గారు, నేను సంవాద్ నుండి మాట్లాడుతున్నాను, మీ లోన్ EMI గురించి.",
        "అవును, చెప్పండి.",
        "ప్రవీణ్ గారు, మీ ₹12,500 EMI సెప్టెంబర్ 20 న చెల్లించాల్సి ఉంది.",
        "అవును, ఈ నెల జీతం ఆలస్యంగా వచ్చింది.",
        "అర్థమైంది, ప్రవీణ్ గారు. ఎప్పుడు చెల్లించగలరు?",
        "అక్టోబర్ 7 లోపు పూర్తి మొత్తం ₹12,500 చెల్లిస్తాను.",
        "ధన్యవాదాలు, ప్రవీణ్ గారు. అక్టోబర్ 7 లోపు పూర్తి మొత్తం ₹12,500 చెల్లింపు నమోదు చేశాను.",
        "సరే, ధన్యవాదాలు."
    ],
    "ml": [
        "നമസ്കാരം ശ്രീ പ്രവീൺ, ഞാൻ സംവാദിൽ നിന്നാണ് വിളിക്കുന്നത്, നിങ്ങളുടെ വായ്പ EMI സംബന്ധിച്ച്.",
        "ശരി, പറയൂ.",
        "ശ്രീ പ്രവീൺ, നിങ്ങളുടെ ₹12,500 EMI സെപ്റ്റംബർ 20-ന് അടയ്ക്കേണ്ടതായിരുന്നു.",
        "അതെ, ഈ മാസം ശമ്പളം വൈകിയാണ് കിട്ടിയത്.",
        "മനസ്സിലായി, ശ്രീ പ്രവീൺ. എപ്പോൾ അടയ്ക്കാൻ കഴിയും?",
        "ഒക്ടോബർ 7-നകം മുഴുവൻ തുകയായ ₹12,500 അടയ്ക്കാം.",
        "നന്ദി, ശ്രീ പ്രവീൺ. ഒക്ടോബർ 7-നകം ₹12,500 മുഴുവൻ തുകയും അടയ്ക്കുമെന്ന് രേഖപ്പെടുത്തി.",
        "ശരി, നന്ദി."
    ],
    "gu": [
        "નમસ્તે શ્રી પ્રવીણ, હું સંવાદમાંથી બોલું છું, તમારી લોન EMI વિશે.",
        "હા, બોલો.",
        "શ્રી પ્રવીણ, તમારી ₹12,500 ની EMI 20 સપ્ટેમ્બરે ભરવાની હતી.",
        "હા, આ મહિને પગાર મોડો આવ્યો.",
        "સમજાયું, શ્રી પ્રવીણ. તમે ક્યારે ચૂકવણી કરી શકશો?",
        "7 ઓક્ટોબર સુધીમાં પૂરી રકમ ₹12,500 ભરી દઈશ.",
        "આભાર, શ્રી પ્રવીણ. 7 ઓક્ટોબર સુધીમાં પૂરી ₹12,500 ની ચુકવણી નોંધાઈ ગઈ છે.",
        "સારું, આભાર."
    ],
    "or": [
        "ନମସ୍କାର ଶ୍ରୀ ପ୍ରବୀଣ, ମୁଁ ସଂବାଦରୁ କହୁଛି, ଆପଣଙ୍କ ଲୋନ୍ EMI ବିଷୟରେ।",
        "ହଁ, କୁହନ୍ତୁ।",
        "ଶ୍ରୀ ପ୍ରବୀଣ, ଆପଣଙ୍କ ₹12,500 EMI ସେପ୍ଟେମ୍ବର 20 ରେ ଦେୟ ଥିଲା।",
        "ହଁ, ଏହି ମାସ ଦରମା ଡେରିରେ ଆସିଲା।",
        "ବୁଝିଲି, ଶ୍ରୀ ପ୍ରବୀଣ। ଆପଣ କେବେ ଦେଇପାରିବେ?",
        "ଅକ୍ଟୋବର 7 ସୁଦ୍ଧା ପୂରା ରାଶି ₹12,500 ଦେବି।",
        "ଧନ୍ୟବାଦ, ଶ୍ରୀ ପ୍ରବୀଣ। ଅକ୍ଟୋବର 7 ସୁଦ୍ଧା ପୂରା ₹12,500 ଦେୟ ଲେଖିନେଲି।",
        "ଠିକ୍ ଅଛି, ଧନ୍ୟବାଦ।"
    ],
    "kn": [
        "ನಮಸ್ಕಾರ ಪ್ರವೀಣ್ ಅವರೇ, ನಾನು ಸಂವಾದ್‌ನಿಂದ ಕರೆ ಮಾಡುತ್ತಿದ್ದೇನೆ, ನಿಮ್ಮ ಸಾಲದ EMI ಬಗ್ಗೆ.",
        "ಹೌದು, ಹೇಳಿ.",
        "ಪ್ರವೀಣ್ ಅವರೇ, ನಿಮ್ಮ ₹12,500 EMI ಸೆಪ್ಟೆಂಬರ್ 20 ರಂದು ಪಾವತಿಸಬೇಕಿತ್ತು.",
        "ಹೌದು, ಈ ತಿಂಗಳು ಸಂಬಳ ತಡವಾಗಿ ಬಂತು.",
        "ಅರ್ಥವಾಯಿತು, ಪ್ರವೀಣ್ ಅವರೇ. ನೀವು ಯಾವಾಗ ಪಾವತಿಸಬಹುದು?",
        "ಅಕ್ಟೋಬರ್ 7 ರೊಳಗೆ ಪೂರ್ಣ ಮೊತ್ತ ₹12,500 ಪಾವತಿಸುತ್ತೇನೆ.",
        "ಧನ್ಯವಾದಗಳು, ಪ್ರವೀಣ್ ಅವರೇ. ಅಕ್ಟೋಬರ್ 7 ರೊಳಗೆ ಪೂರ್ಣ ಮೊತ್ತ ₹12,500 ಪಾವತಿಯನ್ನು ದಾಖಲಿಸಿದ್ದೇನೆ.",
        "ಸರಿ, ಧನ್ಯವಾದಗಳು."
    ]
}

LINES_FC = {
    "en": [
        "Hello Ms. Priya, this is Samvaad calling about your loan EMI.",
        "Yes, please go ahead.",
        "Ms. Priya, your EMI of INR 12,500 was due on 20 September.",
        "Yes, my salary came late this month.",
        "I understand, Ms. Priya. When can you make the payment?",
        "I will pay the full amount of INR 12,500 by 7 October.",
        "Thank you, Ms. Priya. I have noted the full payment of INR 12,500 by 7 October.",
        "Okay, thank you."
    ],
    "ta": [
        "வணக்கம் பிரியா அவர்களே, நான் சம்வாத் அழைக்கிறேன், உங்கள் கடன் EMI பற்றி.",
        "ஆமாம், சொல்லுங்கள்.",
        "பிரியா அவர்களே, உங்கள் ₹12,500 EMI செப்டம்பர் 20 அன்று செலுத்த வேண்டியது.",
        "ஆமாம், இந்த மாதம் சம்பளம் தாமதமாக வந்தது.",
        "புரிகிறது, பிரியா அவர்களே. எப்போது செலுத்த முடியும்?",
        "அக்டோபர் 7க்குள் முழுத் தொகையான ₹12,500 செலுத்துகிறேன்.",
        "நன்றி, பிரியா அவர்களே. அக்டோபர் 7க்குள் ₹12,500 முழுத் தொகை செலுத்துவதாகக் குறித்துக்கொண்டேன்.",
        "சரி, நன்றி."
    ],
    "te": [
        "నమస్కారం ప్రియ గారు, నేను సంవాద్ నుండి మాట్లాడుతున్నాను, మీ లోన్ EMI గురించి.",
        "అవును, చెప్పండి.",
        "ప్రియ గారు, మీ ₹12,500 EMI సెప్టెంబర్ 20 న చెల్లించాల్సి ఉంది.",
        "అవును, ఈ నెల జీతం ఆలస్యంగా వచ్చింది.",
        "అర్థమైంది, ప్రియ గారు. ఎప్పుడు చెల్లించగలరు?",
        "అక్టోబర్ 7 లోపు పూర్తి మొత్తం ₹12,500 చెల్లిస్తాను.",
        "ధన్యవాదాలు, ప్రియ గారు. అక్టోబర్ 7 లోపు పూర్తి మొత్తం ₹12,500 చెల్లింపు నమోదు చేశాను.",
        "సరే, ధన్యవాదాలు."
    ],
    "ml": [
        "നമസ്കാരം ശ്രീമതി പ്രിയ, ഞാൻ സംവാദിൽ നിന്നാണ് വിളിക്കുന്നത്, നിങ്ങളുടെ വായ്പ EMI സംബന്ധിച്ച്.",
        "ശരി, പറയൂ.",
        "ശ്രീമതി പ്രിയ, നിങ്ങളുടെ ₹12,500 EMI സെപ്റ്റംബർ 20-ന് അടയ്ക്കേണ്ടതായിരുന്നു.",
        "അതെ, ഈ മാസം ശമ്പളം വൈകിയാണ് കിട്ടിയത്.",
        "മനസ്സിലായി, ശ്രീമതി പ്രിയ. എപ്പോൾ അടയ്ക്കാൻ കഴിയും?",
        "ഒക്ടോബർ 7-നകം മുഴുവൻ തുകയായ ₹12,500 അടയ്ക്കാം.",
        "നന്ദി, ശ്രീമതി പ്രിയ. ഒക്ടോബർ 7-നകം ₹12,500 മുഴുവൻ തുകയും അടയ്ക്കുമെന്ന് രേഖപ്പെടുത്തി.",
        "ശരി, നന്ദി."
    ],
    "gu": [
        "નમસ્તે શ્રીમતી પ્રિયા, હું સંવાદમાંથી બોલું છું, તમારી લોન EMI વિશે.",
        "હા, બોલો.",
        "શ્રીમતી પ્રિયા, તમારી ₹12,500 ની EMI 20 સપ્ટેમ્બરે ભરવાની હતી.",
        "હા, આ મહિને પગાર મોડો આવ્યો.",
        "સમજાયું, શ્રીમતી પ્રિયા. તમે ક્યારે ચૂકવણી કરી શકશો?",
        "7 ઓક્ટોબર સુધીમાં પૂરી રકમ ₹12,500 ભરી દઈશ.",
        "આભાર, શ્રીમતી પ્રિયા. 7 ઓક્ટોબર સુધીમાં પૂરી ₹12,500 ની ચુકવણી નોંધાઈ ગઈ છે.",
        "સારું, આભાર."
    ],
    "or": [
        "ନମସ୍କାର ଶ୍ରୀମତୀ ପ୍ରିୟା, ମୁଁ ସଂବାଦରୁ କହୁଛି, ଆପଣଙ୍କ ଲୋନ୍ EMI ବିଷୟରେ।",
        "ହଁ, କୁହନ୍ତୁ।",
        "ଶ୍ରୀମତୀ ପ୍ରିୟା, ଆପଣଙ୍କ ₹12,500 EMI ସେପ୍ଟେମ୍ବର 20 ରେ ଦେୟ ଥିଲା।",
        "ହଁ, ଏହି ମାସ ଦରମା ଡେରିରେ ଆସିଲା।",
        "ବୁଝିଲି, ଶ୍ରୀମତୀ ପ୍ରିୟା। ଆପଣ କେବେ ଦେଇପାରିବେ?",
        "ଅକ୍ଟୋବର 7 ସୁଦ୍ଧା ପୂରା ରାଶି ₹12,500 ଦେବି।",
        "ଧନ୍ୟବାଦ, ଶ୍ରୀମତୀ ପ୍ରିୟା। ଅକ୍ଟୋବର 7 ସୁଦ୍ଧା ପୂରା ₹12,500 ଦେୟ ଲେଖିନେଲି।",
        "ଠିକ୍ ଅଛି, ଧନ୍ୟବାଦ।"
    ],
    "kn": [
        "ನಮಸ್ಕಾರ ಪ್ರಿಯಾ ಅವರೇ, ನಾನು ಸಂವಾದ್‌ನಿಂದ ಕರೆ ಮಾಡುತ್ತಿದ್ದೇನೆ, ನಿಮ್ಮ ಸಾಲದ EMI ಬಗ್ಗೆ.",
        "ಹೌದು, ಹೇಳಿ.",
        "ಪ್ರಿಯಾ ಅವರೇ, ನಿಮ್ಮ ₹12,500 EMI ಸೆಪ್ಟೆಂಬರ್ 20 ರಂದು ಪಾವತಿಸಬೇಕಿತ್ತು.",
        "ಹೌದು, ಈ ತಿಂಗಳು ಸಂಬಳ ತಡವಾಗಿ ಬಂತು.",
        "ಅರ್ಥವಾಯಿತು, ಪ್ರಿಯಾ ಅವರೇ. ನೀವು ಯಾವಾಗ ಪಾವತಿಸಬಹುದು?",
        "ಅಕ್ಟೋಬರ್ 7 ರೊಳಗೆ ಪೂರ್ಣ ಮೊತ್ತ ₹12,500 ಪಾವತಿಸುತ್ತೇನೆ.",
        "ಧನ್ಯವಾದಗಳು, ಪ್ರಿಯಾ ಅವರೇ. ಅಕ್ಟೋಬರ್ 7 ರೊಳಗೆ ಪೂರ್ಣ ಮೊತ್ತ ₹12,500 ಪಾವತಿಯನ್ನು ದಾಖಲಿಸಿದ್ದೇನೆ.",
        "ಸರಿ, ಧನ್ಯವಾದಗಳು."
    ]
}

# phonetic replacements for TTS engines to pronounce acronyms distinctly (e.g. E-M-I instead of 'yemi')
TTS_PRONUNCIATIONS = {
    "en": {"EMI": "E M I"},
    "ta": {"EMI": "ஈ எம் ஐ"},
    "te": {"EMI": "ఈ ఎం ఐ"},
    "ml": {"EMI": "ഈ എം ഐ"},
    "gu": {"EMI": "ઈ એમ આઈ"},
    "kn": {"EMI": "ಈ ಎಂ ಐ"},
    "or": {"EMI": "ଇ ଏମ୍ ଆଇ"},
}

def get_tts_text(lang, text):
    # English: "INR 12,500" reads far more naturally as "12,500 rupees"
    if lang == "en":
        text = re.sub(r"INR\s*([\d,]+)", r"\1 rupees", text)
    for word, replacement in TTS_PRONUNCIATIONS.get(lang, {}).items():
        text = text.replace(word, replacement)
    return text


# ---- optional polish with ffmpeg: trim Edge's leading/trailing silence and even out loudness,
# so both speakers sit at the same volume and turns follow each other like a real call.
FFMPEG = shutil.which("ffmpeg")
if not FFMPEG:
    try:
        import imageio_ffmpeg
        FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        FFMPEG = None
POLISH = ("silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.04,"
          "areverse,silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.10,areverse,"
          "loudnorm=I=-18:TP=-2:LRA=9")


def polish(data: bytes) -> bytes:
    if not FFMPEG or not data:
        return data
    try:
        r = subprocess.run([FFMPEG, "-loglevel", "error", "-i", "pipe:0", "-af", POLISH,
                            "-ar", "24000", "-ac", "1", "-b:a", "64k", "-f", "mp3", "pipe:1"],
                           input=data, capture_output=True, timeout=30)
        return r.stdout if r.returncode == 0 and len(r.stdout) > 1000 else data
    except Exception:
        return data

OUT = pathlib.Path(__file__).resolve().parent / "audio"


async def synth(sem, lang, i, text, voice, role, sub=""):
    path = OUT / lang / sub / f"{i}.mp3"
    path.parent.mkdir(parents=True, exist_ok=True)
    spoken_text = get_tts_text(lang, text)
    err = None
    async with sem:
        for _ in range(3):
            try:
                st = STYLE[role]
                await edge_tts.Communicate(spoken_text, voice, rate=st["rate"], pitch=st["pitch"]).save(str(path))
                if path.stat().st_size > 0:
                    path.write_bytes(await asyncio.to_thread(polish, path.read_bytes()))
                    print(f"ok   {lang}/{sub + '/' if sub else ''}{i}.mp3  {voice}")
                    return True
            except Exception as e:  # network hiccup: retry
                err = e
                await asyncio.sleep(1.5)
    print(f"FAIL {lang}/{sub + '/' if sub else ''}{i}.mp3  {voice}  ({err})")
    return False


async def main(langs):
    if not FFMPEG:
        print("note: ffmpeg not found - clips keep Edge's silence padding and uneven loudness "
              "(install ffmpeg and re-run for a more natural result)\n")
    avail = {v["ShortName"] for v in await edge_tts.list_voices()}
    sem = asyncio.Semaphore(4)
    jobs = []
    for lang in langs:
        if lang not in VOICES:
            print(f"skip {lang}: no Edge TTS voice (captions only in the demo)")
            continue
        agent, cust = VOICES[lang]
        for v in (agent, cust):
            if v not in avail:
                print(f"warning: voice {v} not found in your edge-tts voice list")
        for i, text in enumerate(LINES[lang]):
            role = "agent" if i % 2 == 0 else "customer"
            jobs.append(synth(sem, lang, i, text, agent if role == "agent" else cust, role))
            # female customer set (Priya): male agent, female customer
            text_fc = LINES_FC[lang][i] if lang in LINES_FC else text
            jobs.append(synth(sem, lang, i, text_fc, cust if role == "agent" else agent, role, "fc"))
    res = await asyncio.gather(*jobs)
    print(f"\nDone: {sum(res)}/{len(res)} clips in {OUT}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--voices" in args:
        async def show():
            for v in await edge_tts.list_voices():
                if v["Locale"].endswith("-IN"):
                    print(v["ShortName"], v["Gender"])
        asyncio.run(show())
    else:
        asyncio.run(main(args or list(LINES)))