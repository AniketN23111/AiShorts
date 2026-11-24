# V6 Creator Edition — Mac setup

V6 updates V5.2: ongoing and completed streams are processed incrementally, with a Shorts-focused editorial prompt, bold timed dialogue captions, a separate playful three-second opening hook, suggested title, description, hashtags and rationale. Fit 9:16 and captions are selected by default. Choose original framing for regular highlights. This is prompt-based editing, not fine-tuning or a prediction of views. The AI can misinterpret humor or context; review each clip. Visual-only highlight detection, speaker tracking, word-by-word animations and automatic public publishing are not implemented.

## Update existing project
Stop the existing server with Ctrl+C. From the terminal:

```bash
cd ~/Downloads/AI_Shorts
unzip -o ~/Downloads/m4-unified-studio-v6.zip
cd m4-unified-studio
source .venv/bin/activate
python -m pip install -r requirements.txt
open -a Ollama
bash start.sh
```

Open http://127.0.0.1:8000. Paste an authorized source, select Fit 9:16 and captions, set clip target to Unlimited for complete replay coverage (or 6 for early stopping). The first six qualifying moments are not necessarily the top six across a long video. Use YouTube only when acquisition and reuse are permitted. V5.2 capture code is retained; the 403 issue may still occur. The local-file CLI fallback is documented in README.md.

## Optional official YouTube connection
1. In https://console.cloud.google.com/ create/select a project, enable YouTube Data API v3.
2. Configure the OAuth consent screen / Google Auth Platform (branding, audience, data access). If in External Testing, add your own Google account as a test user. Follow Google's current project and consent requirements.
3. Create an OAuth client ID of type Desktop app, download its JSON. Do not share this JSON, tokens, or account credentials with anyone.
4. Save the downloaded JSON locally as `~/.config/m4-shorts-studio/client_secrets.json`. Example (replace file name):

```bash
mkdir -p ~/.config/m4-shorts-studio
chmod 700 ~/.config/m4-shorts-studio
cp ~/Downloads/YOUR_OAUTH_FILE.json ~/.config/m4-shorts-studio/client_secrets.json
chmod 600 ~/.config/m4-shorts-studio/client_secrets.json
python publisher.py connect
```

Run the command from the activated project environment. Authorize the correct channel in your browser; the tool requests upload and read-only YouTube scopes to verify channel identity. Refresh token is stored locally with restricted permissions, not shared with ChatGPT. Testing mode may require periodic reauthorization. You can check the channel with `python publisher.py status`, or remove the local token with `python publisher.py disconnect`. Revoke OAuth access from your Google Account to invalidate access on Google's side.

## Upload a clip
Start the server and click Check channel. In a clip's Review & upload privately panel, review the actual video and title, edit title/description/hashtags, verify audience setting and your rights, then click Upload private Short and confirm the channel. Only square or vertical videos up to 3 minutes pass the uploader's format check. The upload is private; review in YouTube Studio and manually publish when ready. Uploading to YouTube transfers the selected clip and metadata to Google. A local receipt prevents repeat uploads. If an upload fails after starting, check YouTube Studio before retrying, and remove the corresponding `.upload.pending` file only if you confirmed no video was created. The dashboard only shows clips from the current server session; files remain under output/.

## Rights and quality
YouTube reused-content rules are separate from copyright permissions. Captions, cropping and attribution alone do not guarantee monetization. Make original commentary or analysis when appropriate, use only footage you are authorized to acquire and publish, and verify metadata and audience settings. No guaranteed viral performance. No paid AI API needed; YouTube API quotas, internet and storage apply.

## Verification
24 automated tests include regression, real FFmpeg caption/hook render, mocked Google API private upload and duplicate prevention. Actual YouTube access, real OAuth and upload, and MLX/Ollama on an M4 must be tested on the user's Mac. JavaScript syntax checked; browser visual/interaction not tested here.
