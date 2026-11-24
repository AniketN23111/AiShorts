# V7.1 Smart Replay update (Apple M4)

Requires V7. Stop the old server and back up app.py, live.py and index.html before replacing them. Unzip the update inside the V7 project directory, not its parent. Your .venv, output and Google OAuth credentials are not included or changed.

```bash
cd ~/Downloads/AI_Shorts/m4-unified-studio
source .venv/bin/activate
python -m pip install -U 'yt-dlp[default]'
open -a Ollama
bash start.sh
```

Open http://127.0.0.1:8000 and hard refresh. Choose Auto detect, Smart Replay (default on), creator mode and 9:16. Full replay fallback is off by default. Choose Unlimited to scan to the end, or 6 to stop once six qualifying clips have been published locally. This does not find the best six across the entire replay if it stops early.

Completed streams: request audio-only time ranges (120s by default with 65s overlap), transcribe locally, score highlights, fetch only qualifying audiovisual sections, transcribe the selected media again to check dialogue/captions, then apply the V7 editor. Raw working files are temporary; Keep raw saves selected source video ranges only in smart mode. Ongoing streams: existing continuous FFmpeg capture; local files: existing incremental capture. The publishing workflow is unchanged and uploads private videos only after approval.

No automatic full-video fallback in Smart Replay. yt-dlp/FFmpeg must support the source's timestamp seeking. Some formats may transfer preceding data internally or fail, and time ranges can be imprecise. The update rejects large duration mismatches and skips obvious dialogue mismatches; review all timestamps and edits. No guarantee of bandwidth savings, access, or viral performance. If source access is denied or seeking fails, use an authorized local file or a supported authorized source. Do not bypass DRM or membership access controls. Membership alone is not permission to republish. Logs can contain temporary media URLs: do not share raw logs publicly.

Validation: 37 unit/regression tests (including simulated smart replay workflow and existing real FFmpeg renders); JavaScript syntax check. Actual YouTube downloads, M4 MLX inference and real uploads are not verified here.
