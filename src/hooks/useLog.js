import { useCallback, useEffect, useState } from "react";

export function useLog(settingsRef) {
  const [log, setLog] = useState([]);
  const say = useCallback(
    (msg) => setLog((l) => [...l.slice(-(settingsRef.current.logLimit - 1)), { t: new Date().toLocaleTimeString(), msg }]),
    [settingsRef]
  );
  useEffect(() => window.api.onLog((t) => say(String(t).trim())), [say]);
  const clearLog = useCallback(() => setLog([]), []);
  return { log, say, clearLog };
}
