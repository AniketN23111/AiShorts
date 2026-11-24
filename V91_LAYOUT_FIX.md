# V9.1 – strict gameplay / streamer split

Gaming Pro always renders 1080×1920, gameplay at the top (1080×960), streamer at the bottom (1080×960). No captions. Clean and Creator modes are unchanged.

The detected or manually configured facecam area is masked on the top panel to avoid duplicating the streamer. Gameplay is fitted into the top panel to preserve visible HUD; the game underneath an embedded webcam cannot be recovered. The face crop is constrained to the detected webcam region, including during reaction zooms. The source must actually contain both gameplay and a facecam. Candidates with no persistent facecam, an excessively large camera, a possible full-screen face, or long gaps in detection are skipped before export/publication. Both livestream/local-file processing and Smart Replay continue scanning after such a skip. Face detection is heuristic; it cannot prove that the remaining pixels are gameplay, and game characters can cause false positives. Manual facecam coordinates help but still require face detection.

## Installation
Stop the running app (Ctrl+C). In your existing project folder, back up gaming.py, live.py, smart_replay.py and index.html, then extract the UI/layout update archive into that folder. Alternatively extract the full archive into its parent. Existing output and credentials are not removed. Run `source .venv/bin/activate` and `bash start.sh`, then refresh http://127.0.0.1:8000 with Cmd+Shift+R.

Select Gaming Pro. Set Facecam region under Layout, language and facecam if necessary, in normalized x,y,width,height coordinates. Example only: bottom-left quarter of source = 0,0.65,0.25,0.35. Use the actual position in the original video. Existing exports are not re-edited; start a new session. Disable automatic publishing for the first test run and review both panels before enabling it again. If previous clips were uploaded, duplicate protection may prevent uploading overlapping replacements.

## Tests
`python -m unittest discover -q` — 45 tests passed in the build environment. The FFmpeg test renders a synthetic blue gameplay/red webcam source with simulated face detections, checks resolution, actual pixel ordering and camera masking, and validates audio/video. Tests cover missing camera, possible full-screen face and detection gaps. Actual source detection, YouTube acquisition and M4 hardware encoding have not been verified on the user's Mac.
