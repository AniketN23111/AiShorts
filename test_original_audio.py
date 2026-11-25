import json, os, subprocess, tempfile, unittest, urllib.request, urllib.error, threading
from pathlib import Path
from unittest.mock import patch
import app, performance, publisher, viral, visual_reference

class OriginalOnlyTests(unittest.TestCase):
    def test_exact_new_weights(self):
        expected={'hook':25,'retention':25,'entertainment':20,'story':15,'emotion':10,'rewatch':5}
        self.assertEqual(viral.WEIGHTS,expected);self.assertEqual(performance.WEIGHTS,expected)
        self.assertEqual(viral.score({'hook':80,'retention':90,'entertainment':70,'story':100,'emotion':60,'rewatch':80}),81.5)
    def test_real_original_audio_copy_and_ignored_legacy(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);src=root/'source.mp4';dest=root/'out.mp4';tone=root/'music.wav'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=320x180:r=15','-f','lavfi','-i','sine=f=440:r=48000','-t','3','-c:v','libx264','-threads','2','-c:a','aac',str(src)],check=True)
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=f=1500:r=48000','-t','3',str(tone)],check=True)
            clip={'audio_timeline':{'music':{'id':'old'},'sfx':{'id':'old'}},'original_audio_normalized':True}
            with patch.dict(os.environ,{'SHORTS_AUTHORIZED_MUSIC':str(tone),'SHORTS_AUTHORIZED_SFX':str(tone)}),patch('sound_studio.asset_path',side_effect=AssertionError('must never open external assets')):
                viral.decorate(src,dest,[],clip,'off',False,True)
            def hash_audio(p):return subprocess.check_output(['ffmpeg','-v','error','-i',str(p),'-map','0:a:0','-c','copy','-f','hash','-']).strip()
            self.assertEqual(hash_audio(src),hash_audio(dest))
            # Verify general/non-normalized audio path too (external tone must not appear).
            clip.pop('original_audio_normalized');out=root/'enhanced.mp4'
            with patch.dict(os.environ,{'SHORTS_AUTHORIZED_MUSIC':str(tone),'SHORTS_AUTHORIZED_SFX':str(tone)}),patch('sound_studio.asset_path',side_effect=AssertionError('must never open external assets')):
                viral.decorate(src,out,[],clip,'off',False,True)
            import numpy as np
            pcm=np.frombuffer(subprocess.check_output(['ffmpeg','-v','error','-ss','.5'.replace('.5','0.5'),'-i',str(out),'-t','2','-vn','-ac','1','-ar','48000','-f','f32le','-']),dtype='<f4')
            spectrum=abs(np.fft.rfft(pcm*np.hanning(len(pcm))));freqs=np.fft.rfftfreq(len(pcm),1/48000)
            self.assertAlmostEqual(freqs[spectrum.argmax()],440,delta=2)
            self.assertLess(spectrum[abs(freqs-1500)<2].max()/spectrum.max(),.01)
    def test_reference_no_audio_and_cached(self):
        with tempfile.TemporaryDirectory() as td,patch.object(publisher,'CONFIG',Path(td)/'cfg'):
            p=Path(td)/'reference.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=160x90:r=10','-t','3','-c:v','libx264','-an',str(p)],check=True)
            with self.assertRaises(ValueError):visual_reference.analyze(p)
            with patch('sound_studio.analyze_audio',side_effect=AssertionError('reference must not analyze audio')):
                r=visual_reference.analyze(p,True)
            self.assertIn('No audio analyzed',r['limitations']);self.assertNotIn('audio_pulse_bpm',r)
            with patch('performance.scan',side_effect=AssertionError('cache expected')):self.assertEqual(r,visual_reference.analyze(p,True))
            self.assertIn('Optional visual style reference',visual_reference.prompt_guidance(r))
    def test_disabled_http_audio_endpoints(self):
        server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler);host=f'127.0.0.1:{server.server_port}';base='http://'+host
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with tempfile.TemporaryDirectory() as td,patch.object(app,'HOST',host),patch.object(publisher,'CONFIG',Path(td)/'cfg'):
                self.assertEqual(json.load(urllib.request.urlopen(base+'/api/sound/library'))['assets'],[])
                for endpoint in ('/api/sound/import','/api/sound/remix'):
                    req=urllib.request.Request(base+endpoint,data=b'{}',headers={'Origin':base,'X-Local-UI':'1','Content-Type':'application/json'})
                    with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(req)
                    self.assertEqual(caught.exception.code,400);self.assertIn(b'External audio disabled',caught.exception.read())
        finally:server.shutdown();server.server_close();thread.join()
    def test_local_bounded_preview(self):
        import types,smart_replay
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);src=root/'source.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=640x480:r=20','-f','lavfi','-i','sine=f=440:r=48000','-t','10','-c:v','libx264','-threads','2','-c:a','aac',str(src)],check=True)
            args=types.SimpleNamespace(input_file=src)
            preview=smart_replay.fetch(args,root,root/'preview',3,7,'preview')
            self.assertAlmostEqual(smart_replay.duration(preview),4,delta=.2)
            probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=height','-of','json',str(preview)]));self.assertEqual(probe['streams'][0]['height'],360)
            self.assertFalse((root/'download.log').exists())
    def test_local_direct_candidate_uses_original_clock(self):
        import types, smart_replay, live
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);original=root/'original.mp4';original.touch();preview=root/'preview.mkv';preview.touch();out=root/'out';out.mkdir()
            args=types.SimpleNamespace(input_file=original,url=None,mode='replay',minutes=0,segment=60,whisper='w',language='',model='m',score=85,count=1,edit_style='clean',viral_preset='podcast',processing_mode='smart',layout='fit',software=True,captions=True,keep_source=False)
            words=[{'word':t,'start':a,'end':b} for t,a,b in [('actual',5,6),('interesting',6,7),('story',7,8)]]
            seg=[{'start':5,'end':8,'text':'actual interesting story','words':words}];c={'start':4,'end':20,'score':95,'impact':8,'title':'Story','viral_style':'podcast'}
            rolling=Mock();rolling.load.return_value=(preview,seg,60)
            def render(a,src,dest,subs,clip):
                self.assertEqual(src,original);self.assertEqual(clip['start'],64);self.assertEqual(clip['end'],80);self.assertEqual(clip['impact'],68);self.assertEqual(subs[0]['words'][0]['start'],65);dest.touch();return {'viral':True}
            # Exercise second window directly, first window is not a candidate.
            rolling.load.side_effect=[(preview,[],0),(preview,seg,60)]
            with patch.object(smart_replay,'fetch',side_effect=AssertionError('verified local path must not create HD copy')),patch.object(smart_replay,'duration',side_effect=lambda p:120 if p==original else 60),patch('viral.select',side_effect=[[],[c]]),patch('performance.audio_alignment',return_value=0),patch('gaming.verify_visual_range',return_value=True),patch('viral.render',side_effect=render):
                smart_replay._run_replay(args,root,out,lambda **kw:None,lambda *a,**kw:None,live.atomic,Mock(),('Local',120),rolling)
            self.assertTrue((out/'short_01.mp4').exists());self.assertEqual(json.loads((out/'clips.json').read_text())[0]['start'],64)
    def test_duplicate_render_removed_before_export(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'pending_short_02.mp4';p.touch();thumb=p.with_name('short_02_thumb.jpg');thumb.touch()
            m={'fingerprint':['0000000000000000','0000000000000001','0000000000000002','0000000000000003','0000000000000004'],'output_duration':20}
            self.assertFalse(viral.reject_duplicate_export(p,m,[{**m,'output_duration':30}]))
            self.assertTrue(viral.reject_duplicate_export(p,m,[m]));self.assertFalse(p.exists());self.assertFalse(thumb.exists())
