# Shorts Studio — V8 premium UI refresh (V9 UI)

This release changes presentation only. It retains the Gaming Pro V8 backend and the same HTTP routes, request payloads, source modes, rendering, publishing, authentication, analytics and local storage behavior. No new runtime dependencies or external fonts, icon libraries, CDN resources, build steps or Node.js installation are required.

## Update an existing installation (recommended)

1. Stop the server with Ctrl+C.
2. Download `m4-studio-v9-ui-update.zip`.
3. In Terminal:

```bash
cd ~/Downloads/AI_Shorts/m4-unified-studio
cp index.html index.v8.backup.html
unzip -o ~/Downloads/m4-studio-v9-ui-update.zip
bash start.sh
```

4. Open http://127.0.0.1:8000 and refresh (Cmd+Shift+R).

The patch only replaces `index.html` and adds this guide. Your output, `.venv`, Python files and local OAuth files are untouched. To roll back, stop the server, copy `index.v8.backup.html` to `index.html`, and restart.

## Full project installation

If starting from scratch, extract `m4-unified-studio-v9-ui.zip`, then follow `V8_SETUP.md` for dependencies, Ollama and YouTube OAuth. If overlaying the full ZIP onto a working project, back up your source files first; local backend modifications could be overwritten. No backend upgrade is needed for the UI refresh.

## Where to find controls

- **Workspace**: source type, YouTube URL or local path, source mode, editing style, target, interval, time limit, minimum score and rights confirmation. All original defaults and option values are retained.
- **Advanced editing**: export format, streamer/game, manual facecam region, spoken language and legacy captions.
- **Source & storage**: viewing session, Smart Replay, native fallback and raw recording retention.
- **Publishing & analytics**: automatic PUBLIC publishing, audience, daily cap, explicit public consent and Analytics refresh. Use the Channel navigation link to verify the connected channel first.
- **Session monitor**: elapsed time, queue, completed segments, highlights, acquisition, processing, coverage, ETA and technical logs.
- **Highlights**: individual video previews, MP4/SRT downloads where available, editing details, and manual public upload review for Gaming Pro clips. Existing clips stay mounted during status polling.
- **Channel**: check the authorized YouTube channel using the original API.

The theme button follows your system appearance initially and saves your explicit choice in browser localStorage when available. The UI uses native inputs, disclosure panels, video playback controls and a keyboard-accessible native confirmation dialog (browser confirm fallback where unsupported). It supports reduced-motion preferences and a responsive single-column layout at narrower widths. Public publishing still requires the original rights and audience confirmations. No upload is triggered merely by changing a theme or opening a panel.

## Validation

- All 43 original backend unit/integration tests passed in the build environment, including FFmpeg tests. All existing Python source files, test files, launcher and requirements are byte-for-byte identical to V8.
- Chromium browser smoke tests used simulated fetch responses and a simulated localStorage implementation. They exercised source selection, mutually exclusive download modes, form payloads, public confirmation acceptance/cancellation, progress/skeletons, incremental cards and repeated filenames, stop, manual upload, theme switching, error handling, and 320/390/768/1024/1440 px layouts. No uncaught JavaScript errors. Actual video playback, OAuth, Apple M4 inference, and real YouTube publishing were not exercised in those browser tests; no real videos were uploaded. The HTTP server tests cover actual loopback routes and media byte-range responses.
- No full accessibility audit or Safari device test was performed. The existing source acquisition and AI limitations documented in V8 still apply.
