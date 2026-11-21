import { useCallback, useEffect, useRef, useState } from "react";
import { DEFAULTS, SETTINGS_KEY } from "../lib/constants";
import { loadSettings, saveJSON } from "../lib/storage";

export function useSettings() {
  const [settings, setSettings] = useState(loadSettings);
  const settingsRef = useRef(settings);
  settingsRef.current = settings;

  const set = useCallback((patch) => setSettings((s) => ({ ...s, ...patch })), []);
  const setEngineCfg = useCallback((engine, patch) => setSettings((s) => ({ ...s, [engine]: { ...s[engine], ...patch } })), []);
  const resetSettings = useCallback(() => setSettings(DEFAULTS), []);

  useEffect(() => saveJSON(SETTINGS_KEY, settings), [settings]);
  return { settings, settingsRef, set, setEngineCfg, resetSettings };
}
