import { useEffect, useMemo, useRef, useState } from "react";

const call = async (type, payload) => {
  const r = await window.api.engine(type, payload);
  if (!r.ok) throw new Error(r.error);
  return r.result;
};

/* ------------------------------------------------------------------ settings */
const DEFAULTS = {
  theme: "dark",              // dark | light
  textSize: "medium",         // small | medium | large
  density: "comfortable",     // comfortable | compact
  delayMin: 2000,             // ms between lines in auto-run (was 4000–8000)
  delayMax: 4000,
  stopOnError: true,          // auto-run stops at the first failed line
  retries: 0,                 // extra attempts per line in auto-run
  advanceAfterKeep: true,     // jump to next pending line after "Download & next"
  scrollToCurrent: true,
  port: 9222,
  chromeUrl: "https://www.minimax.io/audio/text-to-speech",
  restoreSession: true,       // reopen script, folder and current line on launch
  autosaveProject: true,      // keep <script>.tts-project.json in the output folder up to date
  autoReconnect: true,        // try to reconnect to Chrome when restoring
  showPreview: true,          // audio player for saved clips
  autoPlayPreview: false,     // play the clip right after "Download & next"
  organizeBySegment: false,   // save into a subfolder per script heading (W6-01, W6-02…)
  folderNaming: "code",       // code = W6-01 | full = whole heading text
  logLimit: 200,
  timestamps: true,
};
const SETTINGS_KEY = "mmtts.settings";
const EDITS_KEY = "mmtts.edits";
const SESSION_KEY = "mmtts.session";
const RECENT_KEY = "mmtts.recent";

const loadJSON = (key, fallback) => {
  try { return { ...fallback, ...(JSON.parse(localStorage.getItem(key)) || {}) }; } catch { return fallback; }
};
const saveJSON = (key, value) => { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* ignore */ } };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const downloadFile = (name, text, type) => {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url; a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
};
const baseOf = (path) => (path ? path.split(/[\\/]/).pop().replace(/\.[^.]+$/, "") : "");
const fileSafe = (n) => String(n || "").replace(/[<>:"/\\|?*\x00-\x1f]/g, "_").trim().slice(0, 80) || "project";
const projectPathFor = (dir, name) => joinPath(dir, `${fileSafe(name)}.tts-project.json`);
const csvCell = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;

// Folder name for a script heading. "code" pulls out something like W6-01; falls back to the cleaned heading.
const folderFor = (segment, naming) => {
  const label = (segment || "").trim();
  if (!label) return "";
  if (naming === "code") {
    const m = label.match(/\b[A-Za-z]+\d+[-_]\d+\b/);
    if (m) return m[0].toUpperCase().replace(/_/g, "-");
  }
  const clean = label.replace(/[<>:"/\\|?*\x00-\x1f]/g, "_").replace(/\s+/g, " ").replace(/[. ]+$/, "").slice(0, 60);
  return clean === "Script" ? "" : clean;
};
const joinPath = (base, name) => base + (base.includes("\\") ? "\\" : "/") + name;

const PHASE_LABEL = {
  idle: "Ready",
  generating: "Generating in MiniMax…",
  ready: "Generated — listen in the browser, then keep or redo",
  downloading: "Downloading… (if asked, click the download icon in the Chrome window)",
};

/* ------------------------------------------------------------------ tiny icons */
const ICONS = {
  mic: <><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" /><path d="M19 10v2a7 7 0 0 1-14 0v-2" /><line x1="12" y1="19" x2="12" y2="23" /></>,
  upload: <><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" /></>,
  play: <polygon points="5 3 19 12 5 21 5 3" />,
  activity: <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />,
  sliders: <><line x1="4" y1="21" x2="4" y2="14" /><line x1="4" y1="10" x2="4" y2="3" /><line x1="12" y1="21" x2="12" y2="12" /><line x1="12" y1="8" x2="12" y2="3" /><line x1="20" y1="21" x2="20" y2="16" /><line x1="20" y1="12" x2="20" y2="3" /><line x1="1" y1="14" x2="7" y2="14" /><line x1="9" y1="8" x2="15" y2="8" /><line x1="17" y1="16" x2="23" y2="16" /></>,
  file: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /><line x1="16" y1="13" x2="8" y2="13" /><line x1="16" y1="17" x2="8" y2="17" /></>,
  globe: <><circle cx="12" cy="12" r="10" /><line x1="2" y1="12" x2="22" y2="12" /><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" /></>,
  save: <><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" /><polyline points="17 21 17 13 7 13 7 21" /><polyline points="7 3 7 8 15 8" /></>,
  plus: <><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></>,
  folder: <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />,
};
const Icon = ({ name, size = 17 }) => (
  <svg className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{ICONS[name]}</svg>
);

/* ------------------------------------------------------------------ small components */
const Toggle = ({ on, onChange, label }) => (
  <button type="button" role="switch" aria-checked={on} aria-label={label} className={`toggle ${on ? "on" : ""}`} onClick={() => onChange(!on)}><i /></button>
);
const Seg = ({ value, options, onChange }) => (
  <div className="seq">
    {options.map(([v, label]) => (
      <button key={v} type="button" className={value === v ? "selected" : ""} onClick={() => onChange(v)}>{label}</button>
    ))}
  </div>
);
const SetRow = ({ title, desc, children }) => (
  <div className="setrow">
    <div className="setinfo"><b>{title}</b>{desc && <p>{desc}</p>}</div>
    <div className="setctl">{children}</div>
  </div>
);

function LineEditor({ initial, onSave, onCancel }) {
  const [draft, setDraft] = useState(initial);
  const ref = useRef(null);
  useEffect(() => { ref.current?.focus(); ref.current?.setSelectionRange(draft.length, draft.length); }, []); // eslint-disable-line
  const save = () => onSave(draft.trim());
  return (
    <div className="lineedit" onClick={(e) => e.stopPropagation()}>
      <textarea
        ref={ref}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") onCancel();
          if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); save(); }
        }}
      />
      <div className="hintrow">
        <span>Ctrl+Enter to save · Esc to cancel</span>
        <span className="sp" />
        {draft !== initial && <button className="btn small" onClick={() => setDraft(initial)}>Undo changes</button>}
        <button className="btn small" onClick={onCancel}>Cancel</button>
        <button className="btn small primary" onClick={save}>Save</button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ app */
export default function App() {
  const [settings, setSettings] = useState(() => loadJSON(SETTINGS_KEY, DEFAULTS));
  const [edits, setEdits] = useState(() => loadJSON(EDITS_KEY, {}));   // id -> { orig, text }
  const [page, setPage] = useState("setup");

  const [scriptPath, setScriptPath] = useState("");
  const [items, setItems] = useState([]);
  const [done, setDone] = useState({});
  const [failed, setFailed] = useState({});
  const [cur, setCur] = useState(0);
  const [phase, setPhase] = useState("idle");
  const [auto, setAuto] = useState(false);
  const [outDir, setOutDir] = useState("");
  const [connected, setConnected] = useState(null);
  const [log, setLog] = useState([]);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(null);   // id being edited
  const [playing, setPlaying] = useState(null);   // id of the clip currently playing
  const [loadingId, setLoadingId] = useState(null);
  const [playErr, setPlayErr] = useState("");
  const [savedAt, setSavedAt] = useState(null);
  const [projectName, setProjectName] = useState("");
  const ownedRef = useRef("");               // project file this session owns (safe to overwrite)
  const [recent, setRecent] = useState(() => { try { return JSON.parse(localStorage.getItem(RECENT_KEY)) || []; } catch { return []; } });
  useEffect(() => saveJSON(RECENT_KEY, recent), [recent]);
  const fileInputRef = useRef(null);
  const saveRef = useRef(() => {});
  const [sessionReady, setSessionReady] = useState(false);   // false until restore has finished (or the user picks something)
  const audioRef = useRef(null);

  const stopRef = useRef(false);
  const rowRefs = useRef({});
  const outRef = useRef("");
  const itemsRef = useRef([]);
  const doneRef = useRef({});
  const settingsRef = useRef(settings);
  outRef.current = outDir;
  itemsRef.current = items;
  doneRef.current = done;
  settingsRef.current = settings;

  const set = (patch) => setSettings((s) => ({ ...s, ...patch }));
  useEffect(() => saveJSON(SETTINGS_KEY, settings), [settings]);
  useEffect(() => saveJSON(EDITS_KEY, edits), [edits]);

  const say = (msg) =>
    setLog((l) => [...l.slice(-(settingsRef.current.logLimit - 1)), { t: new Date().toLocaleTimeString(), msg }]);

  useEffect(() => window.api.onLog((t) => say(t.trim())), []);
  useEffect(() => {
    if (settings.scrollToCurrent && page === "run") rowRefs.current[cur]?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [cur, page]); // eslint-disable-line

  const item = items[cur];
  const doneCount = useMemo(() => items.filter((i) => done[i.id]).length, [items, done]);
  const editedCount = useMemo(() => items.filter((i) => i.text !== i.orig).length, [items]);
  const working = phase === "generating" || phase === "downloading";
  const ready = connected && outDir && items.length;

  /* ---------------------------------------------------------------- session */
  useEffect(() => {
    (async () => {
      const sess = loadJSON(SESSION_KEY, {});
      if (!settingsRef.current.restoreSession || !(sess.scriptPath || sess.outDir)) { setSessionReady(true); return; }
      try {
        if (sess.outDir) { setOutDir(sess.outDir); outRef.current = sess.outDir; }
        if (sess.scriptPath) await loadScript(sess.scriptPath, sess.curId);
        setProjectName(sess.projectName || "");
        ownedRef.current = sess.outDir && sess.scriptPath ? projectPathFor(sess.outDir, sess.projectName || baseOf(sess.scriptPath)) : "";
        if (sess.page && sess.scriptPath) setPage(sess.page);
        say("Restored your last session.");
        setSessionReady(true);
        if (settingsRef.current.autoReconnect) await tryReconnect();
      } catch (e) {
        // leave the saved session untouched so a moved file or slow start doesn't wipe it
        say(`Couldn't restore last session: ${e.message}`);
      }
    })();
  }, []); // eslint-disable-line

  useEffect(() => {
    if (!sessionReady) return;
    saveJSON(SESSION_KEY, { scriptPath, outDir, curId: items[cur]?.id || "", page, projectName });
  }, [sessionReady, scriptPath, outDir, cur, page, items.length, projectName]); // eslint-disable-line

  /* ---------------------------------------------------------------- save / open / export */
  const baseName = () => baseOf(scriptPath) || "script";
  const autosaveWarned = useRef(false);

  const rememberProject = (name, path) =>
    setRecent((r) => [{ name, path, scriptPath, savedAt: new Date().toISOString() }, ...r.filter((x) => x.path !== path)].slice(0, 12));

  // Writes the whole session to <output folder>/<project name>.tts-project.json through the engine.
  // A project never overwrites another project's file: a new name (or a name change) creates a new file,
  // and if that file already exists the name gets a number ("Week 6 2").
  // Falls back to a normal download when there is no output folder or the engine can't write files.
  async function writeProject({ silent = false } = {}) {
    if (!scriptPath) { if (!silent) say("Load a script before saving a project."); return false; }
    let name = (projectName || baseName()).trim();
    const build = (n) => JSON.stringify({
      app: "minimax-tts-runner", version: 2, name: n, savedAt: new Date().toISOString(),
      scriptPath, outDir, curId: items[cur]?.id || "", page, edits,
    }, null, 2);
    if (outDir) {
      try {
        let path = projectPathFor(outDir, name);
        if (ownedRef.current !== path) {
          let n = name; let k = 1;
          for (;;) {
            path = projectPathFor(outDir, n);
            const r = await call("write_text", { path, text: build(n), create_only: true });
            if (!r.exists) break;
            k += 1; n = `${name} ${k}`;
            if (k > 50) throw new Error("too many projects with this name");
          }
          if (n !== name) { name = n; setProjectName(n); }
          ownedRef.current = path;
        } else {
          await call("write_text", { path, text: build(name) });
        }
        setSavedAt(new Date().toLocaleTimeString());
        rememberProject(name, path);
        if (!silent) say(`Project "${name}" saved to ${path}`);
        return true;
      } catch (e) {
        if (silent) {
          if (!autosaveWarned.current) { autosaveWarned.current = true; say(`Autosave failed: ${/Unknown request type/.test(e.message) ? "update minimax_server.py to enable saving into the output folder." : e.message}`); }
          return false;
        }
        say(`Couldn't write into the output folder (${e.message}) — downloading instead.`);
      }
    } else if (silent) return false;
    downloadFile(`${fileSafe(name)}.tts-project.json`, build(name), "application/json");
    setSavedAt(new Date().toLocaleTimeString());
    say("Project downloaded. Choose an output folder to save it there automatically.");
    return true;
  }
  const saveProject = () => writeProject({ silent: false });
  saveRef.current = saveProject;

  async function tryReconnect() {
    try {
      const r = await call("connect", { port: Number(settingsRef.current.port) });
      setConnected(r.url);
      say(`Connected: ${r.url}`);
    } catch { say("Chrome isn't running yet — use Open Chrome, then Connect."); }
  }

  useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); saveRef.current(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (!settings.autosaveProject || !sessionReady || !scriptPath || !outDir || working || auto) return;
    const t = setTimeout(() => writeProject({ silent: true }), 2000);
    return () => clearTimeout(t);
  }, [settings.autosaveProject, sessionReady, scriptPath, outDir, cur, page, edits, projectName, working, auto]); // eslint-disable-line

  // Restores everything a project file holds. The project's edits replace the current ones.
  async function applyProject(proj, label) {
    if (proj.app !== "minimax-tts-runner" || !proj.scriptPath) throw new Error("not a MiniMax TTS Runner project file");
    stopAudio();
    const ed = proj.edits || {};
    const name = proj.name || baseOf(proj.scriptPath);
    setEdits(ed);
    setProjectName(name);
    setDone({});
    setOutDir(proj.outDir || ""); outRef.current = proj.outDir || "";
    ownedRef.current = proj.outDir ? projectPathFor(proj.outDir, name) : "";
    await loadScript(proj.scriptPath, proj.curId, ed);
    setSessionReady(true);
    setSavedAt(null);
    setPage(proj.page && proj.page !== "settings" && proj.page !== "setup" ? proj.page : "run");
    say(`Opened project "${name}"${label ? ` (${label})` : ""} — session restored.`);
    if (settingsRef.current.autoReconnect && !connected) await tryReconnect();
  }

  async function openProject(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file || working || auto) return;
    try {
      const proj = JSON.parse(await file.text());
      if (scriptPath) await writeProject({ silent: true });
      await applyProject(proj, file.name);
    } catch (err) { say(`Open project failed: ${err.message}`); }
  }

  async function openRecent(r) {
    if (working || auto) return;
    try {
      const x = await call("read_text", { path: r.path });
      if (!x.found) {
        setRecent((l) => l.filter((i) => i.path !== r.path));
        throw new Error("file no longer exists, removed from the list");
      }
      if (scriptPath && ownedRef.current !== r.path) await writeProject({ silent: true });
      await applyProject(JSON.parse(x.text), r.name);
    } catch (err) {
      const msg = /Unknown request type/.test(err.message) ? "update minimax_server.py to open projects from the list." : err.message;
      say(`Open "${r.name}" failed: ${msg}`);
    }
  }

  // Saves the current project, then clears the workspace so a new one can be started.
  async function newProject() {
    if (working || auto) return;
    if (scriptPath) {
      const ok = await writeProject({ silent: false });
      if (!ok) return say("Project wasn't saved, so it was left open.");
    }
    stopAudio();
    try { localStorage.removeItem(SESSION_KEY); } catch { /* ignore */ }
    setSessionReady(false);
    setScriptPath(""); setItems([]); setDone({}); setFailed({}); setCur(0);
    setOutDir(""); outRef.current = "";
    setEdits({}); setProjectName(""); ownedRef.current = ""; setSavedAt(null);
    setPhase("idle"); setPage("setup");
    autosaveWarned.current = false;
    say("New project started. Choose a script and an output folder.");
  }

  function exportCsv() {
    const rows = [["id", "segment", "original_text", "text", "edited", "saved"]];
    items.forEach((i) => rows.push([i.id, i.segment, i.orig, i.text, i.text !== i.orig ? "yes" : "", done[i.id] ? "yes" : ""]));
    downloadFile(`${baseName()}.edited.csv`, "\ufeff" + rows.map((r) => r.map(csvCell).join(",")).join("\r\n"), "text/csv");
    say(`Exported ${items.length} lines to CSV.`);
  }

  function clearSession() {
    stopAudio();
    try { localStorage.removeItem(SESSION_KEY); } catch { /* ignore */ }
    setSessionReady(false);
    setScriptPath(""); setItems([]); setDone({}); setFailed({}); setCur(0);
    setOutDir(""); outRef.current = "";
    setProjectName(""); ownedRef.current = ""; setSavedAt(null);
    setPhase("idle"); setPage("setup");
    say("Session cleared.");
  }

  /* ---------------------------------------------------------------- setup actions */
  async function loadScript(path, wantId, editsOverride) {
    const ed = editsOverride || edits;
    const r = await call("load_script", { path });
    const merged = r.items.map((it) => {
      const e = ed[it.id];
      return { ...it, orig: it.text, text: e && e.orig === it.text ? e.text : it.text };
    });
    setScriptPath(path);
    setItems(merged);
    setFailed({});
    setEditing(null);
    setCur(0);
    setPhase("idle");
    say(`Loaded ${r.items.length} lines in ${r.segments.length} segments.`);
    const restored = merged.filter((i) => i.text !== i.orig).length;
    if (restored) say(`Restored ${restored} saved text edits.`);
    if (r.empty.length) say(`Warning: ${r.empty.length} IDs have no dialogue text (${r.empty.slice(0, 3).join(", ")}…)`);
    if (outRef.current) await refreshDone(merged, outRef.current);
    if (wantId) {
      const idx = merged.findIndex((i) => i.id === wantId);
      if (idx !== -1) setCur(idx);
    }
  }

  async function chooseScript() {
    const path = await window.api.pickScript();
    if (!path) return;
    try {
      await loadScript(path);
      setSessionReady(true);
    } catch (e) { say(`Script error: ${e.message}`); }
  }

  // Folder a line is saved into: the output folder, or a per-heading subfolder when that setting is on.
  const targetDir = (it) => {
    const base = outRef.current;
    const s = settingsRef.current;
    if (!s.organizeBySegment) return base;
    const name = folderFor(it.segment, s.folderNaming);
    return name ? joinPath(base, name) : base;
  };

  // Every place a line's file could be (current setting first), used by the preview player.
  const candidateDirs = (it) => {
    const base = outRef.current;
    const out = [targetDir(it)];
    ["code", "full"].forEach((nm) => { const n = folderFor(it.segment, nm); if (n) out.push(joinPath(base, n)); });
    out.push(base);
    return [...new Set(out)];
  };

  // Counts a line as done if its file is in the output folder OR in any heading subfolder,
  // so switching the folder option never makes finished lines look pending.
  async function refreshDone(list = items, dir = outDir, moveCur = true) {
    if (!dir) return;
    const naming = settingsRef.current.folderNaming;
    const dirs = new Set([dir]);
    list.forEach((i) => { const n = folderFor(i.segment, naming); if (n) dirs.add(joinPath(dir, n)); });
    const results = await Promise.all([...dirs].map((d) => call("list_done", { outputDir: d }).catch(() => ({ done: [] }))));
    const s = new Set(results.flatMap((r) => r.done));
    const d = {};
    list.forEach((i) => { if (s.has(i.id)) d[i.id] = true; });
    setDone(d);
    if (moveCur) {
      const first = list.findIndex((i) => !d[i.id]);
      setCur(first === -1 ? 0 : first);
    }
  }

  useEffect(() => {
    if (items.length && outDir && !working && !auto) refreshDone(items, outDir, false).catch(() => {});
  }, [settings.folderNaming]); // eslint-disable-line

  async function chooseDir() {
    const dir = await window.api.pickDir();
    if (!dir) return;
    setOutDir(dir);
    outRef.current = dir;
    setSessionReady(true);
    if (items.length) await refreshDone(items, dir);
  }

  async function openBrowser() {
    const r = await window.api.launchChrome(settings.port, settings.chromeUrl);
    say(r.ok ? "Opened Chrome. Log in to MiniMax and pick your voice/settings, then click Connect." : r.error);
  }

  async function connect() {
    setBusy(true);
    try {
      const r = await call("connect", { port: Number(settings.port) });
      setConnected(r.url);
      say(`Connected: ${r.url}`);
    } catch (e) { setConnected(null); say(`Connect failed: ${e.message}`); }
    setBusy(false);
  }

  async function diagnose() {
    try {
      const r = await call("diagnose", {});
      say("DIAGNOSE " + JSON.stringify(r, null, 1));
      setPage("activity");
    } catch (e) { say(`Diagnose failed: ${e.message}`); }
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

  function resetAllEdits() {
    setItems((list) => list.map((x) => ({ ...x, text: x.orig })));
    setEdits({});
    setEditing(null);
    say("All text edits reset to the script originals.");
  }

  /* ---------------------------------------------------------------- per-line actions */
  /* ---------------------------------------------------------------- playback */
  function stopAudio() {
    const a = audioRef.current;
    if (a) { a.pause(); if (a._url) URL.revokeObjectURL(a._url); audioRef.current = null; }
    setPlaying(null);
  }

  async function playLine(it) {
    if (playing === it.id) return stopAudio();
    stopAudio();
    setPlayErr("");
    setLoadingId(it.id);
    try {
      const r = await call("read_audio", { id: it.id, dirs: candidateDirs(it) });
      if (!r.found) throw new Error("Saved file not found in the output folder.");
      const bytes = Uint8Array.from(atob(r.data), (c) => c.charCodeAt(0));
      const url = URL.createObjectURL(new Blob([bytes], { type: r.mime }));
      const a = new Audio(url);
      a._url = url;
      a.onended = stopAudio;
      audioRef.current = a;
      await a.play();
      setPlaying(it.id);
    } catch (e) {
      const msg = /Unknown request type/.test(e.message)
        ? "Playback needs the updated minimax_server.py — replace it and restart the app."
        : e.message;
      setPlayErr(`${it.id}: ${msg}`);
      say(`${it.id} play failed: ${msg}`);
      stopAudio();
    }
    setLoadingId(null);
  }

  async function gen(it) {
    setPhase("generating");
    try {
      const r = await call("generate", { id: it.id, text: it.text });
      say(`${it.id} generated (${r.seconds}s)`);
      setFailed((f) => { const n = { ...f }; delete n[it.id]; return n; });
      setPhase("ready");
      return true;
    } catch (e) {
      setFailed((f) => ({ ...f, [it.id]: e.message }));
      say(`${it.id} generate failed: ${e.message}`);
      setPhase("idle");
      return false;
    }
  }

  async function dl(it) {
    setPhase("downloading");
    try {
      const dir = targetDir(it);
      const r = await call("download", { id: it.id, outputDir: dir });
      say(`${it.id} saved as ${r.name}${dir !== outRef.current ? ` in ${dir.split(/[\\/]/).pop()}` : ""}`);
      setDone((d) => ({ ...d, [it.id]: true }));
      setPhase("idle");
      return true;
    } catch (e) {
      setFailed((f) => ({ ...f, [it.id]: e.message }));
      say(`${it.id} download failed: ${e.message}`);
      setPhase("ready");
      return false;
    }
  }

  const nextPending = (from, d = done) => {
    for (let i = from + 1; i < items.length; i++) if (!d[items[i].id]) return i;
    return Math.min(from + 1, items.length - 1);
  };

  async function keep() {
    if (await dl(item)) {
      if (settings.autoPlayPreview) playLine(item);
      if (settings.advanceAfterKeep) setCur(nextPending(cur, { ...done, [item.id]: true }));
    }
  }

  async function runAuto() {
    if (!outRef.current) return say("Choose an output folder first.");
    stopRef.current = false;
    stopAudio();
    setAuto(true);
    setEditing(null);
    let i = cur;
    const d = { ...doneRef.current };
    while (i < itemsRef.current.length && !stopRef.current) {
      const it = itemsRef.current[i];       // read fresh so edits to upcoming lines are used
      if (d[it.id]) { i++; continue; }
      if (!it.text.trim()) { say(`${it.id} has no text — skipped.`); i++; continue; }
      setCur(i);
      const tries = 1 + Number(settingsRef.current.retries || 0);
      let ok = false;
      for (let t = 0; t < tries && !stopRef.current; t++) {
        ok = (await gen(it)) && (await dl(it));
        if (ok) break;
        if (t < tries - 1) say(`${it.id} retrying (${t + 2}/${tries})…`);
      }
      if (!ok) {
        if (settingsRef.current.stopOnError || stopRef.current) break;
        i++; continue;
      }
      d[it.id] = true;
      const lo = Math.min(settingsRef.current.delayMin, settingsRef.current.delayMax);
      const hi = Math.max(settingsRef.current.delayMin, settingsRef.current.delayMax);
      await sleep(lo + Math.random() * (hi - lo));
      i++;
    }
    setAuto(false);
    say(stopRef.current ? "Auto-run stopped." : "Auto-run finished.");
  }

  /* ---------------------------------------------------------------- pages */
  const TITLES = {
    setup: ["Setup", "Choose a script, connect your browser and pick an output folder."],
    run: ["Runner", `${doneCount} of ${items.length} saved${editedCount ? ` · ${editedCount} edited` : ""}`],
    activity: ["Activity", "Progress and everything the runner has done this session."],
    settings: ["Settings", "Appearance, automation and browser preferences. Saved automatically."],
  };

  const setupPage = (
    <div className="page">
      <div className="hero">
        <div className="heroicon"><Icon name="mic" size={22} /></div>
        <h2>MiniMax TTS Runner</h2>
        <p>Generate every line of your script and save each one as &lt;ID&gt;.mp3.</p>
      </div>
      <div className="cards">
        <div className="picker">
          <div className="pickericon"><Icon name="file" /></div>
          <div className="grow">
            <label>1 · Script</label>
            <strong>{scriptPath ? scriptPath.split(/[\\/]/).pop() : "No script chosen"}</strong>
            <small>{scriptPath ? `${items.length} lines${editedCount ? ` · ${editedCount} edited` : ""}` : "IDs like W06-HEN-001 are read from the script (PDF / Word)."}</small>
          </div>
          <button className="btn" onClick={chooseScript}>{scriptPath ? "Change" : "Choose script"}</button>
        </div>

        <div className="picker">
          <div className="pickericon"><Icon name="globe" /></div>
          <div className="grow">
            <label>2 · Browser</label>
            <strong>{connected ? "Connected" : "Not connected"}</strong>
            <small>{connected || "Open MiniMax, log in, choose your voice, then Connect."}</small>
          </div>
          <div className="btnrow">
            <button className="btn" onClick={openBrowser}>Open Chrome</button>
            <button className="btn" onClick={connect} disabled={busy}>{connected ? "Reconnect" : "Connect"}</button>
            <button className="btn" onClick={diagnose} disabled={!connected}>Diagnose</button>
          </div>
        </div>

        <div className="picker">
          <div className="pickericon"><Icon name="folder" /></div>
          <div className="grow">
            <label>3 · Output folder</label>
            <strong>{outDir || "No folder chosen"}</strong>
            <small>{settings.organizeBySegment ? "Saved into a subfolder per script heading. Existing files count as done." : "Existing files count as done."}</small>
          </div>
          <button className="btn" onClick={chooseDir}>{outDir ? "Change" : "Choose folder"}</button>
        </div>
      </div>

      {recent.length > 0 && (
        <div className="recent">
          <div className="recenthead"><label>Recent projects</label><span>{recent.length}</span></div>
          {recent.map((r) => (
            <div key={r.path} className="recentrow">
              <div className="grow">
                <strong>{r.name}{r.path === ownedRef.current && scriptPath ? <em className="tag">open</em> : null}</strong>
                <small>{baseOf(r.scriptPath)} · {r.path}</small>
              </div>
              <button className="btn small" disabled={working || auto || (r.path === ownedRef.current && !!scriptPath)} onClick={() => openRecent(r)}>Open</button>
              <button className="linkbtn" onClick={() => setRecent((l) => l.filter((i) => i.path !== r.path))}>Remove</button>
            </div>
          ))}
        </div>
      )}

      <div className="picker" style={{ display: "block" }}>
        <label>Progress</label>
        <div className="progressbar"><i style={{ width: items.length ? `${(doneCount / items.length) * 100}%` : 0 }} /></div>
        <div className="progresstext"><span>{doneCount} of {items.length} saved</span><span>{items.length ? Math.round((doneCount / items.length) * 100) : 0}%</span></div>
      </div>

      <div className="actionbar">
        <div>
          <b>{ready ? "Ready to run" : "Finish setup to continue"}</b>
          <span>{ready ? "Everything is connected. Open the runner to generate lines." : "Needs a script, a connected browser and an output folder."}</span>
        </div>
        <button className="btn primary" disabled={!items.length} onClick={() => setPage("run")}>Open runner</button>
      </div>
    </div>
  );

  const runPage = (
    <div className="run">
      <div className="lines">
        {items.length === 0 && (
          <div className="empty"><h2>No script loaded</h2><p>Go to Setup and choose a script to begin.</p></div>
        )}
        {items.map((it, i) => {
          const prev = items[i - 1];
          const isEdited = it.text !== it.orig;
          const locked = working && i === cur || auto && i === cur;
          return (
            <div key={it.id}>
              {(!prev || prev.segment !== it.segment) && it.segment && <div className="seg">{it.segment}</div>}
              <div
                ref={(el) => (rowRefs.current[i] = el)}
                className={`line ${i === cur ? "current" : ""} ${done[it.id] ? "done" : ""} ${failed[it.id] ? "failed" : ""} ${editing === it.id ? "editing" : ""}`}
                onClick={() => !working && !auto && editing !== it.id && setCur(i)}
                onDoubleClick={() => !locked && !auto && setEditing(it.id)}
              >
                <span className="playcell">
                  {done[it.id] && settings.showPreview && (
                    <button
                      className="playbtn"
                      aria-label={playing === it.id ? "Stop" : "Play"}
                      title={playing === it.id ? "Stop" : "Play"}
                      disabled={working || auto || loadingId === it.id}
                      onClick={(e) => { e.stopPropagation(); playLine(it); }}
                    >
                      {loadingId === it.id ? <span className="spin">…</span> : (
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                          {playing === it.id ? <rect x="6" y="6" width="12" height="12" rx="1" /> : <polygon points="7 4 20 12 7 20" />}
                        </svg>
                      )}
                    </button>
                  )}
                </span>
                <code>{it.id}</code>
                {editing === it.id ? (
                  <LineEditor initial={it.text} onSave={(t) => saveEdit(it.id, t)} onCancel={() => setEditing(null)} />
                ) : (
                  <>
                    <span className="txt">{it.text || <em>(no dialogue found — double-click to add text)</em>}</span>
                    <span className="tags">
                      {isEdited && <span className="tag">edited</span>}
                      {failed[it.id] && <span className="tag err">error</span>}
                      {done[it.id] && <span className="tag">saved</span>}
                      <button className="editbtn" disabled={locked || auto} onClick={(e) => { e.stopPropagation(); setEditing(it.id); }}>Edit</button>
                    </span>
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {item && (
        <div className="deck">
          <div className="now">
            <code>{item.id}</code>
            <p>{item.text || <em>(no text)</em>}</p>
            <small className={phase === "ready" ? "ok" : ""}>{auto ? "Auto-run · " : ""}{PHASE_LABEL[phase]}</small>
            {failed[item.id] && <small className="err">{failed[item.id]}</small>}
            {playErr && <small className="err">{playErr}</small>}
          </div>
          <div className="controls">
            {phase !== "ready" ? (
              <button className="btn primary" disabled={!ready || working || auto || !item.text.trim()} onClick={() => gen(item)}>Generate</button>
            ) : (
              <>
                <button className="btn primary" disabled={auto} onClick={keep}>Download &amp; next</button>
                <button className="btn" disabled={working || auto} onClick={() => gen(item)}>Regenerate</button>
              </>
            )}
            <button className="btn" disabled={working || auto} onClick={() => setEditing(item.id)}>Edit text</button>
            <button className="btn" disabled={working || auto} onClick={() => { setPhase("idle"); setCur(nextPending(cur)); }}>Skip</button>
            <span className="sep" />
            {!auto ? (
              <button className="btn" disabled={!ready || working} onClick={runAuto}>Auto-run from here</button>
            ) : (
              <button className="btn stop" onClick={() => { stopRef.current = true; }}>Stop after this line</button>
            )}
          </div>
        </div>
      )}
    </div>
  );

  const activityPage = (
    <div className="page">
      <div className="picker" style={{ display: "block", marginBottom: 14 }}>
        <label>Progress</label>
        <div className="progressbar"><i style={{ width: items.length ? `${(doneCount / items.length) * 100}%` : 0 }} /></div>
        <div className="progresstext"><span>{auto ? `Auto-running · ${item?.id ?? ""}` : PHASE_LABEL[phase]}</span><span>{doneCount} of {items.length}</span></div>
      </div>
      <div className="logpanel">
        <div className="loghead">
          <b>Activity log</b><span>{log.length}</span>
          <div className="logbtns">
            <button className="btn small" disabled={!log.length} onClick={() => navigator.clipboard?.writeText(log.map((l) => `${l.t}  ${l.msg}`).join("\n"))}>Copy</button>
            <button className="btn small" disabled={!log.length} onClick={() => setLog([])}>Clear</button>
          </div>
        </div>
        <div className="logbody">
          {log.length === 0 && <div className="logempty">Nothing yet.</div>}
          {log.map((l, i) => (
            <div key={i} className={`logline ${/fail|error|timed out/i.test(l.msg) ? "error" : /saved|connected|finished/i.test(l.msg) ? "ok" : ""}`}>
              {settings.timestamps && <time>{l.t}</time>}<span>{l.msg}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );

  const settingsPage = (
    <div className="page">
      <div className="settings">
        <div className="setgroup">
          <h3>Appearance</h3>
          <SetRow title="Theme" desc="Flat black-and-white. Dark is the default.">
            <Seg value={settings.theme} onChange={(v) => set({ theme: v })} options={[["dark", "Dark"], ["light", "Light"]]} />
          </SetRow>
          <SetRow title="Text size" desc="Size of the script lines and the current-line display.">
            <Seg value={settings.textSize} onChange={(v) => set({ textSize: v })} options={[["small", "Small"], ["medium", "Medium"], ["large", "Large"]]} />
          </SetRow>
          <SetRow title="Line spacing" desc="Compact fits more script lines on screen.">
            <Seg value={settings.density} onChange={(v) => set({ density: v })} options={[["comfortable", "Comfortable"], ["compact", "Compact"]]} />
          </SetRow>
          <SetRow title="Follow current line" desc="Automatically scroll the script so the current line stays in view.">
            <Toggle label="Follow current line" on={settings.scrollToCurrent} onChange={(v) => set({ scrollToCurrent: v })} />
          </SetRow>
        </div>

        <div className="setgroup">
          <h3>Automation</h3>
          <SetRow title="Delay between lines" desc="Auto-run waits a random time in this range after each line, so it doesn't hammer MiniMax.">
            <input type="number" min="0" step="100" value={settings.delayMin} onChange={(e) => set({ delayMin: Math.max(0, Number(e.target.value)) })} />
            <span>to</span>
            <input type="number" min="0" step="100" value={settings.delayMax} onChange={(e) => set({ delayMax: Math.max(0, Number(e.target.value)) })} />
            <span>ms</span>
          </SetRow>
          <SetRow title="Stop on error" desc="When off, auto-run skips a failed line and carries on with the next one.">
            <Toggle label="Stop on error" on={settings.stopOnError} onChange={(v) => set({ stopOnError: v })} />
          </SetRow>
          <SetRow title="Retries per line" desc="Extra attempts auto-run makes on a failed line before giving up.">
            <input type="number" min="0" max="5" value={settings.retries} onChange={(e) => set({ retries: Math.min(5, Math.max(0, Number(e.target.value))) })} />
          </SetRow>
          <SetRow title="Advance after download" desc="After “Download & next”, jump to the next line that isn't saved yet.">
            <Toggle label="Advance after download" on={settings.advanceAfterKeep} onChange={(v) => set({ advanceAfterKeep: v })} />
          </SetRow>
        </div>

        <div className="setgroup">
          <h3>Export</h3>
          <SetRow title="Subfolder per script heading" desc="On: each line is saved into a folder named after its heading in the script (e.g. W6-01, W6-02). Off: every file goes straight into the output folder.">
            <Toggle label="Subfolder per script heading" on={settings.organizeBySegment} onChange={(v) => set({ organizeBySegment: v })} />
          </SetRow>
          <SetRow title="Play buttons" desc="Show a Play button on every saved line so you can listen to the file.">
            <Toggle label="Play buttons" on={settings.showPreview} onChange={(v) => set({ showPreview: v })} />
          </SetRow>
          {settings.showPreview && (
            <SetRow title="Auto-play after Download & next" desc="Plays the clip as soon as it is saved. Never plays during auto-run.">
              <Toggle label="Auto-play preview" on={settings.autoPlayPreview} onChange={(v) => set({ autoPlayPreview: v })} />
            </SetRow>
          )}
          {settings.organizeBySegment && (
            <SetRow title="Folder name" desc={`Example: ${outDir ? outDir.split(/[\\/]/).pop() + "/" : ""}${folderFor((items[cur] || {}).segment || "W6-01 Warm up", settings.folderNaming) || "(no heading — saved in the output folder)"}/${items[cur]?.id || "W06-HEN-001"}.mp3`}>
              <Seg value={settings.folderNaming} onChange={(v) => set({ folderNaming: v })} options={[["code", "Code only"], ["full", "Full heading"]]} />
            </SetRow>
          )}
        </div>

        <div className="setgroup">
          <h3>Browser</h3>
          <SetRow title="Debugging port" desc="Chrome's remote-debugging port used by Open Chrome and Connect.">
            <input type="number" value={settings.port} onChange={(e) => set({ port: e.target.value })} />
          </SetRow>
          <SetRow title="MiniMax page" desc="The page that “Open Chrome” loads.">
            <input type="text" value={settings.chromeUrl} onChange={(e) => set({ chromeUrl: e.target.value })} />
          </SetRow>
        </div>

        <div className="setgroup">
          <h3>Script &amp; log</h3>
          <SetRow title="Text edits" desc={`${editedCount} line${editedCount === 1 ? "" : "s"} edited in the current script. Edits are remembered between sessions and only change what's sent to MiniMax, never your source file.`}>
            <button className="btn" disabled={!editedCount} onClick={resetAllEdits}>Reset all edits</button>
          </SetRow>
          <SetRow title="Export script as CSV" desc="One row per line: ID, heading, original text, current text, edited and saved flags.">
            <button className="btn" disabled={!items.length} onClick={exportCsv}>Export CSV</button>
          </SetRow>
          <SetRow title="Log timestamps"><Toggle label="Log timestamps" on={settings.timestamps} onChange={(v) => set({ timestamps: v })} /></SetRow>
          <SetRow title="Log length" desc="How many log lines are kept.">
            <input type="number" min="20" max="2000" step="20" value={settings.logLimit} onChange={(e) => set({ logLimit: Math.min(2000, Math.max(20, Number(e.target.value))) })} />
          </SetRow>
        </div>

        <div className="setgroup">
          <h3>Session</h3>
          <SetRow title="Restore last session on launch" desc="Reopens your script, output folder and the line you were on. Text edits are always remembered, whatever this is set to.">
            <Toggle label="Restore last session" on={settings.restoreSession} onChange={(v) => set({ restoreSession: v })} />
          </SetRow>
          <SetRow title="Autosave project file" desc="Keeps <project name>.tts-project.json in your output folder up to date as you work. Each project has its own file, so starting a new project never overwrites another one.">
            <Toggle label="Autosave project file" on={settings.autosaveProject} onChange={(v) => set({ autosaveProject: v })} />
          </SetRow>
          {settings.restoreSession && (
            <SetRow title="Reconnect to Chrome on launch" desc="Tries to reattach to Chrome on the debugging port. If Chrome isn't running yet, use Open Chrome, then Connect.">
              <Toggle label="Reconnect to Chrome" on={settings.autoReconnect} onChange={(v) => set({ autoReconnect: v })} />
            </SetRow>
          )}
          <SetRow title="Current session" desc={scriptPath ? `${scriptPath.split(/[\\/]/).pop()} · ${outDir || "no output folder chosen"}` : "Nothing loaded."}>
            <button className="btn" disabled={working || auto || (!scriptPath && !outDir)} onClick={clearSession}>Clear session</button>
          </SetRow>
        </div>

        <div className="setgroup">
          <h3>Reset</h3>
          <SetRow title="Restore default settings" desc="Does not touch your text edits.">
            <button className="btn" onClick={() => setSettings(DEFAULTS)}>Restore defaults</button>
          </SetRow>
        </div>
      </div>
    </div>
  );

  const NAV = [["setup", "Setup", "upload"], ["run", "Runner", "play"], ["activity", "Activity", "activity"]];

  return (
    <div className="app" data-theme={settings.theme} data-text={settings.textSize} data-density={settings.density}>
      <aside className="sidebar">
        <div className="brand">
          <div className="bug"><Icon name="mic" size={19} /></div>
          <div><b>MiniMax TTS</b><span>Runner</span></div>
        </div>
        <nav>
          {NAV.map(([id, label, icon]) => (
            <button key={id} className={`nav ${page === id ? "active" : ""}`} onClick={() => setPage(id)}>
              <Icon name={icon} />{label}
              {id === "run" && items.length > 0 && <em>{doneCount}/{items.length}</em>}
            </button>
          ))}
        </nav>
        <div className="sidebottom">
          <div className="projname">
            <label>Project</label>
            <input
              key={projectName || (scriptPath ? "s" + scriptPath : "none")}
              defaultValue={projectName}
              placeholder={scriptPath ? baseName() : "Untitled"}
              spellCheck={false}
              onBlur={(e) => setProjectName(e.target.value.trim())}
              onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }}
            />
          </div>
          <button disabled={working || auto} onClick={newProject}><Icon name="plus" />New project</button>
          <button disabled={!scriptPath} onClick={saveProject}><Icon name="save" />Save project</button>
          <button onClick={() => fileInputRef.current?.click()}><Icon name="folder" />Open project</button>
          <input ref={fileInputRef} type="file" accept=".json,application/json" hidden onChange={openProject} />
          {savedAt && <div className="savestate">{settings.autosaveProject && outDir ? "Autosaved" : "Saved"} {savedAt}</div>}
          <button className={page === "settings" ? "active" : ""} onClick={() => setPage("settings")}><Icon name="sliders" />Settings</button>
        </div>
      </aside>

      <div className="main">
        <header className="header">
          <div><h1>{TITLES[page][0]}</h1><p>{TITLES[page][1]}</p></div>
          <div className="status"><span className={`dot ${connected ? "on" : ""}`} />{connected ? "MiniMax connected" : "Not connected"}</div>
        </header>
        <div className="content" style={page === "run" ? { overflow: "hidden" } : undefined}>
          {page === "setup" && setupPage}
          {page === "run" && runPage}
          {page === "activity" && activityPage}
          {page === "settings" && settingsPage}
        </div>
      </div>
    </div>
  );
}