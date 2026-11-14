import { minimaxEmotions, minimaxSoundTags, SOUNDS, SOUND_ALIASES, splitEmotion } from "./tags";

// Every engine request goes through the Python server (minimax_server.py).
export const call = async (type, payload) => {
  const r = await window.api.engine(type, payload);
  if (!r.ok) throw new Error(r.error);
  return r.result;
};

const SOUND_RE = new RegExp(`\\((${[...SOUNDS, ...Object.keys(SOUND_ALIASES)].join("|")})\\)`, "gi");

// MiniMax: emotion goes in voice_setting (not in the text). Interjections like (laughs) only work on speech-2.8;
// on other models they are removed, and any leftover [bracket] text is dropped so it is never read aloud.
export function minimaxText(raw, model) {
  const { text, emotion } = splitEmotion(raw);
  const keepSounds = minimaxSoundTags(model).length > 0;
  const t = text
    .replace(SOUND_RE, (_, s) => (keepSounds ? `(${SOUND_ALIASES[s.toLowerCase()] || s.toLowerCase()})` : " "))
    .replace(/\[[^\]]*\]/g, " ")
    .replace(/[ \t]+/g, " ")
    .trim();
  return { text: t, emotion: minimaxEmotions(model).includes(emotion) ? emotion : "" };
}

// ElevenLabs v3/v4 read [laughs]-style audio tags. Other models would speak them aloud, so they're removed.
export function elevenText(raw, model) {
  const { text, emotion } = splitEmotion(raw);
  let t = text;
  if (/^eleven_v[34]/i.test(model)) {
    t = t.replace(SOUND_RE, (_, s) => `[${(SOUND_ALIASES[s.toLowerCase()] || s).replace(/-/g, " ")}]`);
    if (emotion && emotion !== "fluent") t = `[${emotion}] ${t}`;
  } else {
    t = t.replace(SOUND_RE, " ").replace(/\[[^\]]*\]/g, " ");
  }
  return t.replace(/\s+/g, " ").trim();
}

export const voiceFor = (cfg, character) => (cfg.voices || {})[character] || cfg.voiceId;

// Builds the [requestType, payload] pair for generating one line (or one character's take of a group line).
export function buildGenerate(settings, it, character) {
  const ch = character || it.character;
  if (settings.engine === "elevenlabs") {
    const c = settings.elevenlabs;
    const voiceId = voiceFor(c, ch);
    if (!voiceId) throw new Error(`No voice chosen for ${ch}. Pick one under Setup → ElevenLabs.`);
    return ["eleven_generate", {
      apiKey: c.apiKey, model: c.model, voiceId,
      stability: Number(c.stability), similarity: Number(c.similarity), style: Number(c.style), speed: Number(c.speed),
      text: elevenText(it.text, c.model),
    }];
  }
  const c = settings.minimax;
  const voiceId = voiceFor(c, ch);
  if (!voiceId) throw new Error(`No voice chosen for ${ch}. Pick one under Setup → MiniMax.`);
  const { text, emotion } = minimaxText(it.text, c.model);
  return ["minimax_generate", {
    apiKey: c.apiKey, baseUrl: c.baseUrl, model: c.model, voiceId,
    speed: Number(c.speed), vol: Number(c.vol), pitch: Math.round(Number(c.pitch)),
    emotion, languageBoost: c.languageBoost, text,
  }];
}

export const loadVoiceList = (engine, cfg) =>
  engine === "minimax"
    ? call("minimax_voices", { apiKey: cfg.apiKey, baseUrl: cfg.baseUrl })
    : call("eleven_voices", { apiKey: cfg.apiKey });
