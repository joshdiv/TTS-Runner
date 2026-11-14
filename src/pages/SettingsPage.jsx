import { Seg, SetRow, Toggle } from "../components/ui";
import { exportCsv } from "../lib/export";
import { groupName, lastSegment } from "../lib/paths";

const Group = ({ title, children }) => (
  <div className="setgroup"><h3>{title}</h3>{children}</div>
);

export default function SettingsPage({ settings, set, resetSettings, script, busy, baseName, say, onClearSession }) {
  const { items, cur, outDir, scriptPath, editedCount, done } = script;
  const groupLabel = settings.folderBy === "character" ? "character" : "scene";

  const sample = items[cur] || { id: "ADD-W01-BIL-001", segment: "Scene 1", character: "BIL" };
  const folderExample = `Example: ${outDir ? lastSegment(outDir) + "/" : ""}${groupName(sample, settings.folderBy, settings.folderNaming) || "(no group — saved in the output folder)"}/${sample.id}.mp3`;

  const num = (key, { min = 0, max = Infinity } = {}) => (e) => set({ [key]: Math.min(max, Math.max(min, Number(e.target.value))) });

  return (
    <div className="page">
      <div className="settings">
        <Group title="Appearance">
          <SetRow title="Theme" desc="Flat black-and-white. Dark is the default.">
            <Seg value={settings.theme} onChange={(v) => set({ theme: v })} options={[["dark", "Dark"], ["light", "Light"], ["glass", "Glass"]]} />
          </SetRow>
          <SetRow title="Text size" desc="Size of the script lines and the current-line display.">
            <Seg value={settings.textSize} onChange={(v) => set({ textSize: v })} options={[["small", "Small"], ["medium", "Medium"], ["large", "Large"]]} />
          </SetRow>
          <SetRow title="Line spacing" desc="Compact fits more script lines on screen.">
            <Seg value={settings.density} onChange={(v) => set({ density: v })} options={[["comfortable", "Comfortable"], ["compact", "Compact"]]} />
          </SetRow>
          <SetRow title="Follow current line" desc="Automatically scroll the script so the current line stays in view.">
            <Toggle label="Follow current line" on={settings.scrollToCurrent} onChange={(v) => set({ scrollToCurrent: v })} />
          </SetRow>
        </Group>

        <Group title="Automation">
          <SetRow title="Delay between lines" desc="Auto-run waits a random time in this range after each line, so it stays under the API's rate limits.">
            <input type="number" min="0" step="100" value={settings.delayMin} onChange={num("delayMin")} />
            <span>to</span>
            <input type="number" min="0" step="100" value={settings.delayMax} onChange={num("delayMax")} />
            <span>ms</span>
          </SetRow>
          <SetRow title="Stop on error" desc="When off, auto-run skips a failed line and carries on with the next one.">
            <Toggle label="Stop on error" on={settings.stopOnError} onChange={(v) => set({ stopOnError: v })} />
          </SetRow>
          <SetRow title="Retries per line" desc="Extra attempts auto-run makes on a failed line before giving up.">
            <input type="number" min="0" max="5" value={settings.retries} onChange={num("retries", { max: 5 })} />
          </SetRow>
          <SetRow title="Gap between clips in Auto play" desc="Short pause between lines while you review, in milliseconds.">
            <input type="number" min="0" step="100" value={settings.playGap} onChange={num("playGap")} />
            <span>ms</span>
          </SetRow>
          <SetRow title="Advance after download" desc="After “Download & next”, jump to the next line that isn't saved yet.">
            <Toggle label="Advance after download" on={settings.advanceAfterKeep} onChange={(v) => set({ advanceAfterKeep: v })} />
          </SetRow>
        </Group>

        <Group title="Export">
          <SetRow title="Export grouping" desc="How audio subfolders and the CSV are organised: by scene (Scene 1, Scene 2…) or by character (BIL, REG…). The runner's own order is set with the Sort button at the top of the Runner.">
            <Seg value={settings.folderBy} onChange={(v) => set({ folderBy: v })} options={[["scene", "By scene"], ["character", "By character"]]} />
          </SetRow>
          <SetRow title="Delete voices after mixing" desc="Removes the per-character files from the GRP folder once the mixed line is saved.">
            <Toggle label="Delete voices after mixing" on={settings.clearTakesAfterMix} onChange={(v) => set({ clearTakesAfterMix: v })} />
          </SetRow>
          <SetRow title="Subfolder per group" desc={`On: each audio file is saved into a folder for its ${groupLabel}. Off: every file goes straight into the output folder.`}>
            <Toggle label="Subfolder per group" on={settings.organizeBySegment} onChange={(v) => set({ organizeBySegment: v })} />
          </SetRow>
          {settings.organizeBySegment && settings.folderBy === "scene" && (
            <SetRow title="Scene folder name" desc={folderExample}>
              <Seg value={settings.folderNaming} onChange={(v) => set({ folderNaming: v })} options={[["code", "Code only"], ["full", "Full heading"]]} />
            </SetRow>
          )}
          {settings.organizeBySegment && settings.folderBy === "character" && (
            <SetRow title="Character folder name" desc={folderExample}><span>Uses the character code from the ID.</span></SetRow>
          )}
          <SetRow title="Play buttons" desc="Show a Play button on every saved line so you can listen to the file.">
            <Toggle label="Play buttons" on={settings.showPreview} onChange={(v) => set({ showPreview: v })} />
          </SetRow>
          {settings.showPreview && (
            <SetRow title="Auto-play after Download & next" desc="Plays the clip as soon as it is saved. Never plays during auto-run.">
              <Toggle label="Auto-play preview" on={settings.autoPlayPreview} onChange={(v) => set({ autoPlayPreview: v })} />
            </SetRow>
          )}
        </Group>

        <Group title="Script & log">
          <SetRow title="Text edits" desc={`${editedCount} line${editedCount === 1 ? "" : "s"} edited in the current script (including emotion and sound tags). Edits are remembered between sessions and only change what's sent to the engine, never your source file.`}>
            <button className="btn" disabled={!editedCount} onClick={script.resetAllEdits}>Reset all edits</button>
          </SetRow>
          <SetRow title="Export script as CSV" desc={`One row per line: ID, scene, character, original text, current text, edited and saved flags. Sorted by ${groupLabel}.`}>
            <button className="btn" disabled={!items.length} onClick={() => exportCsv({ items, done, by: settings.folderBy, baseName: baseName(), say })}>Export CSV</button>
          </SetRow>
          <SetRow title="Log timestamps"><Toggle label="Log timestamps" on={settings.timestamps} onChange={(v) => set({ timestamps: v })} /></SetRow>
          <SetRow title="Log length" desc="How many log lines are kept.">
            <input type="number" min="20" max="2000" step="20" value={settings.logLimit} onChange={num("logLimit", { min: 20, max: 2000 })} />
          </SetRow>
        </Group>

        <Group title="Session">
          <SetRow title="Restore last session on launch" desc="Reopens your script, output folder and the line you were on. Text edits are always remembered, whatever this is set to.">
            <Toggle label="Restore last session" on={settings.restoreSession} onChange={(v) => set({ restoreSession: v })} />
          </SetRow>
          <SetRow title="Autosave project file" desc="Keeps your project file (.ttsrunner) up to date as you work. Use File › New project or Save project as… to choose where it lives.">
            <Toggle label="Autosave project file" on={settings.autosaveProject} onChange={(v) => set({ autosaveProject: v })} />
          </SetRow>
          <SetRow title="Current session" desc={scriptPath ? `${lastSegment(scriptPath)} · ${outDir || "no output folder chosen"}` : "Nothing loaded."}>
            <button className="btn" disabled={busy || (!scriptPath && !outDir)} onClick={onClearSession}>Clear session</button>
          </SetRow>
        </Group>

        <Group title="Reset">
          <SetRow title="Restore default settings" desc="Does not touch your text edits. API keys and voice choices are reset too.">
            <button className="btn" onClick={resetSettings}>Restore defaults</button>
          </SetRow>
        </Group>
      </div>
    </div>
  );
}
