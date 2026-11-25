"""Speech-aware edits: conservative jump cuts, reframing and remapped subtitles."""
import math, subprocess, tempfile, re
from pathlib import Path


def edit_plan(segments, start, end, silence=None, extra_holes=None, event_only=False):
    """Remove only interior gaps between transcript phrases; never remove dialogue.
    Gaps are estimates from ASR, not a guarantee of acoustic silence.
    Split retained ranges for restrained punch-ins, at most every ~8 seconds.
    """
    speech = sorted((max(start,float(s['start'])),min(end,float(s['end']))) for s in segments
                    if s.get('text','').strip() and s['end']>start and s['start']<end)
    speech = [(a,b) for a,b in speech if b>a]
    holes=[]
    if speech:
        last=speech[0][1]
        for a,b in speech[1:]:
            if a-last>=1.25:
                # Keep breaths and reaction time; remove at most 2.5s per gap.
                x=last+0.32; y=min(a-0.32,x+2.5)
                if y-x>=0.6: holes.append((x,y))
            last=max(last,b)
    # When acoustic measurements are available, intersect transcript gaps
    # with confirmed quiet audio. This protects laughter and other reactions.
    if silence is not None:
        holes=[(max(a,x),min(b,y)) for a,b in holes for x,y in silence
               if min(b,y)-max(a,x)>=0.6]
    # Additional cuts are only supplied by the opt-in viral editor for isolated fillers.
    holes=sorted(holes+[(max(start+.2,a),min(end-.2,b)) for a,b in (extra_holes or []) if start+.2<a<b<end-.2])
    merged=[]
    for a,b in holes:
        if merged and a<=merged[-1][1]: merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
        else: merged.append((a,b))
    holes=merged
    # Never remove more than 20% of source duration or more than 6 gaps.
    budget=(end-start)*0.2; chosen=[]
    for a,b in holes[:6]:
        length=min(b-a,budget)
        if length>=0.6 or (extra_holes and (a,b) in extra_holes and length>=.12): chosen.append((a,a+length)); budget-=length
    ranges=[]; pos=start
    for a,b in chosen:
        if a-pos>0.1: ranges.append((pos,a))
        pos=b
    if end-pos>0.1: ranges.append((pos,end))
    pieces=[]
    for a,b in ranges:
        # Avoid rapid artificial changes. Use evenly spaced 6–9s shots.
        n=1 if event_only else max(1,math.ceil((b-a)/9))
        for i in range(n):
            pieces.append((a+(b-a)*i/n,a+(b-a)*(i+1)/n))
    return pieces, chosen


def remap(segments,pieces):
    result=[]; offset=0.0
    for a,b in pieces:
        for s in segments:
            x,y=max(a,s['start']),min(b,s['end'])
            if y-x>=0.04:
                text=s['text']
                row={'start':offset+x-a,'end':offset+y-a,'text':text}
                if result and result[-1]['text']==text and abs(result[-1]['end']-row['start'])<0.05:
                    result[-1]['end']=row['end']
                else: result.append(row)
        offset+=b-a
    return result


def quiet_ranges(source,start,end):
    # Silence detection is conservative: no detected quiet = no pause cut.
    result=subprocess.run(['ffmpeg','-hide_banner','-nostats','-ss',str(start),'-i',str(source),'-t',str(end-start),'-vn','-af','silencedetect=noise=-36dB:d=0.6','-f','null','-'],capture_output=True,text=True)
    if result.returncode: return []
    ranges=[]; a=None
    for match in re.finditer(r'silence_(start|end):\s*(-?\d+(?:\.\d+)?)',result.stderr):
        value=max(start,min(end,start+float(match.group(2))))
        if match.group(1)=='start': a=value
        elif a is not None: ranges.append((a,value)); a=None
    if a is not None: ranges.append((a,end))
    return ranges


def render_dynamic(source,dest,segments,clip,layout,software=False,captions=True):
    from shorts import render, duration
    pieces,holes=edit_plan(segments,clip['start'],clip['end'],quiet_ranges(source,clip['start'],clip['end']))
    if not pieces: raise ValueError('Empty edit plan')
    # First make an edited master at the target aspect. Then render captions using
    # the original renderer; all subtitle timestamps are mapped to the edited timeline.
    with tempfile.TemporaryDirectory(prefix='creator-edit-') as tmp:
        temp=Path(tmp)/'edited.mp4'; graph=[]; pairs=[]
        start=clip['start']; length=clip['end']-start
        if layout=='original':
            normal='scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1'
        elif layout=='crop':
            normal='scale=1080:1920:force_original_aspect_ratio=increase:force_divisible_by=2,crop=1080:1920,setsar=1'
        else:
            normal='scale=1080:1920:force_original_aspect_ratio=decrease:force_divisible_by=2,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=0x10141c,setsar=1'
        n=len(pieces)
        def encode(base, tail):
            nonlocal software
            if not software:
                try:
                    subprocess.run(base+['-c:v','h264_videotoolbox','-b:v','8M']+tail,check=True)
                    return
                except subprocess.CalledProcessError: software=True
            subprocess.run(base+['-c:v','libx264','-preset','veryfast','-crf','20']+tail,check=True)
        # Render bounded shots sequentially to avoid buffering a full 1080p clip
        # across parallel filter branches on a 16GB Mac.
        paths=[]
        for i,(a,b) in enumerate(pieces):
            shot=Path(tmp)/f'shot_{i:02}.mp4'; paths.append(shot)
            zoom=',crop=trunc(iw/1.08/2)*2:trunc(ih/1.08/2)*2,scale=1080:1920,setsar=1' if layout!='original' and i%2 else ''
            vf=normal+zoom+',fps=30'
            base=['ffmpeg','-v','error','-y','-ss',f'{a:.4f}','-i',str(source),'-t',f'{b-a:.4f}',
                  '-map','0:v:0','-map','0:a:0','-vf',vf,'-af','acompressor=threshold=0.125:ratio=2:attack=20:release=250,alimiter=limit=0.9',
                  '-ar','48000','-ac','2','-pix_fmt','yuv420p','-filter_threads','2']
            encode(base,['-c:a','aac','-b:a','160k',str(shot)])
        manifest=Path(tmp)/'shots.txt'; manifest.write_text(''.join(f"file '{p.name}'\n" for p in paths))
        subprocess.run(['ffmpeg','-v','error','-y','-f','concat','-safe','1','-i',str(manifest),'-c','copy',str(temp)],check=True)
        final_length=min(sum(b-a for a,b in pieces),duration(temp))
        mapped=remap(segments,pieces)
        # Master is already vertical; fit keeps its frame and enables opening hook.
        render(temp,dest,mapped,{**clip,'start':0,'end':final_length},'original' if layout=='original' else 'fit',software,captions)
        return {'edit_style':'dynamic','jump_cuts':len(holes),'shot_count':n,'removed_seconds':round(sum(b-a for a,b in holes),2),'output_duration':round(duration(dest),2)}
