import { PHASE_LABEL } from "../lib/constants";

export default function ActivityPage({ script, gen, log, clearLog, timestamps }) {
  const { items, item, doneCount } = script;
  return (
    <div className="page">
      <div className="picker" style={{ display: "block", marginBottom: 14 }}>
        <label>Progress</label>
        <div className="progressbar"><i style={{ width: items.length ? `${(doneCount / items.length) * 100}%` : 0 }} /></div>
        <div className="progresstext"><span>{gen.auto ? `Auto-running · ${item?.id ?? ""}` : PHASE_LABEL[gen.phase]}</span><span>{doneCount} of {items.length}</span></div>
      </div>
      <div className="logpanel">
        <div className="loghead">
          <b>Activity log</b><span>{log.length}</span>
          <div className="logbtns">
            <button className="btn small" disabled={!log.length} onClick={() => navigator.clipboard?.writeText(log.map((l) => `${l.t}  ${l.msg}`).join("\n"))}>Copy</button>
            <button className="btn small" disabled={!log.length} onClick={clearLog}>Clear</button>
          </div>
        </div>
        <div className="logbody">
          {log.length === 0 && <div className="logempty">Nothing yet.</div>}
          {log.map((l, i) => (
            <div key={i} className={`logline ${/fail|error|timed out/i.test(l.msg) ? "error" : /saved|connected|finished/i.test(l.msg) ? "ok" : ""}`}>
              {timestamps && <time>{l.t}</time>}<span>{l.msg}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
