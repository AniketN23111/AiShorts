#!/usr/bin/env python3
"""Loopback-only UI for the local Shorts pipeline; no additional Python web dependencies."""
import json, os, re, shutil, signal, subprocess, sys, threading, time, uuid, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, unquote
from youtube_source import validate_url, eta

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'output'
LOCK = threading.Lock()
ACTIVE = None
HOST = '127.0.0.1:8000'


def validate(data):
    if not isinstance(data,dict) or data.get('authorized') is not True:
        raise ValueError('Confirm that you have permission to acquire and reuse this video.')
    if data.get('source_type','youtube') == 'local':
        p=Path(str(data.get('local_path',''))).expanduser().resolve()
        if not p.is_file() or p.suffix.lower() not in {'.mp4','.mkv','.mov','.webm','.m4v'}:
            raise ValueError('Enter the full path to an existing local video (MP4, MKV, MOV, WEBM).')
        url=str(p)
    elif data.get('source_type','youtube') == 'youtube':
        url=validate_url(str(data.get('url','')).strip())
    else: raise ValueError('Invalid source type.')
    if data.get('source_auth','public') not in ('public','chrome'): raise ValueError('Invalid viewing session.')
    if data.get('edit_style','clean') not in ('clean','dynamic','gaming'): raise ValueError('Invalid editing style.')
    count,minutes,segment,score=(int(data.get(k,v)) for k,v in [('count',6),('minutes',0),('segment',120),('score',75)])
    layout,language=data.get('layout','original'),data.get('language','')
    mode=data.get('mode','auto')
    if not (0<=count<=100 and 0<=minutes<=720 and segment in (60,120,180) and 0<=score<=100 and layout in ('original','fit','crop') and language in ('','en','hi','mr') and mode in ('auto','live','replay')):
        raise ValueError('Invalid clip settings.')
    from viral import PRESETS, CAPTIONS
    if data.get('viral_preset','') not in ('',*PRESETS) or data.get('viral_captions','off') not in CAPTIONS: raise ValueError('Invalid viral preset or caption style.')
    if data.get('face_region'):
        from auto_publish import parse_region
        parse_region(data['face_region'])
    if data.get('auto_public') is True:
        if (data.get('edit_style')!='gaming' and not data.get('viral_preset')) or not data.get('channel_id') or data.get('audience') not in ('yes','no') or data.get('public_confirm') is not True or not 1<=int(data.get('daily_limit',6))<=30: raise ValueError('Public publishing requires Gaming or Viral mode, verified channel, audience, consent and daily limit.')
    if data.get('auto_instagram') is True:
        if (data.get('edit_style')!='gaming' and not data.get('viral_preset')) or not re.fullmatch(r'\d+',str(data.get('instagram_account',''))) or data.get('instagram_confirm') is not True or not 1<=int(data.get('daily_limit',6))<=30: raise ValueError('Instagram requires verified professional account, explicit authorization and Gaming or Viral mode.')
    return url,count,minutes,layout,language,segment,score,mode


def start(data):
    global ACTIVE
    url,count,minutes,layout,language,segment,score,mode=validate(data)
    with LOCK:
        if ACTIVE and ACTIVE['proc'].poll() is None: raise ValueError('A session is already running.')
        for tool in ('ffmpeg','ffprobe'):
            if not shutil.which(tool): raise ValueError(f'{tool} is missing. Run setup first.')
        try:
            with urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=3) as response:
                models=json.load(response).get('models',[])
        except (OSError, ValueError) as exc:
            raise ValueError('Ollama is not running. Open Ollama first.') from exc
        from shorts import MODEL
        if not any(m.get('name')==MODEL or m.get('model')==MODEL for m in models):
            raise ValueError(f'Model not installed. Run ollama pull {MODEL}.')
        job=uuid.uuid4().hex; folder=OUTPUT/job; folder.mkdir(parents=True)
        cmd=[sys.executable,'-u',str(ROOT/'live.py'),'--input-file' if data.get('source_type')=='local' else '--url',url,'--mode',mode,'--authorized','--count',str(count),'--minutes',str(minutes),'--layout',layout,'--segment',str(segment),'--score',str(score),'--output',str(folder)]
        cmd+=['--edit-style',data.get('edit_style','clean')]
        if data.get('edit_style')=='gaming':
            cmd+=['--streamer',str(data.get('streamer',''))[:80],'--game',str(data.get('game',''))[:80]]
            if data.get('face_region'): cmd+=['--face-region',data['face_region']]
        if data.get('viral_preset'):
            cmd+=['--viral-preset',data['viral_preset'],'--viral-captions',data.get('viral_captions','off')]
            if data.get('viral_overlays') is True: cmd+=['--viral-overlays']
            if data.get('viral_variants') is True: cmd+=['--viral-variants']
            if data.get('viral_full_scan') is True: cmd+=['--viral-full-scan']
        feedback_channel=data.get('feedback_channel') or data.get('channel_id')
        if feedback_channel:
            cmd+=['--feedback-channel',str(feedback_channel)[:100]]
            if data.get('analytics_refresh') is True: cmd+=['--analytics-refresh']
        if data.get('software') is True: cmd+=['--software']
        if data.get('auto_public') is True:
            import publisher
            if publisher.channel(publisher.service())['id']!=data['channel_id']: raise ValueError('Connected channel changed.')
            cmd+=['--publish-channel',data['channel_id'],'--made-for-kids',data['audience'],'--daily-limit',str(int(data.get('daily_limit',6)))]
        if data.get('auto_instagram') is True:
            from instagram_publisher import account, InstagramError
            try: ig=account()
            except InstagramError as exc: raise ValueError(str(exc)) from None
            if ig['id']!=data['instagram_account']: raise ValueError('Instagram account changed.')
            cmd+=['--instagram-account',ig['id']]
            if data.get('auto_public') is not True: cmd+=['--daily-limit',str(int(data.get('daily_limit',6)))]
        if data.get('smart_replay') is True: cmd+=['--smart-replay']
        elif data.get('native_fallback') is True: cmd+=['--native-fallback']
        if data.get('source_type','youtube')=='youtube' and data.get('source_auth')=='chrome': cmd+=['--browser','chrome']
        if language: cmd+=['--language',language]
        if data.get('captions') is True and data.get('edit_style')!='gaming': cmd+=['--captions']
        if data.get('keep_source') is True: cmd+=['--keep-source']
        with (folder/'run.log').open('w') as log:
            proc=subprocess.Popen(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        ACTIVE={'id':job,'proc':proc,'started':time.time(),'stopped':False}
        return job


def current():
    with LOCK:
        if not ACTIVE:
            return {'id':None}
        return status(ACTIVE)


def status(job):
    folder=OUTPUT/job['id']; rc=job['proc'].poll()
    if rc is not None: job.setdefault('finished',time.time())
    state='running' if rc is None else 'failed' if rc != 0 else 'stopped' if job['stopped'] else 'done'
    info={'stage':'source','message':'Connecting…','eta':'Estimating','progress':None,'capture':'connecting','segments_ready':0,'segments_processed':0,'captured_seconds':0,'target':6}
    if (folder/'status.json').exists(): info.update(json.loads((folder/'status.json').read_text()))
    from live import closed_segments
    info['segments_ready']=max(info['segments_ready'],len(closed_segments(folder/'capture')))
    if info.get('capture') in ('live','replay') and (folder/'capture_done').exists(): info['capture']='ended'
    clips=[]
    for manifest in folder.glob('*/clips.json'):
        for clip in json.loads(manifest.read_text()):
            name=clip.get('file','')
            if re.fullmatch(r'short_\d+\.mp4',name) and (manifest.parent/name).is_file():
                clips.append({**clip,'video':f'/media/{job["id"]}/{manifest.parent.name}/{name}','subtitle':f'/media/{job["id"]}/{manifest.parent.name}/{Path(name).stem}.srt' if (manifest.parent/Path(name).with_suffix('.srt')).exists() else None})
    for clip in clips:
        if clip.get('viral'):
            base=clip['video'].rsplit('/',1)[0]+'/'
            clip['variations']=[{**v,'video':base+v['file']} for v in clip.get('variations',[]) if re.fullmatch(r'short_\d+_alt\.mp4',v.get('file',''))]
            if clip.get('thumbnail_file'): clip['thumbnail']=base+clip['thumbnail_file']
            words=OUTPUT/job['id']/clip['video'].split('/')[-2]/(Path(clip['file']).stem+'_words.json')
            if words.is_file(): clip['words_url']=base+words.name
    logs=[]
    for name in ('run.log','capture.log','download.log'):
        p=folder/name
        if p.exists():
            with p.open('rb') as f:
                f.seek(max(0,f.seek(0,2)-8000)); chunk=f.read().decode(errors='replace'); logs.append(name+'\n'+re.sub(r'https?://[^\s<>\"\']*googlevideo\.com/[^\s<>\"\']+', '[temporary media URL redacted]', chunk))
    if state=='running' and info.get('stage_estimate') is not None and info.get('stage_started') and info.get('stage') in ('transcribe','analyze','export'):
        remaining=info['stage_estimate']-(time.time()-info['stage_started'])
        info['eta']='~'+eta(remaining) if remaining>0 else 'Re-estimating'
    if state!='running': info.update(capture='ended',eta='—',message=f'{len(clips)} highlights ready' if state!='failed' else info['message'] if info.get('stage')=='error' else 'Session failed. See logs; completed highlights are retained.')
    if (folder/'disk_limit').exists(): info['message']+=' · Capture stopped: low disk space.'
    if job['stopped'] and state=='running' and info['capture']!='ended': info['capture']='stopping'
    return {**info,'id':job['id'],'state':state,'elapsed':max(0,int(job.get('finished',time.time())-job['started'])),'logs':'\n'.join(logs),'clips':clips}


class Handler(BaseHTTPRequestHandler):
    def end_headers(self):
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        super().end_headers()
    def reply(self, data, code=200):
        body=json.dumps(data).encode()
        self.send_response(code); self.send_header('Content-Type','application/json'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    def allowed(self):
        return self.headers.get('Host') == HOST
    def do_GET(self):
        if not self.allowed(): return self.reply({'error':'Invalid host'},403)
        path=unquote(urlsplit(self.path).path)
        if path == '/api/status': return self.reply(current())
        if path == '/api/analytics':
            from publisher import CONFIG
            file=CONFIG/'analytics-feedback.json'
            try: return self.reply(json.loads(file.read_text()) if file.exists() else {'sample':[],'summary':'No analytics collected.'})
            except (OSError,ValueError): return self.reply({'error':'Cannot read local analytics cache.'},400)
        if path == '/api/instagram':
            try:
                from instagram_publisher import account
                return self.reply(account())
            except Exception: return self.reply({'error':'Instagram not connected or unavailable. Run python instagram_publisher.py connect in Terminal.'},400)
        if path == '/api/channel':
            try:
                import publisher
                return self.reply(publisher.channel(publisher.service()))
            except Exception: return self.reply({'error':'Channel not connected or unavailable. Run python publisher.py connect in Terminal.'},400)
        if path == '/': return self.file(ROOT/'index.html','text/html; charset=utf-8')
        m=re.fullmatch(r'/media/([0-9a-f]{32})/(\d{8}_\d{6}_\d{6})/(short_\d+(?:\.(?:mp4|srt)|_alt\.mp4|_review\.mp4|_words\.json|_thumb\.jpg))',path)
        if m:
            p=OUTPUT.joinpath(*m.groups())
            return self.file(p,'video/mp4' if p.suffix=='.mp4' else 'application/json' if p.suffix=='.json' else 'image/jpeg' if p.suffix=='.jpg' else 'application/octet-stream')
        return self.reply({'error':'Not found'},404)
    def do_POST(self):
        if not self.allowed() or self.headers.get('Origin') != 'http://'+HOST or self.headers.get('X-Local-UI') != '1':
            return self.reply({'error':'Invalid local request'},403)
        try:
            if self.path == '/api/analytics/import':
                n=int(self.headers.get('Content-Length','0'))
                if not 0<n<=500000: raise ValueError('Invalid CSV request size.')
                data=json.loads(self.rfile.read(n)); from analytics_feedback import import_csv
                return self.reply(import_csv(str(data.get('channel_id','')),str(data.get('csv',''))))
            if self.path == '/api/analytics/refresh':
                try:
                    from analytics_feedback import refresh
                    refresh()
                    return self.reply({'ok':True})
                except Exception: return self.reply({'error':'Analytics refresh failed. Check the analytics OAuth scope and YouTube Analytics API.'},400)
            if self.path == '/api/captions/review':
                n=int(self.headers.get('Content-Length','0'))
                if not 0<n<=150000: raise ValueError('Invalid caption request size.')
                data=json.loads(self.rfile.read(n))
                m=re.fullmatch(r'/media/([0-9a-f]{32})/(\d{8}_\d{6}_\d{6})/(short_\d+\.mp4)',str(data.get('video','')))
                if not m: raise ValueError('Invalid clip path.')
                path=OUTPUT.joinpath(*m.groups()); master=path.with_name(path.stem+'_master.mp4'); original=path.with_name(path.stem+'_words.json')
                if not master.is_file() or not original.is_file(): raise ValueError('No editable caption master exists.')
                words=json.loads(original.read_text()); edits=data.get('words')
                if not isinstance(edits,list) or len(edits)!=len(words) or any(not isinstance(w,str) or not w.strip() or len(w)>80 for w in edits): raise ValueError('Provide one nonempty correction per original timed word.')
                for w,value in zip(words,edits): w['word']=value
                clip=next((c for c in json.loads((path.parent/'clips.json').read_text()) if c.get('file')==path.name),None)
                if not clip: raise ValueError('Clip not found.')
                from viral import decorate,validate_export
                dest=path.with_name(path.stem+'_review.mp4'); pending=dest.with_name('pending_'+dest.name)
                with LOCK:
                    if ACTIVE and ACTIVE['proc'].poll() is None: raise ValueError('Wait for active processing to finish before rendering caption corrections.')
                    try:
                        decorate(master,pending,words,clip,clip['caption_style'],clip.get('overlays',False),False)
                        validate_export(pending,words,clip['caption_style']); os.replace(pending,dest)
                    finally: pending.unlink(missing_ok=True)
                return self.reply({'video':data['video'].rsplit('/',1)[0]+'/'+dest.name})
            if self.path == '/api/instagram/upload':
                n=int(self.headers.get('Content-Length','0'))
                if not 0<n<=16384: raise ValueError('Invalid request size.')
                data=json.loads(self.rfile.read(n))
                m=re.fullmatch(r'/media/([0-9a-f]{32})/(\d{8}_\d{6}_\d{6})/(short_\d+\.mp4)',str(data.get('video','')))
                if not m or data.get('approved') is not True or not re.fullmatch(r'\d+',str(data.get('account_id',''))): raise ValueError('Confirm clip rights and verified Instagram account.')
                path=OUTPUT.joinpath(*m.groups()); manifest=path.parent/'clips.json'
                if not path.is_file() or not manifest.is_file(): raise ValueError('Clip not found.')
                clip=next((c for c in json.loads(manifest.read_text()) if c.get('file')==path.name),None)
                if not clip or (clip.get('edit_style')!='gaming' and not (clip.get('viral') and clip.get('quality'))): raise ValueError('Instagram requires a validated Gaming or Viral export.')
                from instagram_publisher import publish, InstagramError
                from types import SimpleNamespace
                try: return self.reply(publish(path,clip,SimpleNamespace(authorized=True,score=85,instagram_account=data['account_id'],daily_limit=6),caption=data.get('caption')))
                except InstagramError as exc: return self.reply({'error':str(exc)},502)
            if self.path == '/api/upload':
                n=int(self.headers.get('Content-Length','0'))
                if not 0<n<=16384: raise ValueError('Invalid request size.')
                data=json.loads(self.rfile.read(n))
                m=re.fullmatch(r'/media/([0-9a-f]{32})/(\d{8}_\d{6}_\d{6})/(short_\d+\.mp4)',str(data.get('video','')))
                if not m: raise ValueError('Invalid clip path.')
                path=OUTPUT.joinpath(*m.groups())
                if not path.is_file(): raise ValueError('Clip not found.')
                from auto_publish import publish
                from types import SimpleNamespace
                if data.get('approved') is not True or type(data.get('made_for_kids')) is not bool or not data.get('channel_id'): raise ValueError('Confirm rights, audience and verified channel.')
                manifest=path.parent/'clips.json'
                clip=next((c for c in json.loads(manifest.read_text()) if c.get('file')==path.name),None) if manifest.exists() else None
                if not clip or (clip.get('edit_style')!='gaming' and not (clip.get('viral') and clip.get('quality'))): raise ValueError('Public publishing is available for validated Gaming or Viral exports.')
                clip={**clip,'title':data.get('title',clip['title']),'description':data.get('description',clip.get('description',''))}
                try: return self.reply(publish(path,clip,SimpleNamespace(authorized=True,made_for_kids='yes' if data['made_for_kids'] else 'no',score=85,publish_channel=data['channel_id'],daily_limit=6)))
                except ValueError: raise
                except Exception: return self.reply({'error':'Upload failed or outcome uncertain. Check YouTube Studio and the local publishing ledger before retrying.'},502)
            if self.path == '/api/start':
                n=int(self.headers.get('Content-Length','0'))
                if not 0<n<=8192: raise ValueError('Invalid request size.')
                return self.reply({'id':start(json.loads(self.rfile.read(n)))})
            if self.path == '/api/stop':
                with LOCK:
                    if ACTIVE and ACTIVE['proc'].poll() is None:
                        ACTIVE['stopped']=True
                        (OUTPUT/ACTIVE['id']/'stop').touch()
                return self.reply({'ok':True})
            return self.reply({'error':'Not found'},404)
        except (ValueError, TypeError, OSError, subprocess.SubprocessError) as exc:
            return self.reply({'error':str(exc)},400)
    def file(self,p,mime):
        if not p.is_file(): return self.reply({'error':'Not found'},404)
        size=p.stat().st_size; a,b=0,size-1; code=200
        r=self.headers.get('Range')
        if r:
            m=re.fullmatch(r'bytes=(\d*)-(\d*)',r)
            if not m or not (m[1] or m[2]): self.send_error(416); return
            a=int(m[1]) if m[1] else max(0,size-int(m[2])); b=min(size-1,int(m[2])) if m[1] and m[2] else size-1
            if a>b or a>=size: self.send_error(416); return
            code=206
        self.send_response(code); self.send_header('Content-Type',mime); self.send_header('Accept-Ranges','bytes'); self.send_header('Content-Length',str(b-a+1))
        if code==206: self.send_header('Content-Range',f'bytes {a}-{b}/{size}')
        self.end_headers()
        with p.open('rb') as f:
            f.seek(a); left=b-a+1
            try:
                while left:
                    chunk=f.read(min(left,128*1024))
                    if not chunk: break
                    self.wfile.write(chunk); left-=len(chunk)
            except (BrokenPipeError,ConnectionResetError): pass
    def log_message(self,fmt,*args): pass


if __name__=='__main__':
    server=ThreadingHTTPServer(('127.0.0.1',8000),Handler)
    print('AI Shorts Studio: http://'+HOST,flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        with LOCK:
            if ACTIVE and ACTIVE['proc'].poll() is None:
                os.killpg(ACTIVE['proc'].pid,signal.SIGTERM)
        server.server_close()
