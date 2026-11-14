const { app, BrowserWindow, ipcMain, dialog, Menu } = require("electron");
const { spawn } = require("child_process");
const readline = require("readline");
const path = require("path");
const fs = require("fs");
const { buildMenu } = require("./menu.cjs");

let win = null;
let py = null;
let nextId = 1;
const pending = new Map();

// ---------- Python bridge (one JSON object per line, same protocol as your server.py) ----------
function startPython() {
  const cmd = process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");
  const script = path.join(__dirname, "..", "python", "minimax_server.py");
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

ipcMain.handle("engine", (_e, type, payload) => request(type, payload));

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

// File > Open Recent is rebuilt whenever the app reports a new recent list
let recentList = [];
ipcMain.on("recent", (_e, list) => {
  recentList = Array.isArray(list) ? list.slice(0, 12) : [];
  Menu.setApplicationMenu(buildMenu(() => win, recentList));
});

// ---------- Window ----------
function createWindow() {
  const iconPath = path.join(__dirname, "icon.ico");   // put your icon at electron/icon.ico

  win = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 980,
    title: "TTS Runner",
    ...(fs.existsSync(iconPath) ? { icon: iconPath } : {}),
    backgroundColor: "#0a0a0b",
    webPreferences: { preload: path.join(__dirname, "preload.cjs"), contextIsolation: true },
  });

  if (app.isPackaged) win.loadFile(path.join(__dirname, "..", "dist", "index.html"));
  else if (process.argv.includes("--built")) win.loadFile(path.join(__dirname, "..", "dist", "index.html"));
  else win.loadURL("http://localhost:5173");
}

app.whenReady().then(() => {
  startPython();
  Menu.setApplicationMenu(buildMenu(() => win, recentList));
  createWindow();
});

app.on("window-all-closed", () => { if (py) py.kill(); app.quit(); });
