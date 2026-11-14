import { emotionOf, isBracket } from "../lib/tags";
import LineEditor from "./LineEditor";

// One row in the Runner: play button, ID, text (or inline editor) and status tags.
export default function ScriptLine({
  it, rowRef, className, showPreview, isDone, playing, loading, busy, locked, auto,
  isEditing, editorApi, failedMsg, voicesLabel,
  onClick, onPlay, onEdit, onSave, onCancel, onToggleVoices,
}) {
  const isEdited = it.text !== it.orig;
  return (
    <div ref={rowRef} className={className} onClick={onClick}>
      <span className="playcell">
        {isDone && showPreview && (
          <button
            className="playbtn"
            aria-label={playing ? "Stop" : "Play"}
            title={playing ? "Stop" : "Play"}
            disabled={busy || loading}
            onClick={(e) => { e.stopPropagation(); onPlay(); }}
          >
            {loading ? <span className="spin">…</span> : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                {playing ? <rect x="6" y="6" width="12" height="12" rx="1" /> : <polygon points="7 4 20 12 7 20" />}
              </svg>
            )}
          </button>
        )}
      </span>
      <code>{it.id}</code>
      {isEditing ? (
        <LineEditor initial={it.text} apiRef={editorApi} onSave={onSave} onCancel={onCancel} />
      ) : (
        <>
          <span className="txt">{it.text || <em>(no dialogue found — double-click to add text)</em>}</span>
          <span className="tags">
            {isBracket(it.text) && <span className="tag err">needs sound tag</span>}
            {emotionOf(it.text) && <span className="tag">{emotionOf(it.text)}</span>}
            {isEdited && <span className="tag">edited</span>}
            {failedMsg && <span className="tag err">error</span>}
            {isDone && <span className="tag">saved</span>}
            {voicesLabel && <button className="editbtn" onClick={(e) => { e.stopPropagation(); onToggleVoices(); }}>{voicesLabel}</button>}
            <button className="editbtn" disabled={locked || auto} onClick={(e) => { e.stopPropagation(); onEdit(); }}>Edit</button>
          </span>
        </>
      )}
    </div>
  );
}
