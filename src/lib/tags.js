/* Emotion + sound tags. Lines keep the app's own storage format ({emotion}…{/emotion} wrapper and
   (sound) / [tag] markers); lib/engines.js converts them into what each API expects. */

// "neutral" is kept so old saved edits still parse. It means "let the model decide".
export const ALL_EMOTIONS = ["happy", "angry", "sad", "fearful", "disgusted", "surprised", "neutral", "calm", "fluent", "whisper"];

// MiniMax emotion values per model (speech-2.8 has no fluent/whisper; those are 2.6 only).
export const minimaxEmotions = (model) => {
  const base = ["happy", "sad", "angry", "fearful", "disgusted", "surprised", "calm"];
  return /^speech-2\.6/.test(model) ? [...base, "fluent", "whisper"] : base;
};

// MiniMax interjection tags, only supported on speech-2.8-*.
export const SOUNDS = ["laughs", "chuckle", "coughs", "clear-throat", "groans", "breath", "pant", "inhale", "exhale", "gasps", "sniffs", "sighs", "snorts", "burps", "lip-smacking", "humming", "hissing", "emm", "sneezes"];
export const SOUND_ALIASES = { laugh: "laughs", cough: "coughs" };   // old spellings in saved edits
export const minimaxSoundTags = (model) => (/^speech-2\.8/.test(model) ? SOUNDS : []);

// ElevenLabs v3/v4 audio tags. Add more to any list and they appear automatically.
export const ELEVEN_TAGS = {
  "Emotion": ["weak", "angry", "bored", "menacing", "playful", "tired", "excited"],
  "Vocalizations": ["clears throat", "coughing", "chuckling", "sighing", "sniffling", "yawning", "laughing", "sharp exhale", "scoffing", "humming", "panting", "gasping"],
  "Delivery": ["whispering", "singing", "slowly", "softly", "pause", "voice breaking"],
  "Character": ["sleepy drowsy voice", "witch voice", "drunken voice"],
  "Sound effects": ["keyboard typing", "echoing", "knocking on door", "bell ringing", "phone ringing", "dog barking", "crowd cheering", "applause", "rain falling", "drum roll", "heartbeat", "engine starting"],
};
export const ELEVEN_TAG_SET = new Set(Object.values(ELEVEN_TAGS).flat());

const EMO_RE = new RegExp(`^\\{(${ALL_EMOTIONS.join("|")})\\}([\\s\\S]*)\\{/\\1\\}$`, "i");
export const emotionOf = (t) => ((t || "").trim().match(EMO_RE)?.[1] || "").toLowerCase();

// Wraps the whole line. A different emotion replaces the old one; the same emotion again removes it.
export const applyEmotion = (text, emo) => {
  const t = (text || "").trim();
  const m = t.match(EMO_RE);
  const inner = m ? m[2] : t;
  return m && m[1].toLowerCase() === emo ? inner : `{${emo}}${inner}{/${emo}}`;
};

// {happy}text{/happy} -> { text, emotion }. "neutral" is dropped (default delivery).
export const splitEmotion = (t) => {
  const m = (t || "").trim().match(EMO_RE);
  const emo = m ? m[1].toLowerCase() : "";
  return { text: m ? m[2].trim() : (t || "").trim(), emotion: emo === "neutral" ? "" : emo };
};

/* ---- leading [tags] (ElevenLabs style) ---- */
const LEAD_RE = /^((?:\[[^\]]+\]\s*)*)([\s\S]*)$/;
const splitLead = (text) => {
  const t = (text || "").trim();
  const w = t.match(EMO_RE);
  const inner = w ? w[2] : t;
  const m = inner.match(LEAD_RE);
  return { wrap: w ? w[1] : "", lead: m[1].match(/\[[^\]]+\]/g) || [], body: m[2] };
};
const buildLine = ({ wrap, lead, body }) => {
  const inner = [...lead, body].filter(Boolean).join(" ").trim();
  return wrap ? `{${wrap}}${inner}{/${wrap}}` : inner;
};
export const hasLeadTag = (text, tag) => splitLead(text).lead.includes(`[${tag}]`);
export const addLeadTag = (text, tag) => {
  const p = splitLead(text);
  return p.lead.includes(`[${tag}]`) ? text : buildLine({ ...p, lead: [...p.lead, `[${tag}]`] });
};
export const removeLeadTag = (text, tag) => {
  const p = splitLead(text);
  return buildLine({ ...p, lead: p.lead.filter((x) => x !== `[${tag}]`) });
};

// Lines that are still a [bracketed] reaction (e.g. [Laughter]) need to be edited into a sound tag by hand.
export const isBracket = (t) => {
  const s = (t || "").trim();
  if (!/^\[[\s\S]*\]$/.test(s)) return false;
  return s.replace(/\[([^\]]+)\]/g, (m, x) => (ELEVEN_TAG_SET.has(x) ? "" : m)).trim() !== "";
};
