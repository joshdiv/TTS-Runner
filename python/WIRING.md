# Hooking minimax_api.py into minimax_server.py

1. Copy `minimax_api.py` next to `minimax_server.py` and add `import minimax_api`.

2. Add two request types to the dispatcher, next to `eleven_voices` / `eleven_generate`.
   Store the audio exactly the way `eleven_generate` does (the same "pending" variable),
   so the existing `api_save` handler keeps working for both engines:

   ```python
   elif t == "minimax_voices":
       return minimax_api.voices(p)

   elif t == "minimax_generate":
       audio, info = minimax_api.synthesize(p)
       # >>> same assignment eleven_generate uses to remember the last audio, e.g.:
       # PENDING["audio"] = audio; PENDING["ext"] = info["ext"]
       return {"data": base64.b64encode(audio).decode(), "mime": info["mime"], "seconds": info["seconds"]}
   ```

3. Delete the Playwright pieces: the `connect`, `generate`, `download` and `diagnose` handlers,
   the `playwright` import and browser/page globals. `playwright` can come out of requirements.

4. Electron: `window.api.launchChrome` is no longer called. You can remove it from
   preload and main when convenient. Nothing in the UI uses it any more.
