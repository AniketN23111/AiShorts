# AI Shorts Studio V7 — M4 Mac

A complete local project, not just a patch. All editing, speech recognition and editorial scoring run on your Mac. Network access is needed for permitted YouTube acquisition, model downloads and publishing. No paid AI API is required.

## Update existing installation

1. Stop the previous session and server (Control+C). Back up any locally modified source code.
2. Extract this ZIP into the existing `~/Downloads/AI_Shorts` directory. `unzip -o` replaces same-named source files, not `.venv`, `output/` or the OAuth credentials in `~/.config/m4-shorts-studio/`.

```bash
cd ~/Downloads/AI_Shorts
unzip -o ~/Downloads/m4-unified-studio-v7.zip
cd m4-unified-studio
source .venv/bin/activate
python -m pip install -U 'yt-dlp[default]'
python -m pip install -r requirements.txt
open -a Ollama
bash start.sh
```

Open http://127.0.0.1:8000 and hard-refresh (Cmd+Shift+R).

For a new install: install Homebrew, then `brew install python@3.12 ffmpeg-full deno`, `brew install --cask ollama-app`, open Ollama, `ollama pull qwen3:4b-instruct`, and create the environment with `python3.12 -m venv .venv` before running the commands above. FFmpeg needs libass for burned-in captions. The MLX Whisper model downloads on first use.

## Recommended settings

- Source: YouTube link or a local authorized MP4/MKV/MOV/WEBM file (paste the full path, without shell escaping or quotes).
- Source mode: Auto detect. Live uses the available live position; replay starts at the beginning.
- Viewing session: Public by default. Chrome is opt-in only for an account entitled to access the source AND with permission to acquire and reuse footage; you may see a Keychain prompt. Do not share cookies. Upload OAuth is separate from source access.
- Allow native replay fallback: enabled. If the verified format is not directly readable by FFmpeg, yt-dlp can acquire a complete non-DRM replay file; clipping begins only after the file finishes. Chrome-authenticated replays also use this route to avoid passing credentials to FFmpeg. This can require significant free space and time for a multi-hour recording. Live sources still require a compatible directly readable HLS feed. If YouTube denies access, use an authorized local recording; no DRM or membership bypass.
- Editing style: Creator. It cuts only interior transcript gaps with quiet audio, keeps short buffers, removes no more than 20% of a source clip, alternates small centered punch-ins, compresses audio and limits peaks. Clean mode keeps source timing unchanged. ASR and quiet detection can still be wrong; review every edit. No face tracking or word-level animation is included.
- Export: 9:16 Shorts, fit (safe framing). Center crop can cut off multiple speakers; preview before uploading. Captions are timed phrases, not invented word timestamps. Funny opening text is separate from speech captions. SRT timestamps are remapped after edits.
- Target: Unlimited to scan the entire source or 6 to stop at the first six qualifying clips. The system cannot know the global best six without scanning the whole source. Score 85 for selectivity; 75 for more candidates. AI scores are editorial estimates, not views. Source windows are 2 minutes, with overlapping context.
- Keep raw recording off to conserve storage. A long replay can still consume disk space faster than the AI consumes segments; capture stops below 2 GB free.

## Publishing

Use the existing connected account or run `python publisher.py connect`. The Desktop OAuth JSON must be in `~/.config/m4-shorts-studio/client_secrets.json`; the OAuth callback uses localhost. Existing token is preserved. See CREATOR_SETUP.md for Google Cloud setup. Review rights, metadata, audience and every clip, then upload privately; publish manually from YouTube Studio. No automatic public uploads. Account/Google API restrictions can still affect upload availability.

## Troubleshooting

- `No compatible verified source`: check `Selected format diagnostics` in run.log. Compatible public replay formats may use the native fallback. Unsupported live feeds need a creator-authorized recording.
- `403 Forbidden` / `members-only`: access was refused. Do not repeatedly retry a denied source; verify access and permission or use a creator-provided file. Optional Chrome session does not grant access or redistribution rights.
- `download.log`: native replay download progress. `capture.log`: FFmpeg. `run.log`: AI/extractor diagnostics. Never share signed media URLs or browser credentials.
- If a clip contains a badly cut reaction or framing, use Clean mode. The source can be processed again. Captions must be checked for transcription errors.

## Validation and limitations

Local tests include simulated extractor metadata, access-denial behavior, mock publishing, real FFmpeg segment and video rendering, dynamic cuts, subtitle remapping, and punch-ins. Actual YouTube acquisition, macOS Keychain, MLX, VideoToolbox and real Google authorization/publishing have not been exercised in this Linux environment. No guarantee of viral reach or monetization. Republish only with permission and add substantial original value; cropping/captions alone are not necessarily sufficient for monetization.
