import { DEFAULTS, SETTINGS_KEY } from "./constants";

export const loadJSON = (key, fallback) => {
  try { return { ...fallback, ...(JSON.parse(localStorage.getItem(key)) || {}) }; } catch { return fallback; }
};
export const saveJSON = (key, value) => {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* ignore */ }
};

// Old flat ElevenLabs keys -> settings.elevenlabs.*
const LEGACY_ELEVEN = {
  apiKey: "apiKey", apiModel: "model", apiStability: "stability", apiSimilarity: "similarity",
  apiStyle: "style", apiSpeed: "speed", apiVoiceId: "voiceId", apiVoices: "voices", apiVoiceList: "voiceList",
};

// Loads saved settings and upgrades the old shape (engine "browser"/"api", flat api* keys, Chrome options).
export function loadSettings() {
  let raw = {};
  try { raw = JSON.parse(localStorage.getItem(SETTINGS_KEY)) || {}; } catch { /* ignore */ }

  const eleven = { ...DEFAULTS.elevenlabs };
  for (const [old, key] of Object.entries(LEGACY_ELEVEN)) if (raw[old] !== undefined) eleven[key] = raw[old];
  Object.assign(eleven, raw.elevenlabs || {});
  if (!/^eleven_/.test(eleven.model || "")) eleven.model = DEFAULTS.elevenlabs.model;

  const engine = raw.engine === "api" ? "elevenlabs" : raw.engine === "elevenlabs" ? "elevenlabs" : "minimax";
  const s = { ...DEFAULTS, ...raw, engine, minimax: { ...DEFAULTS.minimax, ...(raw.minimax || {}) }, elevenlabs: eleven };
  [...Object.keys(LEGACY_ELEVEN), "port", "chromeUrl", "autoReconnect"].forEach((k) => delete s[k]);
  return s;
}
