export const joinPath = (base, name) => base + (base.includes("\\") ? "\\" : "/") + name;
export const baseOf = (path) => (path ? path.split(/[\\/]/).pop().replace(/\.[^.]+$/, "") : "");
export const lastSegment = (path) => (path ? path.split(/[\\/]/).pop() : "");
// Project name = file name without extension (older ".tts-project.json" files work too).
export const nameFromPath = (p) => baseOf(p).replace(/\.tts-project$/i, "");
export const fileSafe = (n) => String(n || "").replace(/[<>:"/\\|?*\x00-\x1f]/g, "_").trim().slice(0, 80) || "project";
export const projectPathFor = (dir, name) => joinPath(dir, `${fileSafe(name)}.tts-project.json`);

// Folder name for a script heading. "code" pulls out something like W6-01; falls back to "Scene 1".
export const folderFor = (segment, naming) => {
  const label = (segment || "").trim();
  if (!label) return "";
  if (naming === "code") {
    const m = label.match(/\b[A-Za-z]+\d+[-_]\d+\b/);
    if (m) return m[0].toUpperCase().replace(/_/g, "-");
    const s = label.match(/^(scene|segment)\s*0*(\d+)/i);
    if (s) return `${s[1][0].toUpperCase() + s[1].slice(1).toLowerCase()} ${s[2]}`;
  }
  const clean = label.replace(/[<>:"/\\|?*\x00-\x1f]/g, "_").replace(/\s+/g, " ").replace(/[. ]+$/, "").slice(0, 60);
  return clean === "Script" ? "" : clean;
};

// Speaker code from an ID (mirrors the engine): ADD-W01-BIL-001 -> BIL, ADD-W01-GRP-RXN-001 -> GRP, W02-HEN-001 -> HEN.
const NON_CHARACTER = new Set(["SEQ","CUE","REACT","UTILITY","TERM","HUMOR","FEED","ACTION","MOVE","GAMECALL","ALT","EMOTION","TEACHER","SIGNOFF","SAFE","LINE"]);
export const characterOf = (id) => {
  const p = String(id).split("-");
  if (p.length < 3) return String(id);
  if (p.length === 3) return p[1];
  return NON_CHARACTER.has(p[2]) ? p[1] : p[2];
};

// Folder a line belongs to for a grouping mode: scene heading, or character code.
export const groupName = (it, by, naming) => (by === "character" ? (it.character || "") : folderFor(it.segment, naming));
