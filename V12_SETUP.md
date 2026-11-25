# V12 — Viral Editor & Social Studio

This release extends the V11 archive, not a live checkout of your GitHub repo. It preserves the 1080×1920 Gaming Pro layout (gameplay 1080×1344 above streamer 1080×576), Smart Replay, the loopback web application, public YouTube and Instagram publishing, and separate platform upload ledgers. No new runtime dependencies are required. There is no migration of credentials or output files. Back up locally modified code before installing.

## Upgrade on an existing M4 Mac

Stop the running app (Ctrl+C). In Terminal, inside the project containing app.py, start.sh, and .venv:

```bash
pwd
ls app.py start.sh requirements.txt
UPDATE_DIR="$(mktemp -d)"
unzip ~/Downloads/m4-unified-studio-v12-viral-social.zip -d "$UPDATE_DIR"
rsync -av --exclude='.gitignore' "$UPDATE_DIR/m4-unified-studio/" ./
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip check
open -a Ollama
ollama list
bash start.sh
```

Do not use rsync --delete. Keep your existing .gitignore (including .venv/, output/, logs, archives, credentials and generated video files). Open http://127.0.0.1:8000 and refresh with Cmd+Shift+R. Keep the Mac awake and Ollama running while processing. Verify existing connections with `python publisher.py status` and `python instagram_publisher.py status`. Do not commit access tokens or raw audience chat exports. The app listens on loopback only; do not expose it publicly.

If required, install the system tools and models:

```bash
brew install python@3.12 ffmpeg-full deno
brew install --cask ollama-app
ollama pull qwen3:4b-instruct
ollama pull gemma3:4b
```

The vision model is optional but recommended for gameplay with little speech. Without it, the viral selector and reviewer can assess speech and measured signals, but cannot establish purely visual gameplay context. For optional CPU transcription: `python -m pip install -r requirements-cpu.txt`; launch with `SHORTS_ASR_BACKEND=cpu bash start.sh`. Use the CPU video encoder checkbox if VideoToolbox fails. No OpenAI paid API is required.

## Recommended session settings

Gaming Pro + Gaming Highlights; Smart Replay on; full replay scan on; minimum score 85; independent review on (new default in UI); captions off or word highlight; alternate version off for the first test; publishing disabled for the first test. For non-gaming, select Creator or Clean as the base and one of the non-gaming Viral presets. Strict Gaming Pro rejects sources without a reliable separate facecam. It cannot recover gameplay obscured by an embedded facecam.

Completed replays can scan all available footage with overlapping low-resolution previews, fetch only chosen time ranges, and rank qualifying clips for publishing at the end. Live sessions use closed segments and produce clips incrementally; a complete ranking of future moments is impossible. No automatic full-source fallback in Smart Replay. Actual partial downloads depend on source formats and access permissions.

## New: independent editorial review

Enable the checkbox under Viral AI editor (checked by default). The existing selection model first scores windows using the seven exact requested weights (25/25/15/10/10/10/5). The new editorial_review.py performs a second local-model pass on the acquired candidate using only in-range dialogue and optional visual snapshots, not the earlier score. It independently evaluates the opening, payoff, metadata grounding and each rating dimension. Reject if the model reports weak context, unsupported metadata, insufficient evidence or a final score below your configured threshold. The reassessed score replaces the first-pass score in the exported manifest, dashboard ranking and automatic publishing threshold. The first score is retained separately for comparison. Actual model judgments are not factual proof and are not calibrated predictions of future views. The review checks the actual acquired candidate before editing, not the final edited storyline; technical QA checks the final video.

Review is optional to retain the original V11 selection flow. Turning it on increases inference time and can reduce the number of accepted clips. On CLI, use `--viral-review` with `--viral-preset gaming` (or another preset). Model transport errors are visible session errors, not fabricated scores. Invalid or rejected review results skip the candidate. Visual analysis uses bounded snapshots, not continuous video understanding.

## New: session chat export

For authorized audience chat, enter the full local path to a JSONL file (max 25 MB) under Viral AI editor. Each line has `time` in seconds and `message`, for example:

```json
{"time":18.7,"message":"That timing was unexpected"}
{"time":21.1,"message":"What a reaction"}
```

Times must align with the source replay. For an ongoing capture, enable the capture-clock checkbox only when times are relative to the beginning of this capture session. A chat file with the wrong clock could mislead selection; do not use it. CLI: `--chat-file /absolute/path/chat.jsonl --chat-capture-clock` (omit the clock switch for replay). Older `SHORTS_CHAT_JSONL` environment variable remains supported. No live-chat API polling or downloader is provided. Messages are untrusted evidence, never instructions, and are sent only to the local Ollama model. Remove personal data before use; transcripts/selection results may be cached locally.

## New: saved-session library and quality evidence

In Highlights, click Refresh saved sessions, then select a session. The loopback API reads actual manifests and existing media files from output/; missing files are omitted. It lists up to 100 saved sessions and keeps old clips available after restart. Existing automatic or manual upload receipts are displayed when present. Select Current session to return to the live monitor. Upload controls still require explicit account verification, rights, audience and confirmation. Alternative videos and caption corrections remain review-only to avoid accidental duplicate uploads. Five title suggestions are requested from the model; fewer may be available after deduplication. A title picker now fills the existing manual YouTube upload title field. All generated metadata is editable before manual publishing.

Word timestamps must fit within the output duration (small container timing tolerance) and be chronological. The transcript overlap check now uses in-range words when available, rather than treating words outside the cut as missing. Available confidence and timing checks do not prove subtitle accuracy or lip synchronization. Captions remain optional; extra manual language choices are available, with the same Whisper ASR backend. Select a suitable installed font with `SHORTS_CAPTION_FONT` if scripts display incorrectly. No emoji assets are included and automatic overlay glyph coverage is not guaranteed.

## Analytics

Authorized YouTube Analytics and CSV import remain available. New feedback groups by recorded topic/category, style, caption style, hook band and actual CTA display when known, rather than equating generated CTA text with a displayed overlay. CSV optional columns: style, caption_style, hook_band, cta_present (true/false or 1/0), topic. Required columns: video_id,duration,views,retention,average_view_duration,likes,comments,shares,subscribers_gained. Groups require at least three measured videos with at least 100 views each and retention data. When sufficient subscriber counts exist, feedback includes observed subscribers gained per 1,000 views. These are descriptive statistics, not causal conclusions. Historical records without actual CTA-display evidence are unknown. Refreshing API data or importing CSV replaces the single-channel cache as in V11. Instagram performance analytics and continuous model retraining are not implemented.

## Existing feature configuration

- `SHORTS_VISION_MODEL=gemma3:4b` (default; empty disables optional vision).
- `SHORTS_ASR_BACKEND=cpu` and `SHORTS_CPU_MODEL=small` (optional). ASR cache keys now include CPU model selection.
- `SHORTS_AUTHORIZED_MUSIC=/absolute/path/music.wav` and `SHORTS_AUTHORIZED_SFX=/absolute/path/effect.wav` (optional rights-cleared local files only). Existing ducking, impact effect, highpass/noise filtering, compression and limiting remain.
- `SHORTS_CAPTION_FONT=Arial` (default, choose locally installed Unicode-capable font where needed).
- `SHORTS_CHAT_JSONL=/absolute/path/chat.jsonl` (legacy optional chat input).
- Existing model and ASR caches are under `~/.config/m4-shorts-studio/` with bounded entry counts. Existing credentials and upload ledgers stay in that directory.

## Implementation coverage and remaining work

Implemented in V11 and retained: contextual model selection from transcript, optional vision and measured features; exact weighted scoring; ten presets; conservative framing and gaming split; jump cuts, isolated filler removal, zooms, optional karaoke/bold/minimal captions, optional hook and end CTA/comment overlays; local audio enhancements and user-supplied music/effects; metadata, thumbnail frame, alternative presentation/speed; technical quality validation, per-platform duplicate protection, progress/ETA, hardware encoding, CPU option, caches, incremental capture, selective downloads and authorized YouTube analytics. V12 adds actual candidate second-pass review, chat selection via UI, saved-session library, caption timestamp checks, extra language choices, title selection and more reliable measured performance grouping.

Partial or not implemented: reliable active-speaker diarization; game-specific event recognition; automatic live-chat retrieval; semantic redundancy removal; independent verification of full final story after editing; model-calibrated audience predictions; automatic teaser insertion or arbitrary reordered narratives; keyword-semantic/emoji selection in captions (existing word highlighting is time-based); guaranteed smooth loops (similarity/recommendation only); multiple distinct alternate layouts/durations beyond existing alternate style and optional 1.04× speed; comprehensive visual/copyright/lip-sync checks; automatic copyright clearance; full autonomous repair after quality rejection; simultaneous multi-session batch queue; Instagram analytics; continual learning/training. Do not treat this as fully production-certified. Only use material you own or have permission to acquire and publish. No guaranteed viral reach.

## Tests

`python -m unittest discover -v` passed 66 tests in the build environment: 60 original V11 tests and six new V12 tests. Actual FFmpeg render checks ran; local model and publishing tests use mock responses. Python compilation and JavaScript syntax checks passed. Browser navigation was blocked by environment policy; no end-to-end browser verification was completed. Run a short local authorized sample with auto publishing off, verify 70/30 framing and the two scores, preview captions and metadata, restart the app and select the saved session. Verify both accounts, then manually test one upload to each before enabling automatic publishing. M4 acceleration, actual model results, actual YouTube acquisition and live public uploads remain unverified here.
