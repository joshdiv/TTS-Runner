import { useState } from "react";
import { ELEVEN_MODELS, MINIMAX_MODELS, MINIMAX_REGIONS } from "../lib/constants";
import { loadVoiceList } from "../lib/engines";
import { NumField, SelectField } from "./ui";

const VoiceSelect = ({ value, list, onPick, blank }) => (
  <select value={value || ""} onChange={(e) => onPick(e.target.value)}>
    <option value="">{blank}</option>
    {value && !list.some((v) => v.id === value) && <option value={value}>{value}</option>}
    {list.map((v) => <option key={v.id} value={v.id}>{v.name}{v.category ? ` (${v.category})` : ""}</option>)}
  </select>
);

export default function EnginePanel({ engine, cfg, onChange, characters }) {
  const [msg, setMsg] = useState("");
  const mini = engine === "minimax";

  async function loadVoices() {
    setMsg("Loading…");
    try {
      const r = await loadVoiceList(engine, cfg);
      onChange({ voiceList: r.voices });
      setMsg(`${r.voices.length} voices loaded`);
    } catch (e) { setMsg(e.message); }
  }

  const num = (key) => (v) => onChange({ [key]: v });

  return (
    <div className="panel">
      <h3>{mini ? "MiniMax" : "ElevenLabs"}</h3>

      <div className="fieldrow">
        <label className="field grow2">
          <span>API key</span>
          <input
            type="password"
            placeholder={mini ? "Or set MINIMAX_API_KEY" : "Or set ELEVENLABS_API_KEY"}
            value={cfg.apiKey}
            onChange={(e) => onChange({ apiKey: e.target.value.trim() })}
          />
        </label>
        <SelectField className="grow2" label="Model" value={cfg.model} onChange={(v) => onChange({ model: v })} options={mini ? MINIMAX_MODELS : ELEVEN_MODELS} />
      </div>

      {mini && (
        <div className="fieldrow">
          <SelectField className="grow2" label="Server" value={cfg.baseUrl} onChange={(v) => onChange({ baseUrl: v })} options={MINIMAX_REGIONS} />
        </div>
      )}

      <div className="fieldgrid">
        {mini ? (
          <>
            <NumField label="Speed" min={0.5} max={2} step={0.05} value={cfg.speed} onChange={num("speed")} />
            <NumField label="Volume" min={0.1} max={10} step={0.1} value={cfg.vol} onChange={num("vol")} />
            <NumField label="Pitch" min={-12} max={12} step={1} value={cfg.pitch} onChange={num("pitch")} />
          </>
        ) : (
          <>
            <NumField label="Stability" min={0} max={1} step={0.05} value={cfg.stability} onChange={num("stability")} />
            <NumField label="Similarity" min={0} max={1} step={0.05} value={cfg.similarity} onChange={num("similarity")} />
            <NumField label="Style" min={0} max={1} step={0.05} value={cfg.style} onChange={num("style")} />
            <NumField label="Speed" min={0.7} max={1.2} step={0.05} value={cfg.speed} onChange={num("speed")} />
          </>
        )}
      </div>
      <p className="panelhint">
        {mini
          ? "Speed 0.5–2, volume up to 10, pitch −12 to 12. Emotion is set per line with Add Tags. Sound tags such as (laughs) need a speech-2.8 model; fluent and whisper emotions need speech-2.6."
          : "Stability: lower is more expressive. Similarity: higher stays closer to the voice. Style: 0 is neutral. Speed: 1 is normal. v3 and v4 understand emotion and sound tags."}
      </p>

      <div className="panelsplit" />

      <div className="voicehead">
        <b>Voices</b>
        <span className="voicemsg">{msg}</span>
        <button className="btn small" disabled={!cfg.apiKey} onClick={loadVoices}>Load voices</button>
      </div>
      <div className="voicegrid">
        <label className="field">
          <span>Default voice</span>
          <VoiceSelect value={cfg.voiceId} list={cfg.voiceList} onPick={(v) => onChange({ voiceId: v })} blank="Choose a voice" />
        </label>
        {characters.map((ch) => (
          <label key={ch} className="field">
            <span>{ch}</span>
            <VoiceSelect
              value={(cfg.voices || {})[ch]}
              list={cfg.voiceList}
              onPick={(v) => onChange({ voices: { ...cfg.voices, [ch]: v } })}
              blank="Use default voice"
            />
          </label>
        ))}
      </div>
      {mini && <p className="panelhint">Cloned voices show up here after they have been used for synthesis at least once (a MiniMax rule).</p>}
    </div>
  );
}
