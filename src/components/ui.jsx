/* Small shared controls. */
export const Toggle = ({ on, onChange, label }) => (
  <button type="button" role="switch" aria-checked={on} aria-label={label} className={`toggle ${on ? "on" : ""}`} onClick={() => onChange(!on)}><i /></button>
);

export const Seg = ({ value, options, onChange }) => (
  <div className="seq">
    {options.map(([v, label]) => (
      <button key={v} type="button" className={value === v ? "selected" : ""} onClick={() => onChange(v)}>{label}</button>
    ))}
  </div>
);

export const SetRow = ({ title, desc, children }) => (
  <div className="setrow">
    <div className="setinfo"><b>{title}</b>{desc && <p>{desc}</p>}</div>
    <div className="setctl">{children}</div>
  </div>
);

export const NumField = ({ label, value, onChange, min, max, step }) => (
  <label className="field">
    <span>{label}</span>
    <input type="number" min={min} max={max} step={step} value={value} onChange={(e) => onChange(e.target.value)} />
  </label>
);

export const SelectField = ({ label, value, onChange, options, className = "" }) => (
  <label className={`field ${className}`}>
    <span>{label}</span>
    <select value={value} onChange={(e) => onChange(e.target.value)}>
      {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
    </select>
  </label>
);
