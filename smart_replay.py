"""Audio-first, bounded replay acquisition. Never fall back to a full video automatically."""
import math, os, shutil, signal, subprocess, sys, tempfile, time, copy, threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from shorts import duration, transcribe, render
import performance as perf
from youtube_source import validate_url, eta


def probe(url, browser=None, session=None):
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
    if session is not None and not browser and getattr(session,'processing_mode',None) in ('fast','smart') and getattr(session,'viral_preset',''):
        from quick_range import preview_format
        session._preview_plan=preview_format(info)
    return info.get('title','YouTube replay'),float(seconds)


def section_command(url, folder, start, end, audio, browser=None):
    if not 0<=start<end or end-start>250: raise ValueError('Invalid section length')
    cmd=[sys.executable,'-m','yt_dlp','--ignore-config','--no-playlist','--no-simulate','--no-live-from-start','--match-filters','!is_live & !is_upcoming','--socket-timeout','45','--retries','2','--fragment-retries','2','--abort-on-unavailable-fragments','--download-sections',f'*{start:.3f}-{end:.3f}','-f', 'b[height<=360][protocol=https]/b[height<=360]/bv*[height<=360]+ba' if audio=='preview' else 'ba' if audio else 'bv*[height<=1080]+ba/b[height<=1080]/b','--newline','-o',str(folder/'section.%(ext)s')]
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


@perf.timed("source_acquisition")
def fetch(args, job, folder, start, end, audio):
    folder.mkdir(parents=True,exist_ok=True)
    def cancelled():
        event=getattr(args,'_prefetch_cancel',None)
        return (job/'stop').exists() or (event is not None and event.is_set())
    if cancelled(): return None
    if getattr(args,'input_file',None):
        # Local recordings are seeked in small windows instead of copied wholesale.
        local=Path(args.input_file).expanduser().resolve()
        dest=folder/('section.wav' if audio is True else 'section.mkv')
        cmd=['ffmpeg','-nostdin','-v','error','-y','-ss',str(start),'-i',str(local),'-t',str(end-start)]
        if audio is True:cmd+=['-map','0:a:0','-vn','-ac','1','-ar','16000']
        else:
            cmd+=['-map','0:v:0','-map','0:a:0']
            if audio=='preview':cmd+=['-vf',"scale=-2:'min(360,ih)',fps=15",'-filter_threads','2']
            cmd+=['-c:v','libx264','-preset','ultrafast','-crf','20' if audio=='preview' else '17','-threads','2','-c:a','aac','-b:a','96k' if audio=='preview' else '192k']
        proc=subprocess.Popen(cmd+[str(dest)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        began=time.monotonic()
        try:
            while proc.poll() is None:
                if cancelled():return None
                if time.monotonic()-began>180:raise RuntimeError('Local range acquisition timed out.')
                time.sleep(.1)
            if proc.returncode or not dest.is_file():raise RuntimeError('Could not decode selected local video range.')
        finally:terminate(proc)
        if abs(duration(dest)-(end-start))>max(.35,(end-start)*.01):raise RuntimeError('Local range duration mismatch.')
        perf.count('local_preview_ranges' if audio=='preview' else 'local_candidate_ranges');return dest
    if audio=='preview' and getattr(args,'_preview_plan',None):
        from quick_range import supports_range, acquire
        if shutil.disk_usage(folder).free<2*1024**3: raise RuntimeError('Low free disk space.')
        plan=args._preview_plan; dest=folder/'section.mkv'
        try:
            if plan.get('range_verified') or supports_range(plan):
                plan['range_verified']=True
                if acquire(plan,start,end,dest,cancelled,terminate):
                    length=duration(dest)
                    if abs(length-(end-start))<=max(.35,(end-start)*.01):
                        perf.count('direct_preview_hits'); return dest
        except (OSError,ValueError,subprocess.SubprocessError): pass
        dest.unlink(missing_ok=True)
        # Disable this signed URL for subsequent requests after a failure.
        plan.clear()
        if cancelled(): return None
        print('Direct preview unavailable; using native bounded section request.',flush=True)
    with (job/'download.log').open('a') as log:
        log.write(f'\nRequested {"audio" if audio else "video"} section {start:.3f}-{end:.3f}\n'); log.flush()
        proc=subprocess.Popen(section_command(args.url,folder,start,end,audio,getattr(args,'browser',None)),stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        began=time.monotonic()
        try:
            while proc.poll() is None:
                if cancelled(): return None
                if shutil.disk_usage(folder).free<2*1024**3: raise RuntimeError('Low free disk space.')
                limit=180 if audio=='preview' and getattr(args,'processing_mode',None) in ('fast','smart') else 600
                if time.monotonic()-began>limit: raise RuntimeError(f'Section acquisition exceeded {limit} seconds; source may not support efficient seeking. No full-video fallback was started. Try Professional mode for a longer deadline or an authorized local recording.')
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


def shift_segments(segments, offset):
    return [{**s,'start':s['start']+offset,'end':s['end']+offset,**({'words':[{**w,'start':w['start']+offset,'end':w['end']+offset} for w in s['words']]} if 'words' in s else {})} for s in segments]


def stream_signature(path):
    import json
    fields='codec_type,codec_name,profile,width,height,pix_fmt,sample_rate,channels,time_base,r_frame_rate,extradata_size'
    return json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','stream='+fields,'-of','json',str(path)],timeout=30))['streams']


class RollingPreview:
    """Keep one completed preview. Fetch/transcribe each new range only once.
    Guard the stream-copy join against format changes and timing drift; the
    caller falls back to a conventional overlapped request if either occurs.
    """
    def __init__(self, root, *, prefetch=False, total=0, step=0):
        self.root=root; self.previous=None; self.total=total; self.step=step
        self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='preview') if prefetch else None
        self.pending=None; self.cancel=threading.Event()

    def close(self):
        self.cancel.set()
        if self.executor: self.executor.shutdown(wait=True,cancel_futures=True)

    def schedule(self,args,job,index,end):
        # Start after any overlap fallback, then overlap AI and rendering.
        if self.executor and self.pending is None and end<self.total and not (job/'stop').exists() and not (job/'pause').exists():
            pref=copy.copy(args); pref._prefetch_cancel=self.cancel
            self.pending=self.executor.submit(fetch,pref,job,self.root/str(index+1),end,min(self.total,end+self.step),'preview')

    def load(self,args,job,work,index,boundary,end,stage):
        folder=self.root/str(index)
        if self.pending is not None:
            media=self.pending.result(); self.pending=None
            if media is not None: perf.count('prefetched_previews')
        else: media=fetch(args,job,folder,boundary,end,'preview')
        if media is None: return None
        asr=work/'fresh_asr';asr.mkdir()
        stage('transcribe',f'Transcribing new footage {index}',progress=None)
        segments=transcribe(media,asr,args.whisper,args.language or None)
        current=(media,boundary,end,segments)
        previous=self.previous; self.previous=current
        if not previous: return media,segments,boundary
        old,start,prior_end,prior_segments=previous
        try:
            if abs(prior_end-boundary)>.01 or abs(duration(old)-(prior_end-start))>.2 or abs(duration(media)-(end-boundary))>.2 or stream_signature(old)!=stream_signature(media):
                print('Rolling preview incompatible; using checked overlap request.',flush=True);return False
            from live import combine
            joined=combine(old,media,work)
            if abs(duration(joined)-(end-start))>.35:
                print('Rolling preview clock mismatch; using checked overlap request.',flush=True);return False
            perf.count('rolling_preview_reused_seconds',round(boundary-start))
            # Reuse PCM energy measurements when both independently decoded audio caches exist.
            left=perf.read(perf.cache_path('audio',perf.fingerprint(old)));right=perf.read(perf.cache_path('audio',perf.fingerprint(media)))
            if isinstance(left,list) and isinstance(right,list):
                perf.save(perf.cache_path('audio',perf.fingerprint(joined)),left[:round(boundary-start)]+right)
            return joined,prior_segments+shift_segments(segments,boundary-start),start
        except (OSError,ValueError,KeyError,subprocess.SubprocessError) as exc:
            print('Rolling preview join failed; using checked overlap request: '+type(exc).__name__,flush=True);return False
        finally: shutil.rmtree(old.parent,ignore_errors=True)


def run_replay(args,job,out,update,stage,atomic,candidates,info):
    # Only the optimized viral route uses rolling previews; legacy paths remain unchanged.
    optimized=bool(getattr(args,'viral_preset','')) and getattr(args,'processing_mode',None) in perf.MODES
    with tempfile.TemporaryDirectory(prefix='rolling-preview-',dir=job) as tmp:
        rolling=RollingPreview(Path(tmp),prefetch=optimized and args.processing_mode in ('fast','smart'),total=min(info[1],args.minutes*60) if args.minutes else info[1],step=args.segment) if optimized else None
        try: return _run_replay(args,job,out,update,stage,atomic,candidates,info,rolling)
        finally:
            if rolling: rolling.close()


def wait_if_paused(job,update):
    if (job/'pause').exists() and not (job/'stop').exists():
        update(stage='paused',message='Paused at a safe replay boundary',eta='Paused',stage_estimate=None)
        while (job/'pause').exists() and not (job/'stop').exists():time.sleep(.4)
        update(message='Resuming replay' if not (job/'stop').exists() else 'Stopping replay')
    return not (job/'stop').exists()


def _run_replay(args,job,out,update,stage,atomic,candidates,info,rolling):
    title,total=info
    if getattr(args,'mode','auto')=='live': raise ValueError('This is a replay, not an ongoing stream.')
    if args.minutes: total=min(total,args.minutes*60)
    from live import configure_full_scan, publish_ranked, publishing_enabled
    configure_full_scan(args,'replay')
    if getattr(args,'defer_publish',False): update(target=0)
    update(title=title,mode='replay',source_duration=total,capture='smart',message='Smart replay: requesting low-resolution previews' if getattr(args,'edit_style','clean')=='gaming' or getattr(args,'viral_preset','') else 'Smart replay: requesting audio sections only')
    clips=[]; scanned=0.; began=time.monotonic(); stopped=False
    for index,(start,boundary,end) in enumerate(windows(total,args.segment,min(90,250-args.segment) if getattr(args,'processing_mode',None) and getattr(args,'viral_preset','') else 65),1):
        if not wait_if_paused(job,update): stopped=True; break
        window_began=time.monotonic()
        with tempfile.TemporaryDirectory(prefix='smart-',dir=job) as temp:
            root=Path(temp)
            stage('source',f'Fetching analysis section {index}: {eta(start)}–{eta(end)}',progress=None)
            viral=bool(getattr(args,'viral_preset',''))
            gaming=getattr(args,'edit_style','clean')=='gaming' or viral
            rolled=rolling.load(args,job,root,index,boundary,end,stage) if rolling else False
            if rolled is None: stopped=True; break
            if rolled:
                audio,seg,start=rolled
            else:
                audio=fetch(args,job,root/'audio',start,end,'preview' if gaming else True)
                if audio is None: stopped=True; break
                work=root/'asr'; work.mkdir()
                stage('transcribe',f'Transcribing audio section {index}',progress=None)
                seg=transcribe(audio,work,args.whisper,args.language or None)
            if rolling: rolling.schedule(args,job,index,end)
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
                if not wait_if_paused(job,update): stopped=True; break
                a=start+c['start']; b=start+c['end']
                # Re-transcribe the actual acquired audiovisual range; captions and cuts
                # must use the local clip clock, not the remote audio seek clock.
                stage('source',f'Fetching selected highlight {len(clips)+1}',progress=None)
                local_source=getattr(args,'input_file',None)
                source_clock=0.; subs=[]
                # A known local source can render directly, but only with verified preview alignment.
                if local_source and rolling and args.processing_mode in ('fast','smart') and any(s.get('words') for s in seg if s['end']>c['start'] and s['start']<c['end']):
                    original=Path(local_source).expanduser().resolve()
                    delta=perf.audio_alignment(audio,original,c['start'],b-a,media_start=a)
                    subs=perf.aligned_segments(seg,c['start'],c['end'],delta,b-a)
                    if subs:
                        from gaming import verify_visual_range
                        if verify_visual_range(audio,original,c['start'],b-a,media_start=a):
                            media=original;source_clock=a;perf.count('local_direct_renders');perf.count('candidate_asr_avoided')
                        else:subs=[]
                if not subs:
                    media=fetch(args,job,root/f'clip{j}',a,b,False)
                    if media is None: stopped=True; break
                    local_work=root/f'caption{j}';local_work.mkdir()
                    stage('transcribe','Checking dialogue in selected video',progress=None)
                    if rolling and args.processing_mode in ('fast','smart') and any(s.get('words') for s in seg if s['end']>c['start'] and s['start']<c['end']):
                        actual_length=duration(media)
                        delta=perf.audio_alignment(audio,media,c['start'],min(b-a,actual_length))
                        subs=perf.aligned_segments(seg,c['start'],c['end'],delta,actual_length)
                        if subs:
                            perf.count('candidate_asr_avoided');print('Selected footage waveform matched; reusing verified word timestamps.',flush=True)
                    if not subs: subs=transcribe(media,local_work,args.whisper,args.language or None)
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
                local={**c,'start':source_clock,'end':source_clock+min(b-a,duration(media)-source_clock)}
                if source_clock:subs=shift_segments(subs,source_clock)
                stage('export',f'Editing highlight {len(clips)+1}',progress=None)
                name=f'short_{len(clips)+1:02}.mp4'; pending=out/('pending_'+name); dest=out/name
                meta={}
                if viral:
                    from viral import render as viral_render
                    local['impact']=source_clock+c.get('impact',-1)-c['start'] if c.get('impact',-1)>=0 else -1
                    try: meta=viral_render(args,media,pending,subs,local)
                    except ValueError as exc:
                        perf.reject(str(exc)); pending.unlink(missing_ok=True); print('Skipping viral candidate: '+str(exc),flush=True); continue
                elif gaming:
                    from gaming import render as gaming_render, SplitLayoutUnavailable
                    local['impact']=source_clock+c.get('impact',-1)-c['start'] if c.get('impact',-1)>=0 else -1
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
                if viral:
                    from viral import reject_duplicate_export
                    if reject_duplicate_export(pending,meta,clips):continue
                os.replace(pending,dest)
                if pending.with_suffix('.srt').exists(): os.replace(pending.with_suffix('.srt'),dest.with_suffix('.srt'))
                clips.append({**c,'start':a,'end':b,'file':name,**meta,'source_url':getattr(args,'url',None),'source_strategy':'visual_preview' if gaming else 'audio_first','source_identity':getattr(args,'source_identity','')})
                perf.count('accepted_candidates'); atomic(out/'clips.json',clips)
                if publishing_enabled(args) and not getattr(args,'defer_publish',False):
                    from live import publish_ready
                    stage('publish',f'Publishing highlight {len(clips)}',progress=None)
                    publish_ready(args,dest,clips[-1]); atomic(out/'clips.json',clips)
                if args.keep_source and not (local_source and media==Path(local_source).expanduser().resolve()):
                    kept=job/'smart_sources'; kept.mkdir(exist_ok=True); shutil.copy2(media,kept/(f'{len(clips):03}'+media.suffix))
                if args.count and len(clips)>=args.count: break
            if stopped: break
            scanned=end
            update(segments_processed=index,captured_seconds=round(scanned),source_progress=round(100*scanned/total,1),overall_eta=eta((total-scanned)*(time.monotonic()-began)/scanned) if not args.count else None,message=f'Audio section {index} analysed; {len(clips)} highlights ready',last_segment_seconds=round(time.monotonic()-window_began))
            if args.count and len(clips)>=args.count: break
    if not stopped: publish_ranked(args,out,clips,stage)
    update(stage='done',capture='ended',message=f'{len(clips)} highlights ready'+(' (stopped)' if stopped else ''),progress=100,eta='00:00:00',overall_eta=None)
