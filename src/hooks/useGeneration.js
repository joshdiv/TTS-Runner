import { useRef, useState } from "react";
import { TAKES_DIR } from "../lib/constants";
import { buildGenerate, call } from "../lib/engines";
import { joinPath } from "../lib/paths";
import { isBracket } from "../lib/tags";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/* Generating, saving, previewing, group-line takes/mixing, Auto-run and Auto play.
   Both engines are HTTP APIs: generate -> the server holds the audio -> "api_save" writes it to disk. */
export function useGeneration({ script, settingsRef, audio, say, phase, setPhase, rowRefs }) {
  const { itemsRef, doneRef, outRef, characters } = script;
  const [auto, setAuto] = useState(false);
  const [reviewing, setReviewing] = useState(false);   // Auto play running
  const [open, setOpen] = useState({});                // id -> voices panel expanded
  const [takeKey, setTakeKey] = useState("");          // "<id>|<CHAR>" currently being made
  const [mixingId, setMixingId] = useState(null);
  const stopRef = useRef(false);
  const reviewStopRef = useRef(false);
  const pendingRef = useRef(null);                     // last generated audio, not saved yet

  const working = phase === "generating" || phase === "downloading" || reviewing;

  /* ---------------------------------------------------------------- playback */
  function playFail(it, e) {
    audio.setPlayErr(`${it.id}: ${e.message}`);
    say(`${it.id} play failed: ${e.message}`);
  }

  async function fetchClip(it) {
    const r = await call("read_audio", { id: it.id, dirs: script.candidateDirs(it), recursive: true });
    if (!r.found) throw new Error("Saved file not found in the output folder.");
    return audio.b64ToUrl(r);
  }

  async function playLine(it) {
    if (audio.playing === it.id) return audio.stopAudio();
    audio.stopAudio();
    audio.setPlayErr("");
    audio.setLoadingId(it.id);
    try {
      const url = await fetchClip(it);
      audio.setLoadingId(null);
      if ((await audio.playUrl(url, it.id)) === "error") throw new Error("Could not play this file.");
    } catch (e) { playFail(it, e); }
    audio.setLoadingId(null);
  }

  async function playPending() {
    const r = pendingRef.current;
    if (!r) return;
    audio.stopAudio();
    try { await audio.playUrl(audio.b64ToUrl(r), "__pending"); } catch (e) { audio.setPlayErr(e.message); }
  }

  async function playTake(it, ch) {
    const pid = `${it.id}__${ch}`;
    if (audio.playing === pid) return audio.stopAudio();
    audio.stopAudio(); audio.setPlayErr("");
    try {
      const r = await call("read_audio", { id: pid, dirs: [joinPath(outRef.current, TAKES_DIR)] });
      if (!r.found) throw new Error("Take not found in the GRP folder.");
      if ((await audio.playUrl(audio.b64ToUrl(r), pid)) === "error") throw new Error("Could not play this file.");
    } catch (e) { playFail({ id: pid }, e); }
  }

  // Auto play: listens to every saved line from the selected one down to the bottom.
  async function runReview() {
    if (working || auto) return;
    audio.stopAudio();
    script.setEditing(null);
    audio.setPlayErr("");
    reviewStopRef.current = false;
    setReviewing(true);
    let played = 0, skipped = 0, failedAt = null;
    for (let i = script.cur; i < itemsRef.current.length && !reviewStopRef.current; i++) {
      const it = itemsRef.current[i];
      if (!doneRef.current[it.id]) { skipped++; continue; }
      script.setCur(i);
      rowRefs.current[i]?.scrollIntoView({ block: "center", behavior: "smooth" });
      try {
        audio.setLoadingId(it.id);
        const url = await fetchClip(it);
        audio.setLoadingId(null);
        if (reviewStopRef.current) { URL.revokeObjectURL(url); break; }
        const res = await audio.playUrl(url, it.id);
        if (res === "error") throw new Error("Could not play this file.");
        if (res === "ended") played++;
      } catch (e) { audio.setLoadingId(null); playFail(it, e); failedAt = it.id; break; }
      if (reviewStopRef.current) break;
      await sleep(Number(settingsRef.current.playGap) || 0);
    }
    const stopped = reviewStopRef.current;
    setReviewing(false);
    audio.setLoadingId(null);
    say(`Auto play ${failedAt ? `stopped at ${failedAt}` : stopped ? "stopped" : "finished"}: ${played} played${skipped ? `, ${skipped} not saved yet (skipped)` : ""}.`);
  }
  function stopReview() { reviewStopRef.current = true; audio.stopAudio(); }

  /* ---------------------------------------------------------------- generate + save */
  async function gen(it, ch, preview = false) {
    setPhase("generating");
    try {
      const [type, payload] = buildGenerate(settingsRef.current, it, ch);
      const r = await call(type, payload);
      pendingRef.current = r;
      say(`${it.id} generated (${r.seconds}s)`);
      script.setFailed((f) => { const n = { ...f }; delete n[it.id]; return n; });
      setPhase("ready");
      if (preview) playPending();
      return true;
    } catch (e) {
      script.setFailed((f) => ({ ...f, [it.id]: e.message }));
      say(`${it.id} generate failed: ${e.message}`);
      setPhase("idle");
      return false;
    }
  }

  async function dl(it) {
    setPhase("downloading");
    try {
      const dir = script.targetDir(it);
      const r = await call("api_save", { id: it.id, outputDir: dir });
      say(`${it.id} saved as ${r.name}${dir !== outRef.current ? ` in ${dir.split(/[\\/]/).pop()}` : ""}`);
      script.setDone((d) => ({ ...d, [it.id]: true }));
      setPhase("idle");
      return true;
    } catch (e) {
      script.setFailed((f) => ({ ...f, [it.id]: e.message }));
      say(`${it.id} download failed: ${e.message}`);
      setPhase("ready");
      return false;
    }
  }

  const nextPending = (from, d = script.done) => {
    const list = script.items;
    for (let i = from + 1; i < list.length; i++) if (!d[list[i].id]) return i;
    return Math.min(from + 1, list.length - 1);
  };

  async function keep() {
    const it = script.item;
    if (await dl(it)) {
      if (settingsRef.current.autoPlayPreview) playLine(it);
      if (settingsRef.current.advanceAfterKeep) script.setCur(nextPending(script.cur, { ...script.done, [it.id]: true }));
    }
  }

  function skip() { setPhase("idle"); script.setCur(nextPending(script.cur)); }

  /* ---------------------------------------------------------------- group lines (per-character takes + mix) */
  async function makeTake(it, ch) {
    if (!outRef.current) return say("Choose an output folder first.");
    setTakeKey(`${it.id}|${ch}`);
    await gen(it, ch, true);
  }

  async function saveTake(it, ch) {
    setPhase("downloading");
    try {
      const r = await call("api_save", { id: `${it.id}__${ch}`, outputDir: joinPath(outRef.current, TAKES_DIR) });
      say(`${it.id} · ${ch} saved as ${r.name}`);
      script.setTakes((t) => ({ ...t, [it.id]: [...new Set([...(t[it.id] || []), ch])] }));
      setTakeKey("");
      setPhase("idle");
      return true;
    } catch (e) {
      say(`${it.id} · ${ch} download failed: ${e.message}`);
      setPhase("ready");          // keep the generated audio so you can retry the save
      return false;
    }
  }

  async function mixTakes(it) {
    setMixingId(it.id);
    try {
      const r = await call("mix", {
        id: it.id,
        takesDir: joinPath(outRef.current, TAKES_DIR),
        outputDir: script.targetDir(it),
        order: characters,
        deleteTakes: settingsRef.current.clearTakesAfterMix,
      });
      script.setDone((d) => ({ ...d, [it.id]: true }));
      script.setFailed((f) => { const n = { ...f }; delete n[it.id]; return n; });
      say(`${it.id} mixed from ${r.takes} voices, saved as ${r.name}.`);
      await script.refreshTakes();
    } catch (e) {
      script.setFailed((f) => ({ ...f, [it.id]: e.message }));
      say(`${it.id} mix failed: ${e.message}`);
    } finally {
      setMixingId(null);
    }
  }

  /* ---------------------------------------------------------------- auto-run */
  async function runAuto() {
    if (!outRef.current) return say("Choose an output folder first.");
    stopRef.current = false;
    audio.stopAudio();
    setAuto(true);
    script.setEditing(null);
    let i = script.cur;
    const d = { ...doneRef.current };
    while (i < itemsRef.current.length && !stopRef.current) {
      const it = itemsRef.current[i];       // read fresh so edits to upcoming lines are used
      if (d[it.id]) { i++; continue; }
      if (!it.text.trim()) { say(`${it.id} has no text — skipped.`); i++; continue; }
      if (isBracket(it.text)) { say(`${it.id} is still a [bracketed] reaction — edit it into a sound tag first. Skipped.`); i++; continue; }
      if (it.character === "GRP") { say(`${it.id} is a group line. Record its voices by hand, then Mix. Skipped.`); i++; continue; }
      script.setCur(i);
      const tries = 1 + Number(settingsRef.current.retries || 0);
      let ok = false;
      for (let t = 0; t < tries && !stopRef.current; t++) {
        ok = (await gen(it)) && (await dl(it));
        if (ok) break;
        if (t < tries - 1) say(`${it.id} retrying (${t + 2}/${tries})…`);
      }
      if (!ok) {
        if (settingsRef.current.stopOnError || stopRef.current) break;
        i++; continue;
      }
      d[it.id] = true;
      const lo = Math.min(settingsRef.current.delayMin, settingsRef.current.delayMax);
      const hi = Math.max(settingsRef.current.delayMin, settingsRef.current.delayMax);
      await sleep(lo + Math.random() * (hi - lo));
      i++;
    }
    setAuto(false);
    say(stopRef.current ? "Auto-run stopped." : "Auto-run finished.");
  }
  const stopAuto = () => { stopRef.current = true; };

  return {
    phase, working, auto, reviewing, open, setOpen, takeKey, mixingId,
    gen, keep, skip, playLine, playPending, playTake, makeTake, saveTake, mixTakes,
    runAuto, stopAuto, runReview, stopReview,
  };
}
