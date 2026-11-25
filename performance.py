"""V13 bounded scanning, content-addressed caches, timing and editorial primitives.
No network services or new models. Signals propose windows, never establish quality.
"""
import contextlib, functools, hashlib, json, math, os, re, resource, subprocess, time, threading
from pathlib import Path

MODES=('fast','smart','professional')
WEIGHTS={'hook':25,'retention':25,'entertainment':20,'story':15,'emotion':10,'rewatch':5}
PATTERNS=('setup_outcome','question_answer','challenge_victory','argument_resolution','conversation_comedy','suspense_reveal','mistake_consequence','fact_explanation','prediction_result','emotional_payoff','other')
PENALTIES=('missing_context','boring_sections','weak_ending','unclear_speech','poor_visual_quality','repetitive_content','misleading_editing','duplicate_moment')
_STATS={}; _COUNTS={}; _REJECTIONS={}; _START=time.monotonic(); _LOCK=threading.RLock()

def count(name,n=1):
    with _LOCK: _COUNTS[name]=_COUNTS.get(name,0)+n
def reject(reason):
    reason=str(reason)[:140]
    with _LOCK:
        _REJECTIONS[reason]=_REJECTIONS.get(reason,0)+1
        count("rejected_candidates")
@contextlib.contextmanager
def measure(name):
    start=time.monotonic()
    try: yield
    finally:
        with _LOCK:
            _STATS[name]=_STATS.get(name,0)+time.monotonic()-start
            count(name+'_calls')

def timed(name):
    def wrap(fn):
        @functools.wraps(fn)
        def call(*a,**kw):
            with measure(name): return fn(*a,**kw)
        return call
    return wrap

def snapshot():
    import sys
    usage=resource.getrusage(resource.RUSAGE_SELF); children=resource.getrusage(resource.RUSAGE_CHILDREN)
    scale=1024**2 if sys.platform=='darwin' else 1024
    with _LOCK: return {'seconds':{k:round(v,3) for k,v in _STATS.items()},'counts':dict(_COUNTS),'rejection_reasons':dict(_REJECTIONS),'worker_peak_rss_mib':round(usage.ru_maxrss/scale,1),'largest_finished_child_peak_rss_mib':round(children.ru_maxrss/scale,1),'worker_cpu_seconds':round(usage.ru_utime+usage.ru_stime,2),'elapsed_seconds':round(time.monotonic()-_START,2)}

@functools.lru_cache(maxsize=32)
def _fingerprint(path,size,mtime):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def fingerprint(path):
    p=Path(path).resolve(); s=p.stat(); return _fingerprint(str(p),s.st_size,s.st_mtime_ns)

def cache_path(kind,key):
    from publisher import CONFIG
    root=CONFIG/'performance-cache'/kind; root.mkdir(parents=True,exist_ok=True,mode=0o700)
    return root/(hashlib.sha256(('v13.1:'+os.getenv('SHORTS_CACHE_VERSION','v13')+':'+key).encode()).hexdigest()+'.json')

def read(path):
    try:
        obj=json.loads(path.read_text()); os.utime(path,None); return obj
    except (OSError,ValueError): return None

def save(path,obj):
    from publisher import secure_write
    secure_write(path,json.dumps(obj,ensure_ascii=False))
    for old in sorted(path.parent.glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)[200:]: old.unlink(missing_ok=True)

def rms_from_wav(source,wav):
    """Reuse the exact PCM used by ASR rather than decoding the video again."""
    import wave,numpy as np
    p=cache_path('audio',fingerprint(source)); values=[]
    with wave.open(str(wav),'rb') as f:
        rate=f.getframerate()
        while chunk:=f.readframes(rate):
            a=np.frombuffer(chunk,dtype='<i2').astype(np.float32)/32768
            values.append(round(float(np.sqrt(np.mean(a*a))),4))
    save(p,values)

def audio(source,start,end):
    from gaming import audio_features
    p=cache_path('audio',fingerprint(source)); data=read(p)
    if isinstance(data,list):
        count('audio_cache_hits'); return data[int(start):math.ceil(end)]
    count('audio_extra_decodes'); return audio_features(source,start,end)

@timed('scan')
def scan(source,start,end,fps=1):
    """Low resolution sequential FFmpeg scan. No per-frame face classifier."""
    import numpy as np
    p=cache_path('scan',f'{fingerprint(source)}:{start:.3f}:{end:.3f}:{fps}')
    old=read(p)
    if isinstance(old,list): count('scan_cache_hits'); return old
    width,height=160,90; step=width*height
    cmd=['ffmpeg','-v','error','-ss',str(start),'-i',str(source),'-t',str(end-start),'-an','-vf',f'fps={fps},scale={width}:{height},format=gray','-threads','2','-filter_threads','2','-f','rawvideo','-pix_fmt','gray','-']
    raw=subprocess.check_output(cmd,timeout=180)
    frames=[];prev=None
    for i in range(len(raw)//step):
        gray=np.frombuffer(raw[i*step:(i+1)*step],dtype=np.uint8).astype(np.int16)
        motion=float(np.mean(np.abs(gray-prev)))/255 if prev is not None else 0.; prev=gray
        frames.append({'t':round(start+i/fps,2),'motion':round(motion,3),'face':False,'dark':float(np.mean(gray))<18,'scene_change':motion>.25})
    if not frames: raise ValueError('No video frames decoded during scan')
    save(p,frames);count('sampled_frames',len(frames));return frames

def visual_window(frames,speech,lo,total,boundary):
    """Find ONE visually active candidate window with little speech for deeper inspection."""
    best=None
    for mid in range(max(0,int(boundary)-10),math.ceil(total),10):
        a=max(lo,mid-10); b=min(total,mid+20)
        if b-a<10: continue
        fs=[f for f in frames if a<=f['t']<b and not f['dark']]
        if len(fs)<3: continue
        spoken=sum(max(0,min(b,s['end'])-max(a,s['start'])) for s in speech)
        if spoken>(b-a)*.45: continue
        signal=sum(f['motion'] for f in fs)/len(fs)
        if signal>=.025 and (best is None or signal>best[0]): best=(signal,a,b)
    return best[1:] if best else None

def story_score(ratings,penalties):
    if not isinstance(ratings,dict) or any(type(ratings.get(k)) not in (int,float) or not math.isfinite(ratings[k]) or not 0<=ratings[k]<=100 for k in WEIGHTS): raise ValueError('Invalid story ratings')
    if not isinstance(penalties,dict) or any(type(penalties.get(k)) not in (int,float) or not math.isfinite(penalties[k]) or not 0<=penalties[k]<=10 for k in PENALTIES): raise ValueError('Invalid story penalties')
    if penalties['misleading_editing'] or penalties['duplicate_moment']: raise ValueError('Misleading or duplicate moment')
    return round(max(0,sum(ratings[k]*v/100 for k,v in WEIGHTS.items())-sum(penalties.values())),1)

def align(a,b,segments,lo,total):
    # Expand to intact speech phrase boundaries, only when a proposed cut bisects it.
    for s in segments:
        x,y=float(s['start']),float(s['end'])
        if x+.05<a<y-.05 and a-x<=3: a=max(lo,x-.08)
        if x+.05<b<y-.05 and y-b<=3: b=min(total,y+.15)
    # Never silently accept cuts deep inside a long phrase.
    if any(s['start']+.12<a<s['end']-.12 or s['start']+.12<b<s['end']-.12 for s in segments): raise ValueError('Candidate cuts a speech phrase')
    return a,b

def dialogue(segments,a,b):
    words=[]
    for s in segments:
        if s['end']<=a or s['start']>=b: continue
        if s.get('words'): words.extend(w['word'] for w in s['words'] if w['start']>=a and w['end']<=b)
        else: words.append(s['text'])
    return ' '.join(words)

def similar(a,b):
    # Conservative lexical duplicate indicator, not semantic embedding similarity.
    def grams(t):
        w=re.findall(r'\w+',str(t).casefold());return set(zip(w,w[1:],w[2:]))
    x,y=grams(a),grams(b)
    return min(len(x),len(y))>=8 and len(x&y)/min(len(x),len(y))>=.82

def map_words(segments,pieces,length):
    """Map actual source ASR words to a cut timeline; merge adjacent shots first."""
    merged=[]
    for a,b in pieces:
        if merged and abs(a-merged[-1][1])<.001: merged[-1]=(merged[-1][0],b)
        else: merged.append((a,b))
    src=sorted((w for s in segments for w in s.get('words',[])),key=lambda w:w['start']); out=[]; offset=0.
    for a,b in merged:
        for w in src:
            x,y=w['start'],w['end']
            if x>=a-.025 and y<=b+.025 and y>x:
                x=max(0,offset+x-a); y=min(length,offset+y-a)
                if y>x:out.append({**w,'start':round(x,3),'end':round(y,3)})
        offset+=b-a
    # Only reuse if the actual output clock is close to the edit plan and no cut slices a spoken word.
    if abs(length-offset)>.35 or any(any(w['start']+.03<t<w['end']-.03 for t in (a,b)) for a,b in merged for w in src): return []
    return out

@functools.lru_cache(maxsize=1)
def encoders():
    try:
        listing=subprocess.check_output(['ffmpeg','-hide_banner','-encoders'],text=True,timeout=10,stderr=subprocess.STDOUT)
    except (OSError,subprocess.SubprocessError): return ()
    import sys
    # Probe actual encoding support rather than assuming an encoder listed by FFmpeg works.
    preferred=['h264_videotoolbox'] if sys.platform=='darwin' else ['h264_nvenc','h264_qsv','h264_amf']
    ok=[]
    for name in preferred:
        if name not in listing: continue
        try:
            p=subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=s=128x128:r=10','-frames:v','2','-c:v',name,'-f','null','-'],capture_output=True,timeout=10)
            if not p.returncode: ok.append(name)
        except (OSError,subprocess.SubprocessError): pass
    return tuple(ok)

def encoder_args(software):
    available=encoders() if not software else ()
    return ['-c:v',available[0],'-b:v','8M'] if available else None

@timed('audio_alignment')
def audio_alignment(preview,media,start,length,media_start=0.):
    """Verify preview-to-HD alignment on multiple waveform anchors.
    Returns offset on preview clock relative to requested start, or None.
    Fail closed for silence, ambiguous repeated patterns, drift, or decode errors.
    """
    import numpy as np
    rate=8000; pad=.32; left=max(0,start-pad); right=start+length+pad
    def decode(path,a,b):
        cmd=['ffmpeg','-v','error','-ss',str(a),'-i',str(path),'-t',str(b-a),'-vn','-ac','1','-ar',str(rate),'-f','f32le','-']
        return np.frombuffer(subprocess.check_output(cmd,timeout=60),dtype='<f4').astype(np.float64)
    try: x=decode(preview,left,right); y=decode(media,media_start,media_start+length)
    except (OSError,subprocess.SubprocessError): return None
    if len(y)<rate*5:return None
    offsets=[]; radius=int(rate*.23); n=rate*2
    for fraction in (.18,.38,.62,.82):
        idx=int(len(y)*fraction)-n//2; origin=round((start-left)*rate)+idx
        base=origin-radius; stop=origin+n+radius
        if idx<0 or idx+n>len(y) or base<0 or stop>len(x): continue
        target=y[idx:idx+n]; target=target-target.mean(); norm=np.linalg.norm(target)
        if norm/np.sqrt(n)<.008:continue
        search=x[base:stop]; size=1<<(len(search)+n-1).bit_length()
        corr=np.fft.irfft(np.fft.rfft(search,size)*np.fft.rfft(target[::-1],size),size)[n-1:len(search)]
        c=np.concatenate(([0.],np.cumsum(search))); c2=np.concatenate(([0.],np.cumsum(search*search)))
        energy=np.maximum(c2[n:]-c2[:-n]-(c[n:]-c[:-n])**2/n,1e-12)
        matches=corr/(norm*np.sqrt(energy)); best=int(np.argmax(matches)); peak=float(matches[best]); mask=np.abs(np.arange(len(matches))-best)>int(rate*.055)
        if peak<.90 or (mask.any() and peak-float(np.max(matches[mask]))<.035): continue
        offsets.append((best-radius)/rate)
    if len(offsets)<3 or max(offsets)-min(offsets)>.045:return None
    return float(np.median(offsets))


def aligned_segments(segments,start,end,delta,actual_length):
    # Keep only full speech phrases, never invent clipped words or timestamps.
    if delta is None:return []
    a=start+delta; b=min(end+delta,a+actual_length); result=[]
    for s in segments:
        if s['end']<=a or s['start']>=b:continue
        words=s.get('words') or []
        if not words:return []
        kept=[]
        for w in words:
            if w['end']<=a or w['start']>=b:continue
            if w['start']<a-.05 or w['end']>b+.05:return []
            x=max(0,w['start']-a);y=min(actual_length,w['end']-a)
            if x<y:kept.append({**w,'start':x,'end':y})
        if kept:result.append({'start':kept[0]['start'],'end':kept[-1]['end'],'text':' '.join(w['word'] for w in kept),'words':kept})
    return result if sum(len(s['words']) for s in result)>=3 else []
