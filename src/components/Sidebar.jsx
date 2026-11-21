import { useEffect, useRef, useState } from "react";

/* ---------- Tiny icon set (24px grid, stroke follows the text color) ---------- */

const ICONS = {
  menu:    <path d="M4 6h16M4 12h16M4 18h10" />,
  sidebar: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M9 4v16" /></>,
  plus:    <path d="M12 5v14M5 12h14" />,
  setup:   <><path d="M4 6h8M16 6h4M4 12h4M12 12h8M4 18h10M18 18h2" /><circle cx="14" cy="6" r="2" /><circle cx="10" cy="12" r="2" /><circle cx="16" cy="18" r="2" /></>,
  play:    <path d="M8 5l11 7-11 7z" />,
  activity:<path d="M3 12h4l3-8 4 16 3-8h4" />,
};

function Ico({ name, size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {ICONS[name]}
    </svg>
  );
}

/* ---------- Window controls (minimize / maximize / close) ---------- */

const glyph = {
  minimize: <path d="M2 6h8" />,
  maximize: <rect x="2.5" y="2.5" width="7" height="7" />,
  restore:  <path d="M4 2.5h5.5V8M2.5 4h5.5v5.5H2.5z" />,
  close:    <path d="M2.5 2.5l7 7M9.5 2.5l-7 7" />,
};

function WinButton({ kind, label, onClick, danger }) {
  return (
    <button className={`winctl${danger ? " danger" : ""}`} aria-label={label} title={label} onClick={onClick}>
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.2" aria-hidden="true">
        {glyph[kind]}
      </svg>
    </button>
  );
}

export function WindowControls() {
  const [maximized, setMaximized] = useState(false);

  useEffect(() => {
    window.api.win.isMaximized().then(setMaximized);
    return window.api.win.onState((s) => setMaximized(s.maximized));
  }, []);

  return (
    <div className="winctls">
      <WinButton kind="minimize" label="Minimize" onClick={window.api.win.minimize} />
      <WinButton
        kind={maximized ? "restore" : "maximize"}
        label={maximized ? "Restore" : "Maximize"}
        onClick={window.api.win.toggleMaximize}
      />
      <WinButton kind="close" label="Exit" onClick={window.api.win.close} danger />
    </div>
  );
}

/* ---------- Top row: menu + hide/show sidebar ---------- */
/* Rendered inside the sidebar, and in the window bar while the sidebar is hidden. */

export function SidebarTop({ onToggle, onOpen, onSaveAs, onSettings, disabled }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const away = (e) => { if (!ref.current?.contains(e.target)) setOpen(false); };
    const esc = (e) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", esc); };
  }, [open]);

  const run = (fn) => () => { setOpen(false); fn(); };

  return (
    <div className="sidebar-top" ref={ref}>
      <button className={`ghostbtn${open ? " open" : ""}`} aria-label="Menu" title="Menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <Ico name="menu" />
      </button>
      <button className="ghostbtn" aria-label="Toggle sidebar" title="Toggle sidebar" onClick={onToggle}>
        <Ico name="sidebar" />
      </button>

      {open && (
        <div className="menu" role="menu">
          <button className="menuitem" role="menuitem" disabled={disabled} onClick={run(onOpen)}>Open project…</button>
          <button className="menuitem" role="menuitem" disabled={disabled} onClick={run(onSaveAs)}>Save project as…</button>
          <div className="menusep" />
          <button className="menuitem" role="menuitem" onClick={run(onSettings)}>Settings</button>
          <div className="menusep" />
          <button className="menuitem" role="menuitem" onClick={run(window.api.win.close)}>Exit</button>
        </div>
      )}
    </div>
  );
}

/* ---------- Sidebar ---------- */

const NAV = [
  ["setup", "Setup", "setup"],
  ["run", "TTS Runner", "play"],
];


const ORDER_KEY = "recentOrder";

function stableOrder(list) {
  let saved = [];
  try { saved = JSON.parse(localStorage.getItem(ORDER_KEY) || "[]"); } catch { /* ignore */ }
  const have = new Set(list.map((r) => r.path));
  const known = new Set(saved);
  const order = [...list.filter((r) => !known.has(r.path)).map((r) => r.path), ...saved.filter((x) => have.has(x))];
  try { localStorage.setItem(ORDER_KEY, JSON.stringify(order)); } catch { /* ignore */ }
  const byPath = new Map(list.map((r) => [r.path, r]));
  return order.map((x) => byPath.get(x));
}

const samePath = (a, b) => !!a && !!b && a.replace(/\\/g, "/").toLowerCase() === b.replace(/\\/g, "/").toLowerCase();

export function Sidebar({ page, setPage, onNew, onOpenRecent, currentPath, disabled, ...top }) {
  const [recent, setRecent] = useState([]);
  useEffect(() => window.api.onRecent((list) => setRecent(stableOrder(list))), []);

  return (
    <aside className="sidebar">
      <SidebarTop disabled={disabled} {...top} />

      <nav className="nav" aria-label="Pages">
        <button className="navitem" onClick={onNew} disabled={disabled}>
          <Ico name="plus" /> New project
        </button>
        {NAV.map(([id, label, icon]) => (
          <button
            key={id}
            className={`navitem${page === id ? " active" : ""}`}
            aria-current={page === id ? "page" : undefined}
            onClick={() => setPage(id)}
          >
            <Ico name={icon} /> {label}
          </button>
        ))}
      </nav>

      <div className="recent-head">Recent projects</div>
      <div className="recent">
        {recent.length === 0 && <div className="recent-empty">No recent projects</div>}
        {recent.map((r) => (
          <button
            key={r.path}
            className={`recentitem${samePath(r.path, currentPath) ? " active" : ""}`}
            aria-current={samePath(r.path, currentPath) ? "true" : undefined}
            title={r.path}
            disabled={disabled}
            onClick={() => onOpenRecent(r)}
          >
            {r.name}
          </button>
        ))}
      </div>
    </aside>
  );
}