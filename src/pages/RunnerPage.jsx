import { useEffect, useRef, useState } from "react";
import Deck from "../components/Deck";
import GroupPanel from "../components/GroupPanel";
import ScriptLine from "../components/ScriptLine";
import TagMenu from "../components/TagMenu";

export default function RunnerPage({ script, gen, audio, settings, ready, rowRefs }) {
  const { items, item, cur, setCur, done, failed, takes, characters, editing, setEditing, outDir } = script;
  const [sel, setSel] = useState({});            // id -> true, multi-selection
  const anchorRef = useRef(null);
  const editorApi = useRef(null);                // the open LineEditor's insert/emotion functions

  const busy = gen.working || gen.auto;
  const byCharacter = settings.viewSort === "character";
  const editingCurrent = !!item && editing === item.id;
  const selIds = Object.keys(sel);
  const targetIds = selIds.length ? selIds : item ? [item.id] : [];
  const model = settings[settings.engine].model;

  useEffect(() => {
    if (settings.scrollToCurrent) rowRefs.current[cur]?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [cur]); // eslint-disable-line

  // click = select one, Shift+click = range, Ctrl/Cmd+click = toggle
  function selectLine(e, i, it) {
    if (busy || editing === it.id) return;
    if (e.shiftKey && anchorRef.current !== null) {
      const [a, b] = [anchorRef.current, i].sort((x, y) => x - y);
      const s = {}; for (let k = a; k <= b; k++) s[items[k].id] = true;
      setSel(s);
    } else if (e.ctrlKey || e.metaKey) {
      setSel((s) => {
        const n = Object.keys(s).length ? { ...s } : (item ? { [item.id]: true } : {});
        if (n[it.id]) delete n[it.id]; else n[it.id] = true;
        return n;
      });
      anchorRef.current = i;
    } else {
      setSel({});
      anchorRef.current = i;
    }
    setCur(i);
  }

  const tagMenu = (
    <TagMenu
      engine={settings.engine}
      model={model}
      item={item}
      items={items}
      targetIds={targetIds}
      selCount={selIds.length}
      onClearSel={() => setSel({})}
      editingCurrent={editingCurrent}
      editorApi={editorApi}
      bulkEdit={script.bulkEdit}
      disabled={busy}
    />
  );

  return (
    <div className="run">
      <div className="lines">
        {items.length === 0 && <div className="empty"><h2>No script loaded</h2><p>Go to Setup and choose a script to begin.</p></div>}

        {items.map((it, i) => {
          const prev = items[i - 1];
          const head = byCharacter ? it.character : it.segment;
          const prevHead = prev ? (byCharacter ? prev.character : prev.segment) : null;
          const isGroup = it.character === "GRP";
          const have = takes[it.id] || [];
          const cls = ["line", i === cur && "current", sel[it.id] && "selected", done[it.id] && "done", failed[it.id] && "failed", editing === it.id && "editing"].filter(Boolean).join(" ");

          return (
            <div key={it.id}>
              {(!prev || prevHead !== head) && head && <div className="seg">{head}</div>}

              <ScriptLine
                it={it}
                rowRef={(el) => (rowRefs.current[i] = el)}
                className={cls}
                showPreview={settings.showPreview}
                isDone={!!done[it.id]}
                playing={audio.playing === it.id}
                loading={audio.loadingId === it.id}
                busy={busy}
                auto={gen.auto}
                locked={busy && i === cur}
                isEditing={editing === it.id}
                editorApi={editorApi}
                failedMsg={failed[it.id]}
                voicesLabel={isGroup ? `Voices ${have.length}/${characters.length}${done[it.id] ? " · mixed" : ""}` : null}
                onClick={(e) => selectLine(e, i, it)}
                onPlay={() => gen.playLine(it)}
                onEdit={() => setEditing(it.id)}
                onSave={(t) => script.saveEdit(it.id, t)}
                onCancel={() => setEditing(null)}
                onToggleVoices={() => gen.setOpen((o) => ({ ...o, [it.id]: !o[it.id] }))}
              />

              {isGroup && gen.open[it.id] && (
                <GroupPanel
                  it={it}
                  characters={characters}
                  have={have}
                  takeKey={gen.takeKey}
                  phase={gen.phase}
                  working={gen.working}
                  auto={gen.auto}
                  ready={ready}
                  mixing={gen.mixingId === it.id}
                  isDone={!!done[it.id]}
                  showPreview={settings.showPreview}
                  playing={audio.playing}
                  onMake={(ch) => gen.makeTake(it, ch)}
                  onSaveTake={(ch) => gen.saveTake(it, ch)}
                  onPlayTake={(ch) => gen.playTake(it, ch)}
                  onPlayPending={gen.playPending}
                  onPlayMix={() => gen.playLine(it)}
                  onMix={() => gen.mixTakes(it)}
                />
              )}
            </div>
          );
        })}
      </div>

      {item && (
        <Deck
          item={item}
          phase={gen.phase}
          working={gen.working}
          auto={gen.auto}
          reviewing={gen.reviewing}
          ready={ready}
          outDir={outDir}
          failedMsg={failed[item.id]}
          playErr={audio.playErr}
          voicesOpen={!!gen.open[item.id]}
          tagMenu={tagMenu}
          onToggleVoices={() => gen.setOpen((o) => ({ ...o, [item.id]: !o[item.id] }))}
          onGenerate={() => gen.gen(item, undefined, true)}
          onKeep={gen.keep}
          onPlayPending={gen.playPending}
          onEdit={() => setEditing(item.id)}
          onSkip={gen.skip}
          onReview={gen.runReview}
          onStopReview={gen.stopReview}
          onAuto={gen.runAuto}
          onStopAuto={gen.stopAuto}
        />
      )}
    </div>
  );
}
