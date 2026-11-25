"""Optional public progressive preview acceleration. No access bypass or full-file fallback.
Signed media URLs remain in worker memory; they are never written to project logs.
"""
import re, subprocess, time
from urllib.parse import urlsplit


def preview_format(info):
    if info.get('has_drm') or info.get('is_live') or info.get('live_status') in ('is_live','is_upcoming','post_live'):
        return None
    choices=[]
    for f in info.get('formats') or []:
        try:
            u=urlsplit(f.get('url','')); host=u.hostname or ''
            if (u.scheme!='https' or not host.endswith('.googlevideo.com') or u.username or u.password or u.port not in (None,443)
                or f.get('protocol')!='https' or f.get('ext')!='mp4' or f.get('has_drm') or f.get('fragments') or f.get('is_from_start')
                or f.get('vcodec') in (None,'none') or f.get('acodec') in (None,'none') or not 0 < int(f.get('height') or 0)<=360): continue
            choices.append(f)
        except (TypeError,ValueError): continue
    if not choices: return None
    f=max(choices,key=lambda x:(x.get('height') or 0,x.get('tbr') or 0))
    headers={}
    for layer in (info,f):
        for k,v in (layer.get('http_headers') or {}).items():
            if k.lower() in ('user-agent','referer','origin','accept','accept-language') and '\r' not in str(v) and '\n' not in str(v): headers[k]=str(v)
    return {'url':f['url'],'headers':headers}


def supports_range(plan):
    import requests
    try:
        with requests.get(plan['url'],headers={**plan['headers'],'Range':'bytes=1-1','Accept-Encoding':'identity'},stream=True,allow_redirects=False,timeout=(5,8)) as r:
            return r.status_code==206 and bool(re.fullmatch(r'bytes 1-1/[2-9]\d*|bytes 1-1/1\d+',r.headers.get('Content-Range',''),re.I))
    except requests.RequestException: return False


def command(plan,start,end,dest):
    headers=''.join(f'{k}: {v}\r\n' for k,v in plan['headers'].items())
    cmd=['ffmpeg','-hide_banner','-nostdin','-v','error','-y','-rw_timeout','15000000','-ss',f'{start:.3f}']
    if headers: cmd+=['-headers',headers]
    return cmd+['-i',plan['url'],'-t',f'{end-start:.3f}','-map','0:v:0','-map','0:a:0','-c:v','libx264','-preset','ultrafast','-crf','20','-threads','2','-c:a','aac','-b:a','96k',str(dest)]


def acquire(plan,start,end,dest,cancel,terminate,timeout=90):
    # FFmpeg's input seek is accurate when transcoding; range capability is
    # verified separately. Suppress diagnostics containing signed URLs.
    proc=subprocess.Popen(command(plan,start,end,dest),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    began=time.monotonic()
    try:
        while proc.poll() is None:
            if cancel() or time.monotonic()-began>timeout: return False
            time.sleep(.2)
        return proc.returncode==0 and dest.is_file()
    finally: terminate(proc)
