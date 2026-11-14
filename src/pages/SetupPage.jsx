import Icon from "../components/Icon";
import EnginePanel from "../components/EnginePanel";
import ScriptSummary from "../components/ScriptSummary";
import { ENGINES } from "../lib/constants";
import { lastSegment } from "../lib/paths";

const Picker = ({ icon, title, sub, children }) => (
  <div className="picker">
    <div className="pickericon"><Icon name={icon} /></div>
    <div className="grow"><strong>{title}</strong>{sub && <small>{sub}</small>}</div>
    {children}
  </div>
);

export default function SetupPage({ script, settings, set, setEngineCfg, ready, busy, onChooseScript, onChooseDir, onOpenRunner }) {
  const { scriptPath, outDir, items, scanning, characters } = script;
  const engine = settings.engine;

  return (
    <div className="page">
      <div className="setupgrid">
        <div className="setupleft">
          <Picker icon="file" title={scriptPath ? "Script" : "No script chosen"} sub={lastSegment(scriptPath)}>
            <button className="btn" onClick={onChooseScript}>{scriptPath ? "Change" : "Choose script"}</button>
          </Picker>

          <Picker icon="folder" title="Output folder" sub={outDir}>
            <div className="btnrow">
              <button
                className="btn"
                onClick={script.scanFolder}
                disabled={!outDir || !items.length || scanning || busy}
                title="Match files in the output folder to the script and mark them as saved"
              >{scanning ? "Scanning…" : "Scan folder"}</button>
              <button className="btn" onClick={onChooseDir}>{outDir ? "Change" : "Choose folder"}</button>
            </div>
          </Picker>

          <Picker icon="globe" title="Text to Speech Engine">
            <div className="btnrow">
              <select className="enginesel" aria-label="TTS engine" value={engine} onChange={(e) => set({ engine: e.target.value })}>
                {ENGINES.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
              </select>
            </div>
          </Picker>

          <EnginePanel engine={engine} cfg={settings[engine]} onChange={(patch) => setEngineCfg(engine, patch)} characters={characters} />
        </div>

        <aside className="setupright">
          <ScriptSummary
            items={items}
            analysis={script.analysis}
            characters={characters}
            scriptPath={scriptPath}
            fileName={lastSegment(scriptPath)}
            doneCount={script.doneCount}
            ready={ready}
            onOpenRunner={onOpenRunner}
          />
        </aside>
      </div>
    </div>
  );
}
