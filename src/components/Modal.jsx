import { useEffect } from "react";

/* Generic dialog: backdrop click, Escape and the X all close it.
   `footer` replaces the default "Done" button; `wide` makes it wider. */
export default function Modal({ title, onClose, children, wide, footer }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modalback" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={`modalbox${wide ? " wide" : ""}`} role="dialog" aria-modal="true" aria-label={title}>
        <div className="modalhead">
          <h3>{title}</h3>
          <button className="ghostbtn" onClick={onClose} aria-label="Close" title="Close">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
          </button>
        </div>
        <div className="modalbody">{children}</div>
        <div className="modalfoot">
          {footer ?? <button className="btn primary" onClick={onClose}>Done</button>}
        </div>
      </div>
    </div>
  );
}