export const SETTINGS_KEY = "mmtts.settings";
export const EDITS_KEY = "mmtts.edits";
export const SESSION_KEY = "mmtts.session";
export const RECENT_KEY = "mmtts.recent";
export const TAKES_DIR = "GRP";

export const DEFAULTS = {
  theme: "dark",              // dark | light
  textSize: "medium",         // small | medium | large
  density: "comfortable",     // comfortable | compact
  delayMin: 2000,             // ms between lines in auto-run
  delayMax: 4000,
  playGap: 400,               // pause between clips in Auto play (ms)
  stopOnError: true,
  retries: 0,
  advanceAfterKeep: true,
  scrollToCurrent: true,
  restoreSession: true,
  autosaveProject: true,
  showPreview: true,
  autoPlayPreview: false,
  organizeBySegment: false,
  folderNaming: "code",       // code = W6-01 | full = whole heading
  viewSort: "scene",          // scene | character
  folderBy: "scene",          // scene | character
  clearTakesAfterMix: false,
  logLimit: 200,
  timestamps: true,

  engine: "minimax",          // minimax | elevenlabs

  // Per-engine settings. Both engines are plain HTTP APIs now.
  minimax: {
    apiKey: "",
    baseUrl: "https://api.minimax.io",
    model: "speech-2.8-hd",
    speed: 1,                 // 0.5 – 2
    vol: 1,                   // (0, 10]
    pitch: 0,                 // -12 – 12
    languageBoost: "auto",
    voiceId: "",              // default voice
    voices: {},               // character code -> voice_id
    voiceList: [],            // cached from "Load voices"
  },
  elevenlabs: {
    apiKey: "",
    model: "eleven_v4",
    stability: 0.5,
    similarity: 0.75,
    style: 0,
    speed: 1,
    voiceId: "",
    voices: {},
    voiceList: [],
  },
};

export const ENGINES = [["minimax", "MiniMax"], ["elevenlabs", "ElevenLabs"]];

export const MINIMAX_MODELS = [
  ["speech-2.8-hd", "Speech 2.8 HD (best quality, sound tags)"],
  ["speech-2.8-turbo", "Speech 2.8 Turbo (faster, sound tags)"],
  ["speech-2.6-hd", "Speech 2.6 HD (adds fluent / whisper emotions)"],
  ["speech-2.6-turbo", "Speech 2.6 Turbo"],
  ["speech-02-hd", "Speech 02 HD"],
  ["speech-02-turbo", "Speech 02 Turbo"],
  ["speech-01-hd", "Speech 01 HD"],
  ["speech-01-turbo", "Speech 01 Turbo"],
];

export const MINIMAX_REGIONS = [
  ["https://api.minimax.io", "Global (api.minimax.io)"],
  ["https://api-uw.minimax.io", "US West (api-uw.minimax.io)"],
];

export const ELEVEN_MODELS = [
  ["eleven_v4", "Eleven v4 (most expressive)"],
  ["eleven_v4_turbo", "Eleven v4 Turbo (faster)"],
  ["eleven_v3", "Eleven v3"],
  ["eleven_multilingual_v2", "Multilingual v2"],
  ["eleven_flash_v2_5", "Flash v2.5"],
];

export const PHASE_LABEL = {
  idle: "Ready",
  generating: "Generating...",
  ready: "Generated — listen, then keep or redo",
  downloading: "Downloading… ",
};
