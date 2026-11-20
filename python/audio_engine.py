#!/usr/bin/env python3
"""
Script reader for the TTS Runner.

Reads a recording script (PDF or Word) and returns:
    entries  = {id: dialogue_text}                 in script (file) order
    segments = [{"label": "Scene 1", "ids": [...]}, ...]   headings merged by label

Nothing about IDs or characters is built in. Both come from the rules the app passes
to set_rules() (the Customize dialog, stored in id-rules.json):

    {"characters": [
        {"name": "Henry", "code": "HEN", "group": false,
         "patterns": ["AAA-{HEN}-###", "AAA-{HEN}-AAA-###"]}
    ]}

Each pattern is a mask:
    A      one uppercase letter
    #      one digit
    *      one letter or digit
    {TEXT} the literal text TEXT  (the character's unique code goes in braces)
    other  (- _ .) itself
An ID belongs to the first character that has a pattern matching the whole ID.

Scripts WITHOUT IDs are read by character name instead (used when no ID matches):
    Henry: Hello everybody!          "Name: dialogue"
    HENRY                            standard screenplay: a name in capitals on its own line,
    Hello everybody!                 the dialogue directly under it, a blank line after
IDs are then generated from the name: HENRY_001, HENRY_002 ... per character, in script order. A character's
"aliases" (rules file) map other names in the script onto one character.

Understood headings: "Segment 02 ...", "STATE W2-01", "Scene 1" / "SCENE 01: Title",
and screenplay scene headings (INT. / EXT. ...).

Dialogue is the quoted text after the ID. If an ID has NO quoted text but a bracketed
line instead (e.g. [Laughter]), the bracketed text is kept as the line so it can be
edited by hand into a sound tag.

Quick check from the terminal:
    python audio_engine.py "My Script.docx" id-rules.json
"""
import json
import re
import sys
from pathlib import Path

# ----------------------------- ID rules -----------------------------
_MASK_TOKENS = {"A": "[A-Z]", "#": r"\d", "*": "[A-Z0-9]"}
_NEVER = r"(?!x)x"      # a regex that can never match (used while there are no rules)


def mask_to_regex(mask):
    """Turn a format like 'AAA-{HEN}-###' into a regex string.
    A = letter, # = digit, * = letter or digit, {TEXT} = literal text."""
    mask = str(mask).strip()
    if not mask:
        raise ValueError("empty format")
    out, i = [], 0
    while i < len(mask):
        ch = mask[i]
        if ch == "{":
            j = mask.find("}", i)
            if j == -1 or j == i + 1:
                raise ValueError(f"unclosed or empty {{...}} in '{mask}'")
            out.append(re.escape(mask[i + 1:j]))
            i = j + 1
            continue
        out.append(_MASK_TOKENS.get(ch.upper()) or re.escape(ch))
        i += 1
    return "".join(out)


EXTENSION = re.compile(r"\s*\([^)]*\)\s*$")          # (V.O.) (CONT'D) after a screenplay name


def _key(name):
    """A speaker name in a comparable form: 'Col Landa (V.O.)' -> 'COL LANDA'."""
    name = EXTENSION.sub("", str(name))
    return re.sub(r"\s+", " ", name).strip(" .:").upper()


# Rebuilt by set_rules(). The parser functions look them up each time they run.
ID_IN_PDF = None   # finds IDs inside running text (PDF)
ID_FULL = None     # matches a whole paragraph / table cell that is exactly one ID
RULES = []         # [{"code", "name", "group", "regexes": [compiled, ...]}]
ALIASES = {}       # speaker name in the script -> character code (code, name and aliases of every rule)
GENERATED = {}     # IDs made up for scripts without IDs -> character code


def set_rules(characters=()):
    """Load the character rules. Raises ValueError if a rule is invalid."""
    global ID_IN_PDF, ID_FULL, RULES, ALIASES
    rules, every, seen, aliases = [], [], set(), {}
    for c in characters or []:
        code = str(c.get("code", "")).strip().upper()
        if not code:
            raise ValueError("a character has no code")
        if code in seen:
            raise ValueError(f"the code '{code}' is used twice")
        seen.add(code)
        pats = [mask_to_regex(m) for m in (c.get("patterns") or []) if str(m).strip()]
        rules.append({"code": code, "name": c.get("name") or code, "group": bool(c.get("group")),
                      "regexes": [re.compile(p) for p in pats]})
        every += pats
        for nm in [code, c.get("name")] + list(c.get("aliases") or []):
            if nm and str(nm).strip():
                aliases[_key(nm)] = code
    every.sort(key=len, reverse=True)                    # prefer the longest format when searching running text
    alt = "|".join(f"(?:{p})" for p in every) or _NEVER
    ID_IN_PDF = re.compile(rf"\b(?:{alt})\b")
    ID_FULL = re.compile(rf"(?:{alt})")
    RULES = rules
    ALIASES = aliases


set_rules()


def character_of(sid):
    """Code of the character whose pattern matches this ID, or '' if none does."""
    if sid in GENERATED:
        return GENERATED[sid]
    for r in RULES:
        if any(rx.fullmatch(sid) for rx in r["regexes"]):
            return r["code"]
    return ""


def rule_names():
    """{code: display name} for every character listed in Customize."""
    return {r["code"]: r["name"] for r in RULES}


def group_codes():
    """Codes of characters marked as group lines."""
    return [r["code"] for r in RULES if r["group"]]


# ----------------------------- other patterns -----------------------------
PAUSE_TAG = re.compile(r"<#[^#>]*#>")   # old pause tags are stripped from the script text

# Section headings. Add new heading styles here.
SEGMENT_HEAD = re.compile(
    r"(?:Segment\s+\d+|STATE\s+W\d+-\d+|Scene\s+\d+)[^\n]*", re.IGNORECASE)

QUOTE_GREEDY = re.compile(r"[\u201c\"](.*)[\u201d\"]", re.S)    # one paragraph = one quote
QUOTE_LAZY = re.compile(r"[\u201c\"](.*?)[\u201d\"]", re.S)     # PDF body may hold several things
BRACKET_START = re.compile(r"\s*(\[.*?\])", re.S)
SPEAKER_LABEL = re.compile(r"^[^\"\u201c\u201d\[\]:]{1,40}:\s*")


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


# ----------------------------- scripts without IDs (names only) -----------------------------
SCENE_HEAD = re.compile(r"^(?:INT|EXT|I/E)(?:\s*[./]\s*(?:INT|EXT))?\b[\s.\-/]", re.I)
TRANSITION = re.compile(r"^(?:FADE (?:IN|OUT|TO)|CUT TO|DISSOLVE TO|SMASH CUT|MATCH CUT|THE END|CONTINUED)\b", re.I)
LABEL_LINE = re.compile(r"^([A-Za-z][A-Za-z0-9 .'\-]{0,29}?)\s*:\s*(\S.*)$")      # Henry: dialogue
CUE_LINE = re.compile(r"[A-Z][A-Z0-9 .'\-]*(?:\s*\([^)]*\))?")                      # HENRY   /   HENRY (V.O.)
PAREN_LINE = re.compile(r"^\([^)]*\)$")                                              # (whispering)


def _is_heading(line):
    return bool(SCENE_HEAD.match(line) or SEGMENT_HEAD.match(line))


def _is_cue(line):
    return (bool(CUE_LINE.fullmatch(line)) and len(line.split()) <= 5
            and not _is_heading(line) and not TRANSITION.match(line))


def _code_for(key):
    if key in ALIASES:
        return ALIASES[key]
    return re.sub(r"[^A-Z0-9]", "", key)[:24] or "SPK"


def _raw_lines(path):
    """Every line of the script, blank lines kept (they end a speech in screenplay layout)."""
    if path.suffix.lower() in (".docx", ".docm"):
        import zipfile
        import xml.etree.ElementTree as ET
        W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        with zipfile.ZipFile(str(path)) as z:
            root = ET.fromstring(z.read("word/document.xml"))
        out = []
        for p in root.find(W + "body").iter(W + "p"):
            buf = []
            for el in p.iter():
                if el.tag == W + "t":
                    buf.append(el.text or "")
                elif el.tag == W + "br":
                    buf.append("\n")
                elif el.tag == W + "tab":
                    buf.append(" ")
            out.extend(_fix_dashes("".join(buf)).split("\n"))
        return out
    try:
        from pypdf import PdfReader
    except ImportError:
        sys.exit("Missing package. Run:  pip install pypdf")
    text = _fix_dashes("\n".join((page.extract_text() or "") for page in PdfReader(str(path)).pages))
    return text.splitlines()


def _parse_named(lines):
    """Read a script that has character names instead of IDs. Two layouts, mixed freely:
         Henry: dialogue (may continue on the next lines)
         HENRY / dialogue lines / blank line          (standard screenplay)
       Action lines, scene headings (INT./EXT.) and (parentheticals) are not dialogue.
       A name is accepted when it is a character in the rules, appears at least twice, or
       (screenplay layout with blank lines) stands alone above a speech."""
    lines = [l.strip() for l in lines]
    n = len(lines)
    has_blanks = any(not l for l in lines)

    def label(l):
        m = LABEL_LINE.match(l)
        return (_key(m.group(1)), m.group(2)) if m and not _is_heading(l) else None

    seen = {}
    for i, l in enumerate(lines):
        lab = label(l)
        k = lab[0] if lab else (_key(l) if _is_cue(l) and i + 1 < n and lines[i + 1] else None)
        if k:
            seen[k] = seen.get(k, 0) + 1

    ok_label = lambda k: k in ALIASES or seen.get(k, 0) >= 2
    ok_cue = lambda k: k in ALIASES or seen.get(k, 0) >= 2 or has_blanks
    starts_new = lambda l: (_is_heading(l) or bool(label(l) and ok_label(label(l)[0]))
                            or (_is_cue(l) and ok_cue(_key(l))))

    GENERATED.clear()
    entries, segments, counts, cur = {}, [], {}, None

    def emit(key, text):
        nonlocal cur
        text = _clean_dialogue(text)
        if not text:
            return
        code = _code_for(key)
        counts[code] = counts.get(code, 0) + 1
        sid = f"{code}_{counts[code]:03d}"
        entries[sid] = text
        GENERATED[sid] = code
        if cur is None:
            cur = _segment(segments, "Script")
        cur["ids"].append(sid)

    i = 0
    while i < n:
        l = lines[i]
        i += 1
        if not l:
            continue
        if _is_heading(l):
            cur = _segment(segments, l)
            continue
        lab = label(l)
        if lab and ok_label(lab[0]):
            key, buf = lab
            while i < n and lines[i] and not starts_new(lines[i]):
                buf += " " + lines[i]
                i += 1
            emit(key, buf)
        elif _is_cue(l) and ok_cue(_key(l)) and i < n and lines[i]:
            key, buf = _key(l), []
            while i < n and lines[i] and not starts_new(lines[i]):
                if not PAREN_LINE.match(lines[i]):
                    buf.append(lines[i])
                i += 1
            emit(key, " ".join(buf))
    return entries, [sg for sg in segments if sg["ids"]]


# ----------------------------- public API -----------------------------
def load_script_full(path):
    """Read the recording script (PDF or Word). Returns (entries, segments)."""
    path = Path(path)
    if path.suffix.lower() in (".docx", ".docm"):
        entries, segments = _load_script_docx(path)
    else:
        entries, segments = _load_script_pdf(path)
    if entries:                                   # the script has IDs the rules recognise
        GENERATED.clear()
        return entries, segments
    return _parse_named(_raw_lines(path))         # otherwise read it by character name


def load_script(path):
    """Returns {id: dialogue_text}."""
    return load_script_full(path)[0]


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("Usage: python audio_engine.py <script.docx|script.pdf> <id-rules.json>")
    try:
        data = json.load(open(sys.argv[2], encoding="utf-8"))
        set_rules(data["characters"] if isinstance(data, dict) else data)
    except (ValueError, OSError, KeyError) as e:
        sys.exit(f"Bad rules file: {e}")
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