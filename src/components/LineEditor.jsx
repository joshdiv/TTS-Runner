import { useEffect, useRef, useState } from "react";
import { applyEmotion } from "../lib/tags";

// apiRef lets the Add Tags popup act on this editor's draft and cursor.
export default function LineEditor({ initial, onSave, onCancel, apiRef }) {
  const [draft, setDraft] = useState(initial);
  const ref = useRef(null);
  const draftRef = useRef(draft);
  draftRef.current = draft;

  useEffect(() => {
    ref.current?.focus();
    ref.current?.setSelectionRange(draft.length, draft.length);
    if (apiRef) {
      apiRef.current = {
        // Inserts (name) at the cursor, replacing any selected text, with a space on each side where needed.
        insertSound: (name, open = "(", close = ")") => {
          const el = ref.current; const v = draftRef.current;
          if (!el) return;
          const a = el.selectionStart ?? v.length;
          const b = el.selectionEnd ?? a;
          const before = v.slice(0, a); const after = v.slice(b);
          const pre = before && !/\s$/.test(before) ? " " : "";
          const post = after && !/^\s/.test(after) ? " " : "";
          const head = `${before}${pre}${open}${name}${close}${post}`;
          setDraft(head + after);
          requestAnimationFrame(() => { el.focus(); el.setSelectionRange(head.length, head.length); });
        },
        applyEmotion: (emo) => setDraft(applyEmotion(draftRef.current, emo)),
      };
    }
    return () => { if (apiRef) apiRef.current = null; };
  }, []); // eslint-disable-line

  const save = () => onSave(draft.trim());
  return (
    <div className="lineedit" onClick={(e) => e.stopPropagation()}>
      <textarea
        ref={ref}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") onCancel();
          if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); save(); }
        }}
      />
      <div className="hintrow">
        <span>Ctrl+Enter to save · Esc to cancel · use Add Tags below to insert a tag at the cursor</span>
        <span className="sp" />
        {draft !== initial && <button className="btn small" onClick={() => setDraft(initial)}>Undo changes</button>}
        <button className="btn small" onClick={onCancel}>Cancel</button>
        <button className="btn small primary" onClick={save}>Save</button>
      </div>
    </div>
  );
}
