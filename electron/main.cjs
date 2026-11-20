const { app, BrowserWindow, ipcMain, dialog, Menu } = require("electron");
const { spawn } = require("child_process");
const readline = require("readline");
const path = require("path");
const fs = require("fs");

let win = null;
let py = null;
let nextId = 1;
const pending = new Map();

// ---------- Python bridge (one JSON object per line, same protocol as your server.py) ----------
function startPython() {
  const cmd = process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");
  const script = path.join(__dirname, "..", "python", "tts_server.py");
  py = spawn(cmd, ["-u", script], { stdio: ["pipe", "pipe", "pipe"] });

  readline.createInterface({ input: py.stdout }).on("line", (line) => {
    let msg;
    try { msg = JSON.parse(line); } catch { return; }
    const p = pending.get(msg.id);
    if (!p) return;
    pending.delete(msg.id);
    p.resolve(msg.ok ? { ok: true, result: msg.result } : { ok: false, error: msg.error });
  });
  py.stderr.on("data", (d) => win && win.webContents.send("engine-log", d.toString()));
  py.on("error", (err) => failAll(`Could not start Python (${cmd}): ${err.message}`));
  py.on("exit", (code) => { failAll(`Python engine exited (code ${code})`); py = null; });
}

function failAll(error) {
  for (const p of pending.values()) p.resolve({ ok: false, error });
  pending.clear();
}

function request(type, payload) {
  return new Promise((resolve) => {
    if (!py) startPython();
    const id = nextId++;
    pending.set(id, { resolve });
    py.stdin.write(JSON.stringify({ id, type, payload: payload || {} }) + "\n");
  });
}

// ---------- Chrome launcher (separate profile so your MiniMax login is remembered) ----------
function findChrome() {
  const c = [];
  if (process.platform === "win32") {
    for (const base of [process.env.PROGRAMFILES, process.env["PROGRAMFILES(X86)"], process.env.LOCALAPPDATA])
      if (base) c.push(path.join(base, "Google", "Chrome", "Application", "chrome.exe"));
    for (const base of [process.env.PROGRAMFILES, process.env["PROGRAMFILES(X86)"]])
      if (base) c.push(path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"));
  } else if (process.platform === "darwin") {
    c.push("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome");
  } else {
    c.push("/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium", "/usr/bin/chromium-browser");
  }
  return c.find((p) => fs.existsSync(p));
}

ipcMain.handle("launch-chrome", (_e, port, url) => {
  const exe = findChrome();
  if (!exe) return { ok: false, error: "Chrome/Edge not found. Start it yourself with --remote-debugging-port=" + port };
  const profile = path.join(app.getPath("userData"), "chrome-profile");
  const child = spawn(exe, [
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profile}`,
    "--no-first-run",
    url,
  ], { detached: true, stdio: "ignore" });
  child.unref();
  return { ok: true, result: { exe, profile } };
});

// ---------- ID rules: characters + their ID formats, stored as JSON in the app's data folder ----------
// Seeded once from electron/default-id-rules.json, then edited from the Customize dialog.
const rulesFile = () => path.join(app.getPath("userData"), "id-rules.json");
const defaultRulesFile = path.join(__dirname, "default-id-rules.json");

function saveRules(data) {
  const file = rulesFile();
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const tmp = file + ".tmp";                       // write to a temp file first so a crash can't leave half a file
  fs.writeFileSync(tmp, JSON.stringify(data, null, 2), "utf8");
  fs.renameSync(tmp, file);
}

function loadRules() {
  const file = rulesFile();
  if (!fs.existsSync(file)) {                      // first run: copy the defaults
    let seed = { version: 1, characters: [] };
    try { seed = JSON.parse(fs.readFileSync(defaultRulesFile, "utf8")); } catch { /* no defaults shipped */ }
    saveRules(seed);
    return seed;
  }
  try { return JSON.parse(fs.readFileSync(file, "utf8")); }
  catch { return { version: 1, characters: [] }; } // unreadable file: don't overwrite it, just report nothing
}

ipcMain.handle("rules:load", () => loadRules());
ipcMain.handle("rules:save", (_e, data) => { saveRules(data); return true; });
ipcMain.handle("rules:path", () => rulesFile());

// The script reader always gets the current rules, and the characters omitted for that script
// (saved under "ignored" in id-rules.json, keyed by script path), so the renderer never has to pass them.
ipcMain.handle("engine", (_e, type, payload) => {
  if (type !== "load_script") return request(type, payload);
  const data = loadRules();
  return request(type, { ...payload, rules: data.characters || [], ignored: (data.ignored || {})[payload.path] || [] });
});

// ---------- File pickers ----------
ipcMain.handle("pick-script", async () => {
  const r = await dialog.showOpenDialog(win, {
    properties: ["openFile"],
    filters: [{ name: "Recording script", extensions: ["pdf", "docx"] }],
  });
  return r.canceled ? null : r.filePaths[0];
});

ipcMain.handle("pick-dir", async () => {
  const r = await dialog.showOpenDialog(win, { properties: ["openDirectory", "createDirectory"] });
  return r.canceled ? null : r.filePaths[0];
});

// Project files: a Save dialog that always ends in .ttsrunner (the content is JSON)
ipcMain.handle("pick-project-save", async (_e, name) => {
  const base = String(name || "Untitled project").replace(/[<>:"/\\|?*\x00-\x1f]/g, "_");
  const r = await dialog.showSaveDialog(win, {
    title: "Save project as",
    defaultPath: path.join(app.getPath("documents"), `${base}.ttsrunner`),
    filters: [{ name: "TTS Runner project", extensions: ["ttsrunner"] }],
  });
  if (r.canceled || !r.filePath) return null;
  return /\.ttsrunner$/i.test(r.filePath) ? r.filePath : r.filePath + ".ttsrunner";
});

// NEW: replaces File > Open project… (was in menu.cjs). Returns the same shape the menu used to send.
ipcMain.handle("pick-project-open", async () => {
  const r = await dialog.showOpenDialog(win, {
    title: "Open project",
    properties: ["openFile"],
    filters: [
      { name: "TTS Runner project", extensions: ["ttsrunner", "json"] },
      { name: "All files", extensions: ["*"] },
    ],
  });
  if (r.canceled || !r.filePaths[0]) return null;
  try {
    const file = r.filePaths[0];
    return { ok: true, result: { name: path.basename(file), path: file, text: fs.readFileSync(file, "utf8") } };
  } catch (e) {
    return { ok: false, error: e.message };
  }
});

// The recent list now lives in the app UI, so there is no native menu to rebuild.
// Kept as a no-op so existing `api.setRecent(...)` calls don't break.
ipcMain.on("recent", () => {});

// ---------- Window controls (the renderer draws the buttons) ----------
ipcMain.on("win:minimize", () => win?.minimize());
ipcMain.on("win:toggle-maximize", () => {
  if (!win) return;
  win.isMaximized() ? win.unmaximize() : win.maximize();
});
ipcMain.on("win:close", () => win?.close());
ipcMain.handle("win:is-maximized", () => !!win?.isMaximized());

// ---------- Window ----------
function createWindow() {
  const iconPath = path.join(__dirname, "icon.ico");   // put your icon at electron/icon.ico

  win = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 980,
    title: "TTS Runner",
    frame: false,                      // no native title bar / window buttons
    ...(fs.existsSync(iconPath) ? { icon: iconPath } : {}),
    backgroundColor: "#0a0a0b",
    webPreferences: { preload: path.join(__dirname, "preload.cjs"), contextIsolation: true },
  });

  // Tell the renderer when maximize state changes so the button icon can swap
  const sendState = () => win?.webContents.send("win-state", { maximized: win.isMaximized() });
  win.on("maximize", sendState);
  win.on("unmaximize", sendState);

  // With the menu gone we lose the built-in dev shortcuts. Keep them in dev builds only.
  if (!app.isPackaged) {
    win.webContents.on("before-input-event", (e, input) => {
      if (input.type !== "keyDown") return;
      const ctrl = input.control || input.meta;
      if (input.key === "F12" || (ctrl && input.shift && input.key.toLowerCase() === "i")) {
        win.webContents.toggleDevTools();
        e.preventDefault();
      } else if (ctrl && input.key.toLowerCase() === "r") {
        win.webContents.reload();
        e.preventDefault();
      }
    });
  }

  if (app.isPackaged) win.loadFile(path.join(__dirname, "..", "dist", "index.html"));
  else if (process.argv.includes("--built")) win.loadFile(path.join(__dirname, "..", "dist", "index.html"));
  else win.loadURL("http://localhost:5173");
}

app.whenReady().then(() => {
  startPython();
  Menu.setApplicationMenu(null);       // removes File / Edit / View / Window / Help
  createWindow();
});

app.on("window-all-closed", () => { if (py) py.kill(); app.quit(); });