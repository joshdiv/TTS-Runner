import { useRef, useState } from "react";
import { Sidebar, SidebarTop, WindowControls } from "./components/Sidebar";
import { useAudio } from "./hooks/useAudio";
import { useGeneration } from "./hooks/useGeneration";
import { useLog } from "./hooks/useLog";
import { useProject } from "./hooks/useProject";
import { useScript } from "./hooks/useScript";
import { useSettings } from "./hooks/useSettings";
import RunnerPage from "./pages/RunnerPage";
import SettingsPage from "./pages/SettingsPage";
import SetupPage from "./pages/SetupPage";

// Replaces the old File menu: same message shapes, delivered to useProject through api.onMenu
const menu = (action) => () => window.api.emitMenu({ action });

// App is only wiring: hooks own the state and logic, pages own the screens.
export default function App() {
  const [page, setPage] = useState("setup");
  const [collapsed, setCollapsed] = useState(false);        // sidebar hidden
  const [phase, setPhase] = useState("idle");               // idle | generating | ready | downloading
  const [sessionReady, setSessionReady] = useState(false);  // false until restore has finished (or the user picks something)
  const rowRefs = useRef({});
  const busyRef = useRef(false);

  const { settings, settingsRef, set, setEngineCfg, resetSettings } = useSettings();
  const { log, say, clearLog } = useLog(settingsRef);
  const audio = useAudio();
  const script = useScript({ settings, settingsRef, say, phase, setPhase, busyRef });
  const gen = useGeneration({ script, settingsRef, audio, say, phase, setPhase, rowRefs });
  const busy = gen.working || gen.auto;
  busyRef.current = busy;
  const project = useProject({ script, page, setPage, settingsRef, say, audio, busy, sessionReady, setSessionReady });

  const ready = script.items.length > 0 && !!script.outDir;
  const byCharacter = settings.viewSort === "character";
  const onRun = page === "run";

  const chooseScript = async () => { if (await script.chooseScript()) setSessionReady(true); };
  const chooseDir = async () => { if (await script.chooseDir()) setSessionReady(true); };

  // File > Open project…
  const openProject = async () => {
    const r = await window.api.pickProjectOpen();
    if (!r) return;
    if (!r.ok) return say(`Couldn't open project: ${r.error}`);
    window.api.emitMenu({ action: "open", ...r.result });   // { name, path, text }
  };

  // shared by the sidebar's top row and the window bar's copy of it (shown while the sidebar is hidden)
  const topProps = {
    onToggle: () => setCollapsed((c) => !c),
    onOpen: openProject,
    onSaveAs: menu("save-as"),
    onSettings: () => setPage("settings"),
  };

  return (
    <div className={`app${collapsed ? " collapsed" : ""}`} data-theme={settings.theme} data-text={settings.textSize} data-density={settings.density}>
      <Sidebar
        page={page}
        setPage={setPage}
        onNew={menu("new")}
        onOpenRecent={(item) => window.api.emitMenu({ action: "open-recent", item })}
        currentPath={project.projectFile}
        {...topProps}
        disabled={busy}
      />

      <div className="main">
        <header className="winbar">
          {collapsed && <div className="winbar-left"><SidebarTop {...topProps} disabled={busy} /></div>}
          <WindowControls />
        </header>

        <div className="content" style={onRun ? { overflow: "hidden", display: "flex", flexDirection: "column" } : undefined}>
          {onRun && script.items.length > 0 && (
            <div className="runbar">
              <button
                className="btn small"
                disabled={busy}
                title="Change the order of the script lines"
                onClick={() => set({ viewSort: byCharacter ? "scene" : "character" })}
              >Sort: {byCharacter ? "By character" : "By scene"}</button>
            </div>
          )}

          {page === "setup" && (
            <SetupPage
              script={script} settings={settings} set={set} setEngineCfg={setEngineCfg}
              ready={ready} busy={busy}
              log={log} clearLog={clearLog}
              onChooseScript={chooseScript} onChooseDir={chooseDir} onOpenRunner={() => setPage("run")}
            />
          )}
          {onRun && (
            <div style={{ flex: 1, minHeight: 0 }}>
              <RunnerPage script={script} gen={gen} audio={audio} settings={settings} ready={ready} rowRefs={rowRefs} />
            </div>
          )}
          {page === "settings" && (
            <SettingsPage
              settings={settings} set={set} resetSettings={resetSettings} script={script} busy={busy}
              baseName={project.baseName} say={say} onClearSession={project.clearSession}
            />
          )}
        </div>
      </div>
    </div>
  );
}