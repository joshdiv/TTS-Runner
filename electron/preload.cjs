const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("api", {
  engine: (type, payload) => ipcRenderer.invoke("engine", type, payload),
  pickScript: () => ipcRenderer.invoke("pick-script"),
  pickDir: () => ipcRenderer.invoke("pick-dir"),
  launchChrome: (port, url) => ipcRenderer.invoke("launch-chrome", port, url),
  onLog: (cb) => {
    const fn = (_e, text) => cb(text);
    ipcRenderer.on("engine-log", fn);
    return () => ipcRenderer.removeListener("engine-log", fn);
  },
});
