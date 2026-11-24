"""Acquire a single authorized YouTube video or a bounded current live excerpt."""
import math
from pathlib import Path
import subprocess
import time
from urllib.parse import urlparse


def validate_url(url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in {
        'youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be', 'www.youtu.be'
    } or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('Enter a single HTTPS YouTube video or live URL.')
    if parsed.hostname not in {'youtu.be', 'www.youtu.be'} and not (
        parsed.path == '/watch' or parsed.path.startswith(('/live/', '/shorts/'))
    ):
        raise ValueError('Use a video/live link rather than a channel or playlist.')
    return url


def eta(seconds):
    if seconds is None or not math.isfinite(seconds):
        return 'estimating'
    n = max(0, round(seconds))
    return f'{n//3600:02}:{n//60%60:02}:{n%60:02}'


def acquire(url, directory, live_minutes):
    from yt_dlp import YoutubeDL
    validate_url(url)
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    last = [0.0]

    def hook(d):
        if d.get('status') == 'downloading' and time.monotonic() - last[0] >= 2:
            last[0] = time.monotonic()
            total = d.get('total_bytes') or d.get('total_bytes_estimate')
            progress = f'{100*d.get("downloaded_bytes", 0)/total:.0f}%' if total else 'in progress'
            print(f'[Download] {progress} | current stream ETA {eta(d.get("eta"))}', flush=True)
        elif d.get('status') == 'finished':
            print('[Download] Stream received; merging if necessary.', flush=True)

    opts = {'noplaylist': True, 'quiet': True, 'no_warnings': False,
            'format': 'bv*[height<=1080]+ba/b[height<=1080]/b',
            'merge_output_format': 'mkv', 'outtmpl': str(directory / 'source.%(ext)s'),
            'progress_hooks': [hook], 'socket_timeout': 30,
            'retries': 3, 'fragment_retries': 3}
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if not info or info.get('_type') == 'playlist' or info.get('entries') is not None:
            raise ValueError('A single accessible video is required.')
        print(f'Source: {info.get("title", "YouTube video")}', flush=True)
        if info.get('live_status') in {'is_upcoming', 'post_live'}:
            raise ValueError('Stream is not yet playable or the replay is still processing.')
        if info.get('is_live') or info.get('live_status') == 'is_live':
            return capture_live(info, directory, live_minutes)
        ydl.download([url])
    files = [p for p in directory.glob('source.*') if p.suffix in {'.mp4','.mkv','.webm','.mov','.m4v'} and p.is_file()]
    if len(files) != 1:
        raise RuntimeError('Could not locate a single completed video file.')
    return files[0]


def capture_live(info, directory, minutes):
    # A muxed HLS format avoids separate audio/video clock alignment problems.
    formats = [f for f in info.get('formats', []) if str(f.get('protocol','')).startswith('m3u8')
               and f.get('vcodec') not in (None, 'none') and f.get('acodec') not in (None, 'none')
               and f.get('url') and not f.get('has_drm') and (f.get('height') or 0) <= 1080]
    if not formats:
        raise RuntimeError('No supported combined live HLS feed. Try the completed replay or an authorized local recording.')
    f = max(formats, key=lambda x: (x.get('height') or 0, x.get('tbr') or 0))
    target = int(minutes * 60)
    output = directory / 'source.mkv'
    headers = ''.join(f'{k}: {v}\r\n' for k,v in f.get('http_headers', {}).items()
                      if k.lower() in {'user-agent','referer','origin','accept','accept-language'}
                      and '\r' not in str(v) and '\n' not in str(v))
    cmd = ['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-y','-rw_timeout','30000000']
    if headers:
        cmd += ['-headers', headers]
    cmd += ['-i',f['url'],'-t',str(target),'-map','0:v:0','-map','0:a:0','-c','copy',
            '-progress','pipe:1','-nostats',str(output)]
    print(f'[Live] Capturing up to {minutes:g} minutes from the current available position (not historical footage).', flush=True)
    last = 0
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True) as proc:
        try:
            for line in proc.stdout:
                if line.startswith('out_time_us='):
                    try:
                        seconds = int(line.split('=',1)[1])/1_000_000
                    except ValueError:
                        continue
                    if time.monotonic() - last > 3:
                        last = time.monotonic()
                        print(f'[Live] {max(0,min(100,100*seconds/target)):.0f}% | media remaining {eta(target-seconds)}', flush=True)
            status = proc.wait()
        except BaseException:
            proc.terminate()
            proc.wait()
            raise
    if status or not output.exists() or not output.stat().st_size:
        raise RuntimeError('Live capture failed; try the replay or a local recording.')
    return output
