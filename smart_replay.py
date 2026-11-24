"""Audio-first, bounded replay acquisition. Never fall back to a full video automatically."""
import math, os, shutil, signal, subprocess, sys, tempfile, time
from pathlib import Path
from shorts import duration, transcribe, render
from youtube_source import validate_url, eta


def probe(url, browser=None):
    from yt_dlp import YoutubeDL
    options={'quiet':True,'noplaylist':True,'skip_download':True,'socket_timeout':30,'retries':2,'format':'best/bestvideo+bestaudio'}
    if browser: options['cookiesfrombrowser']=(browser,)
    try:
        with YoutubeDL(options) as ydl: info=ydl.extract_info(validate_url(url),download=False)
    except Exception as exc:
        raise RuntimeError('Could not access source metadata. Check viewing access and yt-dlp; use authorized footage only.') from exc
    if not info or info.get('_type') in ('playlist','multi_video'): raise ValueError('Use a single video URL.')
    if info.get('has_drm'): raise ValueError('DRM-protected source is unsupported.')
    status=info.get('live_status')
    if status in ('post_live','is_upcoming'): raise ValueError('Replay is still processing or stream has not started.')
    if info.get('is_live') or status=='is_live': return None
    seconds=info.get('duration')
    if not isinstance(seconds,(int,float)) or not math.isfinite(seconds) or seconds<=0: raise ValueError('Smart replay requires a known duration.')
    return info.get('title','YouTube replay'),float(seconds)


def section_command(url, folder, start, end, audio, browser=None):
    if not 0<=start<end or end-start>250: raise ValueError('Invalid section length')
    cmd=[sys.executable,'-m','yt_dlp','--ignore-config','--no-playlist','--no-simulate','--no-live-from-start','--match-filters','!is_live & !is_upcoming','--socket-timeout','45','--retries','2','--fragment-retries','2','--abort-on-unavailable-fragments','--download-sections',f'*{start:.3f}-{end:.3f}','-f', 'bv*[height<=360]+ba/b[height<=360]' if audio=='preview' else 'ba' if audio else 'bv*[height<=1080]+ba/b[height<=1080]/b','--newline','-o',str(folder/'section.%(ext)s')]
    if not audio or audio=='preview': cmd+=['--merge-output-format','mkv','--force-keyframes-at-cuts']
    if browser: cmd+=['--cookies-from-browser',browser]
    return cmd+[validate_url(url)]


def terminate(proc):
    if proc.poll() is None:
        try: os.killpg(proc.pid,signal.SIGTERM)
        except ProcessLookupError: pass
        try: proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try: os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError: pass
            proc.wait()


def fetch(args, job, folder, start, end, audio):
    folder.mkdir(parents=True,exist_ok=True)
    if (job/'stop').exists(): return None
    with (job/'download.log').open('a') as log:
        log.write(f'\nRequested {"audio" if audio else "video"} section {start:.3f}-{end:.3f}\n'); log.flush()
        proc=subprocess.Popen(section_command(args.url,folder,start,end,audio,getattr(args,'browser',None)),stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        began=time.monotonic()
        try:
            while proc.poll() is None:
                if (job/'stop').exists(): return None
                if shutil.disk_usage(folder).free<2*1024**3: raise RuntimeError('Low free disk space.')
                if time.monotonic()-began>600: raise RuntimeError('Section acquisition exceeded ten minutes; source may not support efficient seeking. No full-video fallback was started.')
                time.sleep(.4)
            if proc.returncode: raise RuntimeError('Requested section could not be acquired. Check download.log. No full-video fallback was started.')
        finally: terminate(proc)
    files=[p for p in folder.glob('section.*') if p.suffix.lower() in {'.mkv','.mp4','.mov','.webm','.m4v','.m4a','.opus','.aac','.mp3','.ogg','.wav'}]
    if len(files)!=1: raise RuntimeError('Section download did not produce one media file.')
    length=duration(files[0]); expected=end-start
    if abs(length-expected)>max(2.,expected*.03): raise RuntimeError(f'Section duration mismatch ({length:.1f} vs {expected:.1f}s); refusing to use uncertain timestamps.')
    return files[0]


def windows(total, step, overlap=65):
    # Cover boundary-spanning 60s highlights; overlap belongs to the prior window.
    pos=0.
    while pos<total:
        end=min(total,pos+step)
        yield max(0.,pos-overlap),pos,end
        pos=end


def run_replay(args,job,out,update,stage,atomic,candidates,info):
    title,total=info
    if getattr(args,'mode','auto')=='live': raise ValueError('This is a replay, not an ongoing stream.')
    if args.minutes: total=min(total,args.minutes*60)
    from live import configure_full_scan, publish_ranked, publishing_enabled
    configure_full_scan(args,'replay')
    if getattr(args,'defer_publish',False): update(target=0)
    update(title=title,mode='replay',source_duration=total,capture='smart',message='Smart replay: requesting low-resolution previews' if getattr(args,'edit_style','clean')=='gaming' else 'Smart replay: requesting audio sections only')
    clips=[]; scanned=0.; began=time.monotonic(); stopped=False
    for index,(start,boundary,end) in enumerate(windows(total,args.segment),1):
        if (job/'stop').exists(): stopped=True; break
        window_began=time.monotonic()
        with tempfile.TemporaryDirectory(prefix='smart-',dir=job) as temp:
            root=Path(temp)
            stage('source',f'Fetching analysis section {index}: {eta(start)}–{eta(end)}',progress=None)
            viral=bool(getattr(args,'viral_preset',''))
            gaming=getattr(args,'edit_style','clean')=='gaming' or viral
            audio=fetch(args,job,root/'audio',start,end,'preview' if gaming else True)
            if audio is None: stopped=True; break
            work=root/'asr'; work.mkdir()
            stage('transcribe',f'Transcribing audio section {index}',progress=None)
            seg=transcribe(audio,work,args.whisper,args.language or None)
            stage('analyze',f'Finding highlights in audio section {index}',progress=None)
            if viral:
                from viral import select as viral_select
                selected=viral_select(args,audio,seg,min(end-start,duration(audio)),boundary-start,start,clips,args.count-len(clips) if args.count else 0)
            elif gaming:
                from live import gaming_candidates
                selected=gaming_candidates(args,audio,seg,min(end-start,duration(audio)),boundary-start,start,clips,args.count-len(clips) if args.count else 0)
            else:
                selected=candidates(seg,args.model,min(end-start,duration(audio)),boundary-start,start,clips,args.score,args.count-len(clips) if args.count else 0)
            update(segments_ready=index)
            for j,c in enumerate(selected):
                if (job/'stop').exists(): stopped=True; break
                a=start+c['start']; b=start+c['end']
                # Re-transcribe the actual acquired audiovisual range; captions and cuts
                # must use the local clip clock, not the remote audio seek clock.
                stage('source',f'Fetching selected highlight {len(clips)+1}',progress=None)
                media=fetch(args,job,root/f'clip{j}',a,b,False)
                if media is None: stopped=True; break
                local_work=root/f'caption{j}';local_work.mkdir()
                stage('transcribe','Checking dialogue in selected video',progress=None)
                subs=transcribe(media,local_work,args.whisper,args.language or None)
                # Reject obvious audio-seek drift using token overlap; otherwise review manually.
                import re
                def words(s): return set(re.findall(r'\w+',s.casefold()))
                wanted=words(' '.join(s['text'] for s in seg if s['end']>c['start'] and s['start']<c['end']))
                actual=words(' '.join(s['text'] for s in subs))
                if wanted and len(wanted & actual)/len(wanted)<.35:
                    print('Skipping candidate: acquired dialogue differs from audio selection.',flush=True); continue
                if gaming and not wanted:
                    from gaming import verify_visual_range
                    if not verify_visual_range(audio,media,c['start'],b-a):
                        print('Skipping candidate: visual timing could not be verified.',flush=True); continue
                local={**c,'start':0.,'end':min(b-a,duration(media))}
                stage('export',f'Editing highlight {len(clips)+1}',progress=None)
                name=f'short_{len(clips)+1:02}.mp4'; pending=out/('pending_'+name); dest=out/name
                meta={}
                if viral:
                    from viral import render as viral_render
                    local['impact']=c.get('impact',-1)-c['start'] if c.get('impact',-1)>=0 else -1
                    try: meta=viral_render(args,media,pending,subs,local)
                    except ValueError as exc:
                        pending.unlink(missing_ok=True); print('Skipping viral candidate: '+str(exc),flush=True); continue
                elif gaming:
                    from gaming import render as gaming_render, SplitLayoutUnavailable
                    local['impact']=c.get('impact',-1)-c['start'] if c.get('impact',-1)>=0 else -1
                    try:
                        meta=gaming_render(media,pending,subs,local,args.software,getattr(args,'face_region',None))
                    except SplitLayoutUnavailable as exc:
                        pending.unlink(missing_ok=True)
                        print('Skipping highlight: '+str(exc),flush=True)
                        update(message='Skipped highlight: '+str(exc))
                        continue
                elif args.edit_style=='dynamic':
                    from creator_edit import render_dynamic
                    meta=render_dynamic(media,pending,subs,local,args.layout,args.software,captions=args.captions)
                else: render(media,pending,subs,local,args.layout,args.software,captions=args.captions)
                os.replace(pending,dest)
                if pending.with_suffix('.srt').exists(): os.replace(pending.with_suffix('.srt'),dest.with_suffix('.srt'))
                clips.append({**c,'start':a,'end':b,'file':name,**meta,'source_url':args.url,'source_strategy':'visual_preview' if gaming else 'audio_first','source_identity':getattr(args,'source_identity','')})
                atomic(out/'clips.json',clips)
                if publishing_enabled(args) and not getattr(args,'defer_publish',False):
                    from live import publish_ready
                    stage('publish',f'Publishing highlight {len(clips)}',progress=None)
                    publish_ready(args,dest,clips[-1]); atomic(out/'clips.json',clips)
                if args.keep_source:
                    kept=job/'smart_sources'; kept.mkdir(exist_ok=True); shutil.copy2(media,kept/(f'{len(clips):03}'+media.suffix))
                if args.count and len(clips)>=args.count: break
            if stopped: break
            scanned=end
            update(segments_processed=index,captured_seconds=round(scanned),source_progress=round(100*scanned/total,1),overall_eta=eta((total-scanned)*(time.monotonic()-began)/scanned) if not args.count else None,message=f'Audio section {index} analysed; {len(clips)} highlights ready',last_segment_seconds=round(time.monotonic()-window_began))
            if args.count and len(clips)>=args.count: break
    if not stopped: publish_ranked(args,out,clips,stage)
    update(stage='done',capture='ended',message=f'{len(clips)} highlights ready'+(' (stopped)' if stopped else ''),progress=100,eta='00:00:00',overall_eta=None)
