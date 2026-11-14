import { useRef, useState } from "react";
import Icon from "./components/Icon";
import { useAudio } from "./hooks/useAudio";
import { useGeneration } from "./hooks/useGeneration";
import { useLog } from "./hooks/useLog";
import { useProject } from "./hooks/useProject";
import { useScript } from "./hooks/useScript";
import { useSettings } from "./hooks/useSettings";
import ActivityPage from "./pages/ActivityPage";
import RunnerPage from "./pages/RunnerPage";
import SettingsPage from "./pages/SettingsPage";
import SetupPage from "./pages/SetupPage";

const NAV = [["setup", "Setup", "upload"], ["run", "Runner", "play"], ["activity", "Activity Log", "activity"]];

// App is only wiring: hooks own the state and logic, pages own the screens.
export default function App() {
  const [page, setPage] = useState("setup");
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

  const chooseScript = async () => { if (await script.chooseScript()) setSessionReady(true); };
  const chooseDir = async () => { if (await script.chooseDir()) setSessionReady(true); };

  return (
    <div className="app" data-theme={settings.theme} data-text={settings.textSize} data-density={settings.density}>
      <header className="topbar">
        <nav className="tbgroup" aria-label="Pages">
          {NAV.map(([id, label, icon]) => (
            <button key={id} className={`tb ${page === id ? "active" : ""}`} title={label} onClick={() => setPage(id)}>
              <Icon name={icon} /><span>{label}</span>
            </button>
          ))}
        </nav>
        <span style={{ flex: 1 }} />
        {page === "run" && script.items.length > 0 && (
          <button
            className="btn small"
            disabled={busy}
            title="Change the order of the script lines"
            onClick={() => set({ viewSort: byCharacter ? "scene" : "character" })}
          >Sort: {byCharacter ? "By character" : "By scene"}</button>
        )}
      </header>

      <div className="main">
        <div className="content" style={page === "run" ? { overflow: "hidden" } : undefined}>
          {page === "setup" && (
            <SetupPage
              script={script} settings={settings} set={set} setEngineCfg={setEngineCfg}
              ready={ready} busy={busy}
              onChooseScript={chooseScript} onChooseDir={chooseDir} onOpenRunner={() => setPage("run")}
            />
          )}
          {page === "run" && <RunnerPage script={script} gen={gen} audio={audio} settings={settings} ready={ready} rowRefs={rowRefs} />}
          {page === "activity" && <ActivityPage script={script} gen={gen} log={log} clearLog={clearLog} timestamps={settings.timestamps} />}
          {page === "settings" && (
            <SettingsPage
              settings={settings} set={set} resetSettings={resetSettings} script={script} busy={busy}
              baseName={project.baseName} say={say} onClearSession={project.clearSession}
            />
          )}
        </div>
      </div>

      <footer className="statusbar">
        <span className="sbname" title={project.projectFile || ""}>Project <b>{project.projectName || (script.scriptPath ? project.baseName() : "Untitled project")}</b></span>
        {script.scriptPath && !project.projectFile && <span>Not saved to a file yet — File › Save project</span>}
        <span className="sbspace" />
        {project.savedAt && <span>{settings.autosaveProject && project.projectFile ? "Autosaved" : "Saved"} {project.savedAt}</span>}
      </footer>
    </div>
  );
}
