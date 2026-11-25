"""Incremental local live clipping. Capture and analysis run concurrently."""
import argparse, csv, json, os, re, signal, subprocess, tempfile, time, shutil
from pathlib import Path
from datetime import datetime
from shorts import WHISPER, MODEL, duration, transcribe, ask_ai, render, write_srt, editorial
from youtube_source import validate_url, eta
from source_fallback import NativeReplayRequired, download_replay


def atomic(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    os.replace(temp, path)


def closed_segments(folder):
    path = folder / 'segments.csv'
    if not path.exists(): return []
    content = path.read_text(errors='replace')
    # Ignore a partially written final record.
    rows = csv.reader(content.splitlines() if content.endswith('\n') else content.splitlines()[:-1])
    return [folder / row[0] for row in rows if len(row)==3 and re.fullmatch(r'part_\d+\.mkv',row[0])]


def select_source(info, mode='auto'):
    """Choose a directly readable, non-DRM source; no full-file download."""
    if not info or info.get('_type') in ('playlist','multi_video'):
        raise ValueError('Paste a single YouTube video URL, not a playlist.')
    status=info.get('live_status')
    is_live=bool(info.get('is_live') or status=='is_live')
    if status=='is_upcoming': raise ValueError('This stream has not started yet.')
    if status=='post_live': raise ValueError('YouTube is still processing this replay. Try again when the replay is available.')
    actual='live' if is_live else 'replay'
    if mode not in ('auto',actual): raise ValueError(f'URL is {actual}, not {mode}. Select Auto detect or the correct mode.')
    def readable(f):
        if not f.get('url') or f.get('has_drm') or f.get('is_from_start'): return False
        if not f.get('fragments'): return True
        # A verified HLS playlist can legitimately carry fragment metadata.
        # Only accept a real playlist URL, not a DASH fragment/base URL.
        from urllib.parse import urlsplit
        path=urlsplit(f['url']).path.lower()
        return str(f.get('protocol','')).startswith('m3u8') and ('.m3u8' in path or '/manifest/' in path)
    formats=[f for f in info.get('formats',[]) if readable(f)]
    def video(f): return f.get('vcodec') not in (None,'none') and (f.get('height') is None or 0 < f['height'] <=1080)
    def audio(f): return f.get('acodec') not in (None,'none')
    def rank(f): return (f.get('height') or 0,f.get('tbr') or 0)
    hls=[f for f in formats if str(f.get('protocol','')).startswith('m3u8')]
    direct=[f for f in formats if f.get('protocol') in ('http','https')]
    # Prefer a single multiplexed source even at lower resolution for reliability.
    # Prefer progressive HTTP for replays; prefer HLS for live input.
    for group in ([hls] if is_live else [direct,hls]):
        muxed=[f for f in group if video(f) and audio(f)]
        v=[f for f in group if video(f) and f.get('acodec')=='none']
        a=[f for f in group if f.get('vcodec')=='none' and audio(f)]
        if muxed:
            selected=[max(muxed,key=rank)]
        elif v and a: selected=[max(v,key=rank),max(a,key=rank)]
        else: continue
        return info.get('title','YouTube video'),selected,actual,None if is_live else info.get('duration')
    raise RuntimeError('No supported direct video/audio or HLS feed found. Try another authorized source or wait for the replay to finish processing.')


# Ask yt-dlp to test the actual selected formats, not just list metadata.
# HLS is naturally segmented; prefer it when available for live AND replay.
# Direct HTTP remains available for completed videos with no HLS source.
HLS_FORMAT = 'b[protocol^=m3u8][height<=?1080]/bv[protocol^=m3u8][height<=?1080]+ba[protocol^=m3u8]'
HTTP_FORMAT = 'b[protocol=https][height<=1080]/bv[protocol=https][height<=1080]+ba[protocol=https]'


def checked_source(info, mode='auto'):
    if not info or info.get('_type') in ('playlist','multi_video'):
        raise ValueError('Paste a single playable video link.')
    # yt-dlp may expose a selection inside requested_downloads instead of at
    # the top level. Only use the selected download, never an arbitrary format.
    downloads = info.get('requested_downloads') or []
    selected = downloads[0] if len(downloads) == 1 and isinstance(downloads[0], dict) else info
    requested = selected.get('requested_formats') or info.get('requested_formats') or [selected]
    catalog = {str(f.get('format_id')): f for f in info.get('formats', [])
               if isinstance(f, dict) and f.get('format_id') is not None}
    merged = []
    for f in requested:
        if not isinstance(f, dict):
            continue
        original = catalog.get(str(f.get('format_id')), {})
        # Recover missing descriptive metadata for this same selected ID.
        # Never recover URLs from unverified catalog rows or clear DRM flags.
        row = dict(f)
        for key in ('protocol', 'height', 'vcodec', 'acodec', 'fragments', 'is_from_start'):
            if row.get(key) is None and key in original:
                row[key] = original[key]
        if any(x.get('has_drm') for x in (info, selected, original, f)):
            row['has_drm'] = True
        if original.get('is_from_start') or selected.get('is_from_start') or info.get('is_from_start'):
            row['is_from_start'] = True
        headers = {}
        for layer in (info, selected, f):
            headers.update({k.lower(): v for k,v in (layer.get('http_headers') or {}).items()})
        row['http_headers'] = headers
        merged.append(row)
    try:
        return select_source({**info, 'formats': merged}, mode)
    except RuntimeError as exc:
        # Safe diagnostics: never print URLs, cookies, request headers, or tokens.
        def label(value):
            s = str(value or 'unknown')
            return s if re.fullmatch(r'[A-Za-z0-9_.+ -]{1,64}', s) else 'redacted'
        print('Selected format diagnostics: ' + json.dumps({
            'live_status': label(info.get('live_status')),
            'available_format_count': len(info.get('formats') or []),
            'selected': [{
                'id': label(f.get('format_id')), 'protocol': label(f.get('protocol')),
                'height': f.get('height') if isinstance(f.get('height'), (int,float)) else None,
                'video_codec': label(f.get('vcodec')), 'audio_codec': label(f.get('acodec')),
                'has_url': bool(f.get('url')), 'fragmented': bool(f.get('fragments')),
                'from_start': bool(f.get('is_from_start')), 'drm': bool(f.get('has_drm')),
            } for f in merged]
        }), flush=True)
        raise RuntimeError('No compatible verified source. See Selected format diagnostics in run.log. '
                           'If the source is restricted or unsupported, use a creator-authorized local recording.') from exc


def resolve_source(url, mode='auto', browser=None):
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError
    selector = HLS_FORMAT if mode == 'live' else HLS_FORMAT+'/'+HTTP_FORMAT+'/bv*[height<=1080]+ba/b[height<=1080]/b'
    options = {'quiet':True,'noplaylist':True,'socket_timeout':30,'retries':2,
               'fragment_retries':2,'check_formats':'selected','format':selector}
    if browser not in (None,'chrome'): raise ValueError('Unsupported browser session')
    if browser: options['cookiesfrombrowser']=(browser,)
    print('Checking available media formats with yt-dlp before capture…', flush=True)
    try:
        with YoutubeDL(options) as ydl:
            info=ydl.extract_info(validate_url(url),download=False)
    except DownloadError as exc:
        message=str(exc).lower()
        if any(x in message for x in ('members-only','private video','join this channel','sign in','403 forbidden','drm')):
            raise RuntimeError('Source access was denied or requires an eligible viewing account. Use a source you are authorized to acquire, or a creator-provided local recording.') from exc
        raise RuntimeError('yt-dlp could not verify a playable media source. Update yt-dlp[default] and Deno; check that the original video is available to you. See run.log for extractor warnings.') from exc
    try:
        title, formats, actual, seconds = checked_source(info,mode)
    except RuntimeError as exc:
        rows=info.get('formats') or []
        # Native fallback only for a known accessible non-live source with at least one non-DRM format.
        if (mode!='live' and not info.get('is_live') and info.get('live_status') not in ('is_live','is_upcoming','post_live')
                and not info.get('has_drm') and any(f.get('url') and not f.get('has_drm') for f in rows)):
            raise NativeReplayRequired('Direct format unsupported; native replay download available.') from exc
        raise
    if browser and actual=='replay':
        raise NativeReplayRequired('Authenticated replay uses the native downloader to keep browser credentials out of FFmpeg.')
    print('Verified source: '+actual+'; format IDs: '+', '.join(str(f.get('format_id','unknown')) for f in formats), flush=True)
    return title,formats,actual,seconds


def capture_failure(logfile):
    # FFmpeg can print a signed media URL; keep error status free of those details.
    with logfile.open('rb') as f:
        f.seek(max(0,f.seek(0,2)-65536)); tail=f.read().decode(errors='replace').lower()
    if '403 forbidden' in tail or 'http error 403' in tail:
        return ('YouTube returned HTTP 403 for the media request. Update yt-dlp and Deno and test the original URL with yt-dlp. '
                'If access is still denied, use an authorized source file instead. Completed clips are retained.')
    return 'Source acquisition disconnected or failed after network retries. See capture log; completed clips are retained.'


def capture_command(formats, seconds, minutes):
    cmd=['ffmpeg','-hide_banner','-loglevel','warning','-nostdin','-y']
    for f in formats:
        headers=''.join(f'{k}: {v}\r\n' for k,v in f.get('http_headers',{}).items() if k.lower() in {'user-agent','referer','origin','accept','accept-language'} and '\r' not in str(v) and '\n' not in str(v))
        cmd+=['-fflags','+discardcorrupt']
        if str(f['url']).startswith(('http://','https://')):
            cmd+=['-rw_timeout','90000000','-reconnect','1',
                  '-reconnect_on_network_error','1','-reconnect_streamed','1',
                  '-reconnect_on_http_error','408,429,5xx','-reconnect_delay_max','30',
                  '-reconnect_max_retries','5','-reconnect_delay_total_max','120']
        if headers: cmd+=['-headers',headers]
        cmd+=['-i',f['url']]
    if minutes: cmd+=['-t',str(minutes*60)]
    return cmd+['-map','0:v:0','-map',f'{len(formats)-1}:a:0','-c','copy','-f','segment','-segment_time',str(seconds),'-reset_timestamps','1','-segment_list','segments.csv','-segment_list_type','csv','part_%06d.mkv']


def candidates(segments, model, total, boundary, offset, existing, min_score, count):
    if not segments or total < 20: return []
    raw=ask_ai(segments,model,3)
    found=[]
    for c in raw:
        try:
            a,b=c['first'],c['last']
            if type(a)!=int or type(b)!=int or not 0<=a<=b<len(segments): continue
            start=max(0,segments[a]['start']); end=min(total,segments[b]['end']); score=max(0,min(100,int(c['score'])))
            # Previous segment supplies context, not duplicate standalone clips.
            if not 20<=end-start<=60 or end<=boundary or score<min_score: continue
            found.append({'start':start,'end':end,'score':score,**editorial(c)})
        except (KeyError,TypeError,ValueError): continue
    chosen=[]
    for c in sorted(found,key=lambda x:x['score'],reverse=True):
        if any(min(c['end']+offset,e['end'])-max(c['start']+offset,e['start'])>0.5 for e in existing): continue
        if any(min(c['end'],e['end'])-max(c['start'],e['start'])>0.5 for e in chosen): continue
        chosen.append(c)
        if count and len(chosen)>=count: break
    return chosen


def combine(prev, current, work):
    # Paths generated locally; concat input uses safe relative filenames via symlinks.
    (work/'prev.mkv').symlink_to(prev.resolve()); (work/'current.mkv').symlink_to(current.resolve())
    (work/'concat.txt').write_text("file 'prev.mkv'\nfile 'current.mkv'\n")
    target=work/'combined.mkv'
    subprocess.run(['ffmpeg','-v','error','-y','-f','concat','-safe','1','-i',str(work/'concat.txt'),'-map','0:v:0','-map','0:a:0','-c','copy',str(target)],check=True)
    return target


def gaming_candidates(args, media, segments, total, boundary, offset, existing, count):
    from gaming import select
    from analytics_feedback import feedback
    return select(segments,args.model,total,boundary,offset,existing,args.score,count,media,getattr(args,'streamer',''),getattr(args,'game',''),feedback(getattr(args,'publish_channel','')))


def publishing_enabled(args):
    return bool(getattr(args,'publish_channel','') or getattr(args,'instagram_account',''))


def publish_ready(args, path, clip):
    if not publishing_enabled(args) or (args.output/'stop').exists(): return
    if getattr(args,'publish_channel',''):
        from auto_publish import publish
        try: clip['publishing']=publish(path,clip,args)
        except Exception as exc:
            clip['publishing']={'state':'failed','message':str(exc)[:300]}
            print('YouTube publishing failed: '+str(exc)[:300],flush=True)
    if getattr(args,'instagram_account','') and not (args.output/'stop').exists():
        from instagram_publisher import publish as publish_reel
        try: clip['instagram_publishing']=publish_reel(path,clip,args)
        except Exception as exc:
            clip['instagram_publishing']={'state':'failed','message':str(exc)[:300]}
            print('Instagram publishing failed: '+str(exc)[:300],flush=True)


def configure_full_scan(args,mode):
    if mode=='replay' and getattr(args,'viral_preset','') and getattr(args,'viral_full_scan',False):
        args.viral_publish_top=args.count; args.count=0; args.defer_publish=True

def publish_ranked(args,out,clips,stage):
    if not getattr(args,'defer_publish',False) or not publishing_enabled(args) or (args.output/'stop').exists(): return
    limit=getattr(args,'viral_publish_top',0)
    ranked=sorted(clips,key=lambda c:c['score'],reverse=True)
    for i,clip in enumerate(ranked[:limit] if limit else ranked):
        if (args.output/'stop').exists(): break
        stage('publish',f'Publishing ranked highlight {i+1}',progress=None)
        publish_ready(args,out/clip['file'],clip); atomic(out/'clips.json',clips)

def main(args):
    if getattr(args,'edit_style','clean')=='gaming': args.captions=False
    if getattr(args,'viral_preset',''):
        os.environ['SHORTS_VIRAL_SESSION']='1'
    from auto_publish import identity
    args.source_identity=identity(getattr(args,'url',None),getattr(args,'input_file',None))
    job=args.output.resolve(); job.mkdir(parents=True,exist_ok=True)
    source=job/'capture'; source.mkdir(); out=job/datetime.now().strftime('%Y%m%d_%H%M%S_%f'); out.mkdir()
    state={'stage':'source','message':'Detecting YouTube source…','capture':'connecting','segments_ready':0,'segments_processed':0,'captured_seconds':0,'eta':'Estimating','title':'','mode':getattr(args,'mode','auto'),'source_duration':None,'source_progress':None,'overall_eta':None,'target':args.count,'segment_seconds':args.segment,'progress':None}
    def update(**kw):
        state.update(kw); atomic(job/'status.json',state)
    def stage(name,message,**kw):
        estimate=timings.get(name)
        update(stage=name,message=message,eta='Estimating',stage_started=time.time(),stage_estimate=estimate,**kw)
    update(); clips=[]; prev=None; prev_segments=[]; prev_len=0.; offset=0.; index=0; proc=None; stop_sent=None; next_due=None; last_ready=0; timings={}
    def stop_capture():
        nonlocal stop_sent
        if proc and proc.poll() is None and stop_sent is None:
            stop_sent=time.monotonic()
            try: proc.send_signal(signal.SIGINT)
            except ProcessLookupError: pass
    try:
        feedback_channel=getattr(args,'feedback_channel','') or getattr(args,'publish_channel','')
        if getattr(args,'analytics_refresh',False) and feedback_channel:
            from analytics_feedback import maybe_refresh
            try: maybe_refresh(feedback_channel)
            except Exception: print('Analytics refresh unavailable; continuing without new feedback.',flush=True)
        if getattr(args,'input_file',None):
            local=args.input_file.expanduser().resolve()
            if not local.is_file(): raise ValueError('Local video file does not exist.')
            if getattr(args,'mode','auto')=='live': raise ValueError('Use replay or auto mode for a local file.')
            title,formats,mode,source_duration=local.stem,[{'url':str(local)}],'replay',duration(local)
        else:
            if getattr(args,'smart_replay',False) and getattr(args,'mode','auto')!='live':
                from smart_replay import probe, run_replay
                info=probe(args.url,getattr(args,'browser',None))
                if info is not None:
                    run_replay(args,job,out,update,stage,atomic,candidates,info)
                    return
                if getattr(args,'mode','auto')=='replay': raise ValueError('This stream is still live; choose Auto detect or Live.')
            try:
                title,formats,mode,source_duration=resolve_source(args.url,getattr(args,'mode','auto'),getattr(args,'browser',None))
            except NativeReplayRequired:
                if not getattr(args,'native_fallback',False):
                    raise RuntimeError('Direct media format unsupported. Enable replay download fallback or use a local authorized recording.')
                native=download_replay(args.url,job,update,getattr(args,'browser',None))
                if native is None:
                    update(stage='done',capture='ended',message='Download stopped'); return
                title,formats,mode,source_duration='Downloaded replay',[{'url':str(native)}],'replay',duration(native)
        configure_full_scan(args,mode)
        if getattr(args,'defer_publish',False): update(target=0)
        if mode=='live': args.source_identity += ':live-session:'+job.name
        expected=min(source_duration,args.minutes*60) if source_duration and args.minutes else source_duration; update(title=title,mode=mode,source_duration=expected); session_started=time.monotonic()
        if (job/'stop').exists(): update(capture='stopped',message='Stopped before capture'); return
        with (job/'capture.log').open('w') as log:
            proc=subprocess.Popen(capture_command(formats,args.segment,args.minutes),cwd=source,stdout=log,stderr=log)
            # A separate supervisor thread stops capture even during inference/export.
            import threading
            finished=threading.Event()
            def supervise():
                while not finished.wait(.5):
                    if proc.poll() is not None:
                        (job/'capture_done').touch(); return
                    if (job/'stop').exists(): stop_capture()
                    if shutil.disk_usage(source).free < 2*1024**3:
                        (job/'disk_limit').touch(); stop_capture()
                    if stop_sent is not None and proc.poll() is None and time.monotonic()-stop_sent>15: proc.kill()
            thread=threading.Thread(target=supervise,daemon=True); thread.start()
            try:
                next_due=time.monotonic()+args.segment
                active_capture='live' if mode=='live' else 'replay'
                update(capture=active_capture,message='Acquiring first segment; waiting for it to close')
                while True:
                    alive=proc.poll() is None; files=closed_segments(source)
                    if len(files)!=last_ready:
                        last_ready=len(files); next_due=time.monotonic()+args.segment
                    update(segments_ready=len(files),capture='stopping' if stop_sent is not None and alive else active_capture if alive else 'ended')
                    if (job/'stop').exists() or (args.count and len(clips)>=args.count):
                        stop_capture(); break
                    if index>=len(files):
                        if not alive: break
                        update(stage='source',message='Waiting for next completed segment',eta='Next segment ~'+eta(max(0,next_due-time.monotonic())) if mode=='live' else 'Waiting for source data',stage_estimate=None,progress=None)
                        time.sleep(1); continue
                    p=files[index]; began=time.monotonic()
                    try:
                        total=duration(p)
                        stage('transcribe',f'Transcribing segment {index+1}',progress=None); started=time.monotonic()
                        with tempfile.TemporaryDirectory(prefix='live-work-') as tmp:
                            work=Path(tmp); seg=transcribe(p,work,args.whisper,args.language or None); timings['transcribe']=time.monotonic()-started
                            boundary=prev_len if prev else 0.; base=offset-boundary
                            window=([s for s in prev_segments if s['end']>=boundary-65] if prev else [])+[{**s,'start':s['start']+boundary,'end':s['end']+boundary,**({'words':[{**w,'start':w['start']+boundary,'end':w['end']+boundary} for w in s['words']]} if 'words' in s else {})} for s in seg]
                            stage('analyze',f'Finding highlights in segment {index+1}',progress=None); started=time.monotonic()
                            if getattr(args,'edit_style','clean')=='gaming' or getattr(args,'viral_preset',''):
                                analysis_media=combine(prev,p,work) if prev else p
                                if getattr(args,'viral_preset',''):
                                    from viral import select as viral_select
                                    selected=viral_select(args,analysis_media,window,boundary+total,boundary,base,clips,args.count-len(clips) if args.count else 0)
                                else:
                                    selected=gaming_candidates(args,analysis_media,window,boundary+total,boundary,base,clips,args.count-len(clips) if args.count else 0)
                            else:
                                analysis_media=None
                                selected=candidates(window,args.model,boundary+total,boundary,base,clips,args.score,args.count-len(clips) if args.count else 0)
                            timings['analyze']=time.monotonic()-started
                            joined=analysis_media if prev else None
                            for j,c in enumerate(selected):
                                stage('export',f'Exporting highlight {len(clips)+1}',progress=round(100*j/max(1,len(selected)))); started=time.monotonic()
                                if c['start']<boundary:
                                    if joined is None: joined=combine(prev,p,work)
                                    media=joined; local=c; subs=window
                                else:
                                    media=p; local={**c,'start':c['start']-boundary,'end':c['end']-boundary}; subs=seg
                                name=f'short_{len(clips)+1:02}.mp4'; temp=out/('pending_'+name)
                                edit_meta = {}
                                if getattr(args,'viral_preset',''):
                                    from viral import render as viral_render
                                    if local.get('impact',-1)>=0 and c['start']>=boundary: local={**local,'impact':local['impact']-boundary}
                                    try:
                                        edit_meta=viral_render(args,media,temp,subs,local)
                                    except ValueError as exc:
                                        temp.unlink(missing_ok=True); print('Skipping viral candidate: '+str(exc),flush=True); continue
                                elif getattr(args,'edit_style','clean') == 'gaming':
                                    from gaming import render as gaming_render, SplitLayoutUnavailable
                                    if local.get('impact',-1)>=0 and c['start']>=boundary: local={**local,'impact':local['impact']-boundary}
                                    try:
                                        edit_meta=gaming_render(media,temp,subs,local,args.software,getattr(args,'face_region',None))
                                    except SplitLayoutUnavailable as exc:
                                        temp.unlink(missing_ok=True)
                                        print('Skipping highlight: '+str(exc),flush=True)
                                        update(message='Skipped highlight: '+str(exc))
                                        continue
                                elif getattr(args,'edit_style','clean') == 'dynamic':
                                    from creator_edit import render_dynamic
                                    edit_meta=render_dynamic(media,temp,subs,local,args.layout,args.software,captions=args.captions)
                                else:
                                    render(media,temp,subs,local,args.layout,args.software,captions=args.captions)
                                dest=out/name; os.replace(temp,dest)
                                if temp.with_suffix('.srt').exists(): os.replace(temp.with_suffix('.srt'),dest.with_suffix('.srt'))
                                clips.append({**c,'start':c['start']+base,'end':c['end']+base,'file':name,**edit_meta,'source_url':getattr(args,'url',None),'source_identity':getattr(args,'source_identity','')})
                                atomic(out/'clips.json',clips)
                                if publishing_enabled(args) and not getattr(args,'defer_publish',False):
                                    stage('publish',f'Publishing highlight {len(clips)}',progress=None)
                                    publish_ready(args,dest,clips[-1]); atomic(out/'clips.json',clips)
                                timings['export']=time.monotonic()-started
                            old=prev; prev=p; prev_segments=seg; prev_len=total; offset+=total
                            if old and not args.keep_source: old.unlink(missing_ok=True)
                        index+=1
                        overall_eta=eta(max(0,expected-offset)*(time.monotonic()-session_started)/offset) if expected and offset>0 and not args.count else None
                        update(segments_processed=index,captured_seconds=round(offset),source_progress=round(min(100,100*offset/expected),1) if expected else None,overall_eta=overall_eta,message=f'Segment {index} processed',last_segment_seconds=round(time.monotonic()-began))
                    except Exception:
                        # Fail visibly rather than silently discard a segment or misalign timestamps.
                        raise
                stop_capture()
                if proc.poll() is None:
                    try: proc.wait(timeout=20)
                    except subprocess.TimeoutExpired: proc.kill(); proc.wait()
                if stop_sent is None and proc.returncode != 0:
                    raise RuntimeError(capture_failure(job/'capture.log'))
                # FFmpeg can report exit code 0 after premature EOF on a damaged HTTP source.
                if stop_sent is None and not (args.count and len(clips)>=args.count) and not (job/'stop').exists() and expected and offset < expected - max(10, expected * 0.005):
                    raise RuntimeError(f'Replay ended early: analysed {offset:.0f} of {expected:.0f} seconds. Check capture.log; completed clips are retained.')
                if not files and not (job/'stop').exists(): raise RuntimeError('No completed segments were acquired.')
                publish_ranked(args,out,clips,stage)
                update(stage='done',capture='ended',message=f'{len(clips)} highlights ready',progress=100,eta='00:00:00')
                if (job/'disk_limit').exists():
                    print('Capture stopped because free storage fell below 2 GB.',flush=True)
            finally:
                finished.set(); thread.join(timeout=2)
    except Exception as exc:
        update(stage='error',message=str(exc),capture='ended',eta='—')
        raise
    finally:
        if proc and proc.poll() is None:
            proc.terminate()
            try: proc.wait(timeout=5)
            except subprocess.TimeoutExpired: proc.kill(); proc.wait()
        if not args.keep_source:
            for p in source.glob('part_*.mkv'): p.unlink(missing_ok=True)
            if (job/'native').exists(): shutil.rmtree(job/'native',ignore_errors=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(); inputs=p.add_mutually_exclusive_group(required=True); inputs.add_argument('--url'); inputs.add_argument('--input-file',type=Path); p.add_argument('--output',type=Path,required=True); p.add_argument('--mode',choices=['auto','live','replay'],default='auto'); p.add_argument('--authorized',action='store_true'); p.add_argument('--count',type=int,default=6); p.add_argument('--minutes',type=int,default=0); p.add_argument('--segment',type=int,default=120); p.add_argument('--score',type=int,default=75); p.add_argument('--layout',choices=['original','fit','crop'],default='original'); p.add_argument('--language',default=''); p.add_argument('--model',default=MODEL); p.add_argument('--whisper',default=WHISPER); p.add_argument('--browser',choices=['chrome']); p.add_argument('--native-fallback',action='store_true'); p.add_argument('--smart-replay',action='store_true'); p.add_argument('--edit-style',choices=['clean','dynamic','gaming'],default='clean'); p.add_argument('--captions',action='store_true'); p.add_argument('--keep-source',action='store_true'); p.add_argument('--software',action='store_true'); p.add_argument('--streamer',default=''); p.add_argument('--game',default=''); p.add_argument('--face-region',type=lambda x: __import__('auto_publish').parse_region(x)); p.add_argument('--publish-channel',default=''); p.add_argument('--made-for-kids',choices=['yes','no']); p.add_argument('--daily-limit',type=int,default=6); p.add_argument('--analytics-refresh',action='store_true'); p.add_argument('--viral-preset',choices=['','auto','gaming','podcast','funny','educational','emotional','motivational','cinematic','minimal','energy'],default=''); p.add_argument('--viral-captions',choices=['off','karaoke','bold','minimal'],default='off'); p.add_argument('--viral-overlays',action='store_true'); p.add_argument('--viral-variants',action='store_true'); p.add_argument('--viral-full-scan',action='store_true'); p.add_argument('--feedback-channel',default=''); p.add_argument('--instagram-account',default=''); p.add_argument('--viral-review',action='store_true'); p.add_argument('--chat-file',default=''); p.add_argument('--chat-capture-clock',action='store_true'); a=p.parse_args()
    if not a.authorized: p.error('Permission required')
    if a.publish_channel and ((a.edit_style!='gaming' and not a.viral_preset) or a.made_for_kids is None or not 1<=a.daily_limit<=30): p.error('Public upload requires Gaming or Viral mode, explicit audience and daily limit 1–30')
    if a.instagram_account and ((a.edit_style!='gaming' and not a.viral_preset) or not a.instagram_account.isdigit() or not 1<=a.daily_limit<=30): p.error('Instagram requires Gaming or Viral mode and daily limit 1–30')
    if not (0<=a.count<=100 and 0<=a.minutes<=720 and 60<=a.segment<=180 and 0<=a.score<=100): p.error('Invalid limits')
    main(a)
