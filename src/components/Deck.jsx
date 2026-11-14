import { PHASE_LABEL } from "../lib/constants";
import { isBracket } from "../lib/tags";

// Bottom bar of the Runner: the current line and its controls. `tagMenu` is rendered inline.
export default function Deck({
  item, phase, working, auto, reviewing, ready, outDir, failedMsg, playErr, voicesOpen, tagMenu,
  onToggleVoices, onGenerate, onKeep, onPlayPending, onEdit, onSkip,
  onReview, onStopReview, onAuto, onStopAuto,
}) {
  const bracket = isBracket(item.text);
  return (
    <div className="deck">
      <div className="now">
        <code>{item.id}</code>
        <p>{item.text || <em>(no text)</em>}</p>
        <small className={phase === "ready" ? "ok" : ""}>
          {reviewing ? "Auto play · listening through saved lines" : <>{auto ? "Auto-run · " : ""}{PHASE_LABEL[phase]}</>}
        </small>
        {bracket && <small className="err">This is a [bracketed] reaction. Edit it into a sound tag such as (laughs) before generating.</small>}
        {failedMsg && <small className="err">{failedMsg}</small>}
        {playErr && <small className="err">{playErr}</small>}
      </div>

      <div className="controls">
        {item.character === "GRP" ? (
          <button className="btn primary" disabled={working || auto} onClick={onToggleVoices}>{voicesOpen ? "Hide voices" : "Show voices"}</button>
        ) : phase !== "ready" ? (
          <button className="btn primary" disabled={!ready || working || auto || !item.text.trim() || bracket} onClick={onGenerate}>Generate</button>
        ) : (
          <>
            <button className="btn primary" disabled={auto} onClick={onKeep}>Download &amp; next</button>
            <button className="btn" onClick={onPlayPending}>▶ Play</button>
            <button className="btn" disabled={working || auto} onClick={onGenerate}>Regenerate</button>
          </>
        )}
        <button className="btn" disabled={working || auto} onClick={onEdit}>Edit text</button>
        <button className="btn" disabled={working || auto} onClick={onSkip}>Skip</button>
        <span className="sep" />
        {tagMenu}
        {!reviewing ? (
          <button className="btn" disabled={!outDir || working || auto} onClick={onReview} title="Plays every saved line from the selected one to the bottom">▶ Auto play</button>
        ) : (
          <button className="btn stop" onClick={onStopReview}>■ Stop auto play</button>
        )}
        {!auto ? (
          <button className="btn" disabled={!ready || working} onClick={onAuto}>Auto-run from here</button>
        ) : (
          <button className="btn stop" onClick={onStopAuto}>Stop after this line</button>
        )}
      </div>
    </div>
  );
}
