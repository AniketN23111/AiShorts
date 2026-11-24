# AI Shorts Studio V8 — Gaming Pro

## Upgrade an existing V7.1 installation (Apple M4, macOS)

Stop the server (Ctrl+C). Back up source files before overwriting. The ZIP contains no OAuth credentials, tokens, media, or virtual environment. It keeps the existing folder name to preserve `.venv` and `output`.

```bash
cd ~/Downloads/AI_Shorts
cp -R m4-unified-studio m4-unified-studio-backup-v71 # may be large; optional if already backed up
unzip -o ~/Downloads/m4-unified-studio-v8.zip
cd m4-unified-studio
source .venv/bin/activate
python -m pip install -U 'yt-dlp[default]'
python -m pip install -r requirements.txt
python -m pip check
open -a Ollama
bash start.sh
```

If installing fresh, first install Homebrew from https://brew.sh, then `brew install python@3.12 ffmpeg-full deno`, `brew install --cask ollama-app`, `open -a Ollama`, `ollama pull qwen3:4b-instruct`, and run `python3.12 -m venv .venv` before activating. If FFmpeg Full is unavailable, install the normal Homebrew FFmpeg; Gaming Pro does not use libass. The existing launch script adds the ffmpeg-full bin directory to PATH when installed. Open http://127.0.0.1:8000 in Chrome/Safari; hard-refresh Cmd+Shift+R. MLX Whisper downloads its model on first use. `opencv-python-headless` installs a native arm64 wheel on supported macOS/Python combinations; use native arm64 Python 3.12 (not Rosetta).

## Recommended settings

Gaming Pro (default), Auto detect, Smart Replay on, full replay fallback off, 120-second analysis interval, score 85, 9:16 export, captions off, raw recording retention off. Clip target 6 stops after the first six accepted clips; Unlimited examines the source until completion/stopped. Game and streamer names are optional user-provided factual metadata, never guessed from visuals. Gaming Pro always uses vertical 1080x1920 and disables captions regardless of legacy layout/subtitle settings. Older clean/dynamic editing styles remain available for local exports.

For a facecam in an unusual position use manual normalized `x,y,width,height` fractions such as `0.75,0.03,0.24,0.30` (example only; adjust to the actual video). Auto mode looks for a persistent frontal face near a screen edge, estimates a crop, then interpolates the detected position within each shot. If none is found, a fitted full gameplay frame with blurred fill avoids losing HUD information. The bottom gameplay panel retains the original frame, so its embedded facecam can remain visible. It does not reconstruct pixels hidden by the original facecam. This is face detection and geometric tracking, not a trained streamer-specific tracker; small, angled, obstructed or animated faces can be missed.

## Public publishing

Use only content you own or have permission to acquire/edit/publish, in compliance with YouTube's terms. Existing desktop OAuth credentials under `~/.config/m4-shorts-studio` are reused. To reconnect: `python publisher.py connect`, then `python publisher.py status`. Click Check channel, choose audience, enable automatic PUBLIC uploads, confirm the session-level authorization and set a daily cap. Default cap: six per local calendar day. No private/unlisted fallback is requested. Public upload runs only after media validation and score threshold. Manual public publishing in Gaming Pro is also available after review; it uses a score threshold of 85 and cap of six. YouTube may reject/restrict publication independently of the API request; the receipt records the returned visibility or marks it unconfirmed. Check YouTube Studio for processing, policy and rights status.

Upload uses Google API resumable requests with bounded retries. A durable, locked channel-specific ledger in `~/.config/m4-shorts-studio/public-uploads.json` prevents exact-file duplicates and overlapping replay/local source ranges; it also blocks duplicate titles. Live timestamps are relative to the session; across restarted live sessions only exact-file duplicates are guaranteed to be detected. Re-encoded near duplicates, edits made before V8 and different local copies are not guaranteed to be detected. Never delete ledger records just to retry an ambiguous upload. If an upload outcome is uncertain, inspect YouTube Studio before resolving it manually; automatic retry of a new insert would risk creating duplicates. The ledger records an upload reservation before the API request, even if a process stops; uncertain reservations require manual reconciliation. Stop does not cancel an already in-flight public upload. The publisher does not independently detect copyright/permission; the user's explicit authorization is required. Rendered MP4s and receipts are kept; raw segments and smart work files are deleted by default.

Google documentation: https://developers.google.com/youtube/data/reference/rest/v3/videos/insert and https://developers.google.com/youtube/data/guides/uploading_a_video

## Optional Analytics

Enable YouTube Analytics API in the same Google Cloud project, add scope `https://www.googleapis.com/auth/yt-analytics.readonly`, then run `python publisher.py connect-analytics` (it includes existing upload/read scopes). Run `python analytics_feedback.py` or tick the optional once-per-day refresh in the dashboard when using automatic publishing. It samples up to 20 recent V8 uploads, uses average view percentage for videos with at least 100 views, requires three samples per duration band, and feeds the measured summary to the local selection model. If missing, stale, not authorized or insufficient, no new adjustment is made. This is directional feedback, not online model training, and may not represent causal effects. Reauthorization may be needed for a testing OAuth app.

## How the pipeline works

Live: V7.1 FFmpeg acquisition, closed segments, overlapping boundary context; a single AI/encoder worker and hardware VideoToolbox when available, with software fallback. Local file: existing incremental capture. Completed replay: low-resolution <=360p audiovisual preview ranges with overlap, local motion/audio/ASR signals, Ollama selects candidates, HD only for selected time ranges. Legacy modes retain audio-first replay. No automatic full-file download in Smart Replay. Seeking may transfer earlier data internally or be unsupported; actual bandwidth and time depend on source. If access denied or seeking fails, use authorized local media or another compatible source. Keep raw saves selected ranges only. Live capture stops if free disk drops below 2 GiB. No general download bandwidth cap or cross-session live reconnection supervisor is implemented.

Gaming selection uses low-rate visual motion, darkness, face presence, RMS audio and speech. It is not a game-specific semantic vision model; clutches, emotions, loading screens and event identity cannot be reliably identified from these proxies alone. It supports speechless action through the visual signal and applies a visual alignment check on fetched clips without dialogue anchors. The LLM assigns editorial scores; scores are not probabilities of views. Dynamic editor uses silence + low motion trimming, reaction punch-ins, shot cuts, subtle impact shake, light grading/sharpening, compression, audio fades and loudness normalization. It avoids invented reorder or distracting transitions. Natural looping is a selection preference, not guaranteed or forced; no optical-flow seamless-loop generation. No text overlays or captions are produced in Gaming Pro. Quality gate checks H.264/AAC, resolution, duration, full decode and audio level before publishing; it does not determine subjective video quality or legal rights.

Logs: `output/<session>/run.log`, `capture.log`, `download.log`, `status.json`, `*/clips.json`. The UI redacts signed Googlevideo URLs in displayed logs; raw files may include temporary signed URLs, so do not share raw logs publicly. `public-uploads.json` is the durable upload log. Use `python -m unittest discover -v` to run tests. Tests use synthetic video and mock YouTube/Ollama; on-Mac MLX, Apple GPU encoding, real YouTube capture, real OAuth and public publishing require verification. No guarantee of reach, monetization, views or platform availability.
