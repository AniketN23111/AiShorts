"""Public publishing, durable cross-session reservations, strict media validation."""
import contextlib, datetime, fcntl, hashlib, json, math, os, re, subprocess, time
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
import publisher

def parse_region(text):
    if not text: return None
    values=tuple(float(x) for x in text.split(','))
    if len(values)!=4 or not all(math.isfinite(x) for x in values): raise ValueError('Facecam region must be x,y,width,height as fractions')
    x,y,w,h=values
    if min(x,y)<0 or min(w,h)<.04 or x+w>1 or y+h>1: raise ValueError('Facecam region outside frame')
    return values

def identity(url,path):
    if url:
        u=urlsplit(url); vid=parse_qs(u.query).get('v',[''])[0] if u.path=='/watch' else u.path.rstrip('/').split('/')[-1]
        return 'youtube:'+vid
    if path:
        p=Path(path).expanduser(); stat=p.stat(); return 'local:'+hashlib.sha256(f'{p.resolve()}:{stat.st_size}:{stat.st_mtime_ns}'.encode()).hexdigest()
    return ''

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def quality(path, detailed=False):
    raw=subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)],timeout=30)
    info=json.loads(raw); v=next((s for s in info['streams'] if s['codec_type']=='video'),{}); a=next((s for s in info['streams'] if s['codec_type']=='audio'),{})
    d=float(info['format']['duration'])
    if (v.get('width'),v.get('height'))!=(1080,1920) or not 9.9<=d<=90.5 or not a or v.get('codec_name')!='h264' or a.get('codec_name')!='aac': raise ValueError('Quality check: expected 1080x1920 H.264/AAC and 10–90 seconds')
    # Full decode checks corruption; volumedetect verifies non-silent audio and peak.
    p=subprocess.run(['ffmpeg','-hide_banner','-nostats','-v','info','-xerror','-i',str(path),'-map','0:v:0','-map','0:a:0','-af','volumedetect'+(',silencedetect=n=-45dB:d=2' if detailed else '')]+(['-vf','blackdetect=d=0.45:pix_th=0.10,freezedetect=n=-50dB:d=3'] if detailed else [])+['-f','null','-'],capture_output=True,text=True,timeout=180)
    mean=re.search(r'mean_volume:\s*(-?[\d.]+) dB',p.stderr); peak=re.search(r'max_volume:\s*(-?[\d.]+) dB',p.stderr)
    if p.returncode or not mean or not peak or float(mean[1]) < -48 or float(peak[1])>=0: raise ValueError('Quality check: decoding failure, silent or clipped audio')
    result={'duration':d,'mean_db':float(mean[1]),'peak_db':float(peak[1])}
    if detailed:
        result.update(black_seconds=sum(float(x) for x in re.findall(r'black_duration:([\d.]+)',p.stderr)),silence_seconds=sum(float(x) for x in re.findall(r'silence_duration:\s*([\d.]+)',p.stderr)),frozen_seconds=sum(float(x) for x in re.findall(r'freeze_duration:\s*([\d.]+)',p.stderr)))
        # A trailing frozen frame run may not emit freeze_duration.
        starts=re.findall(r'freeze_start:\s*([\d.]+)',p.stderr); ends=re.findall(r'freeze_end:\s*([\d.]+)',p.stderr)
        if len(starts)>len(ends): result['frozen_seconds']+=max(0,d-float(starts[-1]))
    return result

@contextlib.contextmanager
def ledger():
    root=publisher.CONFIG; root.mkdir(mode=0o700,parents=True,exist_ok=True); file=root/'public-uploads.json'
    with (root/'public-uploads.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        records=json.loads(file.read_text()) if file.exists() else []
        def save(): publisher.secure_write(file,json.dumps(records,ensure_ascii=False,indent=2))
        yield records,save

def near_duplicate(a,b):
    if not isinstance(a,list) or not isinstance(b,list) or len(a)!=5 or len(b)!=5: return False
    try: return all((int(x,16)^int(y,16)).bit_count()<=5 for x,y in zip(a,b))
    except (ValueError,TypeError): return False

def publish(path,clip,args):
    from googleapiclient.http import MediaFileUpload
    if not args.authorized or args.made_for_kids not in ('yes','no') or clip['score']<args.score: raise ValueError('Publishing permission, audience or score gate not satisfied')
    title=str(clip['title']).strip(); desc='\n\n'.join(x for x in [clip.get('description',''), 'Source: '+clip['source_url'] if clip.get('source_url') else '', ' '.join(clip.get('hashtags',[]))] if x).replace('<','').replace('>','')
    from sound_studio import ensure_publish
    desc=ensure_publish(clip,'youtube',desc)
    if len(desc.encode('utf-8'))>5000 and clip.get('audio_timeline'): raise ValueError('Description including required music credit exceeds upload limit')
    if not 1<=len(title)<=100 or any(c in title for c in '<>'): raise ValueError('Invalid title')
    tags=[]; used=0
    for tag in clip.get('tags',[]):
        tag=' '.join(str(tag).split())[:60]
        if tag and tag not in tags and used+len(tag)+3<450: tags.append(tag);used+=len(tag)+3
    key=digest(path); q=quality(path); source=clip.get('source_identity',''); a,b=clip['start'],clip['end']; day=datetime.date.today().isoformat()
    with ledger() as (records,save):
        api=publisher.service(); ch=publisher.channel(api)
        if ch['id']!=args.publish_channel: raise ValueError('Channel mismatch; upload blocked')
        for r in records:
            if r['channel']!=ch['id']: continue
            same=r['sha256']==key or (source and r.get('source')==source and min(b,r['end'])-max(a,r['start'])>0.5)
            if not same and abs(float(r.get('duration',0))-q['duration'])<=2: same=near_duplicate(r.get('fingerprint'),clip.get('fingerprint'))
            if same: return {'state':'duplicate' if r['state']=='uploaded' else 'uncertain','id':r.get('id'),'message':'Existing or unresolved upload; no duplicate request sent'}
        if any(r['channel']==ch['id'] and r['title'].casefold()==title.casefold() for r in records): return {'state':'title_duplicate','message':'Title already used; edit the title before manually publishing.'}
        if sum(r['channel']==ch['id'] and r['day']==day for r in records)>=args.daily_limit: return {'state':'limit','message':'Daily upload limit reached'}
        # Persist intent before sending. Never replay an ambiguous completed upload.
        record={'channel':ch['id'],'sha256':key,'source':source,'start':a,'end':b,'day':day,'state':'pending','title':title,'duration':q['duration'],'score':clip['score'],'path':str(path),'quality':q,'viral_style':clip.get('viral_style'),'ratings':clip.get('ratings'),'caption_style':clip.get('caption_style'),'hook':clip.get('hook'),'cta':clip.get('cta'),'cta_displayed':clip.get('cta_displayed'),'topic':clip.get('category'),'fingerprint':clip.get('fingerprint')};records.append(record);save()
        request=api.videos().insert(part='snippet,status',body={'snippet':{'title':title,'description':desc.encode('utf-8')[:5000].decode('utf-8','ignore'),'tags':tags,'categoryId':{'gaming':'20','education':'27','entertainment':'24','people':'22'}.get(clip.get('category'),'20')},'status':{'privacyStatus':'public','selfDeclaredMadeForKids':args.made_for_kids=='yes'}},media_body=MediaFileUpload(str(path),mimetype='video/mp4',chunksize=8*1024*1024,resumable=True))
        try:
            response=None
            while response is None: _,response=request.next_chunk(num_retries=4)
            record.update(state='uploaded',id=response['id'],visibility=response.get('status',{}).get('privacyStatus','requested_public'));save()
            result={'state':'uploaded' if record['visibility']=='public' else 'visibility_unconfirmed' if record['visibility']=='requested_public' else 'visibility_mismatch','id':response['id'],'url':'https://www.youtube.com/watch?v='+response['id'],'visibility':response.get('status',{}).get('privacyStatus','requested_public')}
            publisher.secure_write(path.with_suffix('.upload.json'),json.dumps(result)); return result
        except Exception:
            record['state']='uncertain';save(); raise RuntimeError('Upload outcome uncertain; check YouTube Studio. The ledger blocks repeat attempts.') from None
