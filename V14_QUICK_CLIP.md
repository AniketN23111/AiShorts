# V14 Quick Clip Studio

Based on V13. Designed to reduce waiting for long YouTube replays, not to guarantee a first clip by a deadline. Existing gaming 70/30 layout, metadata, captions, quality checks, saved sessions, YouTube/Instagram integrations and publishing safeguards remain in place.

## What changed
- UI defaults: Smart mode, 3 clips, 60-second analysis windows, full replay scan OFF. Full scan remains available for best-of-entire-video ranking; when OFF a finite target stops after the first qualifying clips. API/CLI count defaults remain 6 for compatibility.
- 30 and 45-second windows are now supported for live and replay sources. Shorter windows reduce initial waiting but can miss long stories; the existing rolling context retains one previous window. Prefer 60–120 seconds for longer moments.
- Smart/Fast public replays can reuse a low-resolution combined HTTPS MP4 selected from initial yt-dlp metadata. A byte-range probe must return HTTP 206 with the exact Content-Range. FFmpeg seeks before input decoding and makes only a low-resolution preview, with a 90-second deadline. No browser credentials are passed to this path. If unavailable, the existing authorized yt-dlp section acquisition is used. HD highlights are still fetched through the existing selected-range route and checked against the preview. Remote seeking, actual transfer size, and speed depend on the source/CDN; a timestamp range is not an absolute guarantee of network bytes. No automatic full-video fallback in Smart Replay.
- One next preview is prefetched in a background thread after the current preview/transcript is ready; it overlaps candidate AI review and rendering. It is cancelled when the job ends. No concurrent AI inference is added. Professional mode retains serial acquisition. Preview timeouts in Fast/Smart are 180 seconds for native range requests (other requests 600 seconds). A direct-preview failure can add time before fallback.
- UI shows measured prefetched/direct preview counts. Processing statistics are synchronized between threads. Live capture checks the clip target between exports.
- Full scan OFF means eligible clips may be published incrementally if automatic publishing is explicitly authorized; it does not guarantee the globally best clips. Keep automatic publishing disabled while evaluating the changes.

## Update existing repository
Stop the running server. Back up local source edits. From the root of AIShorts, apply the UI/worker patch:

```sh
unzip -o ~/Downloads/m4-v14-quick-update.zip
source .venv/bin/activate
open -a Ollama
bash start.sh
```

No new dependencies/models. The update does not contain or change .venv, .git, output or OAuth credentials. Refresh the browser. For a clean/full installation use the V14 full archive and V13 setup instructions.

## Recommended settings
- Replay: Auto detect, Smart Replay ON, full download fallback OFF, full scan OFF, clip target 3, Smart mode, 60-second interval; optionally 30 or 45 seconds if moments are short. Keep independent editorial review ON initially. Fast mode is available for lower AI cost. Turn off alternate renders, overlays and captions if unnecessary.
- Ongoing live: explicitly choose Live mode to avoid the replay metadata probe, use 30–60-second analysis windows; capture begins at available live position and waits for the first segment to close. It cannot clip footage that hasn't happened yet. Finite target stops capture; unlimited continues.
- Professional mode or a longer interval if a moment needs more context. Use full scan for globally ranked clips; this necessarily takes longer.

## Validation
81 tests passed in separate groups, including six new tests and actual FFmpeg range seeking against a local HTTP server. The combined full run reached its execution deadline; two existing heavy viral-render tests have not been verified in this release. Python and JavaScript syntax checks passed. No actual YouTube requests, M4 performance measurements, or real social uploads were tested in this environment. No end-to-end speed multiplier is claimed. Only process footage you are authorized to acquire and reuse.
