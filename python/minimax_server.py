"""
MiniMax TTS automation engine for the Electron app.

Protocol (same as your audio-segmenter server.py):
  request : {"id": 1, "type": "...", "payload": {...}}
  response: {"id": 1, "ok": true, "result": {...}} | {"id": 1, "ok": false, "error": "..."}

Types: ping, load_script, connect, diagnose, generate, download, list_done, read_audio, write_text, read_text, disconnect

Playwright attaches to a Chrome you (or the app) started with --remote-debugging-port,
so you log in to MiniMax yourself and nothing here touches your credentials.
"""
import base64
import json
import re
import shutil
import sys
import time
import traceback
from pathlib import Path

# stdout is reserved for the protocol; stray prints go to stderr.
PROTO = sys.stdout
sys.stdout = sys.stderr
for stream in (sys.stdin, PROTO, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import audio_engine as engine  # noqa: E402  (your parser: PDF + Word, IDs, segments)
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout  # noqa: E402

DEFAULT_URL = "https://www.minimax.io/audio/text-to-speech"
AUDIO_EXTS = (".mp3", ".wav", ".m4a", ".flac", ".ogg")
GENERATE_TIMEOUT = 180   # seconds to wait for a clip to finish generating


def send(obj):
    PROTO.write(json.dumps(obj, ensure_ascii=False) + "\n")
    PROTO.flush()


def load_selectors():
    return json.loads((ROOT / "minimax_selectors.json").read_text(encoding="utf-8"))


def safe_name(sid):
    return re.sub(r"[^A-Za-z0-9._-]", "_", sid)


class Runner:
    def __init__(self):
        self.pw = None
        self.browser = None
        self.page = None

    # ---------------------------------------------------------------- browser
    def connect(self, p):
        port = int(p.get("port") or 9222)
        url = p.get("url") or DEFAULT_URL
        if self.pw is None:
            self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        ctx = self.browser.contexts[0] if self.browser.contexts else self.browser.new_context()
        pages = ctx.pages
        page = (next((x for x in pages if "minimax" in x.url and "text-to-speech" in x.url), None)
                or next((x for x in pages if "minimax" in x.url), None))
        if page is None:
            page = ctx.new_page()
            page.goto(url)
        page.bring_to_front()
        self.page = page
        return {"url": page.url, "title": page.title()}

    def disconnect(self, _p):
        try:
            if self.browser:
                self.browser.close()      # only detaches from a CDP browser; Chrome stays open
        finally:
            self.browser = self.page = None
            if self.pw:
                self.pw.stop()
                self.pw = None
        return {"ok": True}

    def _page(self):
        if not self.page or self.page.is_closed():
            raise RuntimeError("Not connected to the browser. Click Connect first.")
        return self.page

    # ---------------------------------------------------------------- finding things
    def _visible(self, selectors, largest=False):
        page = self._page()
        for sel in selectors:
            try:
                found = []
                for el in page.locator(sel).all()[:12]:
                    if el.is_visible():
                        box = el.bounding_box() or {"width": 0, "height": 0}
                        found.append((box["width"] * box["height"], el))
                if found:
                    return max(found, key=lambda t: t[0])[1] if largest else found[0][1]
            except Exception:
                continue
        return None

    def _wait_visible(self, selectors, what, timeout=8.0, **kw):
        end = time.time() + timeout
        while time.time() < end:
            el = self._visible(selectors, **kw)
            if el:
                return el
            time.sleep(0.25)
        raise RuntimeError(f"Could not find the {what} on the page. Run 'Diagnose page' and edit python/minimax_selectors.json.")

    def _audio_sig(self):
        return self._page().evaluate(
            "() => [...document.querySelectorAll('audio')].map(a => a.currentSrc || a.src).join('|')")

    def _is_busy(self, sel):
        try:
            btn = self._visible(sel["generate"])
            if btn is None:
                return True                       # button swapped for a spinner / stop button
            if btn.is_disabled():
                return True
            text = (btn.inner_text() or "").lower()
            return any(w in text for w in sel["busyText"])
        except Exception:
            return True

    # ---------------------------------------------------------------- generate
    def generate(self, p):
        sel = load_selectors()
        text = (p.get("text") or "").strip()
        if not text:
            raise RuntimeError("This line has no dialogue text.")
        page = self._page()
        page.bring_to_front()

        box = self._wait_visible(sel["textInput"], "text box", largest=True)
        box.click()
        box.fill(text)

        before = self._audio_sig()
        btn = self._wait_visible(sel["generate"], "Generate button")
        end = time.time() + 20
        while btn.is_disabled() and time.time() < end:   # wait for the text to register
            time.sleep(0.3)
        btn.click()
        clicked = time.time()

        seen_busy = False
        deadline = clicked + GENERATE_TIMEOUT
        while time.time() < deadline:
            time.sleep(0.5)
            busy = self._is_busy(sel)
            seen_busy = seen_busy or busy
            changed = self._audio_sig() != before
            if not busy and (changed or seen_busy) and time.time() - clicked > 1.5:
                time.sleep(1.0)                  # let the player / download button settle
                return {"seconds": round(time.time() - clicked, 1)}
        raise RuntimeError(
            f"Timed out after {GENERATE_TIMEOUT}s waiting for audio. Check the browser "
            "(login, quota, captcha) or the selectors.")

    # ---------------------------------------------------------------- download

    # The download control is an icon-only button at the right end of the player bar
    # (after the 00:00 ... 00:02 timer and the thumbs up/down icons). Find it by position.
    PLAYER_ICON_JS = """() => {
      document.querySelectorAll('[data-tts-dl]').forEach(e => e.removeAttribute('data-tts-dl'));
      const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
      const times = [...document.querySelectorAll('*')].filter(e =>
        e.children.length === 0 && /^\\d{1,2}:\\d{2}$/.test((e.textContent || '').trim()) && vis(e));
      if (!times.length) return false;
      const dur = times.reduce((a, b) => b.getBoundingClientRect().left > a.getBoundingClientRect().left ? b : a);
      const dr = dur.getBoundingClientRect();
      let bar = dur;
      while (bar.parentElement && bar.getBoundingClientRect().width < 500) bar = bar.parentElement;
      const found = new Map();
      bar.querySelectorAll('*').forEach(el => {
        if (!vis(el)) return;
        const r = el.getBoundingClientRect();
        if (r.left <= dr.right || r.width > 80 || r.height > 80) return;
        const clickable = getComputedStyle(el).cursor === 'pointer' || /^(button|a)$/i.test(el.tagName) ||
                          el.getAttribute('role') === 'button';
        if (clickable) found.set(el, r.right);
      });
      if (!found.size) {
        bar.querySelectorAll('svg,img,[role=img]').forEach(n => {
          if (!vis(n)) return;
          const r = n.getBoundingClientRect();
          if (r.left > dr.right && r.width < 80) found.set(n.closest('button,[role=button],a') || n.parentElement, r.right);
        });
      }
      if (!found.size) return false;
      const best = [...found.entries()].reduce((a, b) => b[1] > a[1] ? b : a)[0];
      best.setAttribute('data-tts-dl', '1');
      return true;
    }"""

    LEARN_JS = """() => {
      if (window.__ttsRec) return;
      window.__ttsRec = true; window.__ttsLast = null;
      const css = el => { const parts = [];
        while (el && el.nodeType === 1 && el !== document.documentElement) {
          let i = 1, s = el; while ((s = s.previousElementSibling)) i++;
          parts.unshift(el.tagName.toLowerCase() + ':nth-child(' + i + ')'); el = el.parentElement; }
        return 'html > ' + parts.join(' > '); };
      document.addEventListener('click', e => {
        if (!e.isTrusted) return;               // ignore script-made clicks (hidden download links)
        let t = e.target; const svg = t.closest && t.closest('svg'); if (svg) t = svg;
        if (!window.__ttsLast) window.__ttsLast = css(t); }, true);
    }"""

    def _learned(self):
        try:
            return json.loads((ROOT / "learned_download.json").read_text("utf-8")).get("selector")
        except Exception:
            return None

    def _save_learned(self, selector):
        (ROOT / "learned_download.json").write_text(json.dumps({"selector": selector}), encoding="utf-8")

    def _download_button(self, sel, timeout=8.0):
        page = self._page()
        end = time.time() + timeout
        while time.time() < end:
            learned = self._learned()
            if learned:
                try:
                    loc = page.locator(learned).first
                    if loc.is_visible():
                        return loc
                except Exception:
                    pass
            try:
                if page.evaluate(self.PLAYER_ICON_JS):
                    return page.locator("[data-tts-dl='1']").first
            except Exception:
                pass
            el = self._visible(sel["download"])
            if el:
                return el
            time.sleep(0.25)
        raise RuntimeError("download icon not found")

    def _clear_old(self, out, sid):
        for old in out.glob(sid + ".*"):          # regeneration replaces the previous take
            if old.suffix.lower() in AUDIO_EXTS:
                old.unlink()

    def _capture_download(self, out, sid, trigger=None, timeout=15):
        """Wait for a download (started by `trigger`, or by you) and save it as <ID>.<ext>.
        Catches both Playwright's download event and a new file in the Downloads folder."""
        page = self._page()
        got = []

        def on_download(d):
            got.append(d)
        page.on("download", on_download)
        dl_dir = Path.home() / "Downloads"
        snap = lambda: set(dl_dir.iterdir()) if dl_dir.is_dir() else set()
        before = snap()
        try:
            if trigger:
                trigger(got)
            end = time.time() + timeout
            while time.time() < end:
                if got:
                    dl = got[0]
                    ext = Path(dl.suggested_filename).suffix.lower() or ".mp3"
                    self._clear_old(out, sid)
                    dest = out / f"{sid}{ext}"
                    dl.save_as(str(dest))
                    return dest
                for f in snap() - before:
                    if f.suffix.lower() in AUDIO_EXTS:
                        time.sleep(0.8)
                        self._clear_old(out, sid)
                        dest = out / f"{sid}{f.suffix.lower()}"
                        shutil.move(str(f), str(dest))
                        return dest
                page.wait_for_timeout(300)        # also lets Playwright deliver events
        finally:
            page.remove_listener("download", on_download)
        raise RuntimeError("no download started")

    FORMAT_JS = """(fmt) => {
      document.querySelectorAll('[data-tts-fmt]').forEach(e => e.removeAttribute('data-tts-fmt'));
      const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
      const re = new RegExp('^\\\\s*' + fmt + '\\\\b', 'i');
      const c = [...document.querySelectorAll('body *')].filter(e => {
        const t = (e.innerText || '').trim(); return vis(e) && t.length < 40 && re.test(t); });
      if (!c.length) return false;
      const area = e => { const r = e.getBoundingClientRect(); return r.width * r.height; };
      c.sort((x, y) => area(x) - area(y));
      c[0].setAttribute('data-tts-fmt', '1'); return true;
    }"""

    CONFIRM_JS = """() => {
      document.querySelectorAll('[data-tts-confirm]').forEach(e => e.removeAttribute('data-tts-confirm'));
      const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
      const re = /^(download|confirm|ok|save|export|continue|next)$/i;
      const c = [...document.querySelectorAll('button,[role=button]')].filter(e => vis(e) && re.test((e.innerText || '').trim()));
      if (!c.length) return false;
      c[c.length - 1].setAttribute('data-tts-confirm', '1'); return true;
    }"""

    def _pick_format(self, sel, got):
        """After the download icon is clicked MiniMax asks MP3 or WAV: choose the preferred one,
        then press a confirm button if the dialog has one."""
        page = self._page()
        fmt = sel.get("preferredFormat", "MP3")
        end, picked = time.time() + 4, False
        while time.time() < end and not got:
            if page.evaluate(self.FORMAT_JS, fmt):
                page.locator("[data-tts-fmt='1']").first.click()
                picked = True
                break
            page.wait_for_timeout(200)
        if not picked:
            return                                # no prompt: the click started the download itself
        end = time.time() + 1.5
        while time.time() < end and not got:
            if page.evaluate(self.CONFIRM_JS):
                page.locator("[data-tts-confirm='1']").first.click()
                return
            page.wait_for_timeout(200)

    def _download_via_icon(self, sel, out, sid):
        btn = self._download_button(sel, timeout=5)

        def trigger(got):
            btn.click()
            self._pick_format(sel, got)
        return self._capture_download(out, sid, trigger, timeout=20)

    def _download_via_audio(self, out, sid):
        """Only works when the player uses a normal https audio URL (not a blob: stream)."""
        page = self._page()
        src = page.evaluate("""() => {
            const a = [...document.querySelectorAll('audio')].map(x => x.currentSrc || x.src).filter(Boolean);
            return a.length ? a[a.length - 1] : null; }""")
        if not src or src.startswith(("blob:", "data:")):
            raise RuntimeError("audio is a blob stream")
        r = page.context.request.get(src)
        if not r.ok or len(r.body()) < 1000:
            raise RuntimeError(f"audio URL gave HTTP {r.status}")
        ctype = r.headers.get("content-type", "").lower()
        ext = (".wav" if "wav" in ctype else ".m4a" if ("mp4" in ctype or "aac" in ctype)
               else ".ogg" if "ogg" in ctype else ".mp3")
        self._clear_old(out, sid)
        dest = out / f"{sid}{ext}"
        dest.write_bytes(r.body())
        return dest

    def _download_via_teaching(self, out, sid):
        """Last resort: you click the download icon once; the app saves that download and
        remembers the icon so later lines are fully automatic."""
        page = self._page()
        page.bring_to_front()
        page.evaluate(self.LEARN_JS)
        page.evaluate("window.__ttsLast = null")
        print("ACTION NEEDED: click the download icon in the MiniMax window now "
              "(waiting up to 90s). The app will remember it.", file=sys.stderr, flush=True)
        dest = self._capture_download(out, sid, trigger=None, timeout=90)
        try:
            last = page.evaluate("window.__ttsLast")
            if last:
                self._save_learned(last)
                print(f"Learned download icon: {last}", file=sys.stderr, flush=True)
        except Exception:
            pass
        return dest

    def download(self, p):
        sel = load_selectors()
        out = Path(p["outputDir"])
        out.mkdir(parents=True, exist_ok=True)
        sid = safe_name(p["id"])
        errors = []
        for name, fn in (("icon", lambda: self._download_via_icon(sel, out, sid)),
                         ("audio", lambda: self._download_via_audio(out, sid)),
                         ("teach", lambda: self._download_via_teaching(out, sid))):
            try:
                dest = fn()
                return {"file": str(dest), "name": dest.name}
            except Exception as e:
                errors.append(f"{name}: {str(e).splitlines()[0]}")
        raise RuntimeError("Download failed - " + " | ".join(errors))

    # ---------------------------------------------------------------- misc
    def diagnose(self, _p):
        return self._page().evaluate("""() => {
          const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
          const short = s => (s || '').replace(/\\s+/g, ' ').trim().slice(0, 60);
          return {
            url: location.href,
            buttons: [...document.querySelectorAll('button,[role=button]')].filter(vis).slice(0, 60).map(b => ({
              text: short(b.innerText), aria: b.getAttribute('aria-label'), title: b.title,
              disabled: b.disabled, cls: short(b.className && b.className.toString())})),
            textInputs: [...document.querySelectorAll('textarea,[contenteditable=true],[role=textbox]')].filter(vis).map(t => ({
              tag: t.tagName, placeholder: t.getAttribute('placeholder'), w: Math.round(t.getBoundingClientRect().width), h: Math.round(t.getBoundingClientRect().height)})),
            audioElements: [...document.querySelectorAll('audio')].map(a => (a.currentSrc || a.src || '').slice(0, 90)),
            playerIcons: (() => {
              const t = [...document.querySelectorAll('*')].filter(e => e.children.length === 0 && /^\\d{1,2}:\\d{2}$/.test((e.textContent || '').trim()) && vis(e));
              if (!t.length) return 'no 00:00 timer found';
              const dur = t.reduce((a, b) => b.getBoundingClientRect().left > a.getBoundingClientRect().left ? b : a);
              const dr = dur.getBoundingClientRect(); let bar = dur;
              while (bar.parentElement && bar.getBoundingClientRect().width < 500) bar = bar.parentElement;
              return [...bar.querySelectorAll('*')].filter(e => { const r = e.getBoundingClientRect(); return vis(e) && r.left > dr.right && r.width < 80; })
                .map(e => ({tag: e.tagName, cursor: getComputedStyle(e).cursor, x: Math.round(e.getBoundingClientRect().left), cls: short(e.className && e.className.toString())}));
            })()
          };
        }""")


def load_script(p):
    path = Path(p["path"])
    if not path.exists():
        raise FileNotFoundError(f"Script not found: {path}")
    entries, segments = engine.load_script_full(path)
    if not entries:
        raise RuntimeError("No dialogue IDs found in the script.")
    seg_of = {sid: sg["label"] for sg in segments for sid in sg["ids"]}
    items = [{"id": sid, "text": text, "segment": seg_of.get(sid, "")} for sid, text in entries.items()]
    empty = [i["id"] for i in items if not i["text"]]
    return {"items": items, "segments": [s["label"] for s in segments], "empty": empty}


def list_done(p):
    folder = Path(p["outputDir"])
    if not folder.is_dir():
        return {"done": []}
    ids = {f.stem for f in folder.iterdir() if f.suffix.lower() in AUDIO_EXTS}
    return {"done": sorted(ids)}


MIME = {".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4", ".flac": "audio/flac", ".ogg": "audio/ogg"}
MAX_PREVIEW_BYTES = 40 * 1024 * 1024


def read_audio(p):
    """Return a saved clip (base64) so the app can play it. Looks for <id>.<audio ext> in each folder given."""
    sid = safe_name(p["id"])
    for d in p.get("dirs") or []:
        folder = Path(d)
        if not folder.is_dir():
            continue
        for f in sorted(folder.iterdir()):
            if f.stem == sid and f.suffix.lower() in AUDIO_EXTS:
                size = f.stat().st_size
                if size > MAX_PREVIEW_BYTES:
                    raise RuntimeError(f"{f.name} is too large to preview ({size // 1048576} MB)")
                return {"found": True, "name": f.name, "path": str(f), "size": size,
                        "mime": MIME.get(f.suffix.lower(), "audio/mpeg"),
                        "data": base64.b64encode(f.read_bytes()).decode("ascii")}
    return {"found": False}


def write_text(p):
    """Write a small text file (the project/session file). Written to a temp file first so a crash can't leave it half-written."""
    path = Path(p["path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    if p.get("create_only") and path.exists():
        return {"exists": True, "path": str(path)}
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(p["text"], encoding="utf-8")
    tmp.replace(path)
    return {"path": str(path)}


def read_text(p):
    path = Path(p["path"])
    if not path.is_file():
        return {"found": False}
    return {"found": True, "text": path.read_text(encoding="utf-8")}


R = Runner()
HANDLERS = {
    "ping": lambda _p: {"ok": True},
    "load_script": load_script,
    "list_done": list_done,
    "read_audio": read_audio,
    "write_text": write_text,
    "read_text": read_text,
    "connect": R.connect,
    "disconnect": R.disconnect,
    "diagnose": R.diagnose,
    "generate": R.generate,
    "download": R.download,
}


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req_id = None
        try:
            req = json.loads(line)
            req_id = req.get("id")
            handler = HANDLERS.get(req.get("type"))
            if handler is None:
                raise ValueError(f"Unknown request type: {req.get('type')!r}")
            send({"id": req_id, "ok": True, "result": handler(req.get("payload") or {})})
        except Exception as exc:
            traceback.print_exc(file=sys.stderr)
            send({"id": req_id, "ok": False, "error": f"{type(exc).__name__}: {exc}"})


if __name__ == "__main__":
    main()