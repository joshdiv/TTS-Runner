#!/usr/bin/env python3
"""Adds support for ADD-W01-BIL-001 / REG / SHA / GRP-RXN style IDs to trim_rename.py.
Usage:  python patch_add_ids.py trim_rename.py
Makes a backup (trim_rename.py.bak) first. Safe to run once; refuses to run twice."""
import re, shutil, sys
from pathlib import Path

path = Path(sys.argv[1] if len(sys.argv) > 1 else "trim_rename.py")
src = path.read_text(encoding="utf-8")
if "ADD-W01 patch" in src:
    sys.exit("Already patched.")

def sub_once(pattern, repl, text, label):
    new, n = re.subn(pattern, lambda m: repl, text, count=0, flags=re.S)
    if n != 1:
        sys.exit(f"Patch '{label}' matched {n} times (expected 1). Nothing was changed.")
    return new

# 1. regex: allow 4- and 5-part IDs
src = sub_once(
    r'r"\[A-Z\]\[A-Z0-9\]\{1,7\}-\[A-Z\]\[A-Z0-9\]\{1,7\}-\[A-Z\]\[A-Z0-9\]\{1,12\}-\\d\{1,4\}"',
    'r"[A-Z][A-Z0-9]{1,7}-[A-Z][A-Z0-9]{1,7}-[A-Z][A-Z0-9]{1,12}(?:-[A-Z][A-Z0-9]{1,12})?-\\d{1,4}"  # ADD-W01 patch',
    src, "ID regex")

# 2. ScriptIndex: parse any number of parts
src = sub_once(
    r'parts = sid\.split\("-"\)\s*\n\s*if len\(parts\) >= 4:[^\n]*\n[^\n]*\n\s*else:[^\n]*\n[^\n]*\n',
    'parts = sid.split("-")\n'
    '            number = int(parts[-1])\n'
    '            prefix, code = parts[0], parts[1]\n'
    '            kind = "-".join(parts[2:-1]) or "LINE"     # BIL, GRP-RXN, ... or LINE for W02-HEN-001\n',
    src, "ScriptIndex parsing")

# 3. prefix alias
src = sub_once(
    r'("W02": \["w02", "w 02", "w two", "w zero two", "double u two"\],)',
    '"W02": ["w02", "w 02", "w two", "w zero two", "double u two"],\n'
    '    "ADD": ["add", "ad", "ed"],',
    src, "PREFIX_ALIASES")

# 4. code aliases
src = sub_once(
    r'CODE_ALIASES = \{"HEN": \["hen", "henn", "han", "henry"\]\}',
    'CODE_ALIASES = {\n'
    '    "HEN": ["hen", "henn", "han", "henry"],\n'
    '    "W01": ["w01", "w 01", "w one", "w zero one", "double u one", "w1"],\n'
    '    "W02": ["w02", "w 02", "w two", "w zero two", "double u two", "w2"],\n'
    '}',
    src, "CODE_ALIASES")

# 5. kind aliases
src = sub_once(
    r'    # 3-part IDs such as W02-HEN-001 have no spoken "kind" word\.',
    '    "BIL": ["bil", "bill", "bell"],\n'
    '    "REG": ["reg", "reggie", "redge", "rej"],\n'
    '    "SHA": ["sha", "shah", "shaw", "shar"],\n'
    '    "GRP-RXN": ["grp rxn", "group rxn", "group reaction", "g r p r x n", "grp reaction"],\n'
    '    # 3-part IDs such as W02-HEN-001 have no spoken "kind" word.',
    src, "KIND_ALIASES")

# 6. Whisper prompt
src = sub_once(
    r'"Yuni Hen Seq Zero Zero Four\. Yuni Hen Q Zero One Nine\."',
    '"Yuni Hen Seq Zero Zero Four. Yuni Hen Q Zero One Nine. "\n'
    '    "ADD W01 BIL 001. ADD W01 REG 001. ADD W01 SHA 001. ADD W01 GRP RXN 001."',
    src, "WHISPER_PROMPT")

shutil.copy2(path, str(path) + ".bak")
path.write_text(src, encoding="utf-8")
print("Patched. Backup saved as", str(path) + ".bak")
print("IMPORTANT: delete the ./cache folder (the prompt changed).")
