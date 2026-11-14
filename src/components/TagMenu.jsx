import { useEffect, useRef, useState } from "react";
import {
  addLeadTag, applyEmotion, ELEVEN_TAGS, emotionOf, hasLeadTag,
  minimaxEmotions, minimaxSoundTags, removeLeadTag,
} from "../lib/tags";

const keepFocus = (ev) => ev.preventDefault();   // clicking a tag must not steal the cursor from the line editor
const cap = (s) => s[0].toUpperCase() + s.slice(1);

// The "Add Tags" popup at the bottom of the Runner. Tags follow the engine chosen on Setup.
export default function TagMenu({ engine, model, item, items, targetIds, selCount, onClearSel, editingCurrent, editorApi, bulkEdit, disabled }) {
  const [open, setOpen] = useState(false);
  const [cat, setCat] = useState("");
  const wrapRef = useRef(null);

  const cats = engine === "minimax"
    ? [["emotion", "Emotion"], ["sound", "Sound tags"]]
    : Object.keys(ELEVEN_TAGS).map((k) => [k, k]);
  const activeCat = cats.some(([k]) => k === cat) ? cat : cats[0][0];
  const targets = items.filter((i) => targetIds.includes(i.id));

  useEffect(() => { setCat(""); }, [engine]);
  useEffect(() => {
    if (!open) return;
    const onDown = (e) => { if (!wrapRef.current?.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  // While a line is being edited the buttons change the draft; otherwise they change the selected line(s).
  function emotionClick(emo) {
    if (!item) return;
    if (editingCurrent && editorApi.current) return editorApi.current.applyEmotion(emo);
    const allHave = targets.every((i) => emotionOf(i.text) === emo);
    bulkEdit(targetIds, (t) => (allHave ? applyEmotion(t, emo) : emotionOf(t) === emo ? t : applyEmotion(t, emo)));
  }
  const soundClick = (name) => { if (editingCurrent) editorApi.current?.insertSound(name); };
  function tagClick(tag) {
    if (!item) return;
    if (editingCurrent && editorApi.current) return editorApi.current.insertSound(tag, "[", "]");
    const allHave = targets.length > 0 && targets.every((i) => hasLeadTag(i.text, tag));
    bulkEdit(targetIds, (t) => (allHave ? removeLeadTag(t, tag) : addLeadTag(t, tag)));
  }

  const sounds = minimaxSoundTags(model);

  return (
    <div className="tagwrap" ref={wrapRef}>
      <button
        type="button"
        className={`btn ${open ? "open" : ""}`}
        disabled={disabled}
        aria-haspopup="dialog"
        aria-expanded={open}
        onMouseDown={keepFocus}
        onClick={() => setOpen((o) => !o)}
      >Add Tags ▴</button>

      {open && (
        <div className="tagpop" role="dialog" aria-label="Add tags" onKeyDown={(e) => { if (e.key === "Escape") setOpen(false); }}>
          <div className="tagcats">
            {cats.map(([key, label]) => (
              <button key={key} type="button" className={`btn small ${activeCat === key ? "primary" : ""}`} onMouseDown={keepFocus} onClick={() => setCat(key)}>{label}</button>
            ))}
          </div>

          {engine === "minimax" && activeCat === "emotion" && (
            <>
              <div className="taghint">{selCount ? `${selCount} lines selected.` : "Applies to the current line."} Click the same emotion again to remove it. Without one, the model picks the emotion from the text.</div>
              <div className="taggrid chips">
                {minimaxEmotions(model).map((e) => (
                  <button
                    key={e}
                    type="button"
                    className={`btn small ${(editingCurrent ? "" : emotionOf(item?.text)) === e ? "primary" : ""}`}
                    disabled={disabled}
                    onMouseDown={keepFocus}
                    onClick={() => emotionClick(e)}
                  >{cap(e)}</button>
                ))}
              </div>
            </>
          )}

          {engine === "minimax" && activeCat === "sound" && (
            <>
              {!sounds.length
                ? <div className="taghint">Sound tags need a speech-2.8 model. On this model they are removed before sending.</div>
                : !editingCurrent && <div className="taghint">Click Edit text first, then click where the sound goes.</div>}
              <div className="taggrid chips">
                {sounds.map((snd) => (
                  <button key={snd} type="button" className="btn small" disabled={!editingCurrent || disabled} onMouseDown={keepFocus} onClick={() => soundClick(snd)}>({snd})</button>
                ))}
              </div>
            </>
          )}

          {engine === "elevenlabs" && ELEVEN_TAGS[activeCat] && (
            <>
              <div className="taghint">
                {selCount
                  ? `${selCount} lines selected — the tag goes at the start of each. `
                  : "Select a line (Ctrl/Shift+click for several), then pick a tag. It goes at the start of the line. "}
                Works with Eleven v3 and v4.
                {selCount > 0 && <button className="linkbtn" onClick={onClearSel}>Clear selection</button>}
              </div>
              <div className="taggrid chips">
                {ELEVEN_TAGS[activeCat].map((tg) => {
                  const on = !editingCurrent && targets.length > 0 && targets.every((i) => hasLeadTag(i.text, tg));
                  return (
                    <button key={tg} type="button" className={`btn small ${on ? "primary" : ""}`} disabled={disabled} onMouseDown={keepFocus} onClick={() => tagClick(tg)}>[{tg}]</button>
                  );
                })}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
