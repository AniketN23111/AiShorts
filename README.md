# V11 — YouTube + Instagram Reels

See [V11_SETUP.md](V11_SETUP.md) for the 70/30 Gaming Pro layout, Instagram connection and upgrade instructions. Earlier setup guides describe historical releases.

# V10 Viral Studio update

See [V10_SETUP.md](V10_SETUP.md) for new features, upgrade instructions, configuration, quality gates and limitations. The rest of this README documents the preserved original workflow.

# AI Shorts Studio V8 — start here

Read [V8_SETUP.md](V8_SETUP.md) for the current installation, Gaming Pro and PUBLIC upload workflow. The older notes below are retained for legacy modes; their private-only instructions no longer apply to the dashboard.

# V7 upgrade

**Start here: [V7_QUICKSTART.md](V7_QUICKSTART.md).** The older general instructions below apply except where the V7 guide supersedes them.

# AI Shorts Studio V5.2 — Live & Replay edition (Apple Silicon)

A loopback-only web application for incremental highlights from authorized ongoing YouTube live streams, completed streams, and ordinary videos. Both modes segment and analyse footage as it arrives, without requiring a full download.

## Install on M4 Mac

1. If Homebrew is missing, install from https://brew.sh and configure it: `eval "$(/opt/homebrew/bin/brew shellenv)"`.
2. Install: `brew install python@3.12 ffmpeg-full deno` and `brew install --cask ollama-app`.
3. Start Ollama: `open -a Ollama`, then `ollama pull qwen3:4b-instruct`. Check with `ollama list`.
4. Unzip this project and open Terminal inside `m4-unified-studio`.

```bash
cd ~/Downloads/m4-unified-studio
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
bash start.sh
```

Open http://127.0.0.1:8000 in Safari or Chrome. Keep Terminal and Ollama open. MLX Whisper Small downloads automatically on first use, which can delay the first clip. No cloud AI API. Use `python -m pip install -U 'yt-dlp[default]'` if YouTube extraction breaks; not all streams offer accessible HLS or direct HTTP video/audio feeds.

## Use

- Paste a single live, completed stream or normal YouTube video URL (not a channel or playlist). Select Auto detect (default), Live now or Completed stream / video. Confirm permission to acquire and reuse the source, in accordance with YouTube's terms.
- Default: target 6 clips; choose Unlimited for continuous clipping. The target stops capture immediately when reached, so later footage is not ranked or analyzed. No capture time limit by default; optional duration limit up to 12 hours.
- Default analysis interval 2 minutes, actual cuts follow source keyframes; select 1 or 3 minutes if preferred. Clip length 20–60 seconds. Selects up to three candidates per segment. Minimum AI score 75 by default; a segment can yield zero clips. Lower the threshold if necessary.
- Original framing is default, with original audio and playback speed, no overlays; video/audio are re-encoded for accurate cuts (not bit-identical). Select 9:16 fit or center crop for vertical Shorts. Captions are optional, with SRT always exported.
- Start clipping. Capture and AI processing run concurrently. One finished MP4 is published to the UI immediately, while capture continues. The previous segment's last ~65 seconds of transcript supply context for boundary-crossing clips. Existing overlapping highlights are rejected.
- Stop session closes FFmpeg and finishes the active segment when possible, skipping the remaining queued segments. If the target is reached, queued footage is skipped. AI requests can take time; stopping capture does not immediately cancel the active inference. Ctrl+C stops the application and may interrupt an in-progress export.
- Watch the capture status, queue, completed clips and estimates. Initial ETA is unknown; later stage estimates use previous stage durations. Capture timing is approximate; an endless stream has no overall ETA. Completed videos show the percentage of the requested footage analysed. With Unlimited clips, the full scan ETA is estimated from elapsed time and analysed footage, after the first segment. When capture outruns processing the queue grows. Increase the interval if overhead is high, or reduce source quality using a supported source. No guaranteed real-time inference performance.
- Find files under `output/<session>/<timestamp>/short_01.mp4`, `short_01.srt`, `clips.json`, etc. The dashboard shows the current session only; files remain on disk after server restart. Raw recordings are deleted after use by default (one prior segment kept temporarily); enable Keep raw recordings before starting if you need them. Capture stops if free disk falls below ~2 GB, but monitor disk space, especially when keeping raw data.

## Limitations

- Live mode captures from the available live edge, not the earlier hours of a stream. Replay mode starts at the beginning of accessible, fully processed footage. Replays still being processed by YouTube are rejected until available. V5.2 prefers HLS for both modes and checks the selected format using yt-dlp before capture. Direct HTTPS remains a fallback for replay. Muxed formats are preferred even when their resolution is lower (sometimes 360p); separate audio/video is best effort when no muxed feed exists. Unsupported segmented formats are rejected. Actual YouTube format availability, network errors and signed URL expiry can interrupt sessions. V5.1 enables bounded FFmpeg HTTP reconnection (up to five retries per connection, 90-second read timeout). This is not a full job restart: expired signed URLs or persistent outages can still end the job; replay restarts from the beginning. No historical DVR access. Completed exports remain on disk. Restart with the link to continue at the current available live position.
- Speech-based AI only, not visual/gaming/sports-event detection. AI scores are editorial estimates, not actual view predictions. Immediate highlights are best within analyzed windows, not guaranteed top six across a stream that has not ended or a replay that has not been fully scanned. Choose Unlimited to analyse the full replay and compare the exported clips by score. The model may select no highlights or miss a moment; review the exported clips, titles and subtitles.
- Apple VideoToolbox H.264 export with software fallback. MLX Whisper and Ollama runtime must be tested on your Mac. First use downloads models. Do not publish without rights.

## Tests

`python -m unittest discover -v` runs URL/setting validation, live status and HTTP range routes, candidate overlap/boundary logic, segment CSV parsing, mock incremental live and replay capture/export, source-mode detection, real synthetic FFmpeg segment/concat/render, captions and legacy selection tests. The test environment has no Apple GPU or live YouTube connection.

## V5.1 connection repair

If upgrading an existing V5 project, stop the running session and server, then extract the new files over the existing folder (the archive contains no output or virtual environment). Activate `.venv`, run `python -m pip install -U 'yt-dlp[default]'`, and start again. A transient HTTP disconnect can be retried within FFmpeg; persistent outages still require a new job. An incomplete replay is reported as failed rather than fully processed. Corrupt packets are discarded when identified, and audio decoding tolerates recoverable errors; this does not reconstruct missing media. Existing exports are not deleted. `python check_http_reconnect.py` tests recovery against a synthetic local HTTP server that drops its first response; no external network is required.

## V5.2: HTTP 403 diagnosis

Update yt-dlp and Deno, then test the original authorized YouTube watch/live URL, not a temporary googlevideo URL:

```bash
source .venv/bin/activate
python -m pip install -U 'yt-dlp[default]'
deno --version
python -m yt_dlp --no-playlist --check-formats --test -f 'b[height<=1080]/bv[height<=1080]+ba' -o '/tmp/shorts-test.%(ext)s' 'YOUR_YOUTUBE_URL'
```

The test downloads a small sample where supported, not the whole recording. V5.2 uses the actual selected and tested formats and merges extractor-level and format-level HTTP headers. It prioritizes HLS, keeps the existing bounded network retries, and displays a specific HTTP 403 message if FFmpeg still receives access denied. These changes cannot guarantee that YouTube will allow direct acquisition. The dashboard redacts complete googlevideo URLs; raw disk logs can still contain temporary URLs and IP information. Do not share them publicly.

If access remains denied, use a recording supplied by the creator or an otherwise authorized local source. Incremental local-file mode (Terminal, results saved under the specified folder, not registered as a dashboard job):

```bash
python live.py --input-file '/path/to/recording.mp4' --authorized --count 0 --segment 120 --layout original --output "output/local-$(date +%Y%m%d-%H%M%S)"
```

No full-video transcription is required in this mode. Live YouTube acquisition has not been tested on an M4 in this environment.

## V6 Creator Edition
See [CREATOR_SETUP.md](CREATOR_SETUP.md) for creator editing and optional private YouTube upload setup.
