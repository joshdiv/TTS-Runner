import { useState } from "react";
import { createPortal } from "react-dom";
import Modal from "./Modal";

/* "3, 4, 5, 9" -> "3–5, 9", so a long list of missing numbers stays readable. */
function spans(nums, fmt) {
  if (!nums.length) return "";
  if (!nums.every((n) => Number.isFinite(n))) return nums.map(fmt).join(", ");
  const s = [...nums].sort((a, b) => a - b);
  const out = [];
  let a = s[0], b = s[0];
  for (let i = 1; i <= s.length; i++) {
    if (s[i] === b + 1) { b = s[i]; continue; }
    out.push(a === b ? fmt(a) : `${fmt(a)}–${fmt(b)}`);
    a = b = s[i];
  }
  return out.join(", ");
}

const SOURCE = { mine: "Customize", found: "Found in script", off: "Omitted" };
const sourceOf = (r) => (r.omitted ? SOURCE.off : r.known ? SOURCE.mine : SOURCE.found);

/* One chip per character: code, number of lines, and one action (omit or restore). */
const CharChip = ({ r, symbol, label, disabled, onClick }) => (
  <span className="chip" title={r.name !== r.code ? r.name : undefined}>
    {r.code}<i>{r.count}</i>
    <button aria-label={`${label} ${r.code}`} title={label} disabled={disabled} onClick={onClick}>{symbol}</button>
  </span>
);

/* A titled group of chips, with an optional "all" action in the header. */
const CharGroup = ({ title, hint, all, className, children }) => (
  <div className={`sumgroup ${className || ""}`}>
    <div className="sumgrouphead">
      <h4>{title}</h4>
      {all}
    </div>
    {hint && <p className="panelhint">{hint}</p>}
    <div className="chips">{children}</div>
  </div>
);

// Summary card on Setup: which characters were found, how far along the script is, and what looks off.
export default function ScriptSummary({
  items, analysis, characters, roster = [], scriptPath, fileName, doneCount, ready, busy, loading = false,
  onOpenRunner, onOmit, onRestore,
}) {
  const [showFull, setShowFull] = useState(false);
  const [copied, setCopied] = useState(false);
  const pct = items.length ? Math.round((doneCount / items.length) * 100) : 0;
  const { problems, missingGroups, missingTotal, dups, empty } = analysis;

  const hasScript = items.length > 0 || roster.length > 0;
  const mine = roster.filter((r) => r.known && !r.omitted);       // characters listed in Customize
  const found = roster.filter((r) => !r.known && !r.omitted);     // names the app picked up from the script itself
  const omitted = roster.filter((r) => r.omitted);
  const codes = (list) => list.map((r) => r.code);

  // Plain-text version of the full report (for copying)
  const buildReportText = () => {
    const lines = [`Script: ${fileName}`, `Lines: ${analysis.total}`, `Saved: ${doneCount}`, "", "Characters:"];
    roster.forEach((r) => lines.push(`  ${r.code}${r.name !== r.code ? ` (${r.name})` : ""}: ${r.count} lines, ${sourceOf(r)}`));
    lines.push("");
    if (missingGroups.length) {
      lines.push(`Missing numbers (${missingTotal}):`);
      missingGroups.forEach((g) => lines.push(`  ${g.prefix}: ${spans(g.missing, g.fmt)}`));
      lines.push("");
    }
    if (dups.length) lines.push(`Duplicate IDs (${dups.length}): ${dups.join(", ")}`, "");
    if (empty.length) lines.push(`IDs with no dialogue text (${empty.length}): ${empty.join(", ")}`, "");
    return lines.join("\n").trim();
  };

  const copyReport = async () => {
    try {
      await navigator.clipboard.writeText(buildReportText());
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {}
  };

  return (
    <div className={`check${loading ? " is-loading" : ""}`} aria-busy={loading}>
      {/* header: title + filename on the left, issue flag on the right (same look as the tiles) */}
      <div className="sumhead">
        <div>
          <h3>Script summary</h3>
          <p title={scriptPath}>{hasScript ? fileName : "Choose a script to see its summary."}</p>
        </div>
        {loading ? (
          <span className="checkflag"><i className="spinner" /> Reading…</span>
        ) : items.length > 0 && (
          <span className={`checkflag ${problems ? "warn" : ""}`}>
            {problems ? `${problems} thing${problems === 1 ? "" : "s"} to look at` : "No issues found"}
          </span>
        )}
      </div>

      {loading && !hasScript && (
        <div className="sumload">
          <div className="loadbar" role="progressbar" aria-label="Reading the script"><i /></div>
          <p className="panelhint">Reading the script. A long PDF takes a little while the first time.</p>
        </div>
      )}

      {hasScript && (
        <>
          <div className="checkgrid stats">
            <div><b>{analysis.total}</b><span>Total lines</span></div>
            <div><b>{characters.length}</b><span>Characters</span></div>
            <div><b>{doneCount}</b><span>Saved</span></div>
          </div>

          {/* characters, split by where they came from. Omitting one takes its lines out of this script. */}
          {mine.length > 0 && (
            <CharGroup title="Your characters" hint="From Customize.">
              {mine.map((r) => <CharChip key={r.code} r={r} symbol="×" label="Omit" disabled={busy} onClick={() => onOmit([r.code])} />)}
            </CharGroup>
          )}

          {found.length > 0 && (
            <CharGroup
              title="Found in the script"
              hint="Names picked up from the script that are not in Customize. Omit anything that is not a real character."
              all={found.length > 1 && <button className="linkbtn" disabled={busy} onClick={() => onOmit(codes(found))}>Omit all</button>}
            >
              {found.map((r) => <CharChip key={r.code} r={r} symbol="×" label="Omit" disabled={busy} onClick={() => onOmit([r.code])} />)}
            </CharGroup>
          )}

          {omitted.length > 0 && (
            <CharGroup
              title="Omitted"
              hint="Left out of this script. Restore one to bring its lines back."
              className="is-omitted"
              all={omitted.length > 1 && <button className="linkbtn" disabled={busy} onClick={() => onRestore(codes(omitted))}>Restore all</button>}
            >
              {omitted.map((r) => <CharChip key={r.code} r={r} symbol="+" label="Restore" disabled={busy} onClick={() => onRestore([r.code])} />)}
            </CharGroup>
          )}

          <div>
            <div className="progressbar"><i style={{ width: `${pct}%` }} /></div>
            <div className="progresstext"><span>{doneCount} of {items.length} saved</span><span>{pct}%</span></div>
          </div>

          {problems > 0 && (
            <ul className="checklist issues">
              {missingGroups.length > 0 && (
                <li>
                  {missingTotal} missing number{missingTotal === 1 ? "" : "s"} in {missingGroups.length} series, starting with <code>{missingGroups[0].prefix}</code> {missingGroups[0].missing.slice(0, 5).map(missingGroups[0].fmt).join(", ")}{missingGroups[0].missing.length > 5 ? "…" : ""}
                </li>
              )}
              {dups.length > 0 && <li>Duplicate IDs: {dups.slice(0, 10).join(", ")}{dups.length > 10 ? "…" : ""}</li>}
              {empty.length > 0 && <li>{empty.length} ID{empty.length === 1 ? " has" : "s have"} no dialogue text: {empty.slice(0, 5).join(", ")}{empty.length > 5 ? "…" : ""}</li>}
            </ul>
          )}
        </>
      )}

      {/* footer sits at the bottom of the card: report button left, main action right */}
      <div className="sumfoot">
        {hasScript ? <button className="btn" onClick={() => setShowFull(true)}>Full report</button> : <span />}
        <button className="btn primary" disabled={!ready} onClick={onOpenRunner}>Open runner</button>
      </div>

      {showFull && createPortal(
        <Modal
          title="Full report"
          wide
          onClose={() => setShowFull(false)}
          footer={<button className="btn" onClick={copyReport}>{copied ? "Copied!" : "Copy report"}</button>}
        >
          <p className="repfile">{fileName}</p>

          <div className="repstats">
            <div><b>{analysis.total}</b><span>Lines</span></div>
            <div><b>{characters.length}</b><span>Characters</span></div>
            <div><b>{doneCount}</b><span>Saved</span></div>
            <div><b>{problems}</b><span>{problems === 1 ? "Issue" : "Issues"}</span></div>
          </div>

          {roster.length > 0 && (
            <section>
              <h4>Characters</h4>
              <table className="reptable">
                <thead><tr><th>Code</th><th>Name</th><th className="num">Lines</th><th>Source</th></tr></thead>
                <tbody>
                  {roster.map((r) => (
                    <tr key={r.code} className={r.omitted ? "off" : ""}>
                      <td><code>{r.code}</code></td>
                      <td className="dim">{r.name !== r.code ? r.name : "—"}</td>
                      <td className="num">{r.count}</td>
                      <td className="dim">{sourceOf(r)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}

          {problems === 0 && <section><h4>Issues</h4><p>No issues found.</p></section>}

          {missingGroups.length > 0 && (
            <section>
              <h4>Missing numbers ({missingTotal})</h4>
              {missingGroups.map((g) => (
                <div key={g.prefix} className="repgroup">
                  <div className="rephead"><code>{g.prefix}</code><span>{g.missing.length} missing</span></div>
                  <p className="repids">{spans(g.missing, g.fmt)}</p>
                </div>
              ))}
            </section>
          )}

          {dups.length > 0 && (
            <section>
              <h4>Duplicate IDs ({dups.length})</h4>
              <p className="repids">{dups.join(", ")}</p>
            </section>
          )}

          {empty.length > 0 && (
            <section>
              <h4>IDs with no dialogue text ({empty.length})</h4>
              <p className="repids">{empty.join(", ")}</p>
            </section>
          )}
        </Modal>,
        // inside the Setup page, so the dialog gets the same button and font styling as the other dialogs
        document.querySelector(".setup") || document.querySelector(".app") || document.body
      )}
    </div>
  );
}