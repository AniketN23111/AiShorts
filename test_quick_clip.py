import tempfile, threading, types, unittest, subprocess, shutil
from pathlib import Path
from unittest.mock import patch, Mock
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import app, smart_replay as s, quick_range as q

class QuickClipTests(unittest.TestCase):
    def test_short_windows_valid(self):
        for seconds in (30,45,60,120,180):
            self.assertEqual(app.validate({'authorized':True,'url':'https://youtu.be/test','segment':seconds})[5],seconds)
        self.assertEqual(app.validate({'authorized':True,'url':'https://youtu.be/test'})[5],60)
        self.assertEqual(list(s.windows(85,30))[-1],(0,60,85))

    def test_preview_selection_rejects_bad_sources(self):
        f={'url':'https://example.googlevideo.com/videoplayback?sig=example','protocol':'https','ext':'mp4','height':360,'vcodec':'avc1','acodec':'aac','http_headers':{'User-Agent':'test','Cookie':'secret'}}
        p=q.preview_format({'formats':[f]});self.assertEqual(p['headers'],{'User-Agent':'test'})
        for change in ({'has_drm':True},{'url':'https://example.org/video.mp4'},{'fragments':[1]},{'height':720},{'acodec':'none'}):
            self.assertIsNone(q.preview_format({'formats':[{**f,**change}]}))
        self.assertIsNone(q.preview_format({'is_live':True,'formats':[f]}))

    def test_prefetch_overlaps_analysis_and_cancel(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);started=threading.Event(); release=threading.Event(); calls=[]
            def fetch(args,job,folder,start,end,kind):
                calls.append((start,end));started.set()
                while not release.wait(.01):
                    if args._prefetch_cancel.is_set(): return None
                folder.mkdir();p=folder/'section.mkv';p.touch();return p
            roll=s.RollingPreview(root,prefetch=True,total=200,step=60)
            try:
                with patch.object(s,'fetch',side_effect=fetch):
                    roll.schedule(types.SimpleNamespace(),root,1,60)
                    self.assertTrue(started.wait(2));self.assertFalse(roll.pending.done())
                    roll.schedule(types.SimpleNamespace(),root,1,60)
                    self.assertEqual(calls,[(60,120)]);release.set()
                    self.assertEqual(roll.pending.result(2).name,'section.mkv')
            finally:roll.close()
            self.assertTrue(roll.cancel.is_set())

    def test_prefetch_shutdown_cancels_running_request(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);started=threading.Event();stopped=threading.Event()
            def fetch(args,*unused):
                started.set();args._prefetch_cancel.wait(2);stopped.set();return None
            roll=s.RollingPreview(root,prefetch=True,total=200,step=60)
            with patch.object(s,'fetch',side_effect=fetch):
                roll.schedule(types.SimpleNamespace(),root,1,60);self.assertTrue(started.wait(1));roll.close()
            self.assertTrue(stopped.is_set())

    def test_failed_range_uses_existing_downloader(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);folder=root/'clip';plan={'url':'example','headers':{}};args=types.SimpleNamespace(url='https://youtu.be/example',_preview_plan=plan)
            proc=Mock();proc.poll.return_value=0;proc.returncode=0
            def popen(*a,**kw): (folder/'section.mp4').touch();return proc
            with patch.object(q,'supports_range',return_value=False),patch.object(s.subprocess,'Popen',side_effect=popen),patch.object(s,'duration',return_value=30):
                self.assertEqual(s.fetch(args,root,folder,0,30,'preview').name,'section.mp4')
            self.assertEqual(plan,{})

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
    def test_real_range_seek(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);source=root/'source.mp4';dest=root/'preview.mkv'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=320x180:r=10','-f','lavfi','-i','sine=frequency=600:sample_rate=48000','-t','12','-c:v','libx264','-g','10','-threads','2','-c:a','aac','-movflags','+faststart',str(source)],check=True)
            data=source.read_bytes();requests=[]
            class Handler(BaseHTTPRequestHandler):
                def log_message(self,*args):pass
                def do_GET(self):
                    raw=self.headers.get('Range');requests.append(raw)
                    if raw:
                        a,b=raw[6:].split('-');start=int(a);end=min(len(data)-1,int(b)) if b else len(data)-1
                        self.send_response(206);self.send_header('Content-Range',f'bytes {start}-{end}/{len(data)}')
                    else:start=0;end=len(data)-1;self.send_response(200)
                    self.send_header('Content-Length',str(end-start+1));self.end_headers()
                    try:self.wfile.write(data[start:end+1])
                    except (BrokenPipeError,ConnectionResetError):pass
            server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                plan={'url':f'http://127.0.0.1:{server.server_port}/video.mp4','headers':{}}
                self.assertTrue(q.supports_range(plan));self.assertTrue(q.acquire(plan,5,9,dest,lambda:False,s.terminate));self.assertAlmostEqual(s.duration(dest),4,delta=.15)
                self.assertEqual(requests[0],'bytes=1-1')
                import cv2,numpy as np
                a=cv2.VideoCapture(str(source));a.set(cv2.CAP_PROP_POS_MSEC,5000);ok,x=a.read();a.release()
                b=cv2.VideoCapture(str(dest));ok2,y=b.read();b.release();self.assertTrue(ok and ok2)
                self.assertLess(float(np.mean(np.abs(x.astype(float)-y.astype(float)))),12)
            finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main()
