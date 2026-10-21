#!/usr/bin/env python3
"""
trim_rename.py  (v3: boundary-based cutting)

For every audio file in ./input:
  1. Transcribes it (faster-whisper, free, runs offline).
  2. Finds EVERY spoken ID in the recording (a file can hold one line or many lines in a row),
     e.g. "W 0 1 H E N S E Q 0 0 8 ... W 0 1 H E N S E Q 0 0 9 ..."   (old format, spelled out)
     or   "Yuni Hen Seq Zero Zero Four ... Yuni Hen Seq Zero Zero Five ..."   (new format, words)
  3. Cross-checks the dialogue after each ID against your recording-script PDF.
  4. Saves a NEW trimmed file for each line, named exactly like the script ID
     (e.g. W01-HEN-SEQ-008.wav, UNI-HEN-SEQ-004.wav).

HOW THE CUTS WORK (new in v3)
  The recording is  ID, dialogue, ID, dialogue, ID, dialogue ...
  So a line's dialogue is EVERYTHING between the end of its ID and the start of the next ID.
  The script no longer guesses where the dialogue ends by comparing text; it uses the neighbouring
  IDs as walls. Inside those walls it looks at the real audio level (not the speech-to-text
  timestamps) to:
    START  = the pause between the spoken ID and the dialogue      -> cut inside that pause
    END    = the last pause before the next ID (or the end of file) -> cut just after the last word
  Silence is then trimmed to LEAD_IN_SEC at the start and TAIL_SEC at the end.

Your original files are only ever READ. Nothing in ./input is edited, moved, renamed or deleted.

Anything uncertain goes to ./needs_review (as a copy) and is explained in log.csv.
The script can be stopped at any time and re-run: finished files are skipped.

SCRIPT ID FORMATS UNDERSTOOD
  UNI-HEN-SEQ-004      (4 parts: prefix-code-kind-number)
  W01-HEN-SEQ-008      (4 parts)
  W02-HEN-001          (3 parts: prefix-code-number, e.g. the Week 2 master script)
"""

import csv
import json
import os
import re
import shutil
import subprocess
import sys
import traceback
from collections import deque
from pathlib import Path

# =============================== SETTINGS ===============================
SCRIPT_PDF = Path("script.pdf")      # your recording script (put it next to this file)
INPUT_DIR = Path("input")            # originals (read-only use)
OUTPUT_DIR = Path("output")          # trimmed + renamed files are created here
REVIEW_DIR = Path("needs_review")    # copies of files that need a human look
CACHE_DIR = Path("cache")            # saved transcripts, so re-runs are fast
LOG_FILE = Path("log.csv")
MISSING_FILE = Path("missing_ids.txt")

EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}
MODEL_SIZE = "small.en"              # "medium.en" is more accurate but slower
DEVICE = "auto"                      # "auto" = use the NVIDIA GPU if it works, otherwise CPU
                                     # ("cpu" forces CPU, "cuda" forces GPU)
USE_VAD = False        # True = let Whisper skip long silences (helps if long files make it invent
                       # words like "Thank you." in the pauses). Delete ./cache after changing it.

DRY_RUN = False        # True = analyse and log only, create no audio files
REDO_ALL = False       # True = ignore previous results and process everything again

MIN_TEXT_MATCH = 60    # % the dialogue must match the script when an ID was heard
STRONG_TEXT_MATCH = 85 # % needed to trust dialogue alone (no ID heard, or ID disagrees)
CONFLICT_MARGIN = 15   # dialogue must beat the heard-ID's text by this much to call a conflict
EXACT_TEXT_MATCH = 95  # if the dialogue matches ONE script line this well, it beats a disagreeing spoken ID
USE_FILE_NUMBER_HINT = True  # use the number at the end of the file name (dialogue_week1_87.wav -> 87th line
                             # of the script) as an extra clue when a line appears under several IDs
HINT_TOLERANCE = 4     # how far the file number may drift from the script position
HINT_MIN_TEXT_MATCH = 70   # dialogue match needed when the file-number clue agrees

# ---- several lines in one recording ----
ANCHOR_MIN_SCORE = 60  # dialogue similarity is enough to establish an anchor
# A strong spoken ID is allowed to establish an anchor even when Whisper only
# transcribed a short/fragmented piece of the following dialogue. This prevents
# an earlier ID (e.g. CUE-011) from being swallowed by the next ID.
SPOKEN_ID_ANCHOR_MIN = 78
SPOKEN_ID_EXACT_NUMBER_MIN = 55
MIN_SEGMENT_WORDS = 3  # fewer leftover words than this are treated as noise, not a line
SPLIT_MIN_GAP = 0.30   # seconds of pause needed to split off a line whose ID was NOT recognised
MIN_CLIP_SEC = 0.30    # a clip shorter than this is sent to needs_review
UNKNOWN_START_REVIEW = True  # never export a line whose start boundary is genuinely unknown
RECOVERED_BOUNDARY_MIN_SCORE = 82

# ---- boundary mode (NEW) ----
BOUNDARY_MODE = True   # True = dialogue is everything between one spoken ID and the next (never shortened
                       # by text matching). False = old behaviour (text matching decides the end).
LONG_REGION_FACTOR = 1.8   # safety net: if the words between two IDs are MORE than
LONG_REGION_EXTRA = 4      #   expected_words * 1.8 + 4, an ID was probably missed in the middle,
                           #   so the old text-based split is used for that stretch only.

# ---- silence trimming (NEW) ----
USE_SILENCE_CUT = True # use the real audio level to place cuts (much more precise than the
                       # speech-to-text timestamps, which are often a little early or late)
LEAD_IN_SEC = 0.10     # silence kept BEFORE the dialogue so it doesn't start abruptly
TAIL_SEC = 0.25        # silence kept AFTER the dialogue (the tail is never longer than 60% of the pause)
TRIM_TRAILING = True   # True = also trim the silence after the LAST line of a file
                       # (False = the last line keeps everything to the end of the file)
START_PAUSE_SEC = 0.10 # shortest pause accepted between a spoken ID and its dialogue
END_PAUSE_SEC = 0.15   # shortest pause accepted as "the dialogue has finished"
                       # (bigger = safer against cutting at a comma pause; smaller = catches fast speakers)
MIN_VOICED_SEC = 0.04  # sounds shorter than this (clicks, pops) are treated as silence
ID_EXCLUSION_SEC = 0.08
AUDIO_START_SAFETY_SEC = 0.035
ID_DIALOGUE_GAP_MIN_SEC = 0.055
ID_DIALOGUE_GAP_MAX_SEC = 1.25
ID_TAIL_GUARD_SEC = 0.16
DIALOGUE_LEAD_SEC = 0.045
START_PRESERVE_SEC = 0.18
START_MIN_LEAD_SEC = 0.08
ID_CONFIRM_WINDOW_SEC = 0.40
DIALOGUE_END_GUARD_SEC = 0.08
AUDIO_END_SAFETY_SEC = 0.050
BOUNDARY_MIN_DIALOGUE_SEC = 0.12
BOUNDARY_MAX_START_LOOKAHEAD_SEC = 1.50
  # HARD RULE: exported dialogue may never start before this long after the last ID word ends.
BOUNDARY_MAX_PAUSE_SEC = 2.50  # prefer a pause close to the next spoken ID; prevents choosing an old internal pause.
CUT_NUDGE_SEC = 0.0    # manual override: cut this many seconds LATER for every START cut (e.g. 0.10).
                       # Use it if you still hear a sliver of the ID; use a negative number if
                       # the first letter of the dialogue is being clipped.
END_NUDGE_SEC = 0.0    # manual override for END cuts: positive = keep more after the last word,
                       # negative = cut earlier. Use it if the ends still sound clipped (e.g. 0.10).

# ---- NO-ID MODE: recordings WITHOUT spoken IDs ----
# The lines are found purely from the script text: (1) work out which script segment(s)
# the recording belongs to, (2) cut the speech into phrases at pauses, (3) align the phrases
# to the script lines of those segments in script order.
NOID_WHISPER_PROMPT = ("Henry the tennis coach talking to the Bug Squad and the Teacher. "
                       "Watch closely. Ready position. Racket up. Nice work!")
NOID_LOCATE_WINDOW = 60     # words per window used to find the script segment
NOID_LOCATE_STEP = 30
NOID_LOCATE_MIN = 0.35      # evidence (0..1) a window needs to vote for a script segment
NOID_ATOM_GAP_SEC = 0.10    # a pause at least this long may separate two script lines
NOID_MIN_QUIET_SEC = 0.08   # shortest silence in the audio counted as a pause
NOID_MIN_SCORE = 60         # % a phrase must match a script line to be considered
NOID_GAIN_BASE = 58         # score above this is a gain for the alignment
NOID_TOPK = 4               # candidate script texts kept per phrase
NOID_BEAM = 12              # alignment states kept per position
NOID_NOISE_COST = -3.0      # cost of speech that matches no line (noise, ad-lib, stray word)
NOID_WORD_DIV = 4.0         # a match is worth (score - base) * words / this  (long exact matches beat fragments)
NOID_LINE_COST = 6.0        # every extra line has a small cost, so one whole-line match beats two fragments
NOID_BRIDGE_FREE_SEC = 0.30 # pauses up to this long inside one line (commas, sentence breaks) are free
NOID_BRIDGE_COST = 40.0     # joining two phrases across a longer pause costs this per second beyond that
NOID_BREAK_COST = 10.0      # cost of splitting at a very short pause
NOID_GOOD_GAP_SEC = 0.35    # a pause this long is a clean split (no cost)
NOID_SKIP_OK = 3            # lines skipped in script order that still count as "in order"
NOID_SKIP_MAX = 12          # lines skipped that the alignment tolerates at all
NOID_ACCEPT = 88            # % needed to leave a line as PENDING instead of REVIEW
NOID_MARGIN = 6             # the best line must beat the runner-up text by this much
NOID_ATTACH_GAP_SEC = 0.22  # a stray word this close to a line is part of that line (mis-heard edge word)
NOID_MIN_STRAY_SEC = 0.15   # isolated speech at least this long (with real sound) is shown for review

# ---- spoken ID recognition ----
# ---- spoken ID recognition ------------------------------------------------
# The master PDF currently contains several ID kinds, not just SEQ/CUE.
# Keep aliases broad because Whisper commonly turns IDs into phonetic text.
PREFIX_ALIASES = {
    "UNI": ["uni", "yuni", "yooni", "youni", "yunie", "unie", "juni", "yoni",
            "you nee", "you ni"],
    "W01": ["w01", "w 01", "w one", "w zero one", "double u one"],
    "W02": ["w02", "w 02", "w two", "w zero two", "double u two"],
}
CODE_ALIASES = {"HEN": ["hen", "henn", "han", "henry"]}
KIND_ALIASES = {
    "SEQ": ["seq", "sequence", "seek", "sik", "sick", "sic", "sec", "seck",
            "sek", "see", "c", "s"],
    "CUE": ["cue", "q", "queue", "que", "kew", "kyu", "see you"],
    "REACT": ["react", "reeact", "re act", "reaction", "reacts"],
    "UTILITY": ["utility", "util", "utilities"],
    "TERM": ["term", "terms"],
    "HUMOR": ["humor", "humour", "hum"],
    "FEED": ["feed", "fed"],
    "ACTION": ["action", "act"],
    "MOVE": ["move", "moves"],
    "GAMECALL": ["gamecall", "game call", "game", "call"],
    "ALT": ["alt", "all", "alternate"],
    "EMOTION": ["emotion", "emotional"],
    "TEACHER": ["teacher"],
    "SIGNOFF": ["signoff", "sign off", "signof"],
    "SAFE": ["safe", "safety"],
    # 3-part IDs such as W02-HEN-001 have no spoken "kind" word.
    "LINE": [],
}
HEAD_MIN_MATCH = 55
ID_PHRASE_MIN_MATCH = 52
ID_STRONG_MATCH = 72
MAX_ID_WORDS = 18
MAX_ID_SCAN_WORDS = 24
MAX_ID_CANDIDATES = 12
NUMBER_MAX_DIGITS = 4
WHISPER_PROMPT = (
    "UNI HEN SEQ 001. UNI HEN CUE 001. UNI HEN REACT 001. "
    "UNI HEN UTILITY 001. UNI HEN TERM 001. UNI HEN ACTION 001. "
    "Yuni Hen Seq Zero Zero Four. Yuni Hen Q Zero One Nine."
)
# ========================================================================

OK_STATUSES = {"OK", "OK_TEXT_ONLY"}
LOG_COLUMNS = ["original_file", "segment", "status", "new_file", "heard_id", "heard_id_raw",
               "best_match_id", "match_score", "cut_at_sec", "end_at_sec", "cut_method",
               "heard_transcript", "note"]


# ----------------------------- app logging & settings -----------------------------
def _log(msg):
    """One human-readable line for the app's activity log (stderr is streamed to the UI)."""
    print(msg, file=sys.stderr, flush=True)


def _progress(**kw):
    """Machine-readable progress for the app's progress bar (never shown as text)."""
    print("@@PROGRESS " + json.dumps(kw), file=sys.stderr, flush=True)


ALLOWED_MODELS = ("tiny.en", "base.en", "small.en", "medium.en")


def apply_settings(cfg):
    """Apply the user's settings from the app. Every value is validated and clamped,
    so a bad or missing value can never break the engine."""
    global MODEL_SIZE, DEVICE, START_PRESERVE_SEC, TAIL_SEC, NOID_ACCEPT, NOID_ATOM_GAP_SEC
    if not isinstance(cfg, dict):
        return

    def num(key, lo, hi, current):
        try:
            v = float(cfg[key])
        except (KeyError, TypeError, ValueError):
            return current
        return min(max(v, lo), hi)

    if cfg.get("modelSize") in ALLOWED_MODELS:
        MODEL_SIZE = cfg["modelSize"]
    if cfg.get("device") in ("auto", "cpu", "cuda"):
        DEVICE = cfg["device"]
    START_PRESERVE_SEC = num("startLeadSec", 0.10, 0.50, START_PRESERVE_SEC)
    TAIL_SEC = num("tailSec", 0.05, 1.00, TAIL_SEC)
    NOID_ACCEPT = num("noidAccept", 60, 100, NOID_ACCEPT)
    NOID_ATOM_GAP_SEC = num("noidMinPause", 0.05, 0.50, NOID_ATOM_GAP_SEC)


# ----------------------------- text helpers -----------------------------
PAUSE_TAG = re.compile(r"<#[^#>]*#>")          # 0.5-second pause tags such as <#0.5#> in the script
NUM_WORDS = ("zero one two three four five six seven eight nine ten eleven twelve thirteen "
             "fourteen fifteen sixteen seventeen eighteen nineteen twenty").split()


def norm(text):
    """Lower-case, strip punctuation, make small numbers words, so texts compare fairly."""
    text = PAUSE_TAG.sub(" ", str(text))
    text = text.lower().replace("\u2019", "'").replace("\u2018", "'").replace("'", "")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    out = []
    for tok in text.split():
        if tok.isdigit() and int(tok) <= 20:
            tok = NUM_WORDS[int(tok)]
        out.append(tok)
    return " ".join(out)


SPOKEN_DIGITS = {
    "zero": "0", "oh": "0", "o": "0",
    "one": "1", "won": "1",
    "two": "2", "to": "2", "too": "2",
    "three": "3", "tree": "3",
    "four": "4", "for": "4",
    "five": "5", "fife": "5",
    "six": "6", "sicks": "6",
    "seven": "7", "heaven": "7",
    "eight": "8", "ate": "8",
    "nine": "9",
    "ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13",
    "fourteen": "14", "fifteen": "15", "sixteen": "16", "seventeen": "17",
    "eighteen": "18", "nineteen": "19", "twenty": "20",
    "doubleu": "w", "dubya": "w", "double": "w",
}

def clean_token(word):
    return re.sub(r"[^a-z0-9]", "", str(word).lower())

def spoken_token(word):
    w = clean_token(word)
    return SPOKEN_DIGITS.get(w, w)

def digit_fragments(tokens):
    """Extract digit characters from noisy Whisper number tokens."""
    out = []
    for raw in tokens:
        w = clean_token(raw)
        if not w:
            continue
        if w in SPOKEN_DIGITS:
            v = SPOKEN_DIGITS[w]
            if v.isdigit() and len(v) == 1:
                out.append(v)
            elif v.isdigit() and int(v) <= 20:
                out.extend(str(int(v)))
            continue
        if w.isdigit():
            out.extend(list(w[-NUMBER_MAX_DIGITS:]))
            continue
        m = re.search(r"(\d{1,%d})$" % NUMBER_MAX_DIGITS, w)
        if m:
            out.extend(list(m.group(1)))
    return "".join(out[:NUMBER_MAX_DIGITS])

def spoken_number_value(tokens):
    digits = digit_fragments(tokens)
    if not digits:
        return None
    return int(digits)

def compact_phrase(tokens):
    return "".join(clean_token(w) for w in tokens)

def fuzzy(a, b):
    from rapidfuzz import fuzz
    return fuzz.ratio(a, b)

def partial_fuzzy(a, b):
    from rapidfuzz import fuzz
    return max(fuzz.ratio(a, b), fuzz.partial_ratio(a, b))

def id_number_forms(number):
    n = int(number)
    s = f"{n:03d}"
    digits = list(s)
    word_digits = [NUM_WORDS[int(d)] for d in digits]
    return {s, str(n), " ".join(digits), " ".join(word_digits),
            "".join(word_digits), "".join(digits)}


# ----------------------------- script (PDF) -----------------------------
# Two ID shapes are understood:
#   4 parts:  W01-HEN-SEQ-008 (week style)  /  UNI-HEN-SEQ-004 (universal style)
#   3 parts:  W02-HEN-001     (Week 2 master script; prefix must look like W02)
# The 3-part form is deliberately restricted to a letter+digits prefix so that ordinary
# text such as "HEN-CUE-001" can never be mistaken for an ID.
ID_IN_PDF = re.compile(
    r"\b(?:"
    r"[A-Z][A-Z0-9]{1,7}-[A-Z][A-Z0-9]{1,7}-[A-Z][A-Z0-9]{1,12}-\d{1,4}"
    r"|[A-Z]\d{1,3}-[A-Z][A-Z0-9]{1,7}-\d{1,4}"
    r")\b"
)


# Section headings: "Segment 02 ..." (older scripts) or "STATE W2-01" (Week 2 master script).
SEGMENT_HEAD = re.compile(r"(?:Segment\s+\d+|STATE\s+W\d+-\d+)[^\n]*")
ID_FULL = re.compile(ID_IN_PDF.pattern.replace(r"\b", ""))


def _clean_dialogue(text):
    return " ".join(PAUSE_TAG.sub(" ", str(text)).split())


def _default_segments(order, size=20):
    """Used when the script has no 'Segment NN' headings: blocks of `size` lines."""
    n = len(order)
    return [{"label": f"Lines {i + 1}\u2013{min(i + size, n)}", "ids": order[i:i + size]}
            for i in range(0, n, size)]


def _fix_dashes(text):
    for dash in "\u2010\u2011\u2012\u2013":           # odd hyphen characters -> "-"
        text = text.replace(dash, "-")
    return text


def _load_script_docx(path):
    """Word script. Two layouts are supported:
       1. a table per segment, column 1 = ID, column 2 = dialogue
       2. plain paragraphs: an ID paragraph followed by a paragraph holding the quoted dialogue"""
    import zipfile
    import xml.etree.ElementTree as ET
    W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(str(path)) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    body = root.find(W + "body")

    def ptext(p):
        return "".join(t.text or "" for t in p.iter(W + "t"))

    entries, segments, cur = {}, [], None
    for el in body:
        if el.tag == W + "p":
            text = ptext(el)
            if SEGMENT_HEAD.match(text.strip()):
                cur = {"label": " ".join(text.split()), "ids": []}
                segments.append(cur)
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
                    cur = {"label": "Script", "ids": []}
                    segments.append(cur)
                cur["ids"].append(sid)

    if not entries:
        # Layout 2: no tables. "ID" paragraph, then (optional [stage directions]), then "quoted dialogue".
        segments, cur, pending = [], None, None
        for p in body.iter(W + "p"):
            text = _fix_dashes(ptext(p)).strip()
            if not text:
                continue
            if SEGMENT_HEAD.match(text):
                cur = {"label": " ".join(text.split()), "ids": []}
                segments.append(cur)
                pending = None
            elif ID_FULL.fullmatch(text):
                pending = text if text not in entries else None
            elif pending and text.startswith("["):
                continue                                   # stage direction between ID and quote
            elif pending:
                m = re.match(r"[\u201c\"](.*?)[\u201d\"]", text, re.S)
                if m:
                    entries[pending] = _clean_dialogue(m.group(1))
                    if cur is None:
                        cur = {"label": "Script", "ids": []}
                        segments.append(cur)
                    cur["ids"].append(pending)
                pending = None
        segments = [sg for sg in segments if sg["ids"]]
    return entries, segments


def _load_script_pdf(path):
    try:
        from pypdf import PdfReader
    except ImportError:
        sys.exit("Missing package. Run:  pip install pypdf rapidfuzz faster-whisper")
    reader = PdfReader(str(path))
    text = _fix_dashes("\n".join((page.extract_text() or "") for page in reader.pages))
    parts = ID_IN_PDF.split(text)
    ids = ID_IN_PDF.findall(text)
    entries = {}
    for i, sid in enumerate(ids):
        body = parts[i + 1]
        m = re.search(r"[\u201c\"](.*?)[\u201d\"]", body, re.S)
        entries[sid] = _clean_dialogue(m.group(1)) if m else ""

    # segments = the "Segment NN" / "STATE W2-NN" headings that sit between the IDs (if the PDF has them)
    events = sorted([(m.start(), "h", " ".join(m.group(0).split())) for m in SEGMENT_HEAD.finditer(text)] +
                    [(m.start(), "i", m.group(0)) for m in ID_IN_PDF.finditer(text)])
    segments, cur, seen = [], None, set()
    for _, kind, val in events:
        if kind == "h":
            cur = {"label": val, "ids": []}
            segments.append(cur)
        elif val not in seen and val in entries:
            seen.add(val)
            if cur is None:
                cur = {"label": "Script", "ids": []}
                segments.append(cur)
            cur["ids"].append(val)
    segments = [sg for sg in segments if sg["ids"]]
    if len(segments) < 2:
        segments = _default_segments(list(entries))
    return entries, segments


def load_script_full(path):
    """Read the recording script (PDF or Word). Returns (entries, segments):
       entries  = {id: dialogue_text} in script order
       segments = [{"label": "Segment 02 · entries 21–40", "ids": [...]}, ...]"""
    path = Path(path)
    if path.suffix.lower() in (".docx", ".docm"):
        return _load_script_docx(path)
    return _load_script_pdf(path)


def load_script(pdf_path):
    """Returns {id: dialogue_text} read from the recording script (PDF or Word)."""
    return load_script_full(pdf_path)[0]


# ----------------------------- matching logic -----------------------------
def file_hint(name):
    """Number at the end of the file name (before the extension), or None."""
    m = re.search(r"(\d+)\.[A-Za-z0-9]+$", name)
    return int(m.group(1)) if m else None


def similarity(a, b):
    from rapidfuzz import fuzz
    return fuzz.ratio(a, b)


class ScriptIndex:
    def __init__(self, entries, segments=None):
        self.entries = entries
        self.order = list(entries)                    # script order (0-based position = index here)
        self.pos = {sid: i + 1 for i, sid in enumerate(entries)}
        segs = [{"label": sg["label"], "ids": [i for i in sg["ids"] if i in entries]}
                for sg in (segments or [])]
        segs = [sg for sg in segs if sg["ids"]]
        self.segments = segs if segs else _default_segments(self.order)
        self.seg_of = {sid: si for si, sg in enumerate(self.segments) for sid in sg["ids"]}
        self._seg_profile = None
        self.norm_text = {sid: norm(t) for sid, t in entries.items()}

        self.text_to_ids = {}
        for sid, nt in self.norm_text.items():
            if nt:
                self.text_to_ids.setdefault(nt, []).append(sid)
        self.unique_texts = list(self.text_to_ids)

        # Fast indexes for ID recognition.
        self.by_tail = {}
        self.by_kind = {}
        self.id_parts = {}
        for sid in entries:
            parts = sid.split("-")
            if len(parts) >= 4:                       # UNI-HEN-SEQ-004
                prefix, code, kind, number = parts[0], parts[1], parts[2], int(parts[3])
            else:                                     # W02-HEN-001 (no kind word)
                prefix, code, kind, number = parts[0], parts[1], "LINE", int(parts[2])
            self.by_tail.setdefault((kind, number), []).append(sid)
            self.by_kind.setdefault(kind, []).append(sid)
            self.id_parts[sid] = (prefix, code, kind, number)

    def top_matches(self, words, limit=2):
        from rapidfuzz import fuzz, process
        query = norm(" ".join(w["w"] for w in words))
        if not query or not self.unique_texts:
            return []
        hits = process.extract(query, self.unique_texts, scorer=fuzz.ratio, limit=limit)
        return [(h[1], self.text_to_ids[h[0]]) for h in hits]

    def best_text_match(self, words):
        top = self.top_matches(words, 1)
        return top[0] if top else (0, [])

    @staticmethod
    def _aliases(canonical, table):
        return [canonical.lower()] + [x.lower() for x in table.get(canonical, [])]

    def head_score(self, heard_head, sid):
        prefix, code, _, _ = self.id_parts[sid]
        expected = [compact_phrase([x]) for x in self._aliases(prefix, PREFIX_ALIASES)]
        expected += [compact_phrase([x]) for x in self._aliases(code, CODE_ALIASES)]
        full = [compact_phrase([p, c]) for p in self._aliases(prefix, PREFIX_ALIASES)
                for c in self._aliases(code, CODE_ALIASES)]
        h = compact_phrase(heard_head)
        if not h:
            return 0
        return max(fuzzy(h, x) for x in full)

    def kind_score(self, heard_kind, canonical):
        h = clean_token(heard_kind)
        aliases = self._aliases(canonical, KIND_ALIASES)
        return max(fuzzy(h, clean_token(a)) for a in aliases)

    def spoken_id_phrase(self, sid):
        prefix, code, kind, number = self.id_parts[sid]
        p = PREFIX_ALIASES.get(prefix, [prefix])
        c = CODE_ALIASES.get(code, [code])
        k = KIND_ALIASES.get(kind, [kind])
        nums = id_number_forms(number)
        return p, c, k, nums

    def resolve_spoken(self, head_tokens, kind, number=None, raw_kind=""):
        """
        Resolve a noisy spoken ID. `number` is treated as a hint, not truth.
        This is the important change: Whisper saying 000 no longer makes the
        recognizer discard the real ID 019.
        """
        pool = self.by_kind.get(kind, [])
        if not pool:
            return None

        scored = []
        for sid in pool:
            _, _, _, n = self.id_parts[sid]
            hs = self.head_score(head_tokens, sid)
            ks = self.kind_score(raw_kind or kind, kind)
            if number is None:
                ns = 0
            elif n == number:
                ns = 100
            else:
                # Close numeric errors such as 19 -> 09 or 018 -> 019 get some credit.
                heard = f"{number:03d}"
                wanted = f"{n:03d}"
                ns = fuzzy(heard, wanted)

            total = hs * 0.58 + ks * 0.22 + ns * 0.20
            scored.append((total, hs, ks, ns, sid))

        scored.sort(reverse=True)
        if not scored:
            return None
        total, hs, ks, ns, sid = scored[0]
        if hs < HEAD_MIN_MATCH and ks < ID_STRONG_MATCH:
            return None
        return sid

    def candidate_ids(self, kind, head_tokens, number=None):
        """Return likely IDs for a spoken kind/head/number."""
        pool = self.by_kind.get(kind, [])
        scored = []
        for sid in pool:
            _, _, _, n = self.id_parts[sid]
            hs = self.head_score(head_tokens, sid)
            ks = self.kind_score(kind, kind)
            if number is None:
                ns = 0
            elif n == number:
                ns = 100
            else:
                ns = fuzzy(f"{number:03d}", f"{n:03d}")
            total = hs * 0.58 + ks * 0.22 + ns * 0.20
            scored.append((total, hs, ns, sid))
        scored.sort(reverse=True)
        if number == 0:
            # Whisper very often emits "000" / "-0 -0 -0" for a real ID.
            # The number is therefore unusable; let the dialogue determine the
            # exact line instead of throwing away CUE/SEQ 019, 020, etc.
            return [sid for _, hs, ns, sid in scored if hs >= HEAD_MIN_MATCH]
        return [sid for _, hs, ns, sid in scored[:MAX_ID_CANDIDATES]
                if hs >= HEAD_MIN_MATCH or (number is not None and ns >= 60)]


    def pick_by_hint(self, ids, hint):
        """Several IDs share one dialogue line: choose the one closest to the file-number clue."""
        if len(ids) == 1:
            return ids[0]
        if not (USE_FILE_NUMBER_HINT and hint):
            return None
        ranked = sorted(ids, key=lambda i: abs(self.pos[i] - hint))
        d0 = abs(self.pos[ranked[0]] - hint)
        d1 = abs(self.pos[ranked[1]] - hint)
        return ranked[0] if d0 <= HINT_TOLERANCE and d1 - d0 >= 2 else None

    def hint_agrees(self, sid, hint):
        return bool(USE_FILE_NUMBER_HINT and hint and abs(self.pos[sid] - hint) <= HINT_TOLERANCE)


def _kind_at(words, pos, index):
    """Return (canonical_kind, words_used, score) for a noisy kind token."""
    from rapidfuzz import fuzz
    best = None
    for kind in index.by_kind:
        for alias in KIND_ALIASES.get(kind, [kind]):
            alias_tokens = alias.split()
            if pos + len(alias_tokens) > len(words):
                continue
            heard_tokens = [clean_token(w["w"]) for w in words[pos:pos + len(alias_tokens)]]
            target_tokens = [clean_token(x) for x in alias_tokens]
            if len(alias_tokens) > 1:
                if any(fuzz.ratio(h, t) < 55 for h, t in zip(heard_tokens, target_tokens)):
                    continue
            heard = "".join(heard_tokens)
            target = "".join(target_tokens)
            # Use ratio, not partial_ratio: partial matching makes ordinary
            # dialogue words such as "Yuni" or "the" look like CUE/TERM.
            sc = fuzz.ratio(heard, target)
            if best is None or sc > best[2]:
                best = (kind, len(alias_tokens), sc)
    return best


def _numberish_token(raw):
    """True only for tokens that can reasonably belong to a spoken ID number."""
    t = clean_token(raw)
    if not t:
        return False
    if re.fullmatch(r"-?\d{1,%d}" % NUMBER_MAX_DIGITS, t):
        return True
    if t in {"o", "oh"}:
        return True
    return t in {clean_token(x) for x in NUM_WORDS}


def spoken_id_candidates(words, index):
    """
    Find noisy spoken IDs anywhere near the beginning of `words`.

    Unlike the old regex, this does NOT require:
      * the ID to start at word 1
      * the kind to be SEQ/CUE
      * Whisper to transcribe the number correctly
      * Whisper to keep hyphens/spaces intact

    Returns (script_id_or_None, words_used_through_ID, heard_label, id_start_offset).
    """
    found = []
    limit = min(len(words), MAX_ID_SCAN_WORDS)

    # First pass: IDs sometimes arrive as one token, e.g. "unihenq013".
    # Split the compact token using every known kind alias.
    for pos in range(limit):
        raw = clean_token(words[pos]["w"])
        if not raw:
            continue
        for kind in index.by_kind:
            kind_aliases = sorted(KIND_ALIASES.get(kind, [kind]), key=lambda x: len(clean_token(x)), reverse=True)
            for alias in kind_aliases:
                ka = clean_token(alias)
                if len(ka) < 2 and ka not in {"q", "s", "c"}:
                    continue
                if ka not in raw:
                    continue
                before, after = raw.split(ka, 1)
                m = re.search(r"(\d{1,%d})$" % NUMBER_MAX_DIGITS, after)
                if not m:
                    continue
                if len(ka) == 1 and before:
                    # Do not mistake the "q" in "seq012" for a CUE.
                    best_hs = max(
                        (index.head_score([before], sid) for sid in index.by_kind.get(kind, [])),
                        default=0
                    )
                    if best_hs < 95:
                        continue
                number = int(m.group(1))
                head_compact = before

                # Also handle Whisper's common form:
                #   "Unihen Q018" / "Uni Hen SEQ012"
                # where the kind+number are one token and the spoken head
                # is in the preceding transcript words.
                if not head_compact:
                    best_head = []
                    best_hs = 0.0
                    for n in range(1, min(4, pos) + 1):
                        ht = [w["w"] for w in words[pos-n:pos]]
                        for sid0 in index.by_kind.get(kind, []):
                            hs = index.head_score(ht, sid0)
                            if hs > best_hs:
                                best_hs = hs
                                best_head = ht
                    if best_hs < HEAD_MIN_MATCH:
                        continue
                    candidates = index.candidate_ids(kind, best_head, number)
                    k = pos + 1
                    label = f"{' '.join(best_head)} {kind} {m.group(1)}"
                    for sid in candidates:
                        found.append((sid, k, label, pos-len(best_head)))
                    continue

                candidates = index.candidate_ids(kind, [head_compact], number)
                if not candidates:
                    continue
                k = pos + 1
                label = f"{head_compact} {kind} {m.group(1)}"
                for sid in candidates:
                    found.append((sid, k, label, pos))

    for pos in range(limit):
        kind_hit = _kind_at(words, pos, index)
        if not kind_hit:
            continue
        kind, kind_words, kind_score = kind_hit
        if kind_score < 65:
            continue

        # Number normally follows the kind. Allow up to 5 Whisper tokens because
        # "Q -0 -1 -9" is a common transcription shape.
        num_start = pos + kind_words
        number_tokens = []
        for w in words[num_start: num_start + NUMBER_MAX_DIGITS + 2]:
            raw = w["w"]
            if _numberish_token(raw):
                number_tokens.append(raw)
            elif number_tokens:
                break
            else:
                # A non-number immediately after the kind means this is not an ID.
                break
        number = spoken_number_value(number_tokens)
        if number is None:
            continue

        # The spoken head is immediately before the kind. Ignore dialogue before
        # it; test the last 1..4 tokens separately.
        best_head = []
        best_head_score = 0
        for n in range(1, min(4, pos) + 1):
            ht = [w["w"] for w in words[pos-n:pos]]
            for sid in index.by_kind.get(kind, []):
                hs = index.head_score(ht, sid)
                if hs > best_head_score:
                    best_head_score = hs
                    best_head = ht

        candidates = index.candidate_ids(kind, best_head, number)
        if not candidates:
            continue

        # Determine how many transcript words belong to the ID.
        # If number tokens were recognized, stop after the last useful number token.
        used_num = len(number_tokens)
        if used_num == 0:
            continue
        k = pos + kind_words + used_num

        # Keep a human-readable version for logging.
        heard_head = " ".join(best_head)
        heard_num = " ".join(number_tokens[:used_num])
        label = f"{heard_head} {kind} {heard_num}".strip()

        # Only accept candidates with a plausible head or an exact numeric hit.
        exact_num = number is not None and any(
            index.id_parts[sid][3] == number for sid in candidates
        )
        if best_head_score >= HEAD_MIN_MATCH or exact_num:
            for sid in candidates:
                found.append((sid, k, label, pos - len(best_head)))

    # Prefer candidates whose ID starts earliest, then those with the best
    # dialogue-friendly candidate. Dedupe by (sid,k).
    seen = set()
    out = []
    for item in sorted(found, key=lambda x: (x[1], x[0])):
        key = (item[0], item[1])
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def cut_point(words, k):
    """Timestamp fallback for a START cut. Never place the cut inside the spoken ID."""
    if k < 1 or k >= len(words):
        return 0.0
    id_last = words[k - 1]
    first = words[k]
    # The ID is metadata only. Its final audio must be completely outside the exported clip.
    earliest = id_last["e"] + ID_EXCLUSION_SEC
    latest = max(0.0, first["s"] - 0.02)
    if earliest <= latest:
        return earliest
    # If Whisper timestamps overlap, do the safest possible thing: start immediately after the ID.
    return max(id_last["e"], 0.0)

def align_by_text(words, index):
    """Try dropping 0..N leading words (the spoken ID) and keep the split that matches the script best.
    Returns (score, words_dropped, [ids sharing that text], margin_over_next_best_line)."""
    best = (0, 0, [], 0)
    for n in range(0, min(len(words) - 1, MAX_ID_WORDS) + 1):
        top = index.top_matches(words[n:], 2)
        if not top:
            continue
        s, ids = top[0]
        if s > best[0]:
            best = (s, n, ids, s - (top[1][0] if len(top) > 1 else 0))
    return best


def text_verdict(words, index, hint):
    """
    Identify a recording from its dialogue alone (plus the file-number clue).
    Returns (id_or_None, cut_or_None, score, guess_label, reason, words_before_dialogue).
    """
    s, n, ids, margin = align_by_text(words, index)
    guess = "/".join(ids[:3])
    if not ids:
        return None, None, 0, "", "No dialogue matched", 0
    chosen = index.pick_by_hint(ids, hint)
    if chosen is None:
        if len(ids) > 1:
            return None, None, s, guess, f"This line appears under {len(ids)} IDs ({', '.join(ids)}) and nothing settles which", 0
        chosen = ids[0]
    if n == 0:
        return None, None, s, guess, "Dialogue matches but no spoken ID found to trim", 0
    strong = (s >= EXACT_TEXT_MATCH and margin >= 3) or (s >= 90 and margin >= 6)
    supported = s >= HINT_MIN_TEXT_MATCH and index.hint_agrees(chosen, hint)
    if strong or supported:
        why = "dialogue" + (" + file order" if supported and not strong else "")
        return chosen, cut_point(words, n), s, guess, why, n
    return None, None, s, guess, f"Dialogue only matches {chosen} {s:.0f}% (next best line is close or too different)", 0


def decide(words, index, hint=None):
    """
    Decide what ONE line of recording is. Returns a dict with:
      status  OK | OK_TEXT_ONLY | REVIEW
      id, cut, score, heard, guess, note, (k = number of words the spoken ID uses)
    """
    res = {"status": "REVIEW", "id": "", "cut": None, "score": 0,
           "heard": "", "heard_raw": "", "guess": "", "note": ""}
    if len(words) < 2:
        res["note"] = "Almost no speech detected"
        return res

    # ---- Evidence 1: the spoken ID ----
    cands = spoken_id_candidates(words, index)
    heard_note = ""
    heard_sid = None
    if cands:
        res["heard_raw"] = cands[0][2]
        scored = []
        for sid, k, label, id_start in cands:
            if sid and k < len(words):
                dialogue_words = words[k:]
                sc = similarity(norm(" ".join(w["w"] for w in dialogue_words)),
                                 index.norm_text[sid])
                # Reward exact/near-exact spoken number, but let dialogue overturn
                # a bad Whisper number. This is what fixes "CUE 000" -> CUE 019.
                parts = index.id_parts[sid]
                number_bonus = 0
                heard_num = spoken_number_value(
                    [w["w"] for w in words[max(0, k-5):k]]
                )
                if heard_num is not None:
                    number_bonus = 4 if heard_num == parts[3] else 0
                scored.append((sc + number_bonus, sc, k, sid, label))
        if scored:
            _, s, k, sid, label = max(scored)
            res["heard"] = sid
            res["heard_raw"] = label
            heard_sid = sid
            res["guess"], res["score"] = sid, round(s, 1)
            best_any, ids_any = index.best_text_match(words[k:])
            disagrees = sid not in ids_any and best_any >= STRONG_TEXT_MATCH and best_any - s >= CONFLICT_MARGIN
            if s >= MIN_TEXT_MATCH and not disagrees:
                res.update(status="OK", id=sid, cut=cut_point(words, k), k=k)
                return res
            heard_note = (f"CONFLICT: spoken ID says {sid} but the dialogue matches {'/'.join(ids_any[:3])} ({best_any:.0f}%)"
                          if disagrees else f"Heard {sid} but the dialogue only matches its script line {s:.0f}%")
        else:
            heard_note = f"Heard '{cands[0][2]}' but no usable dialogue followed the ID"

    # ---- Evidence 2: the dialogue (speech-to-text often garbles the digits of the ID) ----
    chosen, cut, s, guess, why, n_words = text_verdict(words, index, hint)
    if (chosen and heard_sid and chosen != heard_sid
            and index.hint_agrees(heard_sid, hint) and not index.hint_agrees(chosen, hint)):
        # the spoken ID and the file order agree with each other but not with the dialogue: a human should look
        heard_note = f"CONFLICT: spoken ID and file order say {heard_sid} but the dialogue matches {chosen}"
        chosen = None
    if chosen:
        note = f"Spoken ID heard as {res['heard_raw']}; named as {chosen} by {why}" if res["heard_raw"] else f"ID not recognised; named as {chosen} by {why}"
        # `heard` is the normalized/corrected ID written to heard_id in the log.
        # The original noisy Whisper interpretation remains in heard_raw.
        res["heard"] = chosen
        res.update(status="OK_TEXT_ONLY", id=chosen, cut=cut, k=n_words, score=round(s, 1), guess=chosen, note=note)
        return res

    res["score"] = res["score"] or round(s, 1)
    res["guess"] = res["guess"] or guess
    res["note"] = heard_note or ("No spoken ID recognised. " + why)
    if heard_note and why:
        res["note"] += f" | {why}"
    return res


# ----------------------------- several lines in one recording -----------------------------
def spoken_id_anchor_strength(words, start, end, sid, index):
    """
    Score the spoken ID itself, independently of the dialogue after it.

    Whisper often gives us a very good ID followed by only a few dialogue words.
    The old anchor detector rejected that ID when the short dialogue fragment
    scored below ANCHOR_MIN_SCORE, allowing the next ID to swallow it.
    """
    id_words = words[start:end]
    if not id_words:
        return 0.0, False

    parts = index.id_parts[sid]
    prefix, code, kind, number = parts

    # Find the canonical kind inside the spoken-ID words.
    kind_pos = None
    kind_score = 0.0
    for j in range(len(id_words)):
        hit = _kind_at(id_words, j, index)
        if hit and hit[0] == kind and hit[2] > kind_score:
            kind_pos = j
            kind_score = hit[2]

    if kind_pos is None:
        return 0.0, False

    # Everything immediately before the kind is the spoken head (UNI-HEN,
    # W01-HEN, etc.). Compare it against the actual script ID.
    head_words = [w["w"] for w in id_words[:kind_pos]]
    head_score = index.head_score(head_words, sid) if head_words else 0.0

    # Determine whether the spoken number agrees exactly. The number parser is
    # deliberately tolerant of forms such as "0 -1 -6".
    num_words = [w["w"] for w in id_words[kind_pos + 1:]]
    heard_number = spoken_number_value(num_words)
    exact_number = heard_number is not None and heard_number == number

    # Strong kind + head + exact number is a highly reliable anchor.
    if exact_number and head_score >= SPOKEN_ID_EXACT_NUMBER_MIN and kind_score >= 70:
        return max(head_score, kind_score), True

    # If the number is garbled, a very strong head/kind combination can still
    # establish the boundary; dialogue will validate the exact script line.
    strength = 0.60 * head_score + 0.40 * kind_score
    return strength, False


def _expected_dialogue_start(region, expected_sid, index):
    """Find the strongest script-dialogue match anywhere inside a region.

    The old recovery only compared region[0:] / region[n:], which assumes the
    expected dialogue starts at the beginning of the region. That is wrong when
    the previous line's dialogue occurs before a garbled/missed ID.
    """
    expected = index.norm_text.get(expected_sid, "")
    if not expected:
        return None
    exp_words = expected.split()
    n = len(exp_words)
    if not region or n == 0:
        return None

    best = None
    # Compare windows around the expected dialogue length. Allow a few extra
    # words because Whisper can split/merge words or insert a short filler.
    max_start = max(0, len(region) - 1)
    for i in range(max_start + 1):
        for extra in (0, 1, 2, 3):
            b = min(len(region), i + n + extra)
            if b <= i:
                continue
            text = norm(" ".join(w["w"] for w in region[i:b]))
            score = similarity(text, expected)
            # Also compare a fixed-length prefix to avoid a long trailing phrase
            # dominating the ratio.
            fixed = norm(" ".join(w["w"] for w in region[i:min(len(region), i+n+2)]))
            score = max(score, similarity(fixed, expected))
            candidate = (score, i, b)
            if best is None or candidate[0] > best[0]:
                best = candidate
    return best


def _fallback_expected_id_before(region, dialogue_i, expected_sid, index):
    """Recover a malformed spoken ID immediately before a known dialogue line.

    This catches forms such as 'Unihan 6015' where Whisper lost the kind word,
    while the expected script position tells us that the ID is SEQ-015.
    """
    target_num = int(expected_sid.rsplit("-", 1)[1])
    lo = max(0, dialogue_i - MAX_ID_WORDS)
    before = region[lo:dialogue_i]

    # First use the normal ID parser on the short area immediately before the
    # matched dialogue. This is safer than treating arbitrary preceding words as
    # an ID.
    cands = [c for c in spoken_id_candidates(before, index) if c[0] == expected_sid]
    if cands:
        c = min(cands, key=lambda x: x[3])
        return lo + c[3], c[1] - c[3], c[2], 100.0

    # Then look for an obvious UNI/W01 + HEN marker and the exact expected number.
    # A malformed kind (or missing kind) is okay because the expected script order
    # supplies the missing kind.
    for j in range(len(before) - 1, -1, -1):
        token = clean_token(before[j]["w"])
        if not token:
            continue
        prefix_ok = any(token == clean_token(a) or token.startswith(clean_token(a))
                        for a in PREFIX_ALIASES.get(expected_sid.split("-")[0], []))
        if not prefix_ok:
            continue

        digits = []
        end_j = min(len(before), j + 8)
        for k in range(j + 1, end_j):
            digits.extend(digit_fragments([before[k]["w"]]))
            if len(digits) >= 3:
                break
        if digits and int("".join(digits[-3:])) == target_num:
            return lo + j, max(1, k - j + 1), "RECOVERED " + expected_sid, 94.0

    # Last fallback: if the exact expected number occurs immediately before the
    # dialogue, use the nearest plausible prefix word as the ID start.
    for k in range(len(before) - 1, -1, -1):
        digits = digit_fragments([before[k]["w"]])
        if digits and int(digits[-3:]) == target_num:
            start = max(0, k - 3)
            return lo + start, k - start + 1, "RECOVERED " + expected_sid, 88.0
    return None


def _fallback_expected_id_after(region, dialogue_end_i, expected_sid, index):
    """Recover an ID spoken immediately AFTER its dialogue.

    Some takes are recorded as dialogue -> spoken ID -> next dialogue. In that
    layout the expected dialogue is the strongest clue, but the ID belongs to
    the line that just ended and must become the NEXT boundary.
    """
    target_num = int(expected_sid.rsplit("-", 1)[1])
    hi = min(len(region), dialogue_end_i + MAX_ID_WORDS + 1)
    after = region[dialogue_end_i:hi]

    cands = [c for c in spoken_id_candidates(after, index) if c[0] == expected_sid]
    if cands:
        c = min(cands, key=lambda x: x[3])
        return dialogue_end_i + c[3], c[1] - c[3], c[2], 100.0

    expected_prefix = expected_sid.split("-")[0]
    for j, item in enumerate(after):
        token = clean_token(item["w"])
        prefix_ok = any(token == clean_token(a) or token.startswith(clean_token(a))
                        for a in PREFIX_ALIASES.get(expected_prefix, []))
        if not prefix_ok:
            continue
        digits = []
        end_j = min(len(after), j + 8)
        for k in range(j + 1, end_j):
            digits.extend(digit_fragments([after[k]["w"]]))
            if len(digits) >= 3:
                if int("".join(digits[-3:])) == target_num:
                    return dialogue_end_i + j, k - j + 1, "RECOVERED " + expected_sid, 94.0
                break
    return None


def _recover_expected_anchor(region, region_start, expected_sid, index):
    """Return an anchor for expected_sid when its ID is garbled or misplaced."""
    hit = _expected_dialogue_start(region, expected_sid, index)
    if not hit:
        return None
    score, dialogue_i, _ = hit

    # Require a genuinely strong script match. This prevents ordinary dialogue
    # from becoming a false boundary just because it resembles another line.
    if score < 82:
        return None

    rec = _fallback_expected_id_before(region, dialogue_i, expected_sid, index)
    if rec:
        abs_start, k, label, id_score = rec
        return (region_start + abs_start, k, expected_sid, label, max(score, id_score))

    # Some lines have the spoken ID immediately AFTER their dialogue. In that
    # case the recovered anchor is the ID following the matched dialogue.
    rec = _fallback_expected_id_after(region, dialogue_i + max(1, len(index.norm_text[expected_sid].split()) - 1), expected_sid, index)
    if rec:
        abs_start, k, label, id_score = rec
        return (region_start + abs_start, k, expected_sid, label, max(score, id_score))

    # If we can identify the dialogue but not its ID words, put a synthetic
    # boundary immediately before the dialogue. This still guarantees that the
    # previous line cannot swallow the expected dialogue. The ID itself is not
    # included in the exported clip when a real/recovered ID is found; this branch
    # is deliberately a weaker fallback and is logged as RECOVERED.
    return (region_start + dialogue_i, 0, expected_sid, "RECOVERED " + expected_sid, score)


def _expected_next_sid(current_sid, index):
    """Return the next script ID after current_sid, preserving the master-script order."""
    pos = index.pos.get(current_sid)
    if pos is None:
        return None
    target = pos + 1
    for sid, p in index.pos.items():
        if p == target:
            return sid
    return None


def _canonicalize_ordered_anchors(anchors, words, index):
    """Use master-script order to repair weak/malformed spoken-ID anchors.

    A malformed number such as ``CUE 0 1`` can resolve to an impossible ID like
    CUE-697.  When the preceding strong anchor establishes the expected script
    position, prefer that expected ID if the audio region is consistent with it.
    Strong, correctly numbered spoken IDs are never replaced merely because a
    dialogue line resembles another script line.
    """
    if not anchors:
        return anchors

    anchors = sorted(anchors, key=lambda a: a[0])
    out = [anchors[0]]
    for cur in anchors[1:]:
        prev = out[-1]
        expected_sid = _expected_next_sid(prev[2], index)
        if not expected_sid or cur[2] == expected_sid:
            out.append(cur)
            continue

        # If the current spoken ID is strong and its number is exact, keep it.
        label = str(cur[3] or "")
        cur_strength = float(cur[4] or 0)
        number_exact = False
        try:
            number_exact = int(index.id_parts[cur[2]][3]) == int(spoken_number_value(
                [w["w"] for w in words[cur[0]:cur[0] + max(cur[1], 1)] if _numberish_token(w["w"])]
            ))
        except Exception:
            pass
        # A strong, exactly numbered spoken ID is authoritative. Do not let
        # dialogue similarity override it.
        if cur_strength >= SPOKEN_ID_ANCHOR_MIN and number_exact:
            out.append(cur)
            continue

        # If Whisper produced a malformed/incomplete number, but the head + kind
        # clearly agree with the expected next script ID, prefer the ordered ID.
        # Example: "Uni Hen CUE 0 1" can otherwise become a distant real script
        # ID such as CUE-697 because the fuzzy number scorer has no good 016 match.
        try:
            exp_prefix, exp_code, exp_kind, exp_num = index.id_parts[expected_sid]
            cur_prefix, cur_code, cur_kind, cur_num = index.id_parts[cur[2]]
            raw_clean = clean_token(label)
            expected_head_ok = (
                exp_prefix == cur_prefix and exp_code == cur_code and exp_kind == cur_kind
            )
            heard_digits = digit_fragments([w["w"] for w in words[cur[0]:cur[0] + max(cur[1], 1)]])
            incomplete_number = len(heard_digits) < 3
            distant_number = abs(int(cur_num) - int(exp_num)) > 25
            if expected_head_ok and (incomplete_number or distant_number):
                out.append((cur[0], cur[1], expected_sid,
                            "ORDER-RECOVERED " + expected_sid,
                            max(cur_strength, 90.0)))
                continue
        except Exception:
            pass

        # Evaluate the dialogue immediately after this weak anchor against the
        # expected script line. A very strong match means the spoken ID was likely
        # garbled and the master-script order is safer than Whisper's number.
        region_start = cur[0] + max(cur[1], 0)
        next_start = anchors[anchors.index(cur) + 1][0] if cur in anchors and anchors.index(cur) + 1 < len(anchors) else len(words)
        region = words[region_start:next_start]
        expected_text = index.norm_text.get(expected_sid, "")
        score_after = similarity(norm(" ".join(w["w"] for w in region)), expected_text) if region and expected_text else 0

        # Also inspect the gap before this anchor. This catches a dialogue -> ID
        # layout where the expected line belongs to the left side of the ID.
        gap = words[prev[0] + max(prev[1], 0):cur[0]]
        score_before = similarity(norm(" ".join(w["w"] for w in gap)), expected_text) if gap and expected_text else 0

        if max(score_after, score_before) >= RECOVERED_BOUNDARY_MIN_SCORE:
            if score_before > score_after:
                # The ID at cur is the boundary following expected dialogue.
                repaired = (cur[0], cur[1], expected_sid, "ORDER-RECOVERED " + expected_sid, max(score_before, cur_strength))
            else:
                repaired = (cur[0], cur[1], expected_sid, "ORDER-RECOVERED " + expected_sid, max(score_after, cur_strength))
            out.append(repaired)
        else:
            out.append(cur)
    return out


def find_anchors(words, index):
    """Find spoken-ID boundaries, with ordered script recovery for garbled/missed IDs."""
    anchors = []
    q = 0

    # Pass 1: normal spoken-ID detection.
    while q < len(words) - 1:
        candidates = []
        for sid, k, label, id_start in spoken_id_candidates(words[q:q + MAX_ID_SCAN_WORDS], index):
            abs_start = q + id_start
            abs_end = abs_start + (k - id_start)
            if not sid or abs_end >= len(words):
                continue

            expected = index.norm_text[sid]
            n_exp = max(len(expected.split()), 1)
            follow_exact = norm(" ".join(w["w"] for w in words[abs_end: abs_end + n_exp]))
            follow_loose = norm(" ".join(w["w"] for w in words[abs_end: abs_end + n_exp + 2]))
            sc = max(similarity(follow_exact, expected), similarity(follow_loose, expected))
            id_strength, exact_number = spoken_id_anchor_strength(
                words, abs_start, abs_end, sid, index
            )
            candidates.append((abs_start, k - id_start, sid, label, sc, id_strength, exact_number))

        valid = [
            c for c in candidates
            if c[4] >= ANCHOR_MIN_SCORE
            or c[5] >= SPOKEN_ID_ANCHOR_MIN
            or (c[6] and c[5] >= SPOKEN_ID_EXACT_NUMBER_MIN)
        ]
        if valid:
            best_start = min(c[0] for c in valid)
            best = max((c for c in valid if c[0] == best_start), key=lambda c: (c[5], c[4]))
            anchors.append(best[:5])
            q = best[0] + best[1]
        else:
            q += 1

    # Pass 2: ordered recovery. Crucially, search for the expected dialogue
    # ANYWHERE in the gap, then locate the ID immediately before that dialogue.
    # This fixes both:
    #   dialogue -> garbled ID -> next dialogue
    # and:
    #   ID -> dialogue -> missed ID -> next dialogue
    for _ in range(max(4, len(index.entries))):
        changed = False
        anchors.sort(key=lambda a: a[0])

        for i, cur in enumerate(list(anchors)):
            cur_start, cur_k, cur_sid = cur[0], cur[1], cur[2]
            next_start = anchors[i + 1][0] if i + 1 < len(anchors) else len(words)
            expected_pos = index.pos.get(cur_sid, 0) + 1
            if expected_pos > len(index.entries):
                continue

            expected_sid = next((sid for sid, p in index.pos.items() if p == expected_pos), None)
            if expected_sid is None:
                continue

            region_start = cur_start + cur_k
            region_end = next_start
            if region_end - region_start < 2:
                continue
            region = words[region_start:region_end]

            # First try the normal recognizer, but only accept the expected ID.
            expected_candidates = [
                c for c in spoken_id_candidates(region, index) if c[0] == expected_sid
            ]
            if expected_candidates:
                c = min(expected_candidates, key=lambda x: x[3])
                abs_start = region_start + c[3]
                if not any(abs(a[0] - abs_start) <= 1 and a[2] == expected_sid for a in anchors):
                    anchors.append((abs_start, c[1] - c[3], expected_sid, c[2], 100.0))
                    changed = True
                    break

            recovered = _recover_expected_anchor(region, region_start, expected_sid, index)
            if recovered:
                abs_start, k, sid, label, score = recovered
                # Synthetic dialogue-only boundaries are allowed only if they are
                # strongly matched; prefer a real ID candidate whenever possible.
                if not any(abs(a[0] - abs_start) <= 1 and a[2] == expected_sid for a in anchors):
                    anchors.append((abs_start, k, sid, label, score))
                    changed = True
                    break

        if not changed:
            break

    anchors.sort(key=lambda a: a[0])

    # Remove duplicates at the same timestamp AND duplicate recoveries for the
    # same script ID. A dialogue-only recovery can be discovered before a real
    # spoken-ID anchor; when both exist, the real ID anchor must win so the ID
    # audio can be excluded from the exported clip.
    dedup = []
    for a in anchors:
        if dedup and abs(a[0] - dedup[-1][0]) <= 1:
            old = dedup[-1]
            if (a[1] > 0 and old[1] == 0) or a[4] > old[4]:
                dedup[-1] = a
        else:
            dedup.append(a)

    by_sid = {}
    for a in dedup:
        sid = a[2]
        old = by_sid.get(sid)
        if old is None:
            by_sid[sid] = a
            continue
        # Prefer an anchor that actually contains the spoken ID words. If both
        # are real, keep the stronger one; if equally strong, keep the earlier
        # occurrence because it preserves recording order.
        if (a[1] > 0 and old[1] == 0) or (a[1] > 0 and old[1] > 0 and a[4] > old[4]):
            by_sid[sid] = a

    dedup = sorted(by_sid.values(), key=lambda a: a[0])
    dedup = _canonicalize_ordered_anchors(dedup, words, index)
    return dedup

def fit_end(chunk, k, sid, index):
    """
    `chunk` starts with an ID that uses k words. Find where the dialogue of `sid` really ends.
    If a clearly separate further line follows (its own ID was not recognised), split it off.
    Returns (kept_words, leftover_words).
    (In boundary mode this is only a safety net, see region_too_long.)
    """
    expected = index.norm_text.get(sid, "")
    dialogue = chunk[k:]
    if not expected or len(dialogue) < 2:
        return chunk, []
    n_exp = len(expected.split())
    best_n, best_s = len(dialogue), -1.0
    for n in range(1, min(len(dialogue), 2 * n_exp + 6) + 1):
        s = similarity(norm(" ".join(w["w"] for w in dialogue[:n])), expected)
        if s > best_s + 0.01:                       # strictly better -> keeps the shortest of equal fits
            best_s, best_n = s, n
    if best_s < MIN_TEXT_MATCH or best_n >= len(dialogue):
        return chunk, []
    leftover = dialogue[best_n:]
    gap = leftover[0]["s"] - dialogue[best_n - 1]["e"]
    kept = chunk[:k + best_n]
    if len(leftover) >= MIN_SEGMENT_WORDS and gap >= SPLIT_MIN_GAP:
        return kept, leftover                        # another line follows
    if len(leftover) < MIN_SEGMENT_WORDS and gap >= 1.0 and best_s >= 85:
        return kept, []                              # a stray word or two far away (e.g. "Thank you.") = noise
    return chunk, []


def region_too_long(chunk, k, sid, index):
    """
    Boundary-mode safety net. The words between two spoken IDs are normally exactly one line.
    If there are far more words than the script line has, an ID was probably not recognised
    somewhere in the middle, so that stretch is examined by text as before.
    """
    n_exp = len(index.norm_text.get(sid, "").split())
    n_heard = len(norm(" ".join(w["w"] for w in chunk[k:])).split())
    return n_heard > n_exp * LONG_REGION_FACTOR + LONG_REGION_EXTRA


def _best_gap_split(gap, left_sid, right_sid, index):
    """Split the dialogue between two spoken IDs into left-line/right-line text.

    This handles both recording layouts:
        ID -> dialogue -> ID
        dialogue -> ID -> dialogue

    The master script tells us which side of a spoken ID belongs to which line.
    """
    if not gap:
        return 0
    left_text = index.norm_text.get(left_sid, "")
    right_text = index.norm_text.get(right_sid, "")
    if not left_text and not right_text:
        return len(gap)

    n = len(gap)

    # Prefer a clean whole-line match before doing a mixed split. This is especially
    # important for short lines such as CUE-014 = "Watch.": the following line
    # may begin immediately afterward, so comparing the entire gap would dilute
    # the one-word match.
    if left_text:
        ln = len(left_text.split())
        lp = norm(" ".join(w["w"] for w in gap[:ln]))
        if lp and similarity(lp, left_text) >= 92:
            return min(ln, n)
    if right_text:
        rn = len(right_text.split())
        rp = norm(" ".join(w["w"] for w in gap[:rn]))
        if rp and similarity(rp, right_text) >= 92:
            return 0

    # Only evaluate plausible split points; extremely tiny sides are usually the
    # spoken ID itself or transcription noise.
    best = None
    for split in range(0, n + 1):
        ltxt = norm(" ".join(w["w"] for w in gap[:split]))
        rtxt = norm(" ".join(w["w"] for w in gap[split:]))
        ls = similarity(ltxt, left_text) if ltxt and left_text else (100.0 if not ltxt and not left_text else 0.0)
        rs = similarity(rtxt, right_text) if rtxt and right_text else (100.0 if not rtxt and not right_text else 0.0)

        # Exact/near-exact matches deserve more weight than a generic short
        # fragment. Reward a split where both sides independently match.
        score = ls + rs
        if ltxt and left_text and ls >= 85:
            score += 20
        if rtxt and right_text and rs >= 85:
            score += 20
        candidate = (score, split, ls, rs)
        if best is None or candidate[0] > best[0]:
            best = candidate
    return best[1] if best else 0


def analyse(words, index, hint=None):
    """Split a recording into script lines when IDs may be before or after dialogue."""
    anchors = find_anchors(words, index)
    if not anchors:
        d = decide(words, index, hint) if words else {"status": "REVIEW", "id": "", "cut": None, "score": 0, "heard": "", "heard_raw": "", "guess": "", "note": ""}
        d["words"] = words
        d["next_s"] = None
        d["id_at_end"] = False
        return [d] if words else []

    anchors.sort(key=lambda a: a[0])
    n = len(anchors)
    lines = []

    # For every gap between IDs, split its spoken words between the preceding and
    # following script lines. This is the central fix for recordings where an ID is
    # appended to the END of its dialogue.
    gap_splits = []
    for i in range(n - 1):
        a, b = anchors[i], anchors[i + 1]
        gap = words[a[0] + a[1]:b[0]]
        split = _best_gap_split(gap, a[2], b[2], index)
        gap_splits.append((gap, split))

    for i, a in enumerate(anchors):
        sid = a[2]
        id_start = a[0]
        id_k = a[1]
        id_end = id_start + id_k

        # Dialogue immediately after this ID belongs to this line's right side of
        # the current gap. Dialogue immediately before this ID belongs to this line's
        # left side of the previous gap.
        before = []
        after = []
        before_start = before_end = None
        after_start = after_end = None

        if i > 0:
            gap, split = gap_splits[i - 1]
            before = gap[split:]
            if before:
                before_start = before[0]["s"]
                before_end = before[-1]["e"]

        if i < n - 1:
            gap, split = gap_splits[i]
            after = gap[:split]
            if after:
                after_start = after[0]["s"]
                after_end = after[-1]["e"]
        else:
            # Last line: everything after its ID is its dialogue.
            after = words[id_end:]
            if after:
                after_start = after[0]["s"]
                after_end = after[-1]["e"]

        # Prefer an ID-at-end interpretation when the preceding dialogue strongly
        # matches this ID's script line and the following side does not.
        expected = index.norm_text.get(sid, "")
        before_score = similarity(norm(" ".join(w["w"] for w in before)), expected) if before and expected else 0
        after_score = similarity(norm(" ".join(w["w"] for w in after)), expected) if after and expected else 0
        id_at_end = bool(before and before_score >= 75 and before_score >= after_score + 5)

        synthetic_boundary = (id_k == 0 and str(a[3] or "").startswith("RECOVERED"))
        if id_at_end:
            dialogue = before
            # The exported clip must contain dialogue only. The spoken ID is the
            # right-hand boundary and is excluded entirely.
            seg_words = dialogue
            start_override = max(dialogue[0]["s"] - 0.05, 0.0) if dialogue else None
            end_override = max(words[id_start]["s"] - 0.05, 0.0) if dialogue and id_start < len(words) else None
            cut_override = start_override
            k_for_cut = 0
        elif synthetic_boundary:
            # We found the expected dialogue but NOT a trustworthy spoken ID.
            # This is a valid dialogue boundary, but there is no ID audio to trim
            # from the left. Start at the recovered dialogue timestamp rather than
            # pretending k=0 means the recording starts at 0.0 seconds.
            seg_words = words[id_start:id_end] + after
            start_override = words[id_start]["s"] if id_start < len(words) else None
            end_override = None
            cut_override = start_override
            k_for_cut = 0
        else:
            # Normal ID-first line: keep the ID words in the internal word list so
            # refine_cut() can place the start after the spoken ID.
            seg_words = words[id_start:id_end] + after
            start_override = None
            end_override = None
            cut_override = None
            k_for_cut = id_k

        h = hint if i == 0 else (index.pos[lines[-1]["id"]] + 1 if lines and lines[-1].get("id") in index.pos else None)
        d = decide(seg_words, index, h)
        # The anchor is stronger than a text-only disagreement because the ID itself
        # was found/recovered in script order.
        if d["status"] not in OK_STATUSES or d.get("id") != sid:
            d["id"] = sid
            d["guess"] = sid
            d["status"] = "OK" if expected else d["status"]
            d["score"] = max(float(d.get("score", 0) or 0), before_score, after_score)
            d["k"] = k_for_cut
            d["cut"] = cut_point(seg_words, id_k) if not id_at_end and id_k > 0 else (cut_override if cut_override is not None else 0.0)
        else:
            d["k"] = k_for_cut
            if id_at_end:
                d["cut"] = cut_override if cut_override is not None else 0.0

        d["words"] = seg_words
        d["id_at_end"] = id_at_end
        d["synthetic_boundary"] = synthetic_boundary
        d["id_start_abs"] = id_start
        d["id_end_abs"] = id_end
        d["start_override"] = start_override
        d["end_override"] = end_override
        d["next_s"] = anchors[i + 1][0] and words[anchors[i + 1][0]]["s"] if i + 1 < n else None
        lines.append(d)

    return lines


# ----------------------------- precise cuts (audio level map) -----------------------------
class AudioMap:
    """
    Loads a recording ONCE and remembers, for every 10 ms, whether it is quiet or has sound.
    The "quiet" level is worked out from the whole file, so it adapts to your microphone/room noise.
    (Original file is only read.)
    """
    FRAME = 0.01
    SR = 16000

    def __init__(self, path):
        import numpy as np
        proc = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "s16le",
                               "-ac", "1", "-ar", str(self.SR), "-"],
                              capture_output=True, check=True)
        pcm = np.frombuffer(proc.stdout, dtype=np.int16)
        hop = int(self.SR * self.FRAME)
        n = len(pcm) // hop
        if n < 20:
            raise ValueError("audio too short to analyse")
        rms = np.empty(n, dtype=np.float32)
        step = 20000                                       # frames per block, keeps memory small
        for i in range(0, n, step):
            j = min(i + step, n)
            blk = pcm[i * hop: j * hop].astype(np.float32) / 32768.0
            rms[i:j] = np.sqrt((blk.reshape(j - i, hop) ** 2).mean(axis=1))
        loud = float(np.percentile(rms, 90))
        floor = float(np.percentile(rms, 10))
        if loud < 1e-4:
            raise ValueError("file is silent")
        thr = min(max(floor * 3.0, loud * 0.04), loud * 0.25)
        quiet = rms < thr
        # sounds shorter than MIN_VOICED_SEC (clicks, lip smacks) do not count as speech
        min_frames = max(int(round(MIN_VOICED_SEC / self.FRAME)), 1)
        voiced = ~quiet
        padded = np.concatenate(([False], voiced, [False])).astype(np.int8)
        d = np.diff(padded)
        for s, e in zip(np.where(d == 1)[0], np.where(d == -1)[0]):
            if e - s < min_frames:
                voiced[s:e] = False
        self.quiet = ~voiced
        self.n = n

    def quiet_runs(self, t_a, t_b, min_len):
        """
        Quiet stretches of at least `min_len` seconds that touch the window [t_a, t_b].
        Each run is returned with its TRUE start/end (even if it extends outside the window):
        [(start_sec, end_sec), ...] in time order.
        """
        F, q = self.FRAME, self.quiet
        a = min(max(int(t_a / F), 0), self.n)
        b = min(max(int(t_b / F), 0), self.n)
        runs, i = [], a
        while i < b:
            if q[i]:
                s0, j = i, i
                while s0 > 0 and q[s0 - 1]:
                    s0 -= 1
                while j < self.n and q[j]:
                    j += 1
                if (j - s0) * F >= min_len - 1e-9:
                    runs.append((s0 * F, j * F))
                i = j
            else:
                i += 1
        return runs

    def quiet_fraction(self, t_a, t_b):
        """0..1: how much of [t_a, t_b] is quiet."""
        F = self.FRAME
        a = min(max(int(t_a / F), 0), self.n)
        b = min(max(int(t_b / F), 0), self.n)
        if b <= a:
            return 0.0
        return float(self.quiet[a:b].mean())


def drop_ghost_tail(audio, dialogue):
    """
    Whisper sometimes invents words (e.g. "Thank you.") inside silence. Words whose time span is
    (almost) completely silent are not real speech, so they are ignored when placing the END cut.
    """
    d = list(dialogue)
    while audio is not None and len(d) > 1 and audio.quiet_fraction(d[-1]["s"], d[-1]["e"]) >= 0.85:
        d.pop()
    return d


def refine_cut(audio, words, k, fallback):
    """
    Find the ID->dialogue boundary while preserving the beginning of speech.

    Critical rule:
      The first dialogue word timestamp is NOT the clip start. Whisper often
      places that timestamp late, so cutting at/near it can remove the first
      syllable. We therefore preserve a lead-in before dialogue onset.

      The spoken ID remains excluded by requiring the final boundary to be
      after the acoustic ID/dialogue transition when one can be found.
    """
    if k < 1 or k >= len(words):
        return max(fallback + CUT_NUDGE_SEC, 0.0), "timestamps"

    id_last = words[k - 1]
    first = words[k]
    id_end = float(id_last["e"])
    dialogue_ts = float(first["s"])

    # We want to preserve speech beginning before Whisper's word timestamp.
    # This is intentionally larger than the old 35–45 ms lead.
    preferred_start = max(dialogue_ts - START_PRESERVE_SEC, 0.0)

    if audio is not None and dialogue_ts > id_end:
        # Look for the transition pause.  The clip may start shortly after
        # the pause begins, but it must retain a healthy lead before Whisper's
        # first word timestamp.
        runs = [
            r for r in audio.quiet_runs(
                id_end + 0.005,
                min(dialogue_ts, id_end + ID_DIALOGUE_GAP_MAX_SEC),
                ID_DIALOGUE_GAP_MIN_SEC
            )
            if r[0] >= id_end and r[1] <= dialogue_ts + 0.01
        ]

        if runs:
            s, e = max(runs, key=lambda r: r[1])

            # Start after the transition, but never later than the preserved
            # lead-in point. This deliberately favors preserving dialogue.
            transition_start = e + 0.015
            candidate = min(transition_start, preferred_start)

            # If that would fall too close to the ID, prefer the first safe
            # point after the ID rather than clipping speech.
            candidate = max(candidate, id_end + ID_TAIL_GUARD_SEC)

            # Ensure at least a small lead before the Whisper word timestamp.
            candidate = min(candidate, dialogue_ts - START_MIN_LEAD_SEC)

            if candidate >= id_end + ID_TAIL_GUARD_SEC:
                return max(candidate + CUT_NUDGE_SEC, 0.0), "preserve_dialogue_onset"

        # No reliable transition pause: preserve the beginning of speech.
        # The ID tail guard is the only lower bound.
        candidate = max(preferred_start, id_end + ID_TAIL_GUARD_SEC)
        candidate = min(candidate, dialogue_ts - START_MIN_LEAD_SEC)
        if candidate > id_end:
            return max(candidate + CUT_NUDGE_SEC, 0.0), "preserve_dialogue_lead"

    # Overlapping/poor Whisper timestamps. We cannot safely infer the exact
    # transition, so use a conservative ID exclusion floor and a small lead
    # rather than cutting at the dialogue timestamp.
    return max(id_end + ID_TAIL_GUARD_SEC, 0.0), "id_tail_guard"


def cut_point(words, k):
    """Fallback that preserves dialogue onset rather than cutting at first-word timestamp."""
    if k < 1 or k >= len(words):
        return 0.0
    id_end = float(words[k - 1]["e"])
    dialogue_start = float(words[k]["s"])
    preferred = dialogue_start - START_PRESERVE_SEC
    floor = id_end + ID_TAIL_GUARD_SEC
    candidate = max(preferred, floor)
    candidate = min(candidate, dialogue_start - START_MIN_LEAD_SEC)
    return max(candidate, floor, 0.0)


def cut_point(words, k):
    """Timestamp fallback with the same ID-tail exclusion rule."""
    if k < 1 or k >= len(words):
        return 0.0
    id_end = float(words[k - 1]["e"])
    dialogue_start = float(words[k]["s"])
    floor = id_end + ID_TAIL_GUARD_SEC
    return max(min(dialogue_start - DIALOGUE_LEAD_SEC, dialogue_start - 0.005),
               floor, 0.0)


def cut_point(words, k):
    """Timestamp fallback with an absolute spoken-ID exclusion floor."""
    if k < 1 or k >= len(words):
        return 0.0
    id_end = float(words[k - 1]["e"])
    dialogue_start = float(words[k]["s"])
    hard_floor = id_end + ID_EXCLUSION_SEC

    if dialogue_start > hard_floor:
        return max(min(dialogue_start - AUDIO_START_SAFETY_SEC, dialogue_start - 0.005),
                   hard_floor)
    return max(hard_floor, 0.0)


def refine_end(audio, dialogue, next_start):
    """
    End at the last dialogue->ID transition, not at an arbitrary internal
    pause. Keep a small amount of silence after the final spoken word.
    """
    if not dialogue:
        return None, "no_dialogue"

    last = dialogue[-1]
    last_word_end = float(last["e"])

    if next_start is None:
        fallback = last_word_end + TAIL_SEC
        return fallback + END_NUDGE_SEC, "timestamps_final"

    boundary = float(next_start)
    safe_end = boundary - AUDIO_END_SAFETY_SEC

    if audio is not None and safe_end > last_word_end:
        runs = [
            r for r in audio.quiet_runs(
                last_word_end,
                safe_end,
                END_PAUSE_SEC
            )
            if r[0] >= last_word_end and r[1] <= boundary
        ]

        if runs:
            # Only use a pause that is genuinely near the next ID.  Internal
            # pauses farther away are not allowed to terminate the clip.
            s, e = max(runs, key=lambda r: r[1])
            if boundary - e <= 1.0:
                end = s + min(TAIL_SEC, max(DIALOGUE_END_GUARD_SEC, 0.55 * (e - s)))
                end = min(end, safe_end)
                end = max(end, last_word_end + 0.025)
                return end + END_NUDGE_SEC, "dialogue_id_transition"

    # If no reliable transition pause exists, retain the final word and a
    # small tail while staying safely before the next spoken ID.
    end = min(last_word_end + TAIL_SEC, safe_end)
    return max(end + END_NUDGE_SEC, last_word_end + 0.02), "final_word_guard"


def add_nvidia_dll_folders():
    """Windows: let Python find the GPU libraries installed with pip (nvidia-cublas-cu12, nvidia-cudnn-cu12)."""
    if os.name != "nt":
        return
    import site
    roots = set(site.getsitepackages() + [site.getusersitepackages()])
    for root in roots:
        for sub in ("cublas", "cudnn"):
            folder = Path(root) / "nvidia" / sub / "bin"
            if folder.is_dir():
                try:
                    os.add_dll_directory(str(folder))
                except Exception:
                    pass
                os.environ["PATH"] = str(folder) + os.pathsep + os.environ.get("PATH", "")


class Transcriber:
    def __init__(self):
        self.model = None
        self.beam = 5

    def load_model(self):
        from faster_whisper import WhisperModel
        import numpy as np
        print("Loading speech model (first run downloads ~250 MB)...", file=sys.stderr, flush=True)
        if DEVICE in ("auto", "cuda"):
            try:
                add_nvidia_dll_folders()
                model = WhisperModel(MODEL_SIZE, device="cuda", compute_type="float16")
                # tiny test run: GPU library problems only show up when it actually transcribes
                list(model.transcribe(np.zeros(16000, dtype="float32"), language="en")[0])
                self.model, self.beam = model, 5
                print("Using the GPU (fast).", file=sys.stderr, flush=True)
                return
            except Exception as exc:
                print(f"GPU not usable ({str(exc)[:90]}). Using the CPU instead (slower).", file=sys.stderr, flush=True)
                if DEVICE == "cuda":
                    raise
        self.model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
        self.beam = 1                                   # faster on CPU, still fine for short lines
        print("Using the CPU.", file=sys.stderr, flush=True)

    def words(self, path, prompt=None, cache_tag="", progress=None):
        CACHE_DIR.mkdir(exist_ok=True)
        st = path.stat()
        cache = CACHE_DIR / (path.name + cache_tag + ".json")
        if cache.exists():
            try:
                data = json.loads(cache.read_text())
                same_file = data.get("size") == st.st_size and data.get("mtime") == int(st.st_mtime)
                same_model = data.get("model", "small.en") == MODEL_SIZE   # older caches were small.en
                if same_file and same_model:
                    _log(f"    Using the saved transcript ({len(data['words'])} words).")
                    if progress:
                        progress(100)
                    return data["words"]
            except Exception:
                pass                                   # bad cache -> just transcribe again
        if self.model is None:
            self.load_model()
        # Decode with ffmpeg ourselves (16 kHz mono float32) instead of letting faster-whisper
        # use PyAV, so a PyAV/faster-whisper version mismatch can never break analysis.
        import numpy as np
        try:
            proc = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le",
                                   "-ac", "1", "-ar", "16000", "-"],
                                  capture_output=True, check=True)
        except FileNotFoundError:
            raise RuntimeError("ffmpeg was not found. Install it and make sure it is on your PATH.")
        except subprocess.CalledProcessError as exc:
            raise RuntimeError("ffmpeg could not read this audio file: "
                               + exc.stderr.decode(errors="replace").strip()[-300:])
        audio = np.frombuffer(proc.stdout, dtype=np.float32)
        if audio.size == 0:
            raise RuntimeError("This audio file contains no audio.")
        import time
        total = audio.size / 16000.0
        _log(f"    Transcribing {total:.0f}s of audio with {MODEL_SIZE}...")
        t0 = time.time()
        segments, _ = self.model.transcribe(
            audio, language="en", word_timestamps=True, beam_size=self.beam,
            condition_on_previous_text=False, vad_filter=USE_VAD,
            initial_prompt=prompt if prompt is not None else WHISPER_PROMPT)
        words, last = [], -1
        for seg in segments:
            for w in (seg.words or []):
                words.append({"w": w.word.strip(), "s": float(w.start), "e": float(w.end)})
            if progress and total > 0:
                pct = int(min(float(seg.end) / total, 1.0) * 100)
                if pct >= last + 5:
                    last = pct
                    progress(pct)
        if progress:
            progress(100)
        _log(f"    Transcribed {len(words)} words in {time.time() - t0:.0f}s.")
        cache.write_text(json.dumps({"size": st.st_size, "mtime": int(st.st_mtime),
                                     "model": MODEL_SIZE, "words": words}))
        return words


# ----------------------------- files / ffmpeg -----------------------------
def make_trimmed_copy(src, cut, dest, end=None):
    """Create dest from src between `cut` and `end` seconds (end=None: to the end). src is only read."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(".tmp_" + dest.name)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{cut:.3f}", "-i", str(src)]
    if end is not None:
        cmd += ["-t", f"{max(end - cut, 0.05):.3f}"]
    if src.suffix.lower() == ".wav" and dest.suffix.lower() == ".wav":
        cmd += ["-c:a", "copy"]                       # lossless for WAV -> WAV
    cmd.append(str(tmp))
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        if not tmp.exists() or tmp.stat().st_size < 100:
            raise RuntimeError("ffmpeg produced an empty file")
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            tmp.unlink()


def copy_to_review(src):
    REVIEW_DIR.mkdir(exist_ok=True)
    shutil.copy2(src, REVIEW_DIR / src.name)          # a COPY; original untouched


def remove_stale_review_copy(src):
    stale = REVIEW_DIR / src.name
    if stale.exists() and stale.resolve() != src.resolve():
        stale.unlink()


def row_key(name, segment):
    return f"{name}#{segment}"


def load_log():
    if REDO_ALL or not LOG_FILE.exists():
        return {}
    rows = {}
    with open(LOG_FILE, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            r["segment"] = r.get("segment") or "1"    # logs from the older version have no segment column
            rows[row_key(r["original_file"], r["segment"])] = r
    return rows


def save_log(rows):
    tmp = LOG_FILE.with_suffix(".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=LOG_COLUMNS)
        w.writeheader()
        for key in sorted(rows, key=lambda k: (rows[k]["original_file"], int(rows[k].get("segment") or 1))):
            w.writerow({c: rows[key].get(c, "") for c in LOG_COLUMNS})
    os.replace(tmp, LOG_FILE)


# ----------------------------- main -----------------------------
def preflight():
    problems = []
    if not shutil.which("ffmpeg"):
        problems.append("ffmpeg not found. Install it (Windows: winget install ffmpeg / Mac: brew install ffmpeg).")
    if not SCRIPT_PDF.exists():
        problems.append(f"Script PDF not found: {SCRIPT_PDF} (put it next to this file and name it script.pdf).")
    if not INPUT_DIR.is_dir():
        problems.append(f"Input folder not found: {INPUT_DIR}")
    else:
        for d in (OUTPUT_DIR, REVIEW_DIR):
            if d.resolve() == INPUT_DIR.resolve():
                problems.append(f"{d} must be a different folder from {INPUT_DIR} so originals stay untouched.")
    if problems:
        sys.exit("\n".join(["Cannot start:"] + ["  - " + p for p in problems]))



def start_boundary_diagnostic(start_sec, dialogue_start, id_end):
    """Return a simple diagnostic label for start-boundary quality."""
    lead = float(dialogue_start) - float(start_sec)
    if start_sec < id_end:
        return "INVALID_BEFORE_ID_END"
    if lead < START_MIN_LEAD_SEC:
        return "LOW_DIALOGUE_LEAD"
    if lead >= START_PRESERVE_SEC:
        return "PRESERVED_DIALOGUE_LEAD"
    return "SAFE_DIALOGUE_LEAD"


def enforce_boundary_safety(start_sec, end_sec, id_end=None, next_start=None):
    """Final hard safety checks immediately before exporting."""
    if id_end is not None:
        start_sec = max(float(start_sec), float(id_end) + ID_TAIL_GUARD_SEC)
    if next_start is not None:
        end_sec = min(float(end_sec), float(next_start) - AUDIO_END_SAFETY_SEC)
    if end_sec <= start_sec:
        return None, None, "invalid_boundary"
    return start_sec, end_sec, "safe"


def process_file(src, segs, rows, used_ids):
    """Export / log every line found in one recording."""
    n_seg = len(segs)
    suffix = src.suffix.lower()

    audio = None                                                      # level map of the whole recording
    if USE_SILENCE_CUT:
        try:
            audio = AudioMap(src)
        except Exception as exc:
            print(f"    (could not analyse the audio levels: {exc}; using speech-to-text timestamps)")

    for j, sg in enumerate(segs, 1):
        words = sg.get("words", [])
        row = {"original_file": src.name, "segment": j, "status": sg["status"],
               "heard_id": sg.get("heard", ""), "heard_id_raw": sg.get("heard_raw", ""),
               "best_match_id": sg["guess"], "match_score": sg["score"], "note": sg["note"],
               "heard_transcript": " ".join(w["w"] for w in words)[:200]}
        try:
            start = end = None
            if sg["cut"] is not None and words:
                k = sg.get("k", 0)
                if sg.get("synthetic_boundary"):
                    # No reliable spoken ID was found. This line is recoverable from
                    # script order + dialogue, but its start is known only from the
                    # matched dialogue timestamp. Never fall back to 0.0.
                    start = float(sg.get("start_override") or words[0]["s"])
                    if start <= 0.001 and UNKNOWN_START_REVIEW:
                        sg["status"] = "REVIEW"
                        row["status"] = "REVIEW"
                        row["note"] = "Recovered dialogue match but start boundary is not safely known; no audio exported."
                    else:
                        row["cut_method"] = "recovered_dialogue_boundary"
                        row["cut_at_sec"] = f"{start:.2f}"
                        dialogue = drop_ghost_tail(audio, words)
                        end, end_method = refine_end(audio, dialogue, sg.get("next_s"))
                        start, end, safety = enforce_boundary_safety(
                            start, end,
                            id_end=(words[k-1]["e"] if k > 0 else None),
                            next_start=sg.get("next_s"),
                        )
                        if safety != "safe":
                            sg["status"] = "REVIEW"
                            row["status"] = "REVIEW"
                            row["note"] = "Boundary safety check failed; no audio exported."
                            continue
                        row["cut_method"] += "+" + end_method + "+boundary_guard"
                        row["end_at_sec"] = f"{end:.2f}"
                        if end - start < MIN_CLIP_SEC:
                            sg["status"] = "REVIEW"
                            row["status"] = "REVIEW"
                            row["note"] = f"Recovered clip would be only {end - start:.2f}s long."
                        else:
                            new_name = sg["id"] + suffix
                            row["new_file"] = new_name
                            if not DRY_RUN:
                                make_trimmed_copy(src, start, OUTPUT_DIR / new_name, end)
                            used_ids[new_name] = (src.name, str(j))
                            row["status"] = "OK_TEXT_ONLY"
                            row["heard_id"] = ""
                            row["best_match_id"] = sg["id"]
                elif sg.get("id_at_end"):
                    # The ID belongs to the END of this line. The exported audio is
                    # dialogue-only, so never pass through the spoken ID at all.
                    start = max(float(sg.get("start_override") or words[0]["s"]), 0.0)
                    end = float(sg.get("end_override") or start)
                    if end <= start:
                        end = start + MIN_CLIP_SEC
                    row["cut_method"] = "id_at_end"
                    row["cut_at_sec"] = f"{start:.2f}"
                    row["end_at_sec"] = f"{end:.2f}"
                    if end - start < MIN_CLIP_SEC and row["status"] in OK_STATUSES:
                        row["status"] = "REVIEW"
                        row["note"] = f"Clip for {sg['id']} would be only {end - start:.2f}s long. " + row["note"]
                else:
                    start, row["cut_method"] = refine_cut(audio, words, k, sg["cut"])
                    row["cut_at_sec"] = f"{start:.2f}"
                    if sg["next_s"] is not None or TRIM_TRAILING:
                        dialogue = drop_ghost_tail(audio, words[k:] or words[-1:])
                        end, end_method = refine_end(audio, dialogue, sg["next_s"])
                        start, end, safety = enforce_boundary_safety(
                            start, end,
                            id_end=(words[k-1]["e"] if k > 0 else None),
                            next_start=sg.get("next_s"),
                        )
                        if safety != "safe":
                            sg["status"] = "REVIEW"
                            row["status"] = "REVIEW"
                            row["note"] = "Boundary safety check failed; no audio exported."
                            continue
                        row["cut_method"] += "+" + end_method + "+boundary_guard"
                        row["end_at_sec"] = f"{end:.2f}"
                        if end - start < MIN_CLIP_SEC and row["status"] in OK_STATUSES:
                            row["status"] = "REVIEW"
                            row["note"] = f"Clip for {sg['id']} would be only {end - start:.2f}s long. " + row["note"]

            if (not sg.get("synthetic_boundary")) and row["status"] in OK_STATUSES:
                new_name = sg["id"] + suffix
                if new_name in used_ids:                              # already produced: never overwrite
                    row["status"] = "DUPLICATE"
                    row["note"] = f"{sg['id']} was already produced from another recording (or an earlier line of this one); saved in needs_review/duplicates"
                    part = f"_part{j}" if n_seg > 1 else ""
                    dest = REVIEW_DIR / "duplicates" / f"{sg['id']}__from_{src.stem}{part}{suffix}"
                    row["new_file"] = "duplicates/" + dest.name
                    if not DRY_RUN:
                        make_trimmed_copy(src, start, dest, end)
                else:
                    row["new_file"] = new_name
                    if not DRY_RUN:
                        make_trimmed_copy(src, start, OUTPUT_DIR / new_name, end)
                    used_ids[new_name] = (src.name, str(j))
            elif (not sg.get("synthetic_boundary")) and not DRY_RUN:
                if n_seg == 1:
                    copy_to_review(src)                               # whole file, as before
                elif words:                                           # one line of a longer file: save just that part
                    cs = max(words[0]["s"] - 0.1, 0.0)
                    ce = words[-1]["e"] + 0.3
                    make_trimmed_copy(src, cs, REVIEW_DIR / f"{src.stem}__part{j}{suffix}", ce)
        except KeyboardInterrupt:
            raise
        except Exception as exc:                                      # one bad line never stops the batch
            row["status"] = "ERROR"
            row["note"] = f"{type(exc).__name__}: {exc}"[:300]
            traceback.print_exc(limit=1)
        rows[row_key(src.name, j)] = row
        print(f"    part {j}/{n_seg} -> {row.get('new_file') or row['status']}"
              f"  ({row['status']}{': ' + row['note'] if row.get('note') else ''})")

    if not DRY_RUN and all(rows[row_key(src.name, j)]["status"] in OK_STATUSES for j in range(1, n_seg + 1)):
        remove_stale_review_copy(src)


def main():
    preflight()
    entries = load_script(SCRIPT_PDF)
    if not entries:
        sys.exit("No IDs like W01-HEN-SEQ-001, UNI-HEN-SEQ-004 or W02-HEN-001 were found in the script PDF.")
    index = ScriptIndex(entries)
    print(f"Script loaded: {len(entries)} IDs "
          f"({sum(1 for v in index.text_to_ids.values() if len(v) > 1)} dialogue lines are shared by several IDs).")

    files = sorted(p for p in INPUT_DIR.iterdir()
                   if p.is_file() and p.suffix.lower() in EXTS and not p.name.startswith("."))
    if not DRY_RUN:
        OUTPUT_DIR.mkdir(exist_ok=True)
        REVIEW_DIR.mkdir(exist_ok=True)
        (REVIEW_DIR / "duplicates").mkdir(exist_ok=True)

    rows = load_log()
    transcriber = Transcriber()
    # which output names are taken, and by which original file/part (only counts if the file really exists)
    used_ids = {r["new_file"]: (r["original_file"], r["segment"]) for r in rows.values()
                if r.get("status") in OK_STATUSES and r.get("new_file")
                and (OUTPUT_DIR / r["new_file"]).exists()}

    try:
        for i, src in enumerate(files, 1):
            old = [r for r in rows.values() if r["original_file"] == src.name]
            if old and all(r["status"] in OK_STATUSES and (OUTPUT_DIR / r["new_file"]).exists() for r in old):
                continue                                             # already done
            # start this file fresh (its earlier rows / claimed names are rebuilt below)
            for key in [k for k, r in rows.items() if r["original_file"] == src.name]:
                del rows[key]
            for name in [n for n, owner in used_ids.items() if owner[0] == src.name]:
                del used_ids[name]

            print(f"[{i}/{len(files)}] {src.name}")
            try:
                words = transcriber.words(src)
                segs = analyse(words, index, file_hint(src.name))
                if not segs:
                    segs = [{"status": "REVIEW", "id": "", "cut": None, "score": 0, "heard": "", "guess": "",
                             "note": "Almost no speech detected", "words": [], "next_s": None}]
                process_file(src, segs, rows, used_ids)
            except KeyboardInterrupt:
                raise
            except Exception as exc:                                  # one bad file never stops the batch
                rows[row_key(src.name, 1)] = {"original_file": src.name, "segment": 1, "status": "ERROR",
                                              "note": f"{type(exc).__name__}: {exc}"[:300]}
                if not DRY_RUN:
                    try:
                        copy_to_review(src)
                    except Exception:
                        pass
                traceback.print_exc(limit=1)
                print(f"    ERROR: {exc}")
            save_log(rows)                                            # saved after every file
    except KeyboardInterrupt:
        print("\nStopped. Progress is saved; run again to continue where you left off.")

    save_log(rows)

    # ---- cross-check: which script lines never turned up in the audio? ----
    found = {Path(r["new_file"]).stem.split("__")[0] for r in rows.values()
             if r.get("status") in OK_STATUSES | {"DUPLICATE"} and r.get("new_file")}
    missing = [sid for sid in entries if sid not in found]
    with open(MISSING_FILE, "w", encoding="utf-8") as fh:
        fh.write(f"{len(missing)} of {len(entries)} script IDs have no audio file yet\n\n")
        for sid in missing:
            fh.write(f"{sid}\t{entries[sid]}\n")

    counts = {}
    for r in rows.values():
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("\nDone (counts are per line, not per file).", ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
    print(f"Script IDs with no audio: {len(missing)}  (see {MISSING_FILE})")
    print(f"Details for every line: {LOG_FILE}")


# ========================= NO-ID MODE =========================
# Recordings where the speaker does NOT say the IDs. Pipeline:
#   1. locate_script_segments : which script segment(s) is this audio part of?
#   2. _noid_atoms            : cut the speech into phrases at real pauses
#   3. align_noid             : match phrases to script lines, in script order (dynamic programming)
#   4. noid_file_segments     : place the cut points and build the same segment records the
#                               ID mode produces, so review / rename / export work unchanged.

def _bigrams(toks):
    if not toks:
        return []
    if len(toks) == 1:
        return [(toks[0],)]
    return [(toks[i], toks[i + 1]) for i in range(len(toks) - 1)]


def _segment_profile(index):
    """Word-pair 'fingerprint' of every script segment, weighted so that pairs which
    only occur in one segment count for more than pairs found everywhere."""
    if index._seg_profile is not None:
        return index._seg_profile
    from math import log
    grams, df = [], {}
    for seg in index.segments:
        g = set()
        for sid in seg["ids"]:
            g.update(_bigrams(index.norm_text.get(sid, "").split()))
        grams.append(g)
        for x in g:
            df[x] = df.get(x, 0) + 1
    n = max(len(grams), 1)
    idf = {x: log((n + 1) / c) for x, c in df.items()}
    index._seg_profile = (grams, idf)
    return index._seg_profile


def locate_script_segments(words, index):
    """Step 1: which script segment(s) does this recording belong to?
    Returns (active_segment_indexes, hit_indexes, description)."""
    nseg = len(index.segments)
    everything = list(range(nseg))
    toks = [t for w in words for t in norm(w["w"]).split()]
    if nseg <= 1 or len(toks) < 4:
        return everything, [], "whole script"
    grams, idf = _segment_profile(index)

    votes = {}
    for a in range(0, max(len(toks) - 3, 1), NOID_LOCATE_STEP):
        win = toks[a:a + NOID_LOCATE_WINDOW]
        wg = [g for g in _bigrams(win) if g in idf]
        if not wg:
            continue
        total = sum(idf[g] for g in wg)
        scores = [(sum(idf[g] for g in wg if g in gs) / total, si) for si, gs in enumerate(grams)]
        top = max(scores)[0]
        if top < NOID_LOCATE_MIN:
            continue
        for sc, si in scores:                       # a window on a segment border can vote for two
            if sc >= max(NOID_LOCATE_MIN, 0.75 * top):
                votes[si] = max(votes.get(si, 0.0), sc)
    if not votes:
        return everything, [], "whole script (no segment stood out)"

    hits = sorted(votes)
    active = sorted({x for si in hits for x in (si - 1, si, si + 1) if 0 <= x < nseg})
    if nseg > 10 and len(active) > 0.6 * nseg:
        return everything, hits, "whole script (recording spans too much to narrow down)"
    names = [index.segments[si]["label"].split("\u00b7")[0].strip() for si in hits]
    desc = names[0] if len(names) == 1 else f"{names[0]} \u2013 {names[-1]}" + (f" ({len(names)} segments)" if len(names) > 2 else "")
    return active, hits, desc


class _NoIdMatcher:
    """Finds the script lines (inside the located segments) that a stretch of speech resembles."""

    def __init__(self, index, allowed_pos):
        self.index = index
        self.pos_by_text = {}
        for p in allowed_pos:
            nt = index.norm_text.get(index.order[p], "")
            if nt:
                self.pos_by_text.setdefault(nt, []).append(p)
        self.texts = list(self.pos_by_text)
        self.max_words = max((len(t.split()) for t in self.texts), default=1)
        self.cache = {}

    def top(self, query, limit=NOID_TOPK, cutoff=NOID_MIN_SCORE):
        key = (query, limit, cutoff)
        if key in self.cache:
            return self.cache[key]
        from rapidfuzz import fuzz, process
        out = []
        if query and self.texts:
            for text, sc, _ in process.extract(query, self.texts, scorer=fuzz.ratio,
                                               limit=limit, score_cutoff=cutoff):
                for p in self.pos_by_text[text]:
                    out.append((p, float(sc), text))
        self.cache[key] = out
        return out


def _noid_gap(words, i, audio):
    """Pause (seconds) between word i and word i+1."""
    a, b = words[i], words[i + 1]
    gap = float(b["s"]) - float(a["e"])
    if audio is not None:
        # speech-to-text timestamps are loose: also measure the real silence around the gap
        t0, t1 = float(a["e"]) - 0.10, float(b["s"]) + 0.10
        for rs, re_ in audio.quiet_runs(t0, t1, NOID_MIN_QUIET_SEC):
            gap = max(gap, min(re_, t1) - max(rs, t0))
    return gap


def _noid_atoms(words, audio):
    """Step 2: cut the speech into phrases wherever there is a pause.
    Returns [(first_word, last_word_exclusive, pause_after_sec)]."""
    atoms, i0, n = [], 0, len(words)
    for i in range(n):
        if i == n - 1:
            atoms.append((i0, n, 99.0))
            break
        gap = _noid_gap(words, i, audio)
        if gap >= NOID_ATOM_GAP_SEC:
            atoms.append((i0, i + 1, gap))
            i0 = i + 1
    return atoms


def _order_term(prev_pos, pos):
    """Reward lines that follow each other in script order."""
    if prev_pos is None:
        return 0.0
    d = pos - prev_pos
    if d == 1:
        return 8.0
    if 2 <= d <= NOID_SKIP_MAX:
        return max(8.0 - 2.0 * (d - 1), -6.0)
    return -14.0                                    # repeat / backwards / far jump


def align_noid(words, atoms, matcher, start_pos=None, noise_cost=NOID_NOISE_COST):
    """Step 3: choose how the phrases group into script lines.
    Dynamic programming over (phrase position, last matched script line)."""
    n = len(atoms)
    wn = [" ".join(norm(w["w"]).split()) for w in words]
    max_words = int(matcher.max_words * 1.6) + 4
    best = [dict() for _ in range(n + 1)]
    best[0][start_pos] = (0.0, None)

    def relax(j, s, val, bp):
        cur = best[j].get(s)
        if cur is None or val > cur[0]:
            best[j][s] = (val, bp)

    for j in range(n):
        states = dict(sorted(best[j].items(), key=lambda kv: -kv[1][0])[:NOID_BEAM])
        best[j] = states
        if not states:
            continue
        for s, (v, _) in states.items():                      # this phrase is noise
            relax(j + 1, s, v + noise_cost, (j, s, "noise", 0.0))
        wc, parts, bridge = 0, [], 0.0
        for e in range(j + 1, n + 1):
            i0, i1, _gap = atoms[e - 1]
            wc += i1 - i0
            if wc > max_words:
                break
            if e - 1 > j:                       # this phrase is joined to the previous one across a pause
                bridge += NOID_BRIDGE_COST * max(0.0, atoms[e - 2][2] - NOID_BRIDGE_FREE_SEC)
                if bridge > 80.0:
                    break
            parts.extend(t for t in wn[i0:i1] if t)
            query = " ".join(parts)
            cands = matcher.top(query)
            if not cands:
                continue
            q_words = max(len(query.split()), 1)
            gap_after = atoms[e - 1][2]
            bc = NOID_BREAK_COST * max(0.0, 1.0 - gap_after / NOID_GOOD_GAP_SEC)
            for s1, (v, _) in states.items():
                for pos, sc, _text in cands:
                    gain = (sc - NOID_GAIN_BASE) * q_words / NOID_WORD_DIV - NOID_LINE_COST - bridge
                    relax(e, pos, v + gain + _order_term(s1, pos) - bc,
                          (j, s1, "line", sc))

    if not best[n]:
        return []
    state = max(best[n], key=lambda s: best[n][s][0])
    path, e = [], n
    while e > 0:
        _, (j, s1, kind, sc) = best[e][state]
        path.append((j, e, kind, state if kind == "line" else None, sc))
        e, state = j, s1
    path.reverse()

    chunks, noise = [], []

    def flush():
        if noise:
            chunks.append({"kind": "noise", "a0": noise[0], "a1": noise[-1] + 1,
                           "w0": atoms[noise[0]][0], "w1": atoms[noise[-1]][1]})
            noise.clear()
    for j, e, kind, pos, sc in path:
        if kind == "noise":
            if noise and noise[-1] != j - 1:
                flush()
            noise.append(j)
        else:
            flush()
            chunks.append({"kind": "line", "a0": j, "a1": e, "pos": pos, "score": sc,
                           "w0": atoms[j][0], "w1": atoms[e - 1][1]})
    flush()
    return chunks


def _refine_uncertain(chunks, words, audio, matcher):
    """Repair pass. Wherever the phrase-level alignment is unsure (weak match or unmatched
    speech), redo just that stretch with EVERY word boundary allowed as a split. This
    separates two lines that were spoken with almost no pause between them."""
    def weak(c):
        return c["kind"] == "noise" or c["score"] < NOID_ACCEPT

    for _ in range(2):
        out, i, n, changed = [], 0, len(chunks), False
        while i < n:
            if not weak(chunks[i]):
                out.append(chunks[i])
                i += 1
                continue
            j = i
            while j + 1 < n and weak(chunks[j + 1]):
                j += 1
            lo, hi = i, j
            if out:                                   # let the boundary with the neighbours move
                lo -= 1
                out.pop()
            if hi + 1 < n:
                hi += 1
            region = chunks[lo:hi + 1]
            w0, w1 = region[0]["w0"], region[-1]["w1"]
            start_pos = next((c["pos"] for c in reversed(out) if c["kind"] == "line"), None)
            sub = [(k, k + 1, _noid_gap(words, k, audio) if k + 1 < len(words) else 99.0)
                   for k in range(w0, w1)]
            sub[-1] = (sub[-1][0], sub[-1][1], 99.0)
            new = align_noid(words, sub, matcher, start_pos=start_pos,
                             noise_cost=NOID_NOISE_COST / 2.5) if sub else []
            old_sig = [(c["kind"], c["w0"], c["w1"], c.get("pos")) for c in region]
            new_sig = [(c["kind"], c["w0"], c["w1"], c.get("pos")) for c in new]
            if new and new_sig != old_sig:
                changed = True
                out.extend(new)
            else:
                out.extend(region)
            i = hi + 1
        chunks = out
        if not changed:
            break
    return chunks


def _noid_end(audio, dialogue, next_start):
    """END cut: just after the last word, using the real silence when it can be found."""
    last_e = float(dialogue[-1]["e"])
    if next_start is None:
        return last_e + TAIL_SEC + END_NUDGE_SEC
    hard = float(next_start) - 0.02
    end = last_e + TAIL_SEC
    if audio is not None and hard > last_e:
        for rs, re_ in audio.quiet_runs(last_e - 0.05, hard, END_PAUSE_SEC):
            if re_ > last_e + 0.02:
                s0 = min(max(rs, last_e - 0.10), re_)
                end = s0 + min(TAIL_SEC, max(DIALOGUE_END_GUARD_SEC, 0.55 * (re_ - s0)))
                break
    end = min(end + END_NUDGE_SEC, hard)
    return max(end, last_e + 0.02)


def noid_file_segments(src, words, index):
    """Analyse one recording WITHOUT spoken IDs. Returns segment records in the same
    format as the ID mode (plus script_text / alternatives to help the reviewer)."""
    try:
        audio = AudioMap(src)
    except Exception as exc:
        print(f"    (could not analyse the audio levels: {exc}; using speech-to-text timestamps)",
              file=sys.stderr, flush=True)
        audio = None

    active, hits, where = locate_script_segments(words, index)
    allowed = sorted(index.pos[sid] - 1 for si in active for sid in index.segments[si]["ids"])
    matcher = _NoIdMatcher(index, allowed)
    atoms = _noid_atoms(words, audio)
    chunks = align_noid(words, atoms, matcher) if atoms else []
    chunks = _refine_uncertain(chunks, words, audio, matcher) if chunks else []

    # ---- turn chunks into items (real speech only) ----
    ents = []
    for c in chunks:
        cw = drop_ghost_tail(audio, words[c["w0"]:c["w1"]])
        if not cw:
            continue
        if audio is not None and audio.quiet_fraction(cw[0]["s"], cw[-1]["e"]) >= 0.9:
            continue                                               # invented words in silence
        n_real = len([w for w in cw if norm(w["w"])])
        stray = (c["kind"] == "noise" and
                 (n_real < MIN_SEGMENT_WORDS or float(cw[-1]["e"]) - float(cw[0]["s"]) < MIN_CLIP_SEC))
        ents.append({**c, "words": cw, "stray": stray})

    # A stray word or two right next to a line is normally a mis-heard edge word of that line
    # (the alignment trimmed it off because it did not match). Keep it inside the clip so the
    # first / last word of the line is never cut off. Strays far from any line are just noise.
    items, prefix = [], []
    for i, e in enumerate(ents):
        if prefix and not e["stray"] and e["kind"] == "line":
            e["words"] = prefix + e["words"]
        prefix = []
        if not e["stray"]:
            items.append(e)
            continue
        prev = items[-1] if items and items[-1]["kind"] == "line" else None
        nxt = ents[i + 1] if i + 1 < len(ents) and not ents[i + 1]["stray"] and ents[i + 1]["kind"] == "line" else None
        g_prev = float(e["words"][0]["s"]) - float(prev["words"][-1]["e"]) if prev else 99.0
        g_next = float(nxt["words"][0]["s"]) - float(e["words"][-1]["e"]) if nxt else 99.0
        if min(g_prev, g_next) <= NOID_ATTACH_GAP_SEC:
            if g_prev <= g_next:
                prev["words"] = prev["words"] + e["words"]
            else:
                prefix = e["words"]
            continue
        # Isolated short speech that does have real sound (e.g. a one-word line the speech-to-text
        # could not recognise) is never dropped silently: it is listed as unmatched for review.
        t0, t1 = float(e["words"][0]["s"]), float(e["words"][-1]["e"])
        real_sound = (audio.quiet_fraction(t0, t1) < 0.5) if audio is not None else len(e["words"]) >= 2
        if t1 - t0 >= NOID_MIN_STRAY_SEC and real_sound:
            items.append(e)
    for it in items:
        it["text"] = " ".join(" ".join(norm(w["w"]).split()) for w in it["words"] if norm(w["w"]))
    if not items:
        return []

    # ---- cut points ----
    for i, it in enumerate(items):
        first = float(it["words"][0]["s"])
        if i == 0:
            it["start"] = max(first - START_PRESERVE_SEC, 0.0)
        else:
            prev_last = float(items[i - 1]["words"][-1]["e"])
            it["start"] = max(first - START_PRESERVE_SEC, (prev_last + first) / 2.0)
        it["start"] = max(it["start"] + CUT_NUDGE_SEC, 0.0)
    for i, it in enumerate(items):
        nxt = items[i + 1]["start"] if i + 1 < len(items) else None
        it["end"] = _noid_end(audio, it["words"], nxt)
        it["next_s"] = float(items[i + 1]["words"][0]["s"]) if i + 1 < len(items) else None

    # ---- names, statuses and notes ----
    line_items = [it for it in items if it["kind"] == "line"]
    heard_count = {}
    for it in line_items:
        heard_count[it["pos"]] = heard_count.get(it["pos"], 0) + 1

    out = []
    for i, it in enumerate(items):
        notes, review = [], False
        sid = guess = ""
        score = 0.0
        alts = []
        if it["kind"] == "line":
            pos, score = it["pos"], float(it["score"])
            sid = guess = index.order[pos]
            li = line_items.index(it)
            prev_pos = line_items[li - 1]["pos"] if li > 0 else None
            next_pos = line_items[li + 1]["pos"] if li + 1 < len(line_items) else None
            in_order = ((prev_pos is not None and 1 <= pos - prev_pos <= NOID_SKIP_OK) or
                        (next_pos is not None and 1 <= next_pos - pos <= NOID_SKIP_OK))
            cands = matcher.top(it["text"], limit=NOID_TOPK + 2, cutoff=40)
            same_text = matcher.pos_by_text.get(index.norm_text.get(sid, ""), [pos])

            def support(p):                     # how well position p fits between the neighbours
                return (int(prev_pos is not None and 1 <= p - prev_pos <= NOID_SKIP_OK) +
                        int(next_pos is not None and 1 <= next_pos - p <= NOID_SKIP_OK))
            others = [(p, sc, t) for p, sc, t in cands if t != index.norm_text.get(sid, "")]
            runner_up = max((sc for _, sc, _ in others), default=0.0)
            alts = [{"id": index.order[p], "score": round(sc, 1), "text": index.entries.get(index.order[p], "")}
                    for p, sc, _ in sorted(cands, key=lambda x: -x[1]) if p != pos][:4]

            if score < NOID_ACCEPT:
                review = True
                notes.append(f"Dialogue matches {sid} only {score:.0f}%.")
            if len(same_text) > 1:
                rivals = [p for p in same_text if p != pos]
                if support(pos) < 1 or support(pos) <= max(support(p) for p in rivals):
                    review = True
                    notes.append(f"This exact line is in the script under {len(same_text)} IDs "
                                 f"({', '.join(index.order[p] for p in same_text[:4])}"
                                 f"{'…' if len(same_text) > 4 else ''}) and its position in the recording "
                                 "does not settle which one \u2013 check the ID.")
            if prev_pos is not None and not (1 <= pos - prev_pos <= NOID_SKIP_MAX):
                review = True
                notes.append(f"Out of script order (previous line was {index.order[prev_pos]}).")
            elif prev_pos is not None and pos - prev_pos > 1:
                notes.append(f"{pos - prev_pos - 1} script line(s) between the previous clip and this one "
                             "were not found in the recording.")
            if runner_up and score - runner_up < NOID_MARGIN and not (in_order and score >= 97):
                review = True
                notes.append(f"Another script line is almost as close ({runner_up:.0f}%).")
            if heard_count.get(pos, 0) > 1:
                review = True
                notes.append(f"{sid} was heard {heard_count[pos]} times in this recording (retake?) \u2013 "
                             "keep the best take.")
        else:
            review = True
            top = matcher.top(it["text"], limit=3, cutoff=30)
            if top:
                p, score, _ = top[0]
                guess = index.order[p]
                alts = [{"id": index.order[q], "score": round(sc, 1), "text": index.entries.get(index.order[q], "")}
                        for q, sc, _ in top][:4]
            notes.append("No script line matched this speech (ad-lib, retake or a missed line)."
                         + (f" Closest: {guess} ({score:.0f}%)." if guess else ""))

        if it["end"] - it["start"] < MIN_CLIP_SEC:
            review = True
            notes.append(f"Clip is only {it['end'] - it['start']:.2f}s long.")
        if not notes:
            notes.append("Matched by dialogue and script order.")
        seg_label = index.segments[index.seg_of[sid]]["label"] if sid in index.seg_of else ""
        if seg_label:
            notes.append(f"Script: {seg_label}.")

        transcript = " ".join(str(w.get("w", "")).strip() for w in it["words"]
                              if str(w.get("w", "")).strip())
        out.append({
            "key": f"{src.name}-{i}",
            "id": sid, "source": str(src), "recording": src.name,
            "start": round(it["start"], 3), "end": round(it["end"], 3),
            "score": round(float(score), 1),
            "status": "REVIEW" if review else "PENDING",
            "engine_status": "REVIEW" if review else "OK_TEXT_ONLY",
            "heard": "", "heard_raw": "", "guess": guess,
            "transcript": transcript,
            "note": " ".join(notes),
            "id_at_end": False, "synthetic_boundary": False,
            "id_start_abs": None, "id_end_abs": None,
            "next_s": it["next_s"], "k": 0,
            "mode": "noid",
            "script_text": index.entries.get(sid, index.entries.get(guess, "")),
            "script_segment": seg_label,
            "alternatives": alts,
        })
    print(f"    located in {where}; {sum(1 for o in out if o['id'])} line(s) matched, "
          f"{sum(1 for o in out if not o['id'])} unmatched", file=sys.stderr, flush=True)
    return out


# ========================= APP API =========================

def app_boundaries(audio, sg):
    """
    Work out (start, end, note) for one detected segment, using exactly the same
    three cases as the command-line pipeline (process_file):
      - recovered line (no reliable spoken ID)  -> dialogue-match start
      - ID spoken at the END of the line        -> engine-provided overrides
      - normal ID-then-dialogue line            -> refine_cut + refine_end
    `note` is empty when everything is fine, otherwise a reason the human should look.
    """
    words = sg.get("words") or []
    k = int(sg.get("k") or 0)
    next_s = sg.get("next_s")
    next_s = float(next_s) if next_s is not None else None
    id_end = float(words[k - 1]["e"]) if 0 < k <= len(words) else None
    first_s = float(words[0]["s"]) if words else 0.0

    if sg.get("synthetic_boundary"):
        start = float(sg.get("start_override") or first_s)
        end, _ = refine_end(audio, drop_ghost_tail(audio, words), next_s)
        note = ""
        if start <= 0.001 and UNKNOWN_START_REVIEW:
            note = "Recovered dialogue match, but the start boundary is not safely known."
    elif sg.get("id_at_end"):
        start = max(float(sg.get("start_override") or first_s), 0.0)
        end = float(sg.get("end_override") or start)
        if end <= start:
            end = start + MIN_CLIP_SEC
        return start, end, ""
    else:
        cut = sg.get("cut")
        if cut is None:
            cut = cut_point(words, k)
        start, _ = refine_cut(audio, words, k, cut)
        end, _ = refine_end(audio, drop_ghost_tail(audio, words[k:] or words[-1:]), next_s)
        note = ""

    safe_start, safe_end, safety = enforce_boundary_safety(start, end, id_end=id_end, next_start=next_s)
    if safety == "safe":
        start, end = float(safe_start), float(safe_end)
    else:
        # Keep the engine's proposal so the person can see it and fix it by hand.
        start, end = float(start), float(end)
        note = (note + " " if note else "") + "Boundary safety check failed (start/end overlap a neighbouring ID); adjust by hand."
    if safety == "safe" and end - start < MIN_CLIP_SEC:
        note = (note + " " if note else "") + f"Clip is only {end - start:.2f}s long."
    return start, end, note


def app_analyze(files, script_path, transcriber=None, index=None, mode="id"):
    """
    App-facing analysis API.

    IMPORTANT:
    - Does NOT export audio.
    - Does NOT modify source recordings.
    - Uses the existing transcription + detection engine.
    - mode="id"   : the speaker says the ID before each line (spoken-ID detection).
      mode="noid" : no spoken IDs; lines are found from the script text, script segment and order.
    - Returns JSON-safe segment data for Electron/React.
    """

    script_path = Path(script_path)

    if not script_path.exists():
        raise FileNotFoundError(f"Script PDF not found: {script_path}")

    if index is None:
        entries, segments = load_script_full(script_path)
        if not entries:
            raise RuntimeError("No script IDs were found in the script file.")
        index = ScriptIndex(entries, segments)

    mode = "noid" if str(mode).lower() in ("noid", "no_id", "without", "without_id") else "id"

    # One Transcriber for all files (the model loads once, not once per file).
    if transcriber is None:
        transcriber = Transcriber()

    results = []
    errors = []

    n_files = len(files)
    _log(f"Analyzing {n_files} recording{'s' if n_files != 1 else ''} "
         f"({'matching by script, no spoken IDs' if mode == 'noid' else 'detecting spoken IDs'}); "
         f"script has {len(index.entries)} lines in {len(index.segments)} segments.")
    _progress(stage="start", index=0, total=n_files, pct=0)

    for fi, file_path in enumerate(files, 1):
        src = Path(file_path)

        if not src.exists():
            _log(f"[{fi}/{n_files}] ERROR: audio file not found: {src}")
            errors.append({
                "source": str(src),
                "recording": src.name,
                "error": f"Audio file not found: {src}"
            })
            continue

        _log(f"[{fi}/{n_files}] {src.name}")
        _progress(stage="transcribe", index=fi, total=n_files, name=src.name, pct=0)

        def on_pct(pct, fi=fi, name=src.name):
            _progress(stage="transcribe", index=fi, total=n_files, name=name, pct=int(pct * 0.85))
            if pct and pct % 20 == 0 and pct < 100:
                _log(f"    ... {pct}% transcribed")

        try:
            if mode == "noid":
                words = transcriber.words(src, prompt=NOID_WHISPER_PROMPT, cache_tag=".noid", progress=on_pct)
            else:
                words = transcriber.words(src, progress=on_pct)
            _progress(stage="analyze", index=fi, total=n_files, name=src.name, pct=88)
            _log("    Finding lines and cut points...")

            if not words:
                _log("    No speech was detected in this file.")
                errors.append({
                    "source": str(src),
                    "recording": src.name,
                    "error": "No speech was detected in this file."
                })
                continue

            if mode == "noid":
                found = noid_file_segments(src, words, index)
                if not found:
                    errors.append({
                        "source": str(src),
                        "recording": src.name,
                        "error": "Speech was found, but no part of it could be matched to the script."
                    })
                results.extend(found)
                _log(f"    Found {len(found)} segments "
                     f"({sum(1 for f_ in found if f_['status'] == 'REVIEW')} need review).")
                _progress(stage="analyze", index=fi, total=n_files, name=src.name, pct=100)
                continue

            hint = file_hint(src.name) if USE_FILE_NUMBER_HINT else None

            # Existing multi-line analysis engine.
            analyzed = analyse(words, index, hint=hint)

            # Audio map is only used for calculating precise boundaries.
            audio = AudioMap(src)

            file_segments = []

            for i, seg in enumerate(analyzed):

                sid = str(seg.get("id") or "")
                seg_words = seg.get("words") or []

                # Number of words belonging to the spoken ID.
                k = int(seg.get("k") or 0)

                # --------------------------------------------------
                # BOUNDARIES (same logic as the command-line pipeline)
                # --------------------------------------------------

                next_start = seg.get("next_s")

                if next_start is not None:
                    try:
                        next_start = float(next_start)
                    except Exception:
                        next_start = None

                try:
                    start, end, boundary_note = app_boundaries(audio, seg)
                except Exception as exc:
                    traceback.print_exc(file=sys.stderr)
                    fallback_start = float(seg.get("cut") or 0.0)
                    start = fallback_start
                    end = float(next_start) if next_start is not None else fallback_start + MIN_CLIP_SEC
                    boundary_note = f"Could not compute boundaries automatically ({type(exc).__name__}: {exc})."

                if end < start:
                    end = start

                # --------------------------------------------------
                # TRANSCRIPT
                # --------------------------------------------------

                transcript = " ".join(
                    str(w.get("w", "")).strip()
                    for w in seg_words
                    if str(w.get("w", "")).strip()
                ).strip()

                # --------------------------------------------------
                # STATUS
                # --------------------------------------------------

                status = str(seg.get("status") or "REVIEW")

                # Existing engine statuses are:
                # OK
                # OK_TEXT_ONLY
                # REVIEW
                #
                # The UI uses APPROVED separately after human review.
                if status in {"OK", "OK_TEXT_ONLY"} and not boundary_note:
                    ui_status = "PENDING"
                else:
                    ui_status = "REVIEW"

                # --------------------------------------------------
                # RESULT
                # --------------------------------------------------

                file_segments.append({
                    "key": f"{src.name}-{i}",

                    "id": sid,
                    "source": str(src),
                    "recording": src.name,

                    "start": round(start, 3),
                    "end": round(end, 3),

                    "score": float(seg.get("score") or 0),

                    "status": ui_status,
                    "engine_status": status,

                    "heard": str(seg.get("heard") or ""),
                    "heard_raw": str(seg.get("heard_raw") or ""),

                    "guess": str(seg.get("guess") or ""),

                    "transcript": transcript,

                    "note": (str(seg.get("note") or "") + (" " + boundary_note if boundary_note else "")).strip(),

                    "id_at_end": bool(seg.get("id_at_end", False)),
                    "synthetic_boundary": bool(
                        seg.get("synthetic_boundary", False)
                    ),

                    "id_start_abs": seg.get("id_start_abs"),
                    "id_end_abs": seg.get("id_end_abs"),
                    "next_s": next_start,

                    # Keep original engine data available to the UI.
                    "k": k,

                    "mode": "id",
                    "script_text": index.entries.get(sid, ""),
                    "script_segment": (index.segments[index.seg_of[sid]]["label"]
                                       if sid in index.seg_of else ""),
                    "alternatives": []
                })

            results.extend(file_segments)
            _log(f"    Found {len(file_segments)} segments "
                 f"({sum(1 for f_ in file_segments if f_['status'] == 'REVIEW')} need review).")
            _progress(stage="analyze", index=fi, total=n_files, name=src.name, pct=100)

        except Exception as exc:
            traceback.print_exc(file=sys.stderr)

            _log(f"    ERROR: {type(exc).__name__}: {exc}")
            errors.append({
                "source": str(src),
                "recording": src.name,
                "error": f"{type(exc).__name__}: {exc}"
            })

    _log(f"Done: {len(results)} segments from {n_files - len(errors)} of {n_files} file(s)"
         + (f", {len(errors)} failed." if errors else "."))
    _progress(stage="done", index=n_files, total=n_files, pct=100)
    # Every script line (in script order) so the app can list the ones that were NOT found in the audio.
    script_lines = [{"id": sid,
                     "text": index.entries.get(sid, ""),
                     "section": (index.segments[index.seg_of[sid]]["label"] if sid in index.seg_of else "")}
                    for sid in index.order]
    return {
        "count": len(results),
        "segments": results,
        "errors": errors,
        "script_lines": script_lines
    }


def app_export_segment(source, start, end, segment_id, output_dir, options=None):
    """
    Export one approved segment.

    This is called ONLY after human approval in the React UI.
    """

    src = Path(source)
    dest_dir = Path(output_dir)

    if not src.exists():
        raise FileNotFoundError(f"Source audio not found: {src}")

    dest_dir.mkdir(parents=True, exist_ok=True)

    safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(segment_id)).strip()

    if not safe_id:
        raise ValueError("Segment ID is empty.")

    # Export options from the Settings page (all validated).
    options = options if isinstance(options, dict) else {}
    fmt = options.get("format") if options.get("format") in ("wav", "flac", "mp3") else "wav"
    clean = lambda t: re.sub(r"[^A-Za-z0-9_.-]+", "_", str(t or "")).strip()
    name = f"{clean(options.get('prefix'))}{safe_id}{clean(options.get('suffix'))}"

    # Optional: one subfolder per recording (named after the recording file).
    sub = options.get("subfolder")
    if sub:
        folder = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", str(sub)).strip().strip(".").strip()
        if not folder or folder.upper() in ("CON", "PRN", "AUX", "NUL") or re.fullmatch(r"(COM|LPT)\d", folder.upper()):
            folder = (folder + "_recording") if folder else "recording"      # names Windows will not allow
        dest_dir = dest_dir / folder

    dest = dest_dir / f"{name}.{fmt}"

    if dest.exists():
        policy = options.get("overwrite")
        if policy == "skip":
            return {"success": True, "skipped": True, "path": str(dest), "id": safe_id}
        if policy == "number":
            n = 2
            while (dest_dir / f"{name}_{n}.{fmt}").exists():
                n += 1
            dest = dest_dir / f"{name}_{n}.{fmt}"

    make_trimmed_copy(
        src,
        float(start),
        dest,
        end=float(end)
    )

    return {
        "success": True,
        "skipped": False,
        "path": str(dest),
        "id": safe_id
    }


def app_waveform(source, start, end, sample_rate=22050):
    """
    Return a short WAV clip covering [start, end] seconds of a recording so the UI can
    draw and play it. Only this small window is sent to the UI, never the whole
    (possibly very long) recording. The original file is only read.
    """
    import base64
    import io
    import wave

    src = Path(source)
    if not src.exists():
        raise FileNotFoundError(f"Source audio not found: {src}")

    start = max(float(start), 0.0)
    length = max(float(end) - start, 0.1)

    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{length:.3f}",
         "-i", str(src), "-f", "s16le", "-ac", "1", "-ar", str(sample_rate), "-"],
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg could not read this audio: "
                           + proc.stderr.decode(errors="replace").strip()[-300:])
    pcm = proc.stdout
    if not pcm:
        raise RuntimeError("There is no audio in that part of the recording.")

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:                     # proper WAV header so browsers can decode it
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)

    return {
        "start": start,
        "duration": len(pcm) / 2 / sample_rate,
        "sampleRate": sample_rate,
        "wavBase64": base64.b64encode(buf.getvalue()).decode("ascii"),
    }


def app_main():
    """
    JSON stdin/stdout protocol used by Electron.

    Commands:

        {"command":"analyze", ...}
        {"command":"export", ...}
    """

    try:
        request = json.loads(sys.stdin.read())

        command = request.get("command")

        if command == "analyze":

            result = app_analyze(
                request.get("files", []),
                request.get("scriptPath", "")
            )

        elif command == "export":

            result = app_export_segment(
                request["source"],
                request["start"],
                request["end"],
                request["id"],
                request["outputDir"]
            )

        else:
            raise ValueError(
                f"Unknown app command: {command}"
            )

        print(
            json.dumps(
                result,
                ensure_ascii=False
            ),
            flush=True
        )

    except Exception as exc:

        traceback.print_exc(file=sys.stderr)

        print(
            json.dumps({
                "error": str(exc)
            }),
            flush=True
        )

        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--app":
        app_main()
    else:
        main()