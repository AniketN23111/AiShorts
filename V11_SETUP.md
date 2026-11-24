# V11 — YouTube + Instagram Reels

This release builds on the supplied V10 archive, not a GitHub checkout. No existing channel credentials or outputs are included. Use existing rights-cleared sources only.

## Gaming layout

All new Gaming Pro renders (including the Viral Gaming preset and alternates) allocate 1344 pixels of the 1920-pixel canvas to gameplay on top and 576 pixels to the streamer below. Output is 1080x1920. The gameplay source fits within its panel to preserve the HUD; the unused area uses blurred gameplay fill. The source facecam region is masked from the top panel, because pixels behind an embedded webcam cannot be reconstructed. This does not zoom/crop the game to fill the whole 70% panel. Missing or unreliable facecams still cause the candidate to be skipped. Set the facecam region manually if needed. Optional Viral captions remain off by default, and when enabled move near the panel boundary. Existing videos are not re-rendered.

## Install/update

Stop the server. Back up your local code or make a Git commit, then extract the full ZIP into a temporary directory and copy its project files into your existing Git checkout (do not replace `.git`, `.venv`, or `output`).

```bash
cd "$(git rev-parse --show-toplevel)"
UPDATE_DIR="$(mktemp -d)"
unzip ~/Downloads/m4-unified-studio-v11-social.zip -d "$UPDATE_DIR"
rsync -av --exclude='.gitignore' "$UPDATE_DIR/m4-unified-studio/" ./
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip check
open -a Ollama
bash start.sh
```

Open http://127.0.0.1:8000. Existing YouTube authentication stays unchanged. No additional AI models required. New explicit dependency: requests for HTTPS API calls (already commonly installed with Google auth libraries).

## Instagram publishing setup (Facebook Login for Business)

1. Convert your Instagram account to a professional Creator or Business account and link it to a Facebook Page that you manage.
2. In https://developers.facebook.com/apps/ create or configure a Meta app with Instagram API with Facebook Login / Facebook Login for Business. Enable publishing. Follow the current Meta dashboard instructions for app roles, access level, permission review and Page Publishing Authorization where required.
3. Obtain the Instagram professional account's numeric ID and a Facebook Page access token with `instagram_basic`, `instagram_content_publish`, and `pages_read_engagement`. Page discovery may also require `pages_show_list`; additional permissions depend on how you manage the Page. Verify access in Meta's developer tools. The token must belong to the Page linked to the intended Instagram account. For your own app/account, Standard Access may suffice; accounts outside app roles may require Advanced Access and review. Use the supported Graph API version from your app dashboard (the CLI default is v26.0; change if necessary).
4. With your virtual environment activated, run `python instagram_publisher.py connect`. Enter the account ID, API version, and token at the hidden terminal prompt. Do not share the token or commit it. Stored locally at `~/.config/m4-shorts-studio/instagram-token.json` with 0600 file mode. `python instagram_publisher.py status` verifies identity without disclosing the token; `disconnect` removes the local token but does not revoke access at Meta. Reconnect when a token expires.
5. In the dashboard Channel section, click Check Instagram. This verifies account identity, not every publishing permission. Manual publishing: open a generated clip's Instagram Reels section, edit or copy the proposed post caption, confirm rights and click Publish Reel. Or upload the same downloaded MP4 manually through Instagram. Automatic publishing: in Publishing & analytics, enable Instagram and its separate consent checkbox, set a daily cap, and approve the session confirmation. YouTube and Instagram can be enabled independently or together. Ranked replay publishing is shared; each selected primary export may publish once per platform. Alternates are not published automatically.

This integration uses the official resumable media-container protocol for Facebook Login for Business: create a REELS container, stream MP4 bytes to the returned Meta upload URI, poll until FINISHED, then publish. No public file server is needed. See https://developers.facebook.com/docs/instagram-platform/content-publishing/ and https://www.postman.com/meta/instagram/request/gabnx7r/publish-reel . Direct file upload is not assumed to work with Instagram Login-only apps. Meta app setup and approval cannot be automated here. Personal accounts cannot use this publishing integration.

## Safety and recovery

- Existing YouTube publishing unchanged; Instagram uses an independent persistent ledger `~/.config/m4-shorts-studio/instagram-uploads.json`. Source timestamps, SHA256 and existing perceptual fingerprints prevent repeated clips when available. Ledger reservations are locked across processes. A duplicate on YouTube does not block Instagram.
- Requires validated vertical H.264/AAC, 15–45 seconds, non-clipped audible audio and the session score threshold. Manual publishing uses the existing 85-point threshold. Instagram additionally enforces a conservative 300 MiB local cap.
- Metadata reuses contextual AI title, description, comment prompt and relevant hashtags. Instagram has no separate title field; the post caption excludes YouTube-only title hashtags and is editable. Existing V10 video captions and overlays remain optional.
- Failed pre-publish uploads may be manually retried. A lost publish response or crash after reserving blocks duplicate attempts: inspect the account and ledger before any recovery. No automatic replay of an uncertain publish. No automatic token refresh, Instagram analytics or guaranteed delivery is implemented.
- Automatic publishing is off by default. Stop prevents the next platform upload; an in-flight upload may complete. Instagram processing can take several minutes and is performed sequentially with YouTube publishing. Export files are retained. Existing Smart Replay, local AI and Apple Silicon encoding are preserved.
- Only share content you own or have authorization to reuse on each platform. No guarantee of viral reach.

## Tests

Run `python -m unittest discover -v`. The Instagram API tests mock external responses; real account authorization, upload, Meta version compatibility and M4 inference need verification on your own Mac. `test_gaming` verifies rendering with FFmpeg and sample pixel positions. JavaScript syntax can be checked by extracting inline script to a JS file and running `node --check`.
