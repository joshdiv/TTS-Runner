const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("api", {
  engine: (type, payload) => ipcRenderer.invoke("engine", type, payload),
  pickScript: () => ipcRenderer.invoke("pick-script"),
  pickDir: () => ipcRenderer.invoke("pick-dir"),
  pickProjectSave: (name) => ipcRenderer.invoke("pick-project-save", name),
  setRecent: (list) => ipcRenderer.send("recent", list),
  launchChrome: (port, url) => ipcRenderer.invoke("launch-chrome", port, url),
  onLog: (cb) => {
    const fn = (_e, text) => cb(text);
    ipcRenderer.on("engine-log", fn);
    return () => ipcRenderer.removeListener("engine-log", fn);
  },
  onMenu: (cb) => {
    const h = (_e, m) => cb(m);
    ipcRenderer.on("menu", h);
    return () => ipcRenderer.removeListener("menu", h);
  },
});
