const { Menu, dialog, app } = require("electron");
const fs = require("fs");
const path = require("path");

// getWin: () => your BrowserWindow
// recent: [{ name, path }] sent by the app, newest first (File > Open Recent)
function buildMenu(getWin, recent = []) {
  const send = (msg) => getWin()?.webContents.send("menu", msg);

  async function openProject() {
    const r = await dialog.showOpenDialog(getWin(), {
      title: "Open project",
      properties: ["openFile"],
      filters: [
        { name: "TTS Runner project", extensions: ["ttsrunner", "json"] },
        { name: "All files", extensions: ["*"] },
      ],
    });
    if (r.canceled || !r.filePaths[0]) return;
    try {
      const file = r.filePaths[0];
      send({ action: "open", name: path.basename(file), path: file, text: fs.readFileSync(file, "utf8") });
    } catch (e) {
      dialog.showErrorBox("Couldn't open project", e.message);
    }
  }

  const esc = (s) => String(s).replace(/&/g, "&&");   // "&" is a mnemonic marker in Windows menus

  const recentItems = recent.length
    ? [
        ...recent.map((r) => ({ label: esc(r.name), click: () => send({ action: "open-recent", item: r }) })),
        { type: "separator" },
        { label: "Clear recent projects", click: () => send({ action: "clear-recent" }) },
      ]
    : [{ label: "No recent projects", enabled: false }];

  return Menu.buildFromTemplate([
    {
      label: "File",
      submenu: [
        { label: "New project…", click: () => send({ action: "new" }) },
        { label: "Open project…", click: openProject },
        { label: "Open Recent", submenu: recentItems },
        { type: "separator" },
        // registerAccelerator:false = shows the shortcut, the app's own key handler does the work (no double save)
        { label: "Save project", accelerator: "CmdOrCtrl+S", registerAccelerator: false, click: () => send({ action: "save" }) },
        { label: "Save project as…", accelerator: "CmdOrCtrl+Shift+S", registerAccelerator: false, click: () => send({ action: "save-as" }) },
        { type: "separator" },
        { label: "Settings", click: () => send({ action: "settings" }) },
        { type: "separator" },
        { role: "quit", label: "Exit" },
      ],
    },
    {
      label: "Edit",
      submenu: [
        { role: "undo" }, { role: "redo" }, { type: "separator" },
        { role: "cut" }, { role: "copy" }, { role: "paste" }, { role: "selectAll" },
      ],
    },
    {
      label: "View",
      submenu: [
        { role: "reload" }, { role: "forceReload" }, { role: "toggleDevTools" }, { type: "separator" },
        { role: "resetZoom" }, { role: "zoomIn" }, { role: "zoomOut" }, { type: "separator" },
        { role: "togglefullscreen" },
      ],
    },
    { label: "Window", submenu: [{ role: "minimize" }, { role: "close" }] },
    {
      label: "Help",
      submenu: [
        {
          label: "About TTS Runner",
          click: () => dialog.showMessageBox(getWin(), { type: "info", title: "TTS Runner", message: "TTS Runner", detail: `Version ${app.getVersion()}` }),
        },
      ],
    },
  ]);
}

module.exports = { buildMenu };
