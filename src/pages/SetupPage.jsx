import { useRef, useState } from "react";
import CustomizePanel from "../components/CustomizePanel";
import EnginePanel from "../components/EnginePanel";
import LogPanel from "../components/LogPanel";
import Modal from "../components/Modal";
import ScriptSummary from "../components/ScriptSummary";
import { ENGINES } from "../lib/constants";
import { lastSegment } from "../lib/paths";
import logo from "../assets/ttsrunner-icon.png";

const GearIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.6 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
  </svg>
);

/* One small card: uppercase title, italic hint, buttons underneath */
const Tile = ({ area, title, sub, children }) => (
  <section className={`tile ${area}`}>
    <h3>{title}</h3>
    {sub && <p title={sub}>{sub}</p>}
    <div className="tilebtns">{children}</div>
  </section>
);

/*  Layout (wide):   [ script ] [ output ] [      ]
                     [ engine ] [ ids    ] [ log  ]
                     [     summary       ] [      ]       */
export default function SetupPage({
  script, settings, set, setEngineCfg, ready, busy,
  log, clearLog,
  onChooseScript, onChooseDir, onOpenRunner,
}) {
  const { scriptPath, outDir, items, scanning, characters } = script;
  const engine = settings.engine;
  const engineLabel = ENGINES.find(([v]) => v === engine)?.[1] ?? engine;

  const [dialog, setDialog] = useState(null);      // null | "engine" | "customize"
  const rulesChanged = useRef(false);
  const close = () => {
    // new ID rules only apply when the script is read again, so do that once, when the dialog closes
    if (dialog === "customize" && rulesChanged.current) {
      rulesChanged.current = false;
      script.reloadScript?.();
    }
    setDialog(null);
  };

  return (
    <div className="page setup">
      <img className="setuplogo" src={logo} alt="TTS Runner" draggable="false" />

      <div className="setboard">
        <Tile area="t-script" title={scriptPath ? "Script loaded" : "No script chosen"} sub={scriptPath ? lastSegment(scriptPath) : "Choose a .docx or .pdf script"}>
          <button className="btn primary small" onClick={onChooseScript}>{scriptPath ? "Change" : "Choose script"}</button>
        </Tile>

        <Tile area="t-output" title="Output folder" sub={outDir || "Where generated audio files are saved"}>
          <button
            className="btn primary small"
            onClick={script.scanFolder}
            disabled={!outDir || !items.length || scanning || busy}
            title="Match files in the output folder to the script and mark them as saved"
          >{scanning ? "Scanning…" : "Scan folder"}</button>
          <button className="btn primary small" onClick={onChooseDir}>{outDir ? "Change" : "Select output folder"}</button>
        </Tile>

        <Tile area="t-engine" title="TTS engine" sub="Choose your voice provider">
          <select aria-label="TTS engine" value={engine} onChange={(e) => set({ engine: e.target.value })}>
            {ENGINES.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
          </select>
          <button className="btn primary small gearbtn" onClick={() => setDialog("engine")} aria-label={`${engineLabel} settings`} title={`${engineLabel} settings`}>
            <GearIcon />
          </button>
        </Tile>

        <Tile area="t-ids" title="ID formats & characters" sub="Teach the app how your line IDs look">
          <button className="btn primary small" onClick={() => setDialog("customize")}>Customize</button>
        </Tile>

        <div className="area-summary">
          <ScriptSummary
            items={items}
            analysis={script.analysis}
            characters={characters}
            scriptPath={scriptPath}
            fileName={lastSegment(scriptPath)}
            doneCount={script.doneCount}
            roster={script.roster}
            ready={ready}
            busy={busy}
            onOpenRunner={onOpenRunner}
            onOmit={(codes) => script.setOmitted(codes, true)}
            onRestore={(codes) => script.setOmitted(codes, false)}
          />
        </div>

        <div className="area-log">
          <LogPanel log={log} clearLog={clearLog} timestamps={settings.timestamps} />
        </div>
      </div>

      {dialog === "engine" && (
        <Modal title={`${engineLabel} settings`} onClose={close}>
          <EnginePanel engine={engine} cfg={settings[engine]} onChange={(patch) => setEngineCfg(engine, patch)} characters={characters} />
        </Modal>
      )}

      {dialog === "customize" && (
        <Modal title="Customize characters & IDs" wide onClose={close}>
          <CustomizePanel onChange={() => { rulesChanged.current = true; }} />
        </Modal>
      )}
    </div>
  );
}