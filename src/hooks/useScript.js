import { useEffect, useMemo, useRef, useState } from "react";
import { EDITS_KEY, TAKES_DIR } from "../lib/constants";
import { loadJSON, saveJSON } from "../lib/storage";
import { call } from "../lib/engines";
import { folderFor, groupName, joinPath } from "../lib/paths";
import { analyzeScript, orderItems } from "../lib/script";
import { isBracket } from "../lib/tags";

/* The script itself: lines, text edits, which lines already have audio, current line, output folder. */
export function useScript({ settings, settingsRef, say, phase, setPhase, busyRef }) {
  const [edits, setEdits] = useState(() => loadJSON(EDITS_KEY, {}));   // id -> { orig, text }
  const [scriptPath, setScriptPath] = useState("");
  const [items, setItems] = useState([]);
  const [groups, setGroups] = useState([]);        // character codes marked "Group" in Customize
  const [roster, setRoster] = useState([]);        // every character found: { code, name, count, known, omitted }
  const [done, setDone] = useState({});
  const [failed, setFailed] = useState({});
  const [takes, setTakes] = useState({});          // id -> ["BIL","REG",...] saved in the GRP folder
  const [cur, setCur] = useState(0);
  const [outDir, setOutDir] = useState("");
  const [editing, setEditing] = useState(null);    // id being edited
  const [scanInfo, setScanInfo] = useState(null);
  const [scanning, setScanning] = useState(false);

  const outRef = useRef("");
  const itemsRef = useRef([]);
  const doneRef = useRef({});
  outRef.current = outDir;
  itemsRef.current = items;
  doneRef.current = done;

  useEffect(() => saveJSON(EDITS_KEY, edits), [edits]);

  const item = items[cur];
  const analysis = useMemo(() => analyzeScript(items), [items]);
  const doneCount = useMemo(() => items.filter((i) => done[i.id]).length, [items, done]);
  const editedCount = useMemo(() => items.filter((i) => i.text !== i.orig).length, [items]);
  // Characters in script order. Group codes are left out: they are mixes of the others.
  const characters = useMemo(
    () => [...new Set([...items].sort((a, b) => a.n - b.n).map((i) => i.character).filter((c) => c && !groups.includes(c)))],
    [items, groups]
  );

  const changeOutDir = (dir) => { setOutDir(dir); outRef.current = dir; };

  // Clears the workspace. Pass { edits } to also replace the saved text edits, { outDir } to keep a folder.
  function reset(next = {}) {
    if (next.edits !== undefined) setEdits(next.edits);
    setScriptPath(""); setItems([]); setGroups([]); setRoster([]); setDone({}); setFailed({}); setTakes({});
    setCur(0); setEditing(null); setScanInfo(null);
    changeOutDir(next.outDir || "");
    setPhase("idle");
  }

  /* ---------------------------------------------------------------- folders */
  // Folder a line is saved into: the output folder, or a subfolder per scene / character when that setting is on.
  const targetDir = (it) => {
    const base = outRef.current;
    const s = settingsRef.current;
    if (!s.organizeBySegment) return base;
    const name = groupName(it, s.folderBy, s.folderNaming);
    return name ? joinPath(base, name) : base;
  };

  // Every place a line's file could be (current setting first), used by the preview player.
  const candidateDirs = (it) => {
    const base = outRef.current;
    const out = [targetDir(it)];
    [folderFor(it.segment, "code"), folderFor(it.segment, "full"), it.character]
      .forEach((n) => { if (n) out.push(joinPath(base, n)); });
    out.push(base);
    return [...new Set(out)];
  };

  async function refreshTakes(dir = outRef.current) {
    if (!dir) return;
    try {
      const r = await call("list_takes", { dir: joinPath(dir, TAKES_DIR) });
      setTakes(r.takes || {});
    } catch { /* older server: ignore */ }
  }

  // Counts a line as done if its file is in the output folder OR in any scene / character subfolder,
  // so switching the folder options never makes finished lines look pending.
  async function refreshDone(list = items, dir = outDir, moveCur = true) {
    if (!dir) return null;
    const dirs = new Set([dir]);
    list.forEach((i) => {
      [folderFor(i.segment, "code"), folderFor(i.segment, "full"), i.character]
        .forEach((n) => { if (n) dirs.add(joinPath(dir, n)); });
    });
    const results = await Promise.all([...dirs].map((d) => call("list_done", { outputDir: d, recursive: d === dir }).catch(() => ({ done: [] }))));
    const found = new Set(results.flatMap((r) => r.done));
    const d = {};
    list.forEach((i) => { if (found.has(i.id)) d[i.id] = true; });
    setDone(d);
    refreshTakes(dir);
    if (moveCur) {
      const first = list.findIndex((i) => !d[i.id]);
      setCur(first === -1 ? 0 : first);
    }
    const ids = new Set(list.map((i) => i.id));
    const matched = Object.keys(d).length;
    return { matched, pending: list.length - matched, extra: [...found].filter((x) => !ids.has(x)) };
  }

  async function scanFolder() {
    if (!outDir) return say("Choose an output folder first.");
    if (!items.length) return say("Load a script first.");
    setScanning(true);
    try {
      const r = await refreshDone(items, outDir, true);
      setScanInfo(r);
      say(`Scan: ${r.matched} of ${items.length} lines already have audio, ${r.pending} pending${r.extra.length ? `, ${r.extra.length} file(s) not in the script` : ""}.`);
    } catch (e) { say(`Scan failed: ${e.message}`); }
    setScanning(false);
  }

  // Re-check the folder when the folder naming/grouping changes.
  useEffect(() => {
    if (items.length && outDir && !busyRef.current) refreshDone(items, outDir, false).catch(() => {});
  }, [settings.folderNaming, settings.folderBy]); // eslint-disable-line

  // Re-sort the runner when the sort option changes, keeping the selected line selected.
  useEffect(() => {
    if (!itemsRef.current.length || busyRef.current) return;
    const list = itemsRef.current;
    const id = list[cur]?.id;
    const next = orderItems(list, settings.viewSort);
    setItems(next);
    const i = next.findIndex((x) => x.id === id);
    if (i !== -1) setCur(i);
  }, [settings.viewSort]); // eslint-disable-line

  /* ---------------------------------------------------------------- loading */
  // The engine reads the ID rules saved in Customize and returns each line's character and the group codes.
  async function loadScript(path, wantId, editsOverride) {
    const ed = editsOverride || edits;
    const r = await call("load_script", { path });
    const merged = r.items.map((it, n) => {
      const e = ed[it.id];
      return { ...it, n, orig: it.text, text: e && e.orig === it.text ? e.text : it.text };
    });
    const ordered = orderItems(merged, settingsRef.current.viewSort);
    setScriptPath(path);
    setGroups(r.groups || []);
    setRoster(r.roster || []);
    setItems(ordered);
    setFailed({});
    setEditing(null);
    setScanInfo(null);
    setCur(0);
    setPhase("idle");
    say(`Loaded ${r.items.length} lines in ${r.segments.length} segments. Last ID: ${r.items[r.items.length - 1]?.id ?? "none"}.`);
    const restored = merged.filter((i) => i.text !== i.orig).length;
    if (restored) say(`Restored ${restored} saved text edits.`);
    if (r.empty.length) say(`Warning: ${r.empty.length} IDs have no dialogue text (${r.empty.slice(0, 3).join(", ")}…)`);
    const br = merged.filter((i) => isBracket(i.text)).length;
    if (br) say(`${br} line${br === 1 ? " is a" : "s are"} [bracketed] reaction${br === 1 ? "" : "s"} — edit ${br === 1 ? "it" : "them"} into a sound tag like (laughs) before generating.`);
    if (outRef.current) await refreshDone(ordered, outRef.current);
    if (wantId) {
      const idx = ordered.findIndex((i) => i.id === wantId);
      if (idx !== -1) setCur(idx);
    }
  }

  async function chooseScript() {
    const path = await window.api.pickScript();
    if (!path) return false;
    try { await loadScript(path); return true; } catch (e) { say(`Script error: ${e.message}`); return false; }
  }

  // Read the current script again (after the ID rules changed), staying on the same line.
  async function reloadScript() {
    if (!scriptPath || busyRef.current) return false;
    try { await loadScript(scriptPath, itemsRef.current[cur]?.id); return true; }
    catch (e) { say(`Script error: ${e.message}`); return false; }
  }

  // Leave characters out of this script (or bring them back). Saved with the script's path in id-rules.json,
  // so it is remembered; the engine drops their lines when the script is read again.
  async function setOmitted(codes, omit) {
    if (!scriptPath || !codes.length) return;
    try {
      const data = await window.api.rules.load();
      const ignored = { ...(data.ignored || {}) };
      const now = new Set(ignored[scriptPath] || []);
      codes.forEach((c) => (omit ? now.add(c) : now.delete(c)));
      if (now.size) ignored[scriptPath] = [...now]; else delete ignored[scriptPath];
      await window.api.rules.save({ ...data, ignored });
      say(`${omit ? "Omitted" : "Restored"} ${codes.join(", ")}.`);
      await loadScript(scriptPath, itemsRef.current[cur]?.id);
    } catch (e) { say(`Couldn't update the characters: ${e.message}`); }
  }

  async function chooseDir() {
    const dir = await window.api.pickDir();
    if (!dir) return false;
    changeOutDir(dir);
    setScanInfo(null);
    if (items.length) await refreshDone(items, dir);
    return true;
  }

  /* ---------------------------------------------------------------- text editing */
  function saveEdit(id, text) {
    const idx = itemsRef.current.findIndex((i) => i.id === id);
    if (idx === -1) return;
    const it = itemsRef.current[idx];
    setItems((list) => list.map((x) => (x.id === id ? { ...x, text } : x)));
    setEdits((e) => {
      const n = { ...e };
      if (text === it.orig) delete n[id]; else n[id] = { orig: it.orig, text };
      return n;
    });
    setFailed((f) => { const n = { ...f }; delete n[id]; return n; });
    if (idx === cur && phase === "ready") { setPhase("idle"); say(`${id} text changed — generate again to match.`); }
    else say(`${id} text ${text === it.orig ? "reset to original" : "edited"}.`);
    setEditing(null);
  }

  // Applies fn(text) to many lines at once, keeping the edits store in sync.
  function bulkEdit(ids, fn) {
    const idSet = new Set(ids);
    const next = {};
    itemsRef.current.forEach((it) => { if (idSet.has(it.id)) next[it.id] = fn(it.text); });
    setItems((list) => list.map((x) => (idSet.has(x.id) ? { ...x, text: next[x.id] } : x)));
    setEdits((e) => {
      const n = { ...e };
      itemsRef.current.forEach((it) => {
        if (!idSet.has(it.id)) return;
        if (next[it.id] === it.orig) delete n[it.id]; else n[it.id] = { orig: it.orig, text: next[it.id] };
      });
      return n;
    });
    setFailed((f) => { const n = { ...f }; ids.forEach((id) => delete n[id]); return n; });
    if (item && idSet.has(item.id) && phase === "ready") setPhase("idle");
    say(`Updated ${ids.length} line${ids.length === 1 ? "" : "s"}.`);
  }

  function resetAllEdits() {
    setItems((list) => list.map((x) => ({ ...x, text: x.orig })));
    setEdits({});
    setEditing(null);
    say("All text edits reset to the script originals.");
  }

  return {
    // state
    edits, scriptPath, items, groups, roster, done, failed, takes, cur, outDir, editing, scanInfo, scanning,
    // setters other hooks need
    setCur, setDone, setFailed, setTakes, setEditing,
    // refs
    itemsRef, doneRef, outRef,
    // derived
    item, analysis, doneCount, editedCount, characters,
    // actions
    reset, changeOutDir, targetDir, candidateDirs, refreshTakes, refreshDone, scanFolder,
    loadScript, reloadScript, setOmitted, chooseScript, chooseDir, saveEdit, bulkEdit, resetAllEdits,
  };
}