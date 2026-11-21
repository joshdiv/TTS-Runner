
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import traceback
from pathlib import Path

# stdout is reserved for the protocol; stray prints go to stderr.
PROTO = sys.stdout
sys.stdout = sys.stderr
for stream in (sys.stdin, PROTO, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import audio_engine as engine  # noqa: E402  (script reader: PDF + Word, IDs, names, segments)
import elevenlabs_api as eleven  # noqa: E402  (ElevenLabs API client)
import minimax_api as minimax  # noqa: E402  (MiniMax API client)

AUDIO_EXTS = (".mp3", ".wav", ".m4a", ".flac", ".ogg")


def send(obj):
    PROTO.write(json.dumps(obj, ensure_ascii=False) + "\n")
    PROTO.flush()


def safe_name(sid):
    return re.sub(r"[^A-Za-z0-9._-]", "_", sid)


# ---------------------------------------------------------------- script
def load_script(p):
    path = Path(p["path"])
    if not path.exists():
        raise FileNotFoundError(f"Script not found: {path}")
    try:
        engine.set_rules(p.get("rules") or [])
    except ValueError as e:
        raise RuntimeError(f"Bad ID rule: {e}")
    entries, segments = engine.load_script_full(path)
    if not entries:
        raise RuntimeError("No dialogue found. Add each character's ID format or name under Customize on the Setup page.")
    names = engine.rule_names()                       # code -> name, for characters listed in Customize
    omit = {str(c).strip().upper() for c in (p.get("ignored") or [])}
    seg_of = {sid: sg["label"] for sg in segments for sid in sg["ids"]}
    everything = [{"id": sid, "text": text, "segment": seg_of.get(sid, ""), "character": engine.character_of(sid), "n": n}
                  for n, (sid, text) in enumerate(entries.items())]

    # every character found in the script, with how many lines, whether Customize knows it, and whether it is omitted
    roster = {}
    for it in everything:
        c = it["character"]
        if not c:
            continue
        r = roster.setdefault(c, {"code": c, "name": names.get(c, c), "count": 0,
                                  "known": c in names, "omitted": c in omit})
        r["count"] += 1

    items = [it for it in everything if it["character"] not in omit]
    hidden = [it for it in everything if it["character"] in omit]     # sent too, so the app can restore them instantly
    empty = [i["id"] for i in items if not i["text"]]
    characters = list(dict.fromkeys(i["character"] for i in items if i["character"]))
    return {"items": items, "segments": [s["label"] for s in segments], "empty": empty,
            "characters": characters, "groups": engine.group_codes(), "roster": list(roster.values()),
            "omittedItems": hidden}


# ---------------------------------------------------------------- saved audio
def list_done(p):
    folder = Path(p["outputDir"])
    if not folder.is_dir():
        return {"done": []}
    files = folder.rglob("*") if p.get("recursive") else folder.iterdir()
    ids = {f.stem for f in files
           if f.is_file() and f.suffix.lower() in AUDIO_EXTS and "__" not in f.stem}
    return {"done": sorted(ids)}


MIME = {".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4", ".flac": "audio/flac", ".ogg": "audio/ogg"}
MAX_PREVIEW_BYTES = 40 * 1024 * 1024


def read_audio(p):
    """Return a saved clip (base64) so the app can play it."""
    sid = safe_name(p["id"])
    for d in p.get("dirs") or []:
        folder = Path(d)
        if not folder.is_dir():
            continue
        files = folder.rglob("*") if p.get("recursive") else folder.iterdir()
        for f in sorted(files):
            if f.is_file() and f.stem == sid and f.suffix.lower() in AUDIO_EXTS:
                size = f.stat().st_size
                if size > MAX_PREVIEW_BYTES:
                    raise RuntimeError(f"{f.name} is too large to preview ({size // 1048576} MB)")
                return {"found": True, "name": f.name, "path": str(f), "size": size,
                        "mime": MIME.get(f.suffix.lower(), "audio/mpeg"),
                        "data": base64.b64encode(f.read_bytes()).decode("ascii")}
    return {"found": False}


# ---------------------------------------------------------------- group lines (several voices mixed)
def list_takes(p):
    """{ 'ADD-W01-GRP-RXN-001': ['BIL', 'REG'], ... } for the files in the GRP folder."""
    folder = Path(p["dir"])
    takes = {}
    if folder.is_dir():
        for f in folder.iterdir():
            if f.is_file() and f.suffix.lower() in AUDIO_EXTS and "__" in f.stem:
                sid, _, ch = f.stem.rpartition("__")
                takes.setdefault(sid, []).append(ch)
    return {"takes": takes}


def mix(p):
    ff = os.environ.get("FFMPEG_PATH") or shutil.which("ffmpeg")
    if not ff:
        raise RuntimeError("ffmpeg not found. Install it, then restart the app.")
    tdir = Path(p["takesDir"])
    out = Path(p["outputDir"])
    out.mkdir(parents=True, exist_ok=True)
    sid = safe_name(p["id"])
    order = p.get("order") or []

    def rank(f):
        ch = f.stem.rpartition("__")[2]
        return (order.index(ch) if ch in order else len(order), ch)

    takes = sorted((f for f in tdir.glob(sid + "__*.*") if f.suffix.lower() in AUDIO_EXTS), key=rank)
    if not takes:
        raise RuntimeError("No voices saved for this line yet.")
    n = len(takes)
    offset = int(p.get("offsetMs", 40))           # small stagger so it sounds like a crowd
    vol = round(1 / (n ** 0.5), 3)
    parts = [f"[{i}:a]adelay={i * offset}|{i * offset},volume={vol}[a{i}]" for i in range(n)]
    graph = (";".join(parts) + ";" + "".join(f"[a{i}]" for i in range(n))
             + f"amix=inputs={n}:normalize=0:duration=longest,alimiter=limit=0.95[out]")
    cmd = [ff, "-y", "-loglevel", "error"]
    for t in takes:
        cmd += ["-i", str(t)]
    tmp = out / f"{sid}.mixing.mp3"
    cmd += ["-filter_complex", graph, "-map", "[out]", "-c:a", "libmp3lame", "-q:a", "2", str(tmp)]
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    r = subprocess.run(cmd, capture_output=True, text=True, creationflags=flags)
    if r.returncode:
        raise RuntimeError("ffmpeg failed: " + r.stderr.strip()[-300:])
    for old in out.glob(sid + ".*"):
        if old != tmp and old.suffix.lower() in AUDIO_EXTS:
            old.unlink()
    dest = out / f"{sid}.mp3"
    tmp.replace(dest)
    if p.get("deleteTakes"):
        for t in takes:
            t.unlink()
        try:
            tdir.rmdir()                          # only succeeds if the folder is now empty
        except OSError:
            pass
    return {"file": str(dest), "name": dest.name, "takes": n}


# ---------------------------------------------------------------- project / session files
def write_text(p):
    """Write a small text file (the project/session file). Written to a temp file first so a crash can't leave it half-written."""
    path = Path(p["path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    if p.get("create_only") and path.exists():
        return {"exists": True, "path": str(path)}
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(p["text"], encoding="utf-8")
    tmp.replace(path)
    return {"path": str(path)}


def read_text(p):
    path = Path(p["path"])
    if not path.is_file():
        return {"found": False}
    return {"found": True, "text": path.read_text(encoding="utf-8")}


# ---------------------------------------------------------------- generating and keeping a clip
_LAST = {"audio": None, "ext": ".mp3"}     # the clip waiting to be kept


def eleven_generate(p):
    """Generate a clip with ElevenLabs. It is held until the app asks to keep it (api_save)."""
    audio, info = eleven.synthesize(p)
    _LAST["audio"], _LAST["ext"] = audio, info["ext"]
    return {"seconds": info["seconds"], "mime": info["mime"],
            "data": base64.b64encode(audio).decode("ascii")}


def minimax_generate(p):
    """Generate a clip with MiniMax. Held until the app asks to keep it (api_save)."""
    audio, info = minimax.synthesize(p)
    _LAST["audio"], _LAST["ext"] = audio, "." + info["ext"].lstrip(".")
    return {"seconds": info["seconds"], "mime": info["mime"],
            "data": base64.b64encode(audio).decode("ascii")}


def api_save(p):
    """Write the last generated clip to <outputDir>/<id>.<ext>, replacing an older take of the same line."""
    if not _LAST["audio"]:
        raise RuntimeError("Nothing generated yet.")
    out = Path(p["outputDir"])
    out.mkdir(parents=True, exist_ok=True)
    sid = safe_name(p["id"])
    for old in out.glob(sid + ".*"):
        if old.suffix.lower() in AUDIO_EXTS:
            old.unlink()
    dest = out / f"{sid}{_LAST['ext']}"
    dest.write_bytes(_LAST["audio"])
    return {"file": str(dest), "name": dest.name}


HANDLERS = {
    "ping": lambda _p: {"ok": True},
    "load_script": load_script,
    "list_done": list_done,
    "read_audio": read_audio,
    "write_text": write_text,
    "read_text": read_text,
    "list_takes": list_takes,
    "mix": mix,
    "eleven_generate": eleven_generate,
    "eleven_voices": eleven.voices,
    "api_save": api_save,
    "minimax_generate": minimax_generate,
    "minimax_voices": minimax.voices,
}


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req_id = None
        try:
            req = json.loads(line)
            req_id = req.get("id")
            handler = HANDLERS.get(req.get("type"))
            if handler is None:
                raise ValueError(f"Unknown request type: {req.get('type')!r}")
            send({"id": req_id, "ok": True, "result": handler(req.get("payload") or {})})
        except Exception as exc:
            traceback.print_exc(file=sys.stderr)
            send({"id": req_id, "ok": False, "error": f"{type(exc).__name__}: {exc}"})


if __name__ == "__main__":
    main()