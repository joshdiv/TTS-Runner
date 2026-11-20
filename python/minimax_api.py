
import json
import os
import urllib.error
import urllib.request

DEFAULT_BASE = "https://api.minimax.io"      # US West alternative: https://api-uw.minimax.io
SAMPLE_RATE = 32000
BITRATE = 128000

ERRORS = {
    1000: "unknown error",
    1001: "timeout",
    1002: "rate limit exceeded - raise the delay between lines",
    1004: "authentication failed - check the API key and the Server setting",
    1039: "token rate limit exceeded - raise the delay between lines",
    1042: "too many invalid characters in the text (over 10%)",
    2013: "invalid parameters",
}


def _key(p):
    key = (p.get("apiKey") or os.environ.get("MINIMAX_API_KEY") or "").strip()
    if not key:
        raise ValueError("No MiniMax API key. Add it under Setup > MiniMax, or set MINIMAX_API_KEY.")
    return key


def _base(p):
    return (p.get("baseUrl") or DEFAULT_BASE).rstrip("/")


def _post(url, key, body, timeout=120):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read()[:300].decode("utf-8", "replace")
        raise RuntimeError(f"MiniMax HTTP {e.code}: {detail}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Can't reach MiniMax: {e.reason}")


def _check(resp):
    base = resp.get("base_resp") or {}
    code = base.get("status_code", 0)
    if code != 0:
        why = ERRORS.get(code) or base.get("status_msg") or "request failed"
        raise RuntimeError(f"MiniMax error {code}: {why}")


def voices(p):
    """-> {"voices": [{"id", "name", "category"}]} in the same shape as eleven_voices."""
    resp = _post(f"{_base(p)}/v1/get_voice", _key(p), {"voice_type": "all"}, timeout=30)
    _check(resp)
    out = []
    for field, category in (("system_voice", "system"), ("voice_cloning", "cloned"), ("voice_generation", "generated")):
        for v in resp.get(field) or []:
            vid = v.get("voice_id")
            if vid:
                out.append({"id": vid, "name": v.get("voice_name") or vid, "category": category})
    return {"voices": out}


def synthesize(p):
    """Generate one line. Returns (audio_bytes, info). info = {"seconds", "mime", "ext", "chars"}."""
    voice = {
        "voice_id": p["voiceId"],
        "speed": float(p.get("speed", 1)),
        "vol": float(p.get("vol", 1)),
        "pitch": int(p.get("pitch", 0)),
    }
    if p.get("emotion"):
        voice["emotion"] = p["emotion"]

    body = {
        "model": p.get("model") or "speech-2.8-hd",
        "text": p["text"],
        "stream": False,
        "output_format": "hex",
        "voice_setting": voice,
        "audio_setting": {"sample_rate": SAMPLE_RATE, "bitrate": BITRATE, "format": "mp3", "channel": 1},
    }
    if p.get("languageBoost"):
        body["language_boost"] = p["languageBoost"]

    resp = _post(f"{_base(p)}/v1/t2a_v2", _key(p), body)
    _check(resp)
    data = resp.get("data") or {}          # the docs say data can be null, so check it
    hex_audio = data.get("audio")
    if not hex_audio:
        raise RuntimeError("MiniMax returned no audio.")
    extra = resp.get("extra_info") or {}
    info = {
        "seconds": round((extra.get("audio_length") or 0) / 1000, 1),
        "mime": "audio/mpeg",
        "ext": "mp3",
        "chars": extra.get("usage_characters"),
    }
    return bytes.fromhex(hex_audio), info
