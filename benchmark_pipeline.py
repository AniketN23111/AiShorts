#!/usr/bin/env python3
"""Run reproducible, non-publishing baseline vs current benchmarks on authorized local media.
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
    out=output/('current' if new else 'baseline')/str(minutes);out.mkdir(parents=True)
    report=out/'worker_metrics.json';job=out/'job'; log=out/'run.log'
    cli=[str(root/'live.py'),'--input-file',str(source),'--output',str(job),'--authorized','--mode','replay','--count','3','--minutes',str(minutes),'--segment','60','--score','85','--viral-preset',style,'--viral-captions',caption,'--viral-review','--smart-replay','--edit-style','gaming' if style=='gaming' else 'clean']
    cli+=['--processing-mode','smart']
    began=time.monotonic();first=None
    with log.open('w') as f:
        proc=subprocess.Popen([sys.executable,'-c',WORKER,str(root),str(report),*cli],cwd=root,stdout=f,stderr=subprocess.STDOUT,env={**os.environ,'SHORTS_CACHE_VERSION':'benchmark-'+output.name+str(minutes)})
        try:
            while proc.poll() is None:
                if first is None and any(job.glob('*/short_[0-9][0-9].mp4')):first=time.monotonic()-began
                time.sleep(.5)
        except KeyboardInterrupt:proc.terminate();proc.wait();raise
    if first is None and any(job.glob('*/short_[0-9][0-9].mp4')):first=time.monotonic()-began
    manifests=list(job.glob('*/clips.json'));clips=[c for m in manifests for c in json.loads(m.read_text())]
    result={'exit_code':proc.returncode,'elapsed_seconds':round(time.monotonic()-began,2),'first_clip_seconds':round(first,2) if first is not None else None,'clips':len(clips),'scores':[c.get('score') for c in clips],'gpu_utilization':None,'paid_api_cost':0,'manual_editorial_review_required':True}
    if report.exists():result.update(json.loads(report.read_text()))
    if (job/'status.json').exists():result['status']=json.loads((job/'status.json').read_text())
    print(json.dumps({('current' if new else 'baseline')+'_'+str(minutes):result},indent=2),flush=True);return result

def components(baseline,output):
    """Compare the redundant decoration pass on identical pre-normalized masters."""
    import statistics
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);master=root/'master.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=1080x1920:r=30','-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','16','-c:v','libx264','-preset','ultrafast','-threads','2','-af','loudnorm=I=-16:TP=-1.5:LRA=11','-ar','48000','-c:a','aac',str(master)],check=True)
        code="""import os,sys,time,json,resource
from pathlib import Path
sys.path.insert(0,sys.argv[1]);from viral import decorate
source=Path(sys.argv[2]);target=Path(sys.argv[3]);os.environ.pop('SHORTS_AUTHORIZED_MUSIC',None);os.environ.pop('SHORTS_AUTHORIZED_SFX',None)
times=[]
for i in range(3):
 t=time.monotonic();decorate(source,target,[],{'original_audio_normalized':True},'off',False,True);times.append(round(time.monotonic()-t,4))
print(json.dumps({'seconds':times,'largest_child_peak_rss_mib':round(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss/(1024**2 if sys.platform=='darwin' else 1024),1)}))"""
        results={}
        for name,path in [('baseline',baseline),('current',ROOT)]:
            dest=root/(name+'.mp4');r=json.loads(subprocess.check_output([sys.executable,'-c',code,str(path),str(master),str(dest)],text=True))
            def audio_hash(p):return subprocess.check_output(['ffmpeg','-v','error','-i',str(p),'-map','0:a:0','-c','copy','-f','hash','-']).strip()
            r.update(median_seconds=statistics.median(r['seconds']),audio_stream_identical=audio_hash(master)==audio_hash(dest));results[name]=r
        result={'fixture':'Same synthetic 16s 1080x1920 H264/AAC normalized master, CPU mode, captions/overlays off; three decoration trials each.','platform':sys.platform,'machine':os.uname().machine,'results':results,'limitations':'Component measurement only. No real stream, model inference, captions or end-to-end highlight quality comparison.'}
        (output/'components.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--baseline',required=True,type=Path);ap.add_argument('--source',type=Path);ap.add_argument('--authorized',action='store_true');ap.add_argument('--components',action='store_true');ap.add_argument('--minutes',nargs='+',type=int,default=[30,60,180]);ap.add_argument('--style',default='gaming');ap.add_argument('--captions',default='karaoke');ap.add_argument('--output',type=Path,default=Path('benchmarks')/time.strftime('%Y%m%d_%H%M%S'));a=ap.parse_args()
    baseline=a.baseline.resolve();out=a.output.resolve()
    if not (baseline/'live.py').is_file():ap.error('Pass the extracted baseline project directory (V15 for V16 comparison)')
    if a.components:return components(baseline,out)
    if not a.authorized or not a.source or not a.source.is_file():ap.error('Full benchmark needs an authorized local recording and --authorized')
    from shorts import duration
    if max(a.minutes)*60>duration(a.source):ap.error('Source is shorter than the longest requested run')
    results={}
    for m in a.minutes:
        results[str(m)]={'baseline':run_full(baseline,a.source.resolve(),m,out,False,a.style,a.captions),'current':run_full(ROOT,a.source.resolve(),m,out,True,a.style,a.captions)}
    (out/'comparison.json').write_text(json.dumps(results,indent=2))
if __name__=='__main__':main()
