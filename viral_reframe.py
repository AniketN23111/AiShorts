"""Bounded, conservative single-face reframing for non-gaming media."""
import statistics, subprocess, tempfile, math, re, os
from pathlib import Path
from creator_edit import edit_plan,quiet_ranges

STYLES={ # max zoom, saturation, contrast, trim silence
 'podcast':(1.08,1.02,1.025,True), 'funny':(1.12,1.07,1.04,True),
 'educational':(1.025,1.015,1.025,True),'emotional':(1.025,1.01,1.02,False),
 'motivational':(1.07,1.045,1.04,True),'cinematic':(1.015,.96,1.045,False),
 'minimal':(1.,1.,1.,False),'energy':(1.12,1.075,1.055,True)}

def track(source,start,end):
    import performance as perf
    cache=None
    if os.getenv('SHORTS_PROCESSING_MODE') in perf.MODES and Path(source).is_file():
        cache=perf.cache_path('subject-track',f'{perf.fingerprint(source)}:{start:.3f}:{end:.3f}');prior=perf.read(cache)
        if isinstance(prior,list) and len(prior)==3:perf.count('tracking_cache_hits');return prior
    with perf.measure('subject_tracking'):result=_track(source,start,end)
    if cache:perf.save(cache,result)
    return result

def _track(source,start,end):
    import cv2
    cv2.setNumThreads(2);cap=cv2.VideoCapture(str(source));det=cv2.CascadeClassifier(cv2.data.haarcascades+'haarcascade_frontalface_default.xml');rows=[]
    try:
        w,h=int(cap.get(3)),int(cap.get(4));
        if w<=0 or h<=0:return [],0,0
        fps=cap.get(cv2.CAP_PROP_FPS) or 30;step=max(1,round(fps/2));cap.set(cv2.CAP_PROP_POS_MSEC,start*1000)
        for i in range(max(1,math.ceil((end-start)*fps))):
            if not cap.grab():break
            if i%step:continue
            t=start+i/fps;ok,im=cap.retrieve()
            if not ok:continue
            small=cv2.resize(im,(min(480,w),max(1,round(h*min(480,w)/w))));gray=cv2.cvtColor(small,cv2.COLOR_BGR2GRAY);sh,sw=gray.shape
            faces=det.detectMultiScale(gray,1.1,5,minSize=(24,24))
            # Avoid falsely claiming active-speaker recognition. Multiple faces use full fit.
            if len(faces)==1:
                x,y,a,b=faces[0];rows.append((t,(x+a/2)/sw,(y+b/2)/sh,a/sw,b/sh))
    finally:cap.release()
    if len(rows)<max(3,(end-start)*2*.7): return [],w,h
    if max(r[1] for r in rows)-min(r[1] for r in rows)>.48:return [],w,h
    return rows,w,h

def isolated_fillers(segments,start,end):
    words=sorted([w for s in segments for w in s.get('words',[]) if start<=w['start']<w['end']<=end],key=lambda w:w['start']); holes=[]
    for i,w in enumerate(words[1:-1],1):
        v=re.sub(r'[^\w]','',w['word'].casefold()); a,b=w['start'],w['end']; prev,nxt=words[i-1],words[i+1]
        if v in ('um','uh','erm','अं','अह') and .12<=b-a<=.8 and a-prev['end']>=.18 and nxt['start']-b>=.18 and (w.get('probability') or 0)>=.75: holes.append((a,b))
    return holes[:3]

def render(source,dest,segments,clip,software=False):
    from shorts import duration
    style=clip['viral_style'];zoom,sat,contrast,trim=STYLES[style];a,b=clip['start'],clip['end'];rows,w,h=track(source,a,b) if style in ('podcast','funny','emotional','motivational','energy') else ([],0,0)
    optimized=bool(clip.get('processing_mode'))
    fillers=isolated_fillers(segments,a,b) if trim else []
    quiet=quiet_ranges(source,a,b) if trim else []
    # Only trim long, detected trailing silence, never the payoff itself.
    trimmed_end=b
    for x,y in quiet:
        if y>=b-.08 and b-x>1.25 and x+.35-a>=(10 if optimized else 15) and not any(s['end']>x+.35 and s['start']<b for s in segments): trimmed_end=x+.35
    pieces,holes=edit_plan(segments,a,trimmed_end,quiet,fillers,event_only=optimized) if trim else ([(a,b)],[])
    if sum(y-x for x,y in pieces)<(10 if optimized else 15):pieces=[(a,b)];holes=[]
    impact=clip.get('impact',-1)
    if optimized and zoom>1.04 and style not in ('emotional','cinematic','minimal') and a<=impact<=b:
        pieces=[(l,r) for x,y in pieces for cuts in [[x]+[t for t in (impact,impact+1.4) if x+.35<t<y-.35]+[y]] for l,r in zip(cuts,cuts[1:])]
    with tempfile.TemporaryDirectory(prefix='viral-shots-',dir=dest.parent) as td:
        root=Path(td);paths=[]
        for i,(x,y) in enumerate(pieces):
            shot=root/f'shot{i:03}.mp4';paths.append(shot)
            # Preserve entire frame for gameplay-like, educational, or multi-face footage.
            nearby=[r for r in rows if x<=r[0]<=y];z=zoom if (x<impact+1.4 and y>impact and a<=impact<=b if optimized else i%2) else 1.
            if nearby and w/h>9/16:
                cw=max(2,int(h*9/16/z)//2*2);ch=max(2,int(h/z)//2*2)
                # Fit only when the single detected face is not too large for the crop.
                if max(r[3]*w for r in nearby)<cw*.68:
                    first=statistics.median(r[1] for r in nearby[:max(1,len(nearby)//3)]);last=statistics.median(r[1] for r in nearby[-max(1,len(nearby)//3):]);px=lambda v:max(0,min(w-cw,v*w-cw/2));py=max(0,min(h-ch,statistics.median(r[2] for r in nearby)*h-ch*.42))
                    vf=f'crop={cw}:{ch}:x={px(first):.2f}+({px(last)-px(first):.2f})*min(t/{max(.1,y-x):.3f}\\,1):y={py:.2f},scale=1080:1920'
                else:nearby=[]
            if not nearby or w/h<=9/16:
                vf='scale=1080:1920:force_original_aspect_ratio=decrease:force_divisible_by=2,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=0x10141c'
            vf+=f',setsar=1,fps=30,eq=saturation={sat}:contrast={contrast}'
            cmd=['ffmpeg','-v','error','-y','-ss',str(x),'-i',str(source),'-t',str(y-x),'-map','0:v:0','-map','0:a:0','-vf',vf,'-filter_threads','2','-pix_fmt','yuv420p','-ar','48000','-ac','2','-c:a','aac','-b:a','160k']
            from performance import encoder_args
            encoder=encoder_args(software) if optimized else None if software else ['-c:v','h264_videotoolbox','-b:v','8M']
            if encoder:
                result=subprocess.run(cmd+encoder+[str(shot)],timeout=180)
                if not result.returncode:continue
                software=True
            subprocess.run(cmd+['-c:v','libx264','-preset','veryfast','-crf','20','-threads','4',str(shot)],check=True,timeout=180)
        manifest=root/'shots.txt';manifest.write_text(''.join(f"file '{p.name}'\n" for p in paths));subprocess.run(['ffmpeg','-v','error','-y','-f','concat','-safe','1','-i',str(manifest),'-c','copy','-movflags','+faststart',str(dest)],check=True,timeout=120)
    return {'edit_style':'viral','layout':'subject_or_fit','face_tracking_observations':len(rows),'jump_cuts':len(holes),'shot_count':len(pieces),'removed_seconds':round(sum(y-x for x,y in holes)+max(0,b-trimmed_end),2),'filler_candidates':len(fillers),'output_duration':round(duration(dest),2),'edit_pieces':pieces}
