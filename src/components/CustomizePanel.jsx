import { useEffect, useState } from "react";
import { Toggle } from "./ui";

const VALID = /^[A#*{}\w.\-]+$/i;
const clean = (s) => String(s).toUpperCase().replace(/[^A-Z0-9]/g, "");
const enter = (fn) => (e) => { if (e.key === "Enter") fn(); };

/* What the user typed (AAA-HEN-###) -> the stored pattern (AAA-{HEN}-###), or an error. */
function toPattern(input, code) {
  const m = input.trim().toUpperCase();
  if (!m) return { error: "Enter an ID format" };
  if (!VALID.test(m)) return { error: "Use A, #, *, {TEXT}, and - _ . only" };
  const open = (m.match(/{/g) || []).length, close = (m.match(/}/g) || []).length;
  if (open !== close || /{}/.test(m)) return { error: "Check the {…} braces" };
  if (m.includes(`{${code}}`)) return { pattern: m };
  const parts = m.split("-");
  const hits = parts.map((p, i) => (p === code ? i : -1)).filter((i) => i >= 0);
  if (!hits.length) return { error: `The format must contain the code ${code}` };
  if (hits.length > 1) return { error: `${code} appears more than once. Put the right one in {braces}` };
  parts[hits[0]] = `{${code}}`;
  return { pattern: parts.join("-") };
}

/* A sample ID a pattern would match, so you can check it by eye. */
function example(mask) {
  let a = 0, n = 0, out = "";
  for (let i = 0; i < mask.length; i++) {
    const ch = mask[i];
    if (ch === "{") { const j = mask.indexOf("}", i); out += mask.slice(i + 1, j); i = j; }
    else if (ch === "A") out += "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[a++ % 26];
    else if (ch === "#") out += ++n % 10;
    else if (ch === "*") out += "X";
    else out += ch;
  }
  return out;
}

/* ---------------------------------------------------------------- right side: one character */
function CharacterDetail({ c, onEdit, onRemove }) {
  const [format, setFormat] = useState("");
  const [formatError, setFormatError] = useState("");
  const [alias, setAlias] = useState("");
  const aliases = c.aliases || [];

  const addFormat = () => {
    const r = toPattern(format, c.code);
    if (r.error) return setFormatError(r.error);
    if (c.patterns.includes(r.pattern)) return setFormatError("That format is already listed");
    onEdit({ ...c, patterns: [...c.patterns, r.pattern] });
    setFormat(""); setFormatError("");
  };
  const addAlias = () => {
    const a = alias.trim().toUpperCase();
    if (!a || aliases.includes(a)) return;
    onEdit({ ...c, aliases: [...aliases, a] });
    setAlias("");
  };

  return (
    <div className="custdetail">
      <div className="custtitle"><h4>{c.name || c.code}</h4><code>{c.code}</code></div>

      <label className="cfield">
        <span>Name</span>
        <input className="txtin" value={c.name} onChange={(e) => onEdit({ ...c, name: e.target.value })} />
      </label>

      <div className="crow">
        <div><b>Group line</b><p>Voiced by several characters at once</p></div>
        <Toggle label="Group line" on={!!c.group} onChange={(v) => onEdit({ ...c, group: v })} />
      </div>

      <section>
        <h4>ID formats</h4>
        {c.patterns.length === 0 && <p className="panelhint">None. A script without IDs is read by this character's name.</p>}
        <div className="fmtlist">
          {c.patterns.map((p) => (
            <div className="fmtrow" key={p}>
              <code>{p}</code>
              <span>e.g. {example(p)}</span>
              <button className="ghostbtn" aria-label={`Remove ${p}`} onClick={() => onEdit({ ...c, patterns: c.patterns.filter((x) => x !== p) })}>×</button>
            </div>
          ))}
        </div>
        <div className="addrow">
          <input className="txtin" style={{ flex: 1 }} value={format} placeholder={`e.g. AAA-${c.code}-###`} aria-label="New ID format"
                 onChange={(e) => { setFormat(e.target.value.toUpperCase()); setFormatError(""); }} onKeyDown={enter(addFormat)} />
          <button className="btn small" disabled={!format.trim()} onClick={addFormat}>Add</button>
        </div>
        {formatError && <p className="panelhint err">{formatError}</p>}
      </section>

      <section>
        <h4>Other names in the script</h4>
        <p className="panelhint">For scripts without IDs, when this character is called more than one thing, like COL LANDA and NAZI OFFICER.</p>
        {aliases.length > 0 && (
          <div className="chips">
            {aliases.map((a) => (
              <span className="chip" key={a}>{a}<button aria-label={`Remove ${a}`} onClick={() => onEdit({ ...c, aliases: aliases.filter((x) => x !== a) })}>×</button></span>
            ))}
          </div>
        )}
        <div className="addrow">
          <input className="txtin" style={{ flex: 1 }} value={alias} placeholder="e.g. NAZI OFFICER" aria-label="Another name for this character"
                 onChange={(e) => setAlias(e.target.value.toUpperCase())} onKeyDown={enter(addAlias)} />
          <button className="btn small" disabled={!alias.trim()} onClick={addAlias}>Add</button>
        </div>
      </section>

      <div className="custfoot">
        <button className="btn stop small" onClick={onRemove}>Remove character</button>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- right side: new character */
function NewCharacter({ taken, onCreate, onCancel }) {
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState("");

  const suggestion = clean(name).slice(0, 3);          // HEN from "Henry" when the code is left empty
  const k = clean(code) || suggestion;

  const create = () => {
    if (!k) return setError("Enter a name or a code");
    if (taken.includes(k)) return setError(`${k} is already in the list`);
    onCreate({ name: name.trim() || k, code: k, group: false, patterns: [], aliases: [] });
  };

  return (
    <div className="custdetail">
      <div className="custtitle"><h4>New character</h4></div>
      <label className="cfield">
        <span>Name</span>
        <input className="txtin" value={name} placeholder="e.g. Henry" autoFocus onChange={(e) => { setName(e.target.value); setError(""); }} onKeyDown={enter(create)} />
      </label>
      <label className="cfield">
        <span>Code: the part of the ID that is unique to them</span>
        <input className="txtin" value={code} maxLength={12} placeholder={suggestion || "e.g. HEN"}
               onChange={(e) => { setCode(clean(e.target.value)); setError(""); }} onKeyDown={enter(create)} />
      </label>
      {error && <p className="panelhint err">{error}</p>}
      <p className="panelhint">You can add ID formats and other names after creating the character.</p>
      <div className="addrow">
        <button className="btn primary" disabled={!k} onClick={create}>Create</button>
        {taken.length > 0 && <button className="btn stop" onClick={onCancel}>Cancel</button>}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- the panel */
export default function CustomizePanel({ onChange }) {
  const [data, setData] = useState(null);                 // null until loaded
  const [sel, setSel] = useState(null);                   // selected code, or "new"

  useEffect(() => {
    window.api.rules.load().then((d) => setData({ version: 1, characters: [], ...d })).catch(() => setData({ version: 1, characters: [] }));
  }, []);

  if (!data) return <p className="panelhint">Loading…</p>;

  const list = data.characters;
  const chosen = sel === "new" ? "new" : list.some((c) => c.code === sel) ? sel : (list[0]?.code ?? "new");
  const current = list.find((c) => c.code === chosen);

  // every change is saved straight away
  const commit = (characters) => {
    const next = { ...data, characters };
    setData(next);
    window.api.rules.save(next);
    onChange?.();                                         // lets the page know the rules changed
  };

  return (
    <>
      <details className="help">
        <summary>How do ID formats work?</summary>
        <p>
          Write an ID the way it looks in your script, using <code>A</code> for any letter, <code>#</code> for any digit,{" "}
          <code>*</code> for either, and <code>{"{TEXT}"}</code> for fixed text. The character's code is the part that makes the ID theirs: in{" "}
          <code>AAA-HEN-###</code>, <code>HEN</code> is the code. If your script has no IDs, skip the formats and the app finds lines by name.
        </p>
      </details>

      <div className="cust">
        <div className="custlist">
          <button className="btn small custnew" onClick={() => setSel("new")}>+ Add character</button>
          {list.map((c) => (
            <button key={c.code} className={`custitem${chosen === c.code ? " active" : ""}`} onClick={() => setSel(c.code)}>
              <span>{c.name || c.code}</span><code>{c.code}</code>
            </button>
          ))}
        </div>

        {current ? (
          <CharacterDetail
            key={current.code}
            c={current}
            onEdit={(next) => commit(list.map((x) => (x.code === current.code ? next : x)))}
            onRemove={() => { commit(list.filter((x) => x.code !== current.code)); setSel(null); }}
          />
        ) : (
          <NewCharacter
            taken={list.map((c) => c.code)}
            onCreate={(c) => { commit([...list, c]); setSel(c.code); }}
            onCancel={() => setSel(null)}
          />
        )}
      </div>
    </>
  );
}