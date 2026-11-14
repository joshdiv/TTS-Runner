#!/usr/bin/env python3
"""
Script reader for the MiniMax TTS Runner.

Reads a recording script (PDF or Word) and returns:
    entries  = {id: dialogue_text}                 in script (file) order
    segments = [{"label": "Scene 1", "ids": [...]}, ...]   headings merged by label

Understood ID shapes:
    4+ parts: W01-HEN-SEQ-008, UNI-HEN-SEQ-004, ADD-W01-BIL-001, ADD-W01-GRP-RXN-001
    3 parts : W02-HEN-001   (prefix must look like W02)

Understood headings: "Segment 02 ...", "STATE W2-01", "Scene 1" / "SCENE 01: Title".

Dialogue is the quoted text after the ID. If an ID has NO quoted text but a bracketed
line instead (e.g. [Laughter]), the bracketed text is kept as the line so it can be
edited by hand into a sound tag.

Usage for a quick check:  python audio_engine.py "My Script.docx"
"""
import re
import sys
from pathlib import Path

# ----------------------------- patterns -----------------------------
PAUSE_TAG = re.compile(r"<#[^#>]*#>")   # old pause tags are stripped from the script text

ID_IN_PDF = re.compile(
    r"\b(?:"
    r"[A-Z][A-Z0-9]{1,7}-[A-Z][A-Z0-9]{1,7}-[A-Z][A-Z0-9]{1,12}(?:-[A-Z][A-Z0-9]{1,12})?-\d{1,4}"
    r"|[A-Z]\d{1,3}-[A-Z][A-Z0-9]{1,7}-\d{1,4}"
    r")\b"
)
ID_FULL = re.compile(ID_IN_PDF.pattern.replace(r"\b", ""))

# Section headings. Add new heading styles here.
SEGMENT_HEAD = re.compile(
    r"(?:Segment\s+\d+|STATE\s+W\d+-\d+|Scene\s+\d+)[^\n]*", re.IGNORECASE)

QUOTE_GREEDY = re.compile(r"[\u201c\"](.*)[\u201d\"]", re.S)    # one paragraph = one quote
QUOTE_LAZY = re.compile(r"[\u201c\"](.*?)[\u201d\"]", re.S)     # PDF body may hold several things
BRACKET_START = re.compile(r"\s*(\[.*?\])", re.S)
SPEAKER_LABEL = re.compile(r"^[^\"\u201c\u201d\[\]:]{1,40}:\s*")

# ID kinds that are NOT a character (so the character is the second part, e.g. UNI-HEN-SEQ-004 -> HEN)
NON_CHARACTER_KINDS = {
    "SEQ", "CUE", "REACT", "UTILITY", "TERM", "HUMOR", "FEED", "ACTION", "MOVE",
    "GAMECALL", "ALT", "EMOTION", "TEACHER", "SIGNOFF", "SAFE", "LINE",
}


# ----------------------------- helpers -----------------------------
def _fix_dashes(text):
    for dash in "\u2010\u2011\u2012\u2013":
        text = text.replace(dash, "-")
    return text


def _clean_dialogue(text):
    return " ".join(PAUSE_TAG.sub(" ", str(text)).split())


def _segment(segments, label):
    """Return the segment with this label, creating it if needed. Repeated headings
    (e.g. "Scene 1" once per character block) all land in the same segment."""
    label = " ".join(str(label).split())
    for sg in segments:
        if sg["label"] == label:
            return sg
    sg = {"label": label, "ids": []}
    segments.append(sg)
    return sg


def _default_segments(order, size=20):
    n = len(order)
    return [{"label": f"Lines {i + 1}\u2013{min(i + size, n)}", "ids": order[i:i + size]}
            for i in range(0, n, size)]


def character_of(sid):
    """Speaker code from an ID: ADD-W01-BIL-001 -> BIL, ADD-W01-GRP-RXN-001 -> GRP,
    W02-HEN-001 -> HEN, UNI-HEN-SEQ-004 -> HEN."""
    parts = str(sid).split("-")
    if len(parts) < 3:
        return str(sid)
    if len(parts) == 3:
        return parts[1]
    return parts[1] if parts[2] in NON_CHARACTER_KINDS else parts[2]


# ----------------------------- Word script -----------------------------
def _quote_open(s):
    """True while a quote has been opened but not closed yet."""
    return s.count('"') % 2 == 1 or s.count("\u201c") > s.count("\u201d")


def _parse_paragraphs(paras):
    """Paragraph layout: an ID paragraph, then  CHARACTER: "dialogue"  (the quote may run over
    several paragraphs). A labelled [bracket] with no quote (BOG CLASS: [Laughter]) is the line.
    Directions that follow the line are skipped."""
    entries, segments, cur = {}, [], None
    n = len(paras)
    stops = lambda p: bool(ID_FULL.fullmatch(p) or SEGMENT_HEAD.match(p))
    i = 0
    while i < n:
        t = paras[i]
        i += 1
        if SEGMENT_HEAD.match(t):
            cur = _segment(segments, t)
            continue
        if not ID_FULL.fullmatch(t) or t in entries:
            continue
        sid, text, direction, k = t, None, "", i
        for _ in range(2):                              # an unlabelled direction may come first
            if k >= n or stops(paras[k]):
                break
            p = paras[k]
            m = SPEAKER_LABEL.match(p)
            rest = p[m.end():] if m else p
            if re.search(r"[\u201c\"]", rest):          # dialogue, maybe over several paragraphs
                buf = rest
                k += 1
                while _quote_open(buf) and k < n and not stops(paras[k]):
                    buf += " " + paras[k]
                    k += 1
                q = QUOTE_GREEDY.search(buf)
                text = _clean_dialogue(q.group(1) if q else buf.lstrip("\"\u201c"))
                break
            if rest.startswith("["):
                if m:                                   # BOG CLASS: [Laughter]
                    buf = rest
                    k += 1
                    while buf.count("[") > buf.count("]") and k < n and not stops(paras[k]):
                        buf += " " + paras[k]
                        k += 1
                    text = _clean_dialogue(buf)
                    break
                direction = direction or rest           # old layout: direction before the quote
                k += 1
                continue
            break
        if text is None:
            text = _clean_dialogue(direction)
        entries[sid] = text
        if cur is None:
            cur = _segment(segments, "Script")
        cur["ids"].append(sid)
    return entries, [sg for sg in segments if sg["ids"]]


def _load_script_docx(path):
    """Word script. Two layouts:
       1. a table per segment: column 1 = ID, column 2 = dialogue
       2. paragraphs: an ID paragraph, then CHARACTER: "dialogue" (see _parse_paragraphs)"""
    import zipfile
    import xml.etree.ElementTree as ET
    W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(str(path)) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    body = root.find(W + "body")

    def ptext(p):
        return "".join(t.text or "" for t in p.iter(W + "t"))

    entries, segments = {}, []
    cur = None

    # ---- layout 1: tables ----
    for el in body:
        if el.tag == W + "p":
            text = ptext(el).strip()
            if SEGMENT_HEAD.match(text):
                cur = _segment(segments, text)
        elif el.tag == W + "tbl":
            for tr in el.iter(W + "tr"):
                cells = [" ".join(ptext(p) for p in tc.iter(W + "p")).strip()
                         for tc in tr.findall(W + "tc")]
                if len(cells) < 2:
                    continue
                sid = _fix_dashes(cells[0]).strip()
                if not ID_FULL.fullmatch(sid) or sid in entries:
                    continue
                entries[sid] = _clean_dialogue(cells[1])
                if cur is None:
                    cur = _segment(segments, "Script")
                cur["ids"].append(sid)
    if entries:
        return entries, [sg for sg in segments if sg["ids"]]

    # ---- layout 2: paragraphs ----
    paras = [_fix_dashes(ptext(p)).strip() for p in body.iter(W + "p")]
    return _parse_paragraphs([p for p in paras if p])


# ----------------------------- PDF script -----------------------------
def _load_script_pdf(path):
    try:
        from pypdf import PdfReader
    except ImportError:
        sys.exit("Missing package. Run:  pip install pypdf")
    reader = PdfReader(str(path))
    text = _fix_dashes("\n".join((page.extract_text() or "") for page in reader.pages))
    parts = ID_IN_PDF.split(text)
    ids = ID_IN_PDF.findall(text)
    entries = {}
    for i, sid in enumerate(ids):
        body = parts[i + 1]
        m = QUOTE_LAZY.search(body)
        if m:
            line = _clean_dialogue(m.group(1))
        else:
            b = BRACKET_START.match(body)
            line = _clean_dialogue(b.group(1)) if b else ""
        entries.setdefault(sid, line)

    events = sorted([(m.start(), "h", " ".join(m.group(0).split())) for m in SEGMENT_HEAD.finditer(text)] +
                    [(m.start(), "i", m.group(0)) for m in ID_IN_PDF.finditer(text)])
    segments, cur, seen = [], None, set()
    for _, kind, val in events:
        if kind == "h":
            cur = _segment(segments, val)
        elif val not in seen and val in entries:
            seen.add(val)
            if cur is None:
                cur = _segment(segments, "Script")
            cur["ids"].append(val)
    segments = [sg for sg in segments if sg["ids"]]
    if len(segments) < 2:
        segments = _default_segments(list(entries))
    return entries, segments


# ----------------------------- public API -----------------------------
def load_script_full(path):
    """Read the recording script (PDF or Word). Returns (entries, segments)."""
    path = Path(path)
    if path.suffix.lower() in (".docx", ".docm"):
        return _load_script_docx(path)
    return _load_script_pdf(path)


def load_script(path):
    """Returns {id: dialogue_text}."""
    return load_script_full(path)[0]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage: python audio_engine.py <script.docx|script.pdf>")
    ents, segs = load_script_full(sys.argv[1])
    print(f"{len(ents)} IDs in {len(segs)} segments")
    for sg in segs:
        chars = {}
        for sid in sg["ids"]:
            chars[character_of(sid)] = chars.get(character_of(sid), 0) + 1
        print(f"  {sg['label']}: {len(sg['ids'])} lines  {chars}")
    brackets = [s for s, t in ents.items() if t.startswith("[")]
    empty = [s for s, t in ents.items() if not t]
    print(f"Bracket-only lines: {len(brackets)}   Empty lines: {len(empty)}")