const { contextBridge, ipcRenderer } = require("electron");

// Subscribe helper: returns an unsubscribe function
const listen = (channel, cb) => {
  const fn = (_e, data) => cb(data);
  ipcRenderer.on(channel, fn);
  return () => ipcRenderer.removeListener(channel, fn);
};

// The native menu is gone, but useProject still listens through api.onMenu.
// Sidebar buttons feed the same listeners through api.emitMenu, so useProject needs no changes.
const menuListeners = new Set();

// Recent projects: useProject already calls api.setRecent(list) whenever it changes.
// We keep the latest list here and let the sidebar subscribe to it.
let recent = [];
const recentListeners = new Set();

contextBridge.exposeInMainWorld("api", {
  // engine + files
  engine: (type, payload) => ipcRenderer.invoke("engine", type, payload),
  pickScript: () => ipcRenderer.invoke("pick-script"),
  pickDir: () => ipcRenderer.invoke("pick-dir"),
  pickProjectSave: (name) => ipcRenderer.invoke("pick-project-save", name),
  pickProjectOpen: () => ipcRenderer.invoke("pick-project-open"),
  setRecent: (list) => {
    recent = Array.isArray(list) ? list : [];
    recentListeners.forEach((cb) => cb(recent));
  },
  projectChanged: () => ipcRenderer.send("project:changed"),
  onRecent: (cb) => {            // cb([{ name, path }, ...]) is called now and on every change
    recentListeners.add(cb);
    cb(recent);
    return () => recentListeners.delete(cb);
  },
  onLog: (cb) => listen("engine-log", cb),

  // menu actions: { action: "new" | "open" | "save" | "save-as" | "settings" | ... }
  onMenu: (cb) => {
    menuListeners.add(cb);
    return () => menuListeners.delete(cb);
  },
  emitMenu: (msg) => menuListeners.forEach((cb) => cb(msg)),

  // ID rules (characters + formats), stored as id-rules.json
  rules: {
    load: () => ipcRenderer.invoke("rules:load"),
    save: (data) => ipcRenderer.invoke("rules:save", data),
    path: () => ipcRenderer.invoke("rules:path"),
  },

  // window controls
  win: {
    minimize: () => ipcRenderer.send("win:minimize"),
    toggleMaximize: () => ipcRenderer.send("win:toggle-maximize"),
    close: () => ipcRenderer.send("win:close"),
    isMaximized: () => ipcRenderer.invoke("win:is-maximized"),
    onState: (cb) => listen("win-state", cb),   // cb({ maximized })
  },
});