# V13 — Performance & Story Studio

This is a source-level upgrade of the supplied V12 archive, not a checkout of any remote repository. No new runtime dependency or AI model is required. YouTube and Instagram publishing are retained; existing connection files stay in their original location, outside this archive. No credentials or generated media are distributed.

## Installation (macOS / existing V12)

Stop the old application. Back up or commit your existing source changes. From your project root:

```sh
UPDATE_DIR="$(mktemp -d)"
unzip ~/Downloads/m4-unified-studio-v13-performance.zip -d "$UPDATE_DIR"
rsync -av --exclude='.gitignore' "$UPDATE_DIR/m4-unified-studio/" ./
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip check
open -a Ollama
bash start.sh
```

Add `benchmarks/` to your existing `.gitignore` before committing. Never commit `.venv`, output, tokens, cookies or local media. Visit http://127.0.0.1:8000 and hard refresh. Your existing YouTube and Instagram account setup is unchanged; test manual uploads before re-enabling automatic publishing. Only acquire and publish footage you have permission to reuse.

## Recommended settings

Gaming Pro + Gaming Highlights; Processing quality: Smart; analysis interval 120 seconds; Smart Replay on; full replay scan on; minimum score 85; captions off for clean gameplay or word highlight if desired; overlays and alternate renders off initially; full-download fallback off; automatic publishing off until verified. Gaming Pro remains 70% gameplay on top and 30% facecam below, rejecting unreliable facecam/full-streamer candidates. Select unlimited clips for continuous live scanning. Full replay scan still renders qualifying clips progressively and ranks them before publishing, with the selected count as the maximum uploads; it does not defer all rendering until a global top-K is known.

## Modes and selection

V13 mode applies to nonempty Viral presets. Original editor paths remain available. Fast samples 0.5 FPS; Smart 1 FPS; Professional 2 FPS. The prompt requests at most 1, 2 or 3 candidates per window, respectively; the acceptance gate is still applied. Cheap grayscale sampled motion and scene-change indicators are proposals, not event recognition. A promising low-speech visual window can receive targeted vision analysis. A candidate without speech requires observed visual evidence and independent review. Smart reviews gaming candidates with targeted vision when the review switch is on; Professional always independently reviews. Vision is optional (Gemma 3 4B via existing local Ollama); without it, purely visual highlights cannot be grounded and are rejected. Snapshot analysis cannot guarantee detection of every brief event.

The requested V13 score is 25% hook, 20% story completeness, 20% retention, 15% entertainment, 10% emotion/surprise, 5% context and 5% rewatch/share. Penalties are model-assessed, 0–10 each; misleading or duplicate moments are rejected, not merely discounted. All ratings and explanations must validate. Editorial scores are not calibrated predictions of actual views or watch time. Ten storytelling patterns plus `other` are accepted. Phrase-boundary alignment can expand by up to 3 seconds and rejects a cut bisecting a longer phrase. Candidate duration 10–90 seconds, subject to context, renderer and technical validation. Prior silent/low-motion checks and upload ledgers remain. Lexical trigram overlap helps reject repeated dialogue, not a true semantic embedding model.

## Processing changes and safety fallbacks

- Smart Replay holds one preceding preview; new sections are acquired and transcribed once, joined using stream copy when codec signature and measured durations match. Incompatible streams fall back to the existing checked overlapped request. Rolling reuse is limited to compatible previews. No automatic full-source video download.
- Fast/Smart try multi-anchor waveform correlation before reusing candidate word timestamps. A weak, ambiguous or drifting match triggers actual-media ASR. Professional retains actual-media ASR. Visual-only sources retain visual range verification.
- Existing real ASR word timestamps are remapped across retained edit pieces if the render clock and word boundaries match, otherwise the edited master is transcribed. No invented word timings. PCM RMS is reused from the ASR WAV when available. Some paths still decode audio separately.
- Event-driven shots replace fixed periodic subdivisions in Viral render paths. Original edit paths remain. Conservative silence and filler removal protect context; gameplay cuts require low motion. Face tracking is still a heuristic, not an active-speaker classifier. Zoom follows a proposed impact, not a fixed timer. No new freeze-frame/replay/slow-motion effects added.
- Gaming masters with captions/overlays/music/SFX disabled can be exported directly, without a second audio pass. Caption masters and alternate renders still need additional encodes when necessary; general rendering still uses shot files and a concat stage. Hardware support is probed once per process (Apple VideoToolbox, NVIDIA NVENC, Intel QSV, AMD AMF where listed and working); CPU fallback remains. This probes availability, not speed or quality of every encoder.
- Final validation combines volume, black-frame, silence and freeze analysis in one decode; checks available track durations/offsets, caption timings and confidence. Professional rejects predominantly frozen frames. These checks cannot guarantee true lip-sync, correct context, or copyright clearance. Upload validation is still independent.
- Replay pause/resume waits at safe window/candidate boundaries; a long model request or render must finish first. Stop while paused works. Live capture cannot be paused via this control. App termination/restart does not automatically resume an interrupted job; existing saved outputs and content-addressed caches are retained. Capture reconnection remains the V12 mechanism.

## Configuration / cache / logs

`SHORTS_CACHE_VERSION` (default `v13`) is a cache namespace. Bump after changing model weights under the same tag, source analysis behavior or when you want fresh inference. The cache is local under the existing publisher CONFIG directory, with separate performance-cache directories for audio, scan, vision, review, facecam and subject-track. Existing ASR and editor JSON caches remain; entries are bounded by count. Source keys use SHA-256 and relevant ranges/configuration. Byte changes invalidate media caches; a redownload with changed container bytes may miss. No full WAV or full source is added to the persistent cache. Cache directory files may contain transcripts and should remain private. CPU ASR uses the existing optional `requirements-cpu.txt`, `SHORTS_ASR_BACKEND=cpu`, and `SHORTS_CPU_MODEL`. Existing `SHORTS_VISION_MODEL`, `SHORTS_AUTHORIZED_MUSIC`, `SHORTS_AUTHORIZED_SFX`, `SHORTS_CAPTION_FONT` and chat JSONL inputs remain supported. `SHORTS_PROCESSING_MODE` is set automatically for new Viral sessions.

Dashboard status includes measured ASR, local model requests, scanning, rendering, accepted/rejected candidates, common rejection reasons and worker peak RSS. Timings are cumulative, update at processing boundaries, and can be nested (do not add all counters to calculate total elapsed). Worker RSS excludes Ollama and concurrent child processes; it is not total machine memory. GPU usage is not available in this implementation. Existing logs and throughput-based replay ETA remain. Analytics and CSV import are retained with additional duration buckets; no unverified new analytics metrics are manufactured.

## Benchmarks

See `V13_COMPONENT_BENCHMARK.json`. Single run on Linux x86-64, Python 3.13.5: old scan 4.093s, new scan 0.384s, warm cache 0.001s; validation 1.356s vs 0.885s. Different sampling granularity, no real ASR/Ollama inference; these are not end-to-end or quality comparisons. V12 baseline: 66 tests passed, 39.097 seconds. Actual M4 performance and quality are unmeasured here.

Extract the old V12 ZIP to a separate directory. To run the synthetic component benchmark locally:

```sh
python benchmark_pipeline.py --baseline /path/to/v12/m4-unified-studio --components
```

To measure the entire old/new local pipeline against identical portions of a permitted recording at least three hours long, with the same installed models:

```sh
python benchmark_pipeline.py --baseline /path/to/v12/m4-unified-studio \
  --source /path/to/authorized-3-hour-recording.mp4 --authorized \
  --minutes 30 60 180 --style gaming --captions karaoke
```

Outputs go to `benchmarks/`. Runs are sequential, no publishing or external acquisition, with isolated caches. Metrics include time to first observed final clip, total wall time, stage times, request counts, worker/child peak RSS, count of clips and model scores. GPU usage is null. A missing clip has null time-to-first-clip; review the run logs and exit codes. Compare actual clip quality against manually annotated reference highlights (scores are not comparable across old/new weighting). This can take substantial time and disk space. Run on representative real footage to establish the 3–5x end-to-end target, not a guaranteed result.

## Outstanding scope

Full real 30/60/180-minute tests, real M4 inference and hardware throughput, Safari/browser interactions and actual public uploads remain to be verified. No new dependencies, no real account actions performed. The application server and JavaScript can be checked locally. True active-speaker diarization/important-object detection, automatic game-event recognition, native live chat retrieval, reference-video style learning, semantic embeddings, guaranteed seamless loops, persistent interrupted-job resume, automatic live reconnect across expired source URLs, unified single-pass rendering for all styles, dynamic multi-person layouts, and verified stayed-to-watch/engaged-view analytics are not fully implemented. Existing analytics-based feedback is directional and is not model training. Content and rights review remain necessary. This is a targeted performance and editorial upgrade, not a production certification of all 26 requested requirements.
