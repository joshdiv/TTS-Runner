import { PHASE_LABEL } from "../lib/constants";
import { isBracket } from "../lib/tags";

// Voices panel under a group (GRP) line: one take per character, then Mix.
export default function GroupPanel({
  it, characters, have, takeKey, phase, working, auto, ready, mixing, isDone, showPreview, playing,
  onMake, onSaveTake, onPlayTake, onPlayPending, onPlayMix, onMix,
}) {
  return (
    <div className="grppanel">
      {characters.map((ch) => {
        const has = have.includes(ch);
        const mine = takeKey === `${it.id}|${ch}`;
        const pending = mine && phase === "ready";
        const busyMine = mine && working;
        const blocked = phase === "ready" && !pending;
        return (
          <div key={ch} className="grprow">
            <code>{ch}</code>
            <span className="grpstat">{busyMine ? PHASE_LABEL[phase] : pending ? "generated, not saved" : has ? "saved" : "not recorded"}</span>
            <span className="grpacts">
              {has && !pending && showPreview && (
                <button className="btn small" disabled={working || auto} onClick={() => onPlayTake(ch)}>
                  {playing === `${it.id}__${ch}` ? "Stop" : "Play"}
                </button>
              )}
              {pending ? (
                <>
                  <button className="btn small" onClick={onPlayPending}>Play</button>
                  <button className="btn small" disabled={working || auto} onClick={() => onMake(ch)}>Regenerate</button>
                  <button className="btn small primary" disabled={auto} onClick={() => onSaveTake(ch)}>Save</button>
                </>
              ) : (
                <button
                  className="btn small"
                  disabled={!ready || working || auto || blocked || !it.text.trim() || isBracket(it.text)}
                  onClick={() => onMake(ch)}
                >{has ? "Redo" : "Generate"}</button>
              )}
            </span>
          </div>
        );
      })}
      <div className="grpfoot">
        <span className="grpmsg">{mixing ? "Mixing…" : isDone ? `Mixed as ${it.id}.mp3` : ""}</span>
        {isDone && !mixing && showPreview && (
          <button className="btn small" disabled={working || auto} onClick={onPlayMix}>{playing === it.id ? "Stop" : "Play mix"}</button>
        )}
        <button className="btn small primary" disabled={working || auto || mixing || !have.length} onClick={onMix}>
          {mixing ? "Mixing…" : `${isDone ? "Re-mix" : "Mix"} ${have.length} voice${have.length === 1 ? "" : "s"}`}
        </button>
      </div>
    </div>
  );
}
