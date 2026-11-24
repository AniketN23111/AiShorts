"""Native downloader fallback for accessible, non-DRM completed videos only."""
import os, subprocess, sys, time, shutil, re
from pathlib import Path
from youtube_source import validate_url

# Keep fallback explicit; never retry an access-denied source via alternate identities.
class NativeReplayRequired(RuntimeError):
    pass


def native_command(url, folder, browser=None):
    if browser not in (None, "chrome"): raise ValueError("Unsupported browser session")
    cmd=[sys.executable,'-m','yt_dlp','--ignore-config','--no-playlist','--no-simulate',
            '--socket-timeout','45','--retries','3','--fragment-retries','3','--abort-on-unavailable-fragments',
            '--check-formats','--no-live-from-start','--match-filters','!is_live & !is_upcoming',
            '-f','bv*[height<=1080]+ba/b[height<=1080]/b', '--merge-output-format','mkv',
            '--newline','-o',str(folder/'source.%(ext)s')]
    if browser: cmd+=['--cookies-from-browser',browser]
    return cmd+[validate_url(url)]


def download_replay(url, job, update, browser=None):
    folder=job/'native'; folder.mkdir(exist_ok=True)
    update(stage='source',capture='downloading',message='Using native downloader for this replay. Clipping starts after the file is complete.',eta='See technical logs for download estimate')
    with (job/'download.log').open('w') as log:
        proc=subprocess.Popen(native_command(url,folder,browser),stdout=log,stderr=subprocess.STDOUT)
        try:
            while proc.poll() is None:
                if (job/'stop').exists(): return None
                if shutil.disk_usage(folder).free<2*1024**3: raise RuntimeError('Low free disk space during native download.')
                time.sleep(.5)
            if proc.returncode:
                raise RuntimeError('Native replay download failed. Check download.log. For restricted or unavailable sources, use a creator-authorized local recording.')
        finally:
            if proc.poll() is None:
                proc.terminate()
                try: proc.wait(timeout=5)
                except subprocess.TimeoutExpired: proc.kill(); proc.wait()
    files=[p for p in folder.glob('source.*') if p.suffix.lower() in {'.mkv','.mp4','.mov','.webm','.m4v'} and p.is_file()]
    if len(files)!=1: raise RuntimeError('Native download did not produce one complete media file.')
    return files[0]
