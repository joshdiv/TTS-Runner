// Right-hand summary card on Setup: what was detected in the script and what looks off.
export default function ScriptSummary({ items, analysis, characters, scriptPath, fileName, doneCount, ready, onOpenRunner }) {
  const pct = items.length ? Math.round((doneCount / items.length) * 100) : 0;
  const { problems, missingGroups, missingTotal, dups, empty } = analysis;
  return (
    <div className="check">
      <div className="checkhead">
        <label>Summary</label>
        {items.length > 0 && (
          <span className={`checkflag ${problems ? "warn" : ""}`}>
            {problems ? `${problems} thing${problems === 1 ? "" : "s"} to look at` : "No issues found"}
          </span>
        )}
      </div>

      {items.length === 0 ? (
        <p className="panelhint">Choose a script to see its summary.</p>
      ) : (
        <>
          <div className="checkgrid summary">
            <div className="wide"><b title={scriptPath}>{fileName}</b><span>Filename</span></div>
            <div><b>{analysis.total}</b><span>Total lines</span></div>
            <div><b>{characters.length}</b><span>Characters detected</span></div>
          </div>
          {characters.length > 0 && <div className="charlist">{characters.map((c) => <code key={c}>{c}</code>)}</div>}

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

          <div className="panelsplit" />
          <div className="progressbar"><i style={{ width: `${pct}%` }} /></div>
          <div className="progresstext"><span>{doneCount} of {items.length} saved</span><span>{pct}%</span></div>
        </>
      )}

      <button className="btn primary widebtn-open" disabled={!ready} onClick={onOpenRunner}>Open runner</button>
    </div>
  );
}
