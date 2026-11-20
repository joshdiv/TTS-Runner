"""
ElevenLabs text-to-speech client.

Only talks to the ElevenLabs API: no files, no saved state, no app protocol. The server
(tts_server.py) calls these two functions and decides what to do with the result.

    voices(p)      -> {"voices": [{"id", "name", "category"}, ...]}     cloned voices first
    synthesize(p)  -> (audio_bytes, {"seconds", "mime", "ext"})

p is the request payload from the app: apiKey, text, voiceId, model, stability,
similarity, style, speed. The key falls back to the ELEVENLABS_API_KEY environment variable.
"""
import json
import os
import re
import time
import urllib.error
import urllib.request

BASE_URL = "https://api.elevenlabs.io/v1"
OUTPUT_FORMAT = "mp3_44100_128"
DEFAULT_MODEL = "eleven_v4"
MIN_AUDIO_BYTES = 1000          # anything smaller is an error message, not audio

KEY_HELP = "Add it in the ElevenLabs settings (the gear next to the engine on the Setup page)."


def _key(p):
    key = (p.get("apiKey") or os.environ.get("ELEVENLABS_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("No ElevenLabs API key. " + KEY_HELP)
    return key


def _request(url, key, body=None, timeout=120):
    """GET when there is no body, POST (JSON) when there is. Returns the raw response bytes."""
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        headers={"xi-api-key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"ElevenLabs HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Could not reach ElevenLabs: {e.reason}")


def voices(p):
    """Every voice on the account, cloned ones first."""
    data = json.loads(_request(f"{BASE_URL}/voices", _key(p)).decode("utf-8"))
    rank = {"cloned": 0, "professional": 1, "generated": 2}
    out = [{"id": v["voice_id"], "name": v.get("name", ""), "category": v.get("category", "")}
           for v in data.get("voices", [])]
    out.sort(key=lambda v: (rank.get(v["category"], 3), v["name"].lower()))
    return {"voices": out}


def synthesize(p):
    """Generate one line. Returns (audio_bytes, info)."""
    key = _key(p)
    text = (p.get("text") or "").strip()
    if not text:
        raise RuntimeError("This line has no dialogue text.")
    voice_id = p.get("voiceId")
    if not voice_id:
        raise RuntimeError("No voice chosen for this character.")
    model = p.get("model") or DEFAULT_MODEL
    if not model.startswith("eleven_"):
        raise RuntimeError(f"'{model}' is not an ElevenLabs model. Pick one in the ElevenLabs settings.")

    voice_settings = {
        "stability": float(p.get("stability", 0.5)),
        "similarity_boost": float(p.get("similarity", 0.75)),
    }
    if not re.match(r"eleven_v[34]", model):      # v3/v4 take only stability and similarity
        voice_settings["style"] = float(p.get("style", 0))
        voice_settings["speed"] = float(p.get("speed", 1))
    body = {"text": text, "model_id": model, "voice_settings": voice_settings}

    t0 = time.time()
    audio = _request(f"{BASE_URL}/text-to-speech/{voice_id}?output_format={OUTPUT_FORMAT}", key, body)
    if len(audio) < MIN_AUDIO_BYTES:
        raise RuntimeError("ElevenLabs returned no audio: " + audio.decode("utf-8", "replace")[:200])
    return audio, {"seconds": round(time.time() - t0, 1), "mime": "audio/mpeg", "ext": ".mp3"}