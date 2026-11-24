# AI Shorts Studio V10 — Viral Studio

This is an upgrade of the supplied V9.1 ZIP, not a checkout of your current GitHub repo. Preserve any local modifications before installing. The original V9.1 editor remains selectable (`Original V9.1 editor`). No production model calls or real YouTube uploads were performed in the test environment.

## Upgrade on Apple Silicon

Stop the running application. From the parent of your existing `m4-unified-studio` folder, back up any modified code or commit it to Git. Extract the archive over the existing folder. If your local checkout is named `AISHORTS` or something else, extract to a separate folder and copy the code files into your checkout instead. Never replace your local `.venv`, OAuth configuration or `output/` folder. The ZIP does not contain them.

```bash
cd /path/to/m4-unified-studio
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip check
open -a Ollama
ollama pull qwen3:4b-instruct
ollama pull gemma3:4b  # optional vision model, strongly recommended for visual-only gameplay
bash start.sh
```

For a new checkout, use `python3.12 -m venv .venv` first. Install missing tools with `brew install python@3.12 ffmpeg-full deno`. Use the existing Ollama installation. Open http://127.0.0.1:8000 and hard-refresh the page. If the server says the model is missing, check `ollama list`. Existing OAuth tokens under `~/.config/m4-shorts-studio` remain untouched.

## First session

- Paste an authorized public YouTube link or choose an authorized local video.
- Editing style: Gaming Pro retains gameplay top / streamer bottom, 50/50. It skips unreliable facecams and full-screen streamer scenes. It overrides the selected Viral preset to gaming. For other presets, select Creator or Clean as the base editing style.
- Viral preset: Gaming Highlights is selected initially. Automatic AI Style delegates style choice to the model for non-Gaming-Pro sessions. Original V9.1 editor disables all new Viral processing.
- Smart Replay: enabled when selected, requests bounded low-resolution AV sections and only downloads HD candidate ranges. Actual network transfer depends on seek support. Native full-download fallback remains a separate choice. DRM/access denials are not bypassed.
- Score: start at 85. Scores are weighted subjective AI assessments; they are not view/retention estimates calibrated against outcomes. Some sessions will have no accepted clips.
- Full scan: on for V10 replay. It scans the entire selected replay duration, incrementally exports every qualifying clip, and ranks the collection by score. The clip target in this mode caps automatic uploads, not the number of local exports. Public uploads, if authorized, happen after full scan. Ongoing live streams retain incremental capture and use the original clip target; an indefinite stream cannot be globally ranked until it ends. A stopped or failed replay does not auto-publish the ranked batch.
- Captions: off initially to preserve the previous explicit no-text gaming preference. Select Word highlight, Bold phrases or Minimal phrases to enable. Word-level times are re-transcribed on the edited video clock. Optional hook/CTA overlays are separate. They stay off unless selected. Captions are kept inside the portrait safe region. Corrected captions render a review-only copy without modifying the original or uploaded Short. One correction per original timed word; changing timing or word count is not supported.
- Alternate: optional second local version using different caption presentation, alternate hook/CTA and 4% faster pacing for clips long enough. Only the primary is eligible for uploading. If no safe difference is possible or validation fails, no alternate is returned. Compare in the clip's Viral details panel.
- Disable auto-public for the first test. Then check channel, confirm rights and audience, and explicitly enable public publishing if satisfied. Non-gaming Viral exports are now eligible after the same validation and consent gates. Daily limit and upload ledger remain enforced.

## Optional local configuration

Set in Terminal before running `bash start.sh` (the shell environment is passed to the worker). Do not paste credentials into this file or into the UI.

| Variable | Default | Meaning |
|---|---|---|
| SHORTS_VISION_MODEL | gemma3:4b | Local Ollama vision model; set empty to disable. Eight timestamped snapshots per window. If missing/fails, speech + measured motion/audio still work, but speechless highlights without visual evidence are rejected. |
| SHORTS_ASR_BACKEND | mlx | Set `cpu` to request faster-whisper. Optional dependency: `python -m pip install -r requirements-cpu.txt`. MLX import/runtime failure attempts CPU fallback when installed. |
| SHORTS_CPU_MODEL | small | faster-whisper model name. First run downloads model weights. |
| SHORTS_CAPTION_FONT | Arial | Installed font name; choose a script-appropriate font for Marathi/Hindi (e.g. Kohinoor Devanagari if installed). Rendering depends on font availability. |
| SHORTS_AUTHORIZED_MUSIC | unset | Absolute path to original/licensed/authorized local audio. Loops underneath voice at low gain with sidechain ducking. Do not set unless you have the rights. |
| SHORTS_AUTHORIZED_SFX | unset | Local authorized sound effect; short, quiet effect at model-suggested impact timestamp mapped onto the edited timeline. No remote audio downloads. |
| SHORTS_CHAT_JSONL | unset | Optional creator-authorized chat export for replay with one JSON object per line: `{"time":12.5,"message":"..."}`. Time is seconds from source start. Only relevant bounded samples used; no automatic live chat retrieval. |

CPU video encoding can also be selected in the dashboard. The main editor prefers Apple VideoToolbox and falls back to libx264; alternate pace render uses libx264. Local models, visual analysis, and FFmpeg run sequentially in one worker to limit memory; capture remains concurrent. There is no multi-job scheduler. Data is not sent to paid AI APIs. Initial model downloads and YouTube access require internet.

## Analytics

Enable YouTube Analytics API in your existing Google Cloud project and run `python publisher.py connect-analytics` to grant the additional read-only scope. Do not share the JSON credentials or token. Use Channel → Refresh analytics. This requests measured per-video metrics for up to the last 20 successfully recorded uploads and retention curves for up to 5 when supported. API reporting delays and permissions can mean no data. See Google Analytics API channel reports for supported combinations.

Alternatively, use the Channel → Import measured analytics CSV control or:

```bash
python analytics_feedback.py import UC_YOUR_REAL_CHANNEL_ID /path/to/metrics.csv
```

CSV columns (numeric values, duration/average_view_duration in seconds, retention in percent; real video IDs only):

```
video_id,duration,views,retention,average_view_duration,likes,comments,shares,subscribers_gained,style,caption_style
```

The last two columns are optional. Import replaces the local feedback cache, clearly labeled user_import. Enter the same channel ID in the import section or verify the connected channel before starting a session to use cached feedback. Groups require >=3 videos and >=100 views each. Feedback is directional context in the model prompt, not trained weights or causal optimization. Metrics unavailable remain absent; no hardcoded dashboard performance.

## Data and quality

- The new editor combines semantic transcript, measured signals, optional vision observations and replay chat. Weighted ratings: opening hook 25%, retention 25%, entertainment 15%, emotion 10%, curiosity 10%, rewatch 10%, subscriber conversion 5%. Model must give reasons and evidence, score calculated from validated components. No fake metrics. Metadata includes up to five unique valid titles (model output may supply fewer), hashtags within the 100-character title limit, description, keywords, category, discussion prompt, pinned comment suggestion, hook/CTA, thumbnail text and selected JPEG frame. Suggestions do not post a pinned comment or upload a thumbnail.
- The general editor has content-specific pacing, color, safe fit / single persistent face tracking, restrained zoom, quiet-pause trimming and conservative isolated filler cuts. Gaming Pro uses the existing strict split, audio/motion-aware cuts, reaction zoom and HUD preservation. It cannot recover occluded source gameplay. Single-face tracking is not active-speaker diarization; multiple faces fit rather than arbitrarily choosing one.
- No artificial reordering, misleading pre-roll, or forced loop. Model prefers natural opening/payoff and looping; quiet outro removal for suitable non-gaming styles and first/last frame similarity reported as a heuristic. Meaningful pauses preserved where possible. No semantic removal of repetitive sentences or reliable game-specific events detection.
- Each primary export checks resolution/codec/duration, full decoding, volume/peak, available A/V track durations, black/silent periods, ASR confidence and transcript overlap when possible. It rejects obviously bad outputs; does not guarantee lip-sync, caption truth, copyright clearance, crop accuracy, or story quality. Copyright indicator is advisory; use authorized footage. Public upload revalidates media, checks score, exact SHA-256, source time overlap, repeated title, and optional perceptual frame fingerprint. Live restart timing is not globally aligned, perceptual checks can miss near-duplicates. Uncertain upload is blocked pending manual reconciliation. No forced retry after ambiguity. Google may impose public visibility restrictions on unaudited API projects; no private fallback is attempted.
- `output/<job>/<timestamp>/clips.json` holds actual scores, explanations, quality and metadata. Run/capture/download logs are available; UI redacts temporary media URLs. Local ASR/editor caches under `~/.config/m4-shorts-studio/{asr-cache,editor-cache}` retain up to 200 entries each; delete them to purge cached transcript/analysis. Clean master and word timings remain for caption editing; delete those per clip if no longer needed. Render intermediates and processed source segments are removed unless keep-source is enabled. A full scan with many accepted clips and alternates can use significant output disk space.
- Run `python -m unittest discover -v` to verify locally. Real inference, Safari playback, actual YouTube acquisition/permissions/uploads, and M4 throughput require on-device verification. Browser smoke test used mocked API data; real FFmpeg renders used synthetic fixtures. No guarantee of viral performance or production readiness without these acceptance tests.
