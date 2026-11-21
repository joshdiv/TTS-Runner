import json
import re
import sys
from collections import Counter
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
        raise RuntimeError("Reading PDFs needs a package. Run:  pip install pdfplumber")
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
PAGE_NUMBER = re.compile(r"^\d{1,3}\.?$")                                            # 22.   (a page number on its own line)
PAGE_FURNITURE = re.compile(r"^\(?\s*(?:MORE|CONTINUED|CONT'D|CONTINUING)\s*\)?\s*:?$", re.I)
SCENE_NUM_BOTH = re.compile(r"^(\d+[A-Z]{0,2})\s+(.+?)\s+\1$")                        # 40  FLASHBACK   40
SCENE_NUM_GLUED = re.compile(r"^(.*?)(\d+[A-Z]{0,2})\s+\2$")                          # INT. ABATTOIR - LATER2 2
ABBREV_END = re.compile(r"\b(?:JR|SR|MR|MRS|MS|DR|ST)\.$")


def _heading(text):
    """The scene name if this line is a scene heading (scene numbers removed), else None."""
    m = SCENE_NUM_BOTH.match(text)
    if m and m.group(2) == m.group(2).upper():
        return " ".join(m.group(2).split())
    if text == text.upper():
        g = SCENE_NUM_GLUED.match(text)
        if g and g.group(1).strip():
            return " ".join(g.group(1).split())
    if SCENE_HEAD.match(text) or SEGMENT_HEAD.match(text):
        return " ".join(text.split())
    return None


def _is_cue_text(t):
    """Could this line be a speaker name? Short, capitals, no sentence punctuation at the end."""
    if not CUE_LINE.fullmatch(t) or len(t.split()) > 5:
        return False
    bare = EXTENSION.sub("", t).strip()
    if bare.endswith((".", ":", "-")) and not ABBREV_END.search(bare):
        return False                                    # "RIDE IN ON THEIR CARRIAGE."  "CUT TO:"
    return not (_heading(t) or TRANSITION.match(t))


def _join(parts):
    """Join wrapped dialogue lines. A line ending in a single hyphen joins the next one without a space."""
    out = ""
    for p in parts:
        if out.endswith("-") and not out.endswith("--") and p[:1].islower():
            out += p
        else:
            out += (" " if out else "") + p
    return out


def _code_for(key):
    if key in ALIASES:
        return ALIASES[key]
    return re.sub(r"[^A-Z0-9]", "", key)[:24] or "SPK"


# ---- reading the file into lines: (indent, text), blank lines kept ----
_LINES_CACHE = {}       # the latest script's lines, so changing a rule does not read the file again


def _pdf_lines(path):
    """Every line of a PDF with its indentation. pdfplumber reads words correctly; pypdf is the fallback."""
    pages = None
    try:
        import pdfplumber
        with pdfplumber.open(str(path)) as pdf:
            pages = [(pg.extract_text(layout=True) or "") for pg in pdf.pages]
    except ImportError:
        pass
    if pages is None:
        try:
            from pypdf import PdfReader
        except ImportError:
            raise RuntimeError("Reading PDFs needs a package. Run:  pip install pdfplumber")
        pages = []
        for pg in PdfReader(str(path)).pages:
            try:
                pages.append(pg.extract_text(extraction_mode="layout") or "")
            except TypeError:                                   # older pypdf: no layout mode
                pages.append(pg.extract_text() or "")
    out = []
    for text in pages:
        rows = [_fix_dashes(l.replace("\xa0", " ").rstrip()) for l in text.split("\n")]
        # a page number (or "CONTINUED:") near the top or bottom of the page is page furniture, not script
        filled = [k for k, r in enumerate(rows) if r.strip()]
        for k in filled[:2] + filled[-2:]:
            t = " ".join(rows[k].split())
            if PAGE_NUMBER.match(t) or PAGE_FURNITURE.match(t):
                rows[k] = ""
        while rows and not rows[0].strip():                     # blank lines at the top and bottom of a page are page
            rows.pop(0)                                         # margins; keeping them would cut a speech that runs
        while rows and not rows[-1].strip():                    # over a page break
            rows.pop()
        for l in rows:
            out.append((len(l) - len(l.lstrip(" ")), " ".join(l.split())))
    return out


def _docx_lines(path):
    """Every line of a Word file. Indent comes from the paragraph's left indent (about 144 twips per column)."""
    import zipfile
    import xml.etree.ElementTree as ET
    W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(str(path)) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    out = []
    for p in root.find(W + "body").iter(W + "p"):
        indent = 0
        ppr = p.find(W + "pPr")
        if ppr is not None:
            ind = ppr.find(W + "ind")
            if ind is not None:
                try:
                    indent = round(int(ind.get(W + "left") or ind.get(W + "start") or 0) / 144)
                except ValueError:
                    pass
            jc = ppr.find(W + "jc")
            if jc is not None and jc.get(W + "val") == "center":
                indent = max(indent, 36)
        buf = []
        for el in p.iter():
            if el.tag == W + "t":
                buf.append(el.text or "")
            elif el.tag == W + "br":
                buf.append("\n")
            elif el.tag == W + "tab":
                buf.append(" ")
        for line in _fix_dashes("".join(buf)).split("\n"):
            out.append((indent, " ".join(line.split())))
    return out


def _raw_lines(path):
    path = Path(path)
    st = path.stat()
    key = (str(path), st.st_mtime_ns, st.st_size)
    if key not in _LINES_CACHE:
        _LINES_CACHE.clear()
        _LINES_CACHE[key] = _docx_lines(path) if path.suffix.lower() in (".docx", ".docm") else _pdf_lines(path)
    return _LINES_CACHE[key]


def _parse_named(lines):
    """Read a script that has character names instead of IDs.

       Screenplay layout (when the file keeps indentation): action sits at the margin, dialogue is
       indented, and speaker names are indented furthest. That is enough to tell them apart, so
       page numbers, scene numbers, action lines and all-caps shouting inside action are ignored.

       Otherwise two plain-text layouts, mixed freely:
         Henry: dialogue (may continue on the next lines)
         HENRY / dialogue lines / blank line
       In plain text a name is accepted when it is a character in the rules, appears at least twice,
       or (with blank lines in the script) stands alone above a speech.

       lines: [(indent, text)] or plain strings. Parentheticals like (whispering) are dropped."""
    rows = []
    for item in lines:
        indent, text = item if isinstance(item, tuple) else (0, item)
        text = " ".join(str(text).split())
        if text and (PAGE_NUMBER.match(text) or PAGE_FURNITURE.match(text)):
            continue                                            # page numbers, (MORE), CONTINUED:
        rows.append((indent, text))
    ind = [r[0] for r in rows]
    txt = [r[1] for r in rows]
    n = len(rows)

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

    # --- does the file keep screenplay indentation? base = action margin, cue_min = where names start
    filled = [(i, t) for i, t in rows if t]
    long_counts = Counter(i for i, t in filled if len(t) > 30 and t != t.upper())
    cue_min = None
    if long_counts:
        floor = min(max(5, 0.03 * sum(long_counts.values())), max(long_counts.values()))
        base = min(i for i, c in long_counts.items() if c >= floor)
        cues_at = Counter(i for i, t in filled if i > base + 4 and _is_cue_text(t))
        if cues_at:
            level, c = cues_at.most_common(1)[0]
            if c >= 5:
                cue_min = base + 0.6 * (level - base)

    if cue_min is not None:
        is_cue = lambda k: bool(txt[k]) and ind[k] >= cue_min and _is_cue_text(txt[k])
        i = 0
        while i < n:
            k, i = i, i + 1
            if not txt[k]:
                continue
            head = _heading(txt[k])
            if head:
                cur = _segment(segments, head)
            elif is_cue(k):
                key, buf = _key(txt[k]), []
                while i < n:                                    # blank lines (page margins) do not end a speech;
                    if not txt[i]:                              # a line back at the action margin does
                        i += 1
                        continue
                    if ind[i] <= base + 2 or is_cue(i) or _heading(txt[i]):
                        break
                    if not PAREN_LINE.match(txt[i]):
                        buf.append(txt[i])
                    i += 1
                emit(key, _join(buf))
        return entries, [sg for sg in segments if sg["ids"]]

    # --- plain text: no usable indentation
    has_blanks = any(not t for t in txt)

    def label(k):
        m = LABEL_LINE.match(txt[k])
        return (_key(m.group(1)), m.group(2)) if m and not _heading(txt[k]) else None

    seen = {}
    for k in range(n):
        lab = label(k)
        key = lab[0] if lab else (_key(txt[k]) if _is_cue_text(txt[k]) and k + 1 < n and txt[k + 1] else None)
        if key:
            seen[key] = seen.get(key, 0) + 1

    ok_label = lambda key: key in ALIASES or seen.get(key, 0) >= 2
    ok_cue = lambda key: key in ALIASES or seen.get(key, 0) >= 2 or has_blanks
    starts_new = lambda k: bool(_heading(txt[k]) or (label(k) and ok_label(label(k)[0]))
                                or (_is_cue_text(txt[k]) and ok_cue(_key(txt[k]))))

    i = 0
    while i < n:
        k, i = i, i + 1
        if not txt[k]:
            continue
        head = _heading(txt[k])
        if head:
            cur = _segment(segments, head)
            continue
        lab = label(k)
        if lab and ok_label(lab[0]):
            key, buf = lab[0], [lab[1]]
            while i < n and txt[i] and not starts_new(i):
                buf.append(txt[i])
                i += 1
            emit(key, _join(buf))
        elif _is_cue_text(txt[k]) and ok_cue(_key(txt[k])) and i < n and txt[i]:
            key, buf = _key(txt[k]), []
            while i < n and txt[i] and not starts_new(i):
                if not PAREN_LINE.match(txt[i]):
                    buf.append(txt[i])
                i += 1
            emit(key, _join(buf))
    return entries, [sg for sg in segments if sg["ids"]]


# ----------------------------- public API -----------------------------
def _pdf_has_ids(path, pages=12):
    """Quick look at the first pages: does anything match an ID format from Customize?
    Saves reading a long screenplay twice when it has no IDs at all."""
    if not any(r["regexes"] for r in RULES):
        return False
    try:
        from pypdf import PdfReader
    except ImportError:
        return False
    reader = PdfReader(str(path))
    text = _fix_dashes("\n".join((pg.extract_text() or "") for pg in reader.pages[:pages]))
    return bool(ID_IN_PDF.search(text))


def load_script_full(path):
    """Read the recording script (PDF or Word). Returns (entries, segments).
    IDs from Customize are used when the script has them; otherwise it is read by character name."""
    path = Path(path)
    if path.suffix.lower() in (".docx", ".docm"):
        entries, segments = _load_script_docx(path)
    elif _pdf_has_ids(path):
        entries, segments = _load_script_pdf(path)
    else:
        entries, segments = {}, []
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