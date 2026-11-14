import { useRef, useState } from "react";

// One clip plays at a time. playUrl() resolves with "ended", "stopped" or "error" so Auto play can await it.
export function useAudio() {
  const [playing, setPlaying] = useState(null);     // id of the clip currently playing
  const [loadingId, setLoadingId] = useState(null);
  const [playErr, setPlayErr] = useState("");
  const audioRef = useRef(null);

  function endClip(a, why) {
    if (!a || a._done) return;
    a._done = true;
    a.pause();
    if (a._url) URL.revokeObjectURL(a._url);
    if (audioRef.current === a) audioRef.current = null;
    setPlaying(null);
    a._resolve?.(why);
  }
  const stopAudio = () => endClip(audioRef.current, "stopped");

  function playUrl(url, id) {
    return new Promise((resolve, reject) => {
      const a = new Audio(url);
      a._url = url;
      a._resolve = resolve;
      audioRef.current = a;
      a.onended = () => endClip(a, "ended");
      a.onerror = () => endClip(a, "error");
      a.play().then(() => setPlaying(id)).catch((e) => { endClip(a, "error"); reject(e); });
    });
  }

  // { data: base64, mime } from the server -> object URL
  const b64ToUrl = (r) => {
    const bytes = Uint8Array.from(atob(r.data), (c) => c.charCodeAt(0));
    return URL.createObjectURL(new Blob([bytes], { type: r.mime }));
  };

  return { playing, loadingId, setLoadingId, playErr, setPlayErr, playUrl, stopAudio, b64ToUrl };
}
