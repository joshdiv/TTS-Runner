/* The activity log (moved here from the old Activity page). */
export default function LogPanel({ log, clearLog, timestamps }) {
  // Newest first: reverse a copy (never mutate the prop)
  const entries = log.map((l, i) => ({ ...l, i })).reverse();

  return (
    <div className="logpanel">
      <div className="loghead">
        <b>Activity log</b><span>{log.length}</span>
        <div className="logbtns">
          <button
            className="btn small"
            disabled={!log.length}
            onClick={() =>
              navigator.clipboard?.writeText(
                // copy in newest-first order to match what's on screen
                entries.map((l) => `${l.t}  ${l.msg}`).join("\n")
              )
            }
          >
            Copy
          </button>
          <button className="btn small" disabled={!log.length} onClick={clearLog}>Clear</button>
        </div>
      </div>
      <div className="logbody">
        {log.length === 0 && <div className="logempty">Nothing yet.</div>}
        {entries.map((l) => (
          <div
            key={l.i}
            className={`logline ${/fail|error|timed out/i.test(l.msg) ? "error" : /saved|connected|finished/i.test(l.msg) ? "ok" : ""}`}
          >
            {timestamps && <time>{l.t}</time>}<span>{l.msg}</span>
          </div>
        ))}
      </div>
    </div>
  );
}