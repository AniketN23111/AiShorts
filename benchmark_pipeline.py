#!/usr/bin/env python3
"""Run reproducible, non-publishing V12 vs V13 benchmarks on authorized local media.
Component mode needs FFmpeg/OpenCV only. Full mode needs working local AI models.
"""
import argparse, json, os, subprocess, sys, tempfile, time
from pathlib import Path

ROOT=Path(__file__).resolve().parent
WORKER=r'''
import json,sys,time,functools,runpy,resource,os
from pathlib import Path
root=Path(sys.argv[1]); sys.path.insert(0,str(root)); report=Path(sys.argv[2]); sys.argv=sys.argv[3:]; stats={};counts={}
import publisher
publisher.CONFIG=report.parent/'isolated-cache'
import viral,shorts

def instrument(module,name,label):
    old=getattr(module,name)
    @functools.wraps(old)
    def wrapper(*args,**kwargs):
        start=time.monotonic();counts[label]=counts.get(label,0)+1
        try:return old(*args,**kwargs)
        finally:stats[label]=stats.get(label,0)+time.monotonic()-start
    setattr(module,name,wrapper)
for module,name,label in [(shorts,'transcribe','transcription'),(viral,'model_request','ai_requests'),(viral,'visual_context','vision_context'),(viral,'select','selection'),(viral,'render','render_and_review'),(viral,'validate_export','quality')]: instrument(module,name,label)
try:runpy.run_path(str(root/'live.py'),run_name='__main__')
finally:
    me=resource.getrusage(resource.RUSAGE_SELF);children=resource.getrusage(resource.RUSAGE_CHILDREN); scale=1024**2 if sys.platform=='darwin' else 1024
    report.write_text(json.dumps({'timings_seconds':stats,'calls':counts,'worker_peak_rss_mib':me.ru_maxrss/scale,'largest_finished_child_peak_rss_mib':children.ru_maxrss/scale},indent=2))
'''

def run_full(root,source,minutes,output,new,style,caption):
    out=output/('v13' if new else 'v12')/str(minutes);out.mkdir(parents=True)
    report=out/'worker_metrics.json';job=out/'job'; log=out/'run.log'
    cli=[str(root/'live.py'),'--input-file',str(source),'--output',str(job),'--authorized','--mode','replay','--count','0','--minutes',str(minutes),'--segment','120','--score','85','--viral-preset',style,'--viral-captions',caption,'--viral-review','--viral-full-scan','--edit-style','gaming' if style=='gaming' else 'clean']
    if new:cli+=['--processing-mode','smart']
    began=time.monotonic();first=None
    with log.open('w') as f:
        proc=subprocess.Popen([sys.executable,'-c',WORKER,str(root),str(report),*cli],cwd=root,stdout=f,stderr=subprocess.STDOUT,env={**os.environ,'SHORTS_CACHE_VERSION':'benchmark-'+output.name+str(minutes)})
        try:
            while proc.poll() is None:
                if first is None and any(job.glob('*/short_[0-9][0-9].mp4')):first=time.monotonic()-began
                time.sleep(.5)
        except KeyboardInterrupt:proc.terminate();proc.wait();raise
    manifests=list(job.glob('*/clips.json'));clips=[c for m in manifests for c in json.loads(m.read_text())]
    result={'exit_code':proc.returncode,'elapsed_seconds':round(time.monotonic()-began,2),'first_clip_seconds':round(first,2) if first is not None else None,'clips':len(clips),'scores':[c.get('score') for c in clips],'gpu_utilization':None,'paid_api_cost':0,'manual_editorial_review_required':True}
    if report.exists():result.update(json.loads(report.read_text()))
    if (job/'status.json').exists():result['status']=json.loads((job/'status.json').read_text())
    print(json.dumps({('v13' if new else 'v12')+'_'+str(minutes):result},indent=2),flush=True);return result

def components(baseline,output):
    import gaming,performance,publisher,viral_reframe,viral
    output.mkdir(parents=True,exist_ok=True)
    def elapsed(fn):start=time.perf_counter();value=fn();return round(time.perf_counter()-start,3),value
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);publisher.CONFIG=root/'cache';source=root/'proxy.mp4';vertical=root/'vertical.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=640x360:r=15','-f','lavfi','-i','sine=frequency=440','-t','120','-c:v','libx264','-preset','ultrafast','-threads','2','-c:a','aac',str(source)],check=True)
        # V12's unchanged original scanning implementation, using its actual source file.
        cmd='import sys,time,json;sys.path.insert(0,sys.argv[1]);import gaming;t=time.perf_counter();frames,_=gaming.sample(sys.argv[2],0,120);print(json.dumps({"seconds":time.perf_counter()-t,"samples":len(frames)}))'
        old=json.loads(subprocess.check_output([sys.executable,'-c',cmd,str(baseline),str(source)],text=True))
        new,frames=elapsed(lambda:performance.scan(source,0,120,1));cached,_=elapsed(lambda:performance.scan(source,0,120,1))
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=1080x1920:r=30','-f','lavfi','-i','sine=frequency=440','-t','16','-c:v','libx264','-preset','ultrafast','-threads','2','-c:a','aac',str(vertical)],check=True)
        cmd='import sys,time,json;sys.path.insert(0,sys.argv[1]);from viral import validate_export;from pathlib import Path;t=time.perf_counter();validate_export(Path(sys.argv[2]),[],"off");print(json.dumps({"seconds":time.perf_counter()-t}))'
        oldq=json.loads(subprocess.check_output([sys.executable,'-c',cmd,str(baseline),str(vertical)],text=True))
        newq,_=elapsed(lambda:viral.validate_export(vertical,[],'off'))
        result={'environment':{'platform':sys.platform,'machine':os.uname().machine,'python':sys.version.split()[0]},'fixture':'synthetic 120s 640x360 proxy; 16s 1080x1920 output; no real AI inference','scan':{'v12_seconds':round(old['seconds'],3),'v13_seconds':new,'v12_samples':old['samples'],'v13_samples':len(frames),'warm_cache_seconds':cached},'quality_validation':{'v12_seconds':round(oldq['seconds'],3),'v13_seconds':newq},'limitations':'One run, different scan granularity; not an end-to-end benchmark or clip-quality comparison.'}
        (output/'components.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--baseline',required=True,type=Path);ap.add_argument('--source',type=Path);ap.add_argument('--authorized',action='store_true');ap.add_argument('--components',action='store_true');ap.add_argument('--minutes',nargs='+',type=int,default=[30,60,180]);ap.add_argument('--style',default='gaming');ap.add_argument('--captions',default='karaoke');ap.add_argument('--output',type=Path,default=Path('benchmarks')/time.strftime('%Y%m%d_%H%M%S'));a=ap.parse_args()
    baseline=a.baseline.resolve();out=a.output.resolve()
    if not (baseline/'live.py').is_file():ap.error('Pass the extracted V12 project directory')
    if a.components:return components(baseline,out)
    if not a.authorized or not a.source or not a.source.is_file():ap.error('Full benchmark needs an authorized local recording and --authorized')
    from shorts import duration
    if max(a.minutes)*60>duration(a.source):ap.error('Source is shorter than the longest requested run')
    results={}
    for m in a.minutes:
        results[str(m)]={'v12':run_full(baseline,a.source.resolve(),m,out,False,a.style,a.captions),'v13':run_full(ROOT,a.source.resolve(),m,out,True,a.style,a.captions)}
    (out/'comparison.json').write_text(json.dumps(results,indent=2))
if __name__=='__main__':main()
