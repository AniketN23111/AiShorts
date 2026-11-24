import tempfile, unittest, subprocess, json, shutil, threading, time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import live, shorts

class LiveTests(unittest.TestCase):
    def test_source_detection(self):
        muxed={'url':'https://example.com/media','protocol':'https','height':720,'vcodec':'avc1','acodec':'aac'}
        hls={**muxed,'protocol':'m3u8_native'}
        replay={'title':'Replay','live_status':'was_live','duration':18000,'formats':[muxed]}
        self.assertEqual(live.select_source(replay),('Replay',[muxed],'replay',18000))
        self.assertEqual(live.select_source({**replay,'live_status':'is_live','formats':[hls]}),('Replay',[hls],'live',None))
        with self.assertRaises(ValueError): live.select_source(replay,'live')
        with self.assertRaises(ValueError): live.select_source({**replay,'live_status':'post_live'})
        with self.assertRaises(RuntimeError): live.select_source({**replay,'formats':[{**muxed,'has_drm':True}]})
    def test_separate_replay_formats(self):
        base={'url':'https://example.com/media','protocol':'https'}
        v={**base,'height':1080,'vcodec':'avc1','acodec':'none'}
        a={**base,'vcodec':'none','acodec':'aac'}
        self.assertEqual(live.select_source({'formats':[v,a]})[1],[v,a])
    def test_muxed_preferred_for_reliability(self):
        base={'url':'https://example.com/media','protocol':'https'}
        muxed={**base,'height':360,'vcodec':'avc1','acodec':'aac'}
        video={**base,'height':1080,'vcodec':'avc1','acodec':'none'}
        audio={**base,'vcodec':'none','acodec':'aac'}
        self.assertEqual(live.select_source({'formats':[video,audio,muxed]})[1],[muxed])
    def test_checked_source_uses_verified_format_and_headers(self):
        rejected={'url':'https://example.com/rejected','protocol':'https','height':1080,'vcodec':'avc1','acodec':'aac'}
        verified={'url':'https://example.com/verified','protocol':'https','height':360,'vcodec':'avc1','acodec':'aac','http_headers':{'user-agent':'format UA'}}
        info={**verified,'formats':[rejected,verified],'http_headers':{'User-Agent':'format UA','Referer':'https://www.youtube.com/'},'duration':3600}
        result=live.checked_source(info)
        self.assertEqual(result[1][0]['url'],verified['url'])
        self.assertEqual(result[1][0]['http_headers']['referer'],'https://www.youtube.com/')
        self.assertIn('user-agent: format UA',' '.join(live.capture_command(result[1],120,0)))
    def test_checked_separate_headers(self):
        video={'url':'https://example.com/v','protocol':'https','height':720,'vcodec':'avc1','acodec':'none','http_headers':{'User-Agent':'video UA'}}
        audio={'url':'https://example.com/a','protocol':'https','vcodec':'none','acodec':'aac'}
        info={'requested_formats':[video,audio],'http_headers':{'User-Agent':'base UA','Referer':'https://www.youtube.com/'}}
        formats=live.checked_source(info)[1]
        self.assertEqual([f['http_headers']['user-agent'] for f in formats],['video UA','base UA'])
    def test_resolve_requests_format_checks(self):
        import sys, types
        from unittest.mock import MagicMock
        ydl=MagicMock(); ydl.return_value.__enter__.return_value.extract_info.return_value={'url':'https://example.com/ok','protocol':'https','height':360,'vcodec':'avc1','acodec':'aac'}
        pkg=types.ModuleType('yt_dlp'); pkg.YoutubeDL=ydl
        utils=types.ModuleType('yt_dlp.utils'); utils.DownloadError=type('DownloadError',(Exception,),{})
        with patch.dict(sys.modules,{'yt_dlp':pkg,'yt_dlp.utils':utils}):
            live.resolve_source('https://youtu.be/test')
        self.assertEqual(ydl.call_args.args[0]['check_formats'],'selected')
        self.assertTrue(ydl.call_args.args[0]['format'].startswith(live.HLS_FORMAT))
    def test_403_is_distinct_from_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            f=Path(tmp)/'capture.log'; f.write_text('HTTP error 403 Forbidden\nError opening input file https://example.com/secret')
            self.assertIn('HTTP 403',live.capture_failure(f)); self.assertNotIn('secret',live.capture_failure(f))
            f.write_text('Operation timed out'); self.assertIn('network retries',live.capture_failure(f))
    def test_network_options_per_input(self):
        cmd=live.capture_command([{'url':'https://example.com/video'},{'url':'https://example.com/audio'}],120,0)
        for opt in ('-reconnect','-reconnect_on_network_error','-reconnect_streamed','-rw_timeout','-reconnect_max_retries'):
            self.assertEqual(cmd.count(opt),2)
        self.assertNotIn('-reconnect',live.capture_command([{'url':'/tmp/local.mkv'}],120,0))
    def test_incremental_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            job=Path(tmp)/'job'
            command=['python','-u','-c',"import pathlib,time; pathlib.Path('part_000000.mkv').touch(); pathlib.Path('segments.csv').write_text('part_000000.mkv,0,30\\n'); time.sleep(30)"]
            a=SimpleNamespace(output=job,url='https://youtu.be/test',mode='auto',count=1,minutes=0,segment=120,score=75,layout='original',software=True,captions=False,keep_source=False,whisper='mock',language='',model='mock')
            def fake_render(source,dest,*args,**kwargs): dest.write_bytes(b'video'); dest.with_suffix('.srt').write_text('sub')
            with patch('live.resolve_source',return_value=('Replay',[],'replay',300)),patch('live.capture_command',return_value=command),patch('live.duration',return_value=30),patch('live.transcribe',return_value=[dict(start=0,end=30,text='speech')]),patch('live.ask_ai',return_value=[dict(first=0,last=0,title='Clip',score=90)]),patch('live.render',side_effect=fake_render),patch('live.shutil.disk_usage',return_value=SimpleNamespace(free=10*1024**3)):
                live.main(a)
            status=json.loads((job/'status.json').read_text())
            self.assertEqual((status['mode'],status['source_progress'],status['stage']),('replay',10.0,'done'))
            self.assertEqual(len(json.loads(next(job.glob('*/clips.json')).read_text())),1)
    def test_local_file_mode_uses_incremental_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); job=root/'job'; local=root/'input.mp4'; local.touch()
            command=['python','-u','-c',"import pathlib,time; pathlib.Path('part_000000.mkv').touch(); pathlib.Path('segments.csv').write_text('part_000000.mkv,0,30\\n'); time.sleep(30)"]
            args=SimpleNamespace(output=job,input_file=local,mode='auto',count=1,minutes=0,segment=120,score=75,layout='original',software=True,captions=False,keep_source=False,whisper='mock',language='',model='mock')
            def fake_render(source,dest,*args,**kwargs): dest.write_bytes(b'video'); dest.with_suffix('.srt').write_text('sub')
            with patch('live.resolve_source') as resolve,patch('live.capture_command',return_value=command) as capture,patch('live.duration',return_value=30),patch('live.transcribe',return_value=[dict(start=0,end=30,text='speech')]),patch('live.ask_ai',return_value=[dict(first=0,last=0,title='Clip',score=90)]),patch('live.render',side_effect=fake_render),patch('live.shutil.disk_usage',return_value=SimpleNamespace(free=10*1024**3)):
                live.main(args)
                resolve.assert_not_called(); capture.assert_called_once_with([{'url':str(local.resolve())}],120,0)
            self.assertEqual(json.loads((job/'status.json').read_text())['stage'],'done')
    def test_segments_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp); (p/'segments.csv').write_text('part_000000.mkv,0,120\npart_000001.mkv,120,240\npart_000002.mkv,240')
            self.assertEqual([x.name for x in live.closed_segments(p)],['part_000000.mkv','part_000001.mkv'])
    def test_overlap(self):
        seg=[dict(start=i*10,end=(i+1)*10,text='speech') for i in range(12)]
        raw=[dict(first=0,last=2,title='Old',score=99),dict(first=4,last=7,title='Crossing',score=95),dict(first=8,last=10,title='New',score=90),dict(first=9,last=11,title='Low',score=50)]
        with patch('live.ask_ai',return_value=raw):
            self.assertEqual([x['title'] for x in live.candidates(seg,'mock',120,60,0,[],75,0)],['Crossing','New'])
            self.assertEqual([x['title'] for x in live.candidates(seg,'mock',120,60,0,[dict(start=40,end=70)],75,0)],['New'])
    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'ffmpeg required')
    def test_real_segments_and_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp); subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=10','-f','lavfi','-i','sine=frequency=440','-t','6','-c:v','libx264','-g','10','-c:a','aac','-y',str(p/'input.mkv')],check=True)
            subprocess.run(live.capture_command([{'url':str(p/'input.mkv')}],2,0),cwd=p,check=True,capture_output=True)
            files=live.closed_segments(p); self.assertEqual(len(files),3)
            w=p/'work';w.mkdir(); combo=live.combine(files[0],files[1],w)
            out=p/'out.mp4'; shorts.render(combo,out,[dict(start=1,end=3,text='Test')],dict(start=1,end=3),'original',True,captions=False)
            probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(out)]))
            video=next(s for s in probe['streams'] if s['codec_type']=='video');self.assertEqual((video['width'],video['height']),(320,180)); self.assertTrue(out.with_suffix('.srt').is_file())
    def test_incremental_publication(self):
        # Simulate capture process that emits two closed segment records then remains live.
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp); job=p/'job'; command=['python','-u','-c',"import time, pathlib; f=pathlib.Path('segments.csv'); pathlib.Path('part_000000.mkv').touch(); f.write_text('part_000000.mkv,0,30\\n'); time.sleep(30)"]
            a=SimpleNamespace(output=job,url='https://youtu.be/test',count=1,minutes=0,segment=120,score=75,layout='original',software=True,captions=False,keep_source=False,whisper='mock',language='',model='mock')
            def fake_render(source,dest,*args,**kwargs): dest.write_bytes(b'video'); dest.with_suffix('.srt').write_text('sub')
            seg=[dict(start=0,end=30,text='speech')]
            with patch('live.resolve_source',return_value=('Test',[],'live',None)),patch('live.capture_command',return_value=command),patch('live.duration',return_value=30),patch('live.transcribe',return_value=seg),patch('live.ask_ai',return_value=[dict(first=0,last=0,title='Clip',score=90)]),patch('live.render',side_effect=fake_render),patch('live.shutil.disk_usage',return_value=SimpleNamespace(free=10*1024**3)):
                live.main(a)
            manifest=next(job.glob('*/clips.json')); self.assertEqual(len(json.loads(manifest.read_text())),1); self.assertEqual(json.loads((job/'status.json').read_text())['stage'],'done')

if __name__=='__main__': unittest.main()
