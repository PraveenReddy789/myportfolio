import WebSocket from 'ws';
import crypto from 'crypto';

const VOICES = {
  en: ['en-IN-NeerjaNeural', 'en-IN-PrabhatNeural'],
  ta: ['ta-IN-PallaviNeural', 'ta-IN-ValluvarNeural'],
  te: ['te-IN-ShrutiNeural', 'te-IN-MohanNeural'],
  ml: ['ml-IN-SobhanaNeural', 'ml-IN-MidhunNeural'],
  gu: ['gu-IN-DhwaniNeural', 'gu-IN-NiranjanNeural'],
  kn: ['kn-IN-SapnaNeural', 'kn-IN-GaganNeural'],
};

const STYLES = {
  agent: { rate: '-4%', pitch: '+0Hz' },
  customer: { rate: '-7%', pitch: '+0Hz' }
};

const EMIS = {
  en: 'E M I',
  ta: 'ஈ எம் ஐ',
  te: 'ఈ ఎం ఐ',
  ml: 'ഈ എം ఐ',
  gu: 'ઈ એમ આઈ',
  kn: 'ಈ ಎಂ ಐ',
};

function formatText(lang, text) {
  if (lang === 'en') {
    text = text.replace(/INR\s*([\d,]+)/g, '$1 rupees');
  }
  if (EMIS[lang]) {
    text = text.split('EMI').join(EMIS[lang]);
  }
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function synthesizeEdgeTTS(lang, voice, text, role) {
  return new Promise((resolve, reject) => {
    const connId = crypto.randomUUID().replace(/-/g, '');
    const reqId = crypto.randomUUID().replace(/-/g, '');
    const url = `wss://speech.platform.bing.com/consumer/speech/synthesize/readaloud/edge/v1?TrustedClientToken=6A5AA1D4EA6542D8A41F31D3FB00E088&ConnectionId=${connId}`;

    const ws = new WebSocket(url, {
      headers: {
        'Origin': 'chrome-extension://jdiccldimpdaibmpdkjnbmckianbfold',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0',
        'Pragma': 'no-cache',
        'Cache-Control': 'no-cache'
      }
    });

    const audioChunks = [];
    let timeout = setTimeout(() => {
      ws.close();
      reject(new Error('TTS synthesis timeout'));
    }, 9000);

    ws.on('open', () => {
      const configMsg = `X-Timestamp:${new Date().toISOString()}\r\nContent-Type:application/json; charset=utf-8\r\nPath:speech.config\r\n\r\n{"context":{"synthesis":{"audio":{"metadataoptions":{"sentenceBoundaryEnabled":"false","wordBoundaryEnabled":"false"},"outputFormat":"audio-24khz-48kbitrate-mono-mp3"}}}}`;
      ws.send(configMsg);

      const st = STYLES[role] || STYLES.agent;
      const formatted = formatText(lang, text);
      const xmlLang = voice.slice(0, 5);
      const ssml = `<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='${xmlLang}'><voice name='${voice}'><prosody pitch='${st.pitch}' rate='${st.rate}'>${formatted}</prosody></voice></speak>`;
      const ssmlMsg = `X-RequestId:${reqId}\r\nContent-Type:application/ssml+xml\r\nPath:ssml\r\nX-Timestamp:${new Date().toISOString()}\r\n\r\n${ssml}`;
      ws.send(ssmlMsg);
    });

    ws.on('message', (data, isBinary) => {
      if (isBinary) {
        const buffer = Buffer.from(data);
        if (buffer.length > 2) {
          const headerLen = buffer.readUInt16BE(0);
          if (buffer.length > 2 + headerLen) {
            const header = buffer.subarray(2, 2 + headerLen).toString('utf-8');
            if (header.includes('Path:audio')) {
              audioChunks.push(buffer.subarray(2 + headerLen));
            }
          }
        }
      } else {
        const str = data.toString('utf-8');
        if (str.includes('Path:turn.end')) {
          clearTimeout(timeout);
          ws.close();
          resolve(Buffer.concat(audioChunks));
        }
      }
    });

    ws.on('error', (err) => {
      clearTimeout(timeout);
      reject(err);
    });
  });
}

export default async function handler(req, res) {
  let lang = 'te', text = '', role = 'agent', alt = false;
  if (req.query) {
    lang = req.query.lang || 'te';
    text = req.query.text || '';
    role = req.query.role || 'agent';
    alt = req.query.alt === '1';
  } else if (req.url) {
    const url = new URL(req.url, 'http://localhost');
    lang = url.searchParams.get('lang') || 'te';
    text = url.searchParams.get('text') || '';
    role = url.searchParams.get('role') || 'agent';
    alt = url.searchParams.get('alt') === '1';
  }

  if (!text) {
    if (res && res.status) return res.status(400).json({ error: 'Missing text parameter' });
    return new Response(JSON.stringify({ error: 'Missing text parameter' }), { status: 400 });
  }

  if (!VOICES[lang]) {
    if (res && res.status) return res.status(404).json({ error: 'Unsupported language' });
    return new Response(JSON.stringify({ error: 'Unsupported language' }), { status: 404 });
  }

  let voiceIndex = role === 'agent' ? 0 : 1;
  if (alt) {
    voiceIndex = 1 - voiceIndex;
  }
  const voice = VOICES[lang][voiceIndex];

  try {
    const audioBuffer = await synthesizeEdgeTTS(lang, voice, text, role);
    if (res && res.setHeader) {
      res.setHeader('Content-Type', 'audio/mpeg');
      res.setHeader('Cache-Control', 'public, max-age=86400');
      res.setHeader('Access-Control-Allow-Origin', '*');
      return res.status(200).send(audioBuffer);
    }
    return new Response(audioBuffer, {
      status: 200,
      headers: {
        'Content-Type': 'audio/mpeg',
        'Cache-Control': 'public, max-age=86400',
        'Access-Control-Allow-Origin': '*'
      }
    });
  } catch (err) {
    if (res && res.status) return res.status(500).json({ error: err.message || 'TTS generation failed' });
    return new Response(JSON.stringify({ error: err.message }), { status: 500 });
  }
}
