const { app, BrowserWindow, ipcMain, dialog } = require("electron");
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

// ---------- Window ----------
function createWindow() {
  win = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 980,
    backgroundColor: "#e8ecf0",
    webPreferences: { preload: path.join(__dirname, "preload.cjs"), contextIsolation: true },
  });
  win.setMenuBarVisibility(false);
  if (app.isPackaged) win.loadFile(path.join(__dirname, "..", "dist", "index.html"));
  else if (process.argv.includes("--built")) win.loadFile(path.join(__dirname, "..", "dist", "index.html"));
  else win.loadURL("http://localhost:5173");
}

app.whenReady().then(() => { startPython(); createWindow(); });
app.on("window-all-closed", () => { if (py) py.kill(); app.quit(); });
