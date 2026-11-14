import { useEffect, useRef, useState } from "react";
import { RECENT_KEY, SESSION_KEY } from "../lib/constants";
import { call } from "../lib/engines";
import { baseOf, nameFromPath, projectPathFor } from "../lib/paths";
import { loadJSON, saveJSON } from "../lib/storage";

const NEEDS_UPDATE = "update minimax_server.py to enable saving project files.";

/* Project file (.ttsrunner): save / open / recent / new, autosave, and restoring the last session on launch. */
export function useProject({ script, page, setPage, settingsRef, say, audio, busy, sessionReady, setSessionReady }) {
  const ownedRef = useRef("");
  const [projectFile, setProjectFile] = useState("");
  const [savedAt, setSavedAt] = useState(null);
  const [recent, setRecent] = useState(() => { try { return JSON.parse(localStorage.getItem(RECENT_KEY)) || []; } catch { return []; } });
  const autosaveWarned = useRef(false);
  const saveRef = useRef(() => {});
  const menuRef = useRef(() => {});

  const { scriptPath, outDir, items, cur, edits } = script;
  const setOwned = (p) => { ownedRef.current = p || ""; setProjectFile(p || ""); };
  const baseName = () => baseOf(scriptPath) || "script";
  const projectName = projectFile ? nameFromPath(projectFile) : "";

  useEffect(() => {
    saveJSON(RECENT_KEY, recent);
    window.api.setRecent?.(recent.map((r) => ({ name: r.name, path: r.path })));   // feeds File > Open Recent
  }, [recent]);

  // Skips the update when this project is already first in the list, so autosaves don't keep rebuilding the menu.
  const rememberProject = (name, path, sp = scriptPath) =>
    setRecent((r) => (r[0] && r[0].path === path && r[0].name === name
      ? r
      : [{ name, path, scriptPath: sp, savedAt: new Date().toISOString() }, ...r.filter((x) => x.path !== path)].slice(0, 12)));

  const projectJson = (name) => JSON.stringify({
    app: "minimax-tts-runner", version: 4, name, savedAt: new Date().toISOString(),
    scriptPath, outDir, curId: items[cur]?.id || "", page, edits,
  }, null, 2);

  // Writes the whole session to the project file. With no file yet (or saveAs) a Save dialog asks where it
  // should live. Autosave (silent) never opens a dialog.
  async function writeProject({ silent = false, saveAs = false } = {}) {
    let path = ownedRef.current;
    if (!path || saveAs) {
      if (silent) return false;
      if (!scriptPath && !path) { say("Load a script before saving a project."); return false; }
      const picked = await window.api.pickProjectSave(projectName || (scriptPath ? baseName() : "Untitled project"));
      if (!picked) return false;
      path = picked;
    }
    const name = nameFromPath(path);
    try {
      await call("write_text", { path, text: projectJson(name) });
      setOwned(path);
      setSavedAt(new Date().toLocaleTimeString());
      rememberProject(name, path);
      if (!silent) say(`Project "${name}" saved to ${path}`);
      return true;
    } catch (e) {
      const msg = /Unknown request type/.test(e.message) ? NEEDS_UPDATE : e.message;
      if (silent) {
        if (!autosaveWarned.current) { autosaveWarned.current = true; say(`Autosave failed: ${msg}`); }
      } else say(`Couldn't save project: ${msg}`);
      return false;
    }
  }
  saveRef.current = (asNew) => writeProject({ saveAs: !!asNew });

  /* ---------------------------------------------------------------- open / new */
  // Restores everything a project file holds. The project's edits replace the current ones.
  async function applyProject(proj, label, filePath) {
    if (proj.app !== "minimax-tts-runner") throw new Error("not a TTS Runner project file");
    audio.stopAudio();
    setSessionReady(false);
    const ed = proj.edits || {};
    const path = filePath || (proj.outDir ? projectPathFor(proj.outDir, proj.name || baseOf(proj.scriptPath)) : "");
    const name = path ? nameFromPath(path) : (proj.name || baseOf(proj.scriptPath));
    script.reset({ edits: ed, outDir: proj.outDir });
    setOwned(path);
    if (proj.scriptPath) await script.loadScript(proj.scriptPath, proj.curId, ed);
    setSessionReady(true);
    setSavedAt(null);
    setPage(proj.scriptPath && proj.page && proj.page !== "settings" && proj.page !== "setup" ? proj.page : "setup");
    say(`Opened project "${name}"${label ? ` (${label})` : ""} — session restored.`);
  }

  // File > Open project… (the native dialog sends the file's text and path).
  async function openProjectFile(m) {
    if (busy) return;
    try {
      const proj = JSON.parse(m.text);
      if (ownedRef.current && ownedRef.current !== m.path) await writeProject({ silent: true });
      await applyProject(proj, m.name, m.path);
    } catch (err) { say(`Open project failed: ${err.message}`); }
  }

  // File > Open Recent
  async function openRecent(r) {
    if (busy || !r) return;
    try {
      const x = await call("read_text", { path: r.path });
      if (!x.found) {
        setRecent((l) => l.filter((i) => i.path !== r.path));
        throw new Error("file no longer exists, removed from the recent list");
      }
      if (ownedRef.current && ownedRef.current !== r.path) await writeProject({ silent: true });
      await applyProject(JSON.parse(x.text), r.name, r.path);
    } catch (err) {
      say(`Open "${r.name}" failed: ${/Unknown request type/.test(err.message) ? "update minimax_server.py to open projects." : err.message}`);
    }
  }

  // File > New project: asks where to save the new project file, then starts with a clean workspace.
  async function newProject() {
    if (busy) return;
    if (scriptPath && !ownedRef.current && !window.confirm("The current project isn't saved to a file yet. Start a new project anyway?")) return;
    const picked = await window.api.pickProjectSave("Untitled project");
    if (!picked) return;
    if (ownedRef.current) await writeProject({ silent: true });   // save the project we're leaving
    const name = nameFromPath(picked);
    try {
      await call("write_text", {
        path: picked,
        text: JSON.stringify({ app: "minimax-tts-runner", version: 4, name, savedAt: new Date().toISOString(), scriptPath: "", outDir: "", curId: "", page: "setup", edits: {} }, null, 2),
      });
    } catch (e) {
      return say(`Couldn't create the project file: ${/Unknown request type/.test(e.message) ? NEEDS_UPDATE : e.message}`);
    }
    audio.stopAudio();
    script.reset({ edits: {} });
    setSavedAt(null);
    setPage("setup");
    setOwned(picked);
    rememberProject(name, picked, "");
    autosaveWarned.current = false;
    setSessionReady(true);
    say(`New project "${name}" created at ${picked}. Choose a script and an output folder.`);
  }

  function clearSession() {
    audio.stopAudio();
    try { localStorage.removeItem(SESSION_KEY); } catch { /* ignore */ }
    setSessionReady(false);
    script.reset();
    setOwned(""); setSavedAt(null);
    setPage("setup");
    say("Session cleared.");
  }

  /* ---------------------------------------------------------------- session restore + autosave */
  useEffect(() => {
    (async () => {
      const sess = loadJSON(SESSION_KEY, {});
      if (!settingsRef.current.restoreSession || !(sess.scriptPath || sess.outDir || sess.projectFile)) { setSessionReady(true); return; }
      try {
        if (sess.outDir) script.changeOutDir(sess.outDir);
        if (sess.scriptPath) await script.loadScript(sess.scriptPath, sess.curId);
        // Sessions saved before project files existed keep autosaving to their old file in the output folder.
        setOwned(sess.projectFile || (sess.outDir && sess.scriptPath ? projectPathFor(sess.outDir, sess.projectName || baseOf(sess.scriptPath)) : ""));
        if (sess.page && sess.scriptPath) setPage(sess.page);
        say("Restored your last session.");
        setSessionReady(true);
      } catch (e) {
        // leave the saved session untouched so a moved file or slow start doesn't wipe it
        say(`Couldn't restore last session: ${e.message}`);
      }
    })();
  }, []); // eslint-disable-line

  useEffect(() => {
    if (!sessionReady) return;
    saveJSON(SESSION_KEY, { scriptPath, outDir, curId: items[cur]?.id || "", page, projectFile });
  }, [sessionReady, scriptPath, outDir, cur, page, items.length, projectFile]); // eslint-disable-line

  useEffect(() => {
    if (!settingsRef.current.autosaveProject || !sessionReady || !projectFile || busy) return;
    const t = setTimeout(() => writeProject({ silent: true }), 2000);
    return () => clearTimeout(t);
  }, [sessionReady, projectFile, scriptPath, outDir, cur, page, edits, busy]); // eslint-disable-line

  // Ctrl+S / Ctrl+Shift+S
  useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); saveRef.current(e.shiftKey); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Commands from the native menu bar (electron/menu.cjs). menuRef always holds the latest closures.
  menuRef.current = (m) => {
    if (m.action === "new") newProject();
    else if (m.action === "open") openProjectFile(m);
    else if (m.action === "open-recent") openRecent(m.item);
    else if (m.action === "clear-recent") setRecent([]);
    else if (m.action === "save") writeProject();
    else if (m.action === "save-as") writeProject({ saveAs: true });
    else if (m.action === "settings") setPage("settings");
  };
  useEffect(() => window.api.onMenu?.((m) => menuRef.current(m)), []);

  return { projectFile, projectName, savedAt, baseName, clearSession };
}
