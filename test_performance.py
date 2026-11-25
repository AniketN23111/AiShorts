import json, os, shutil, subprocess, tempfile, types, unittest, wave
from pathlib import Path
from unittest.mock import patch
import performance as p, viral, editorial_review, creator_edit, app, smart_replay, publisher

class PerformanceTests(unittest.TestCase):
    def test_weights_and_penalties(self):
        r={k:90 for k in p.WEIGHTS}; z={k:0 for k in p.PENALTIES}
        self.assertEqual(sum(p.WEIGHTS.values()),100);self.assertEqual(p.story_score(r,z),90)
        self.assertEqual(p.story_score(r,{**z,'weak_ending':4}),86)
        for bad in ({**z,'misleading_editing':1},{**z,'weak_ending':float('nan')},{}):
            with self.assertRaises(ValueError):p.story_score(r,bad)
    def test_boundaries_and_lexical_duplicate(self):
        rows=[{'start':5,'end':8,'text':'The opening'},{'start':15,'end':18,'text':'The complete payoff'}]
        a,b=p.align(6,17,rows,0,30);self.assertLess(a,5);self.assertGreater(b,18)
        with self.assertRaises(ValueError):p.align(10,22,[{'start':0,'end':13}],0,30)
        phrase='this is an actual interesting story about a surprising result for everyone listening today'
        self.assertTrue(p.similar(phrase,phrase+' indeed'));self.assertFalse(p.similar(phrase,'another thing happened'))
    def test_word_remap_preserves_timing_and_fails_closed(self):
        rows=[{'words':[{'word':'one','start':1,'end':2},{'word':'two','start':4.9,'end':5.1},{'word':'three','start':10,'end':11}]}]
        self.assertEqual(p.map_words(rows,[(0,5),(5,7),(9,12)],10)[2]['start'],8)
        self.assertEqual(p.map_words(rows,[(0,5),(9,12)],8),[])
        self.assertEqual(p.map_words(rows,[(0,7),(9,12)],12),[])
    def test_event_only_edits(self):
        self.assertEqual(len(creator_edit.edit_plan([],0,30)[0]),4)
        self.assertEqual(creator_edit.edit_plan([],0,30,event_only=True)[0],[(0,30)])
    def test_mode_validation(self):
        for m in p.MODES:app.validate({'authorized':True,'url':'https://youtu.be/test','processing_mode':m})
        with self.assertRaises(ValueError):app.validate({'authorized':True,'url':'https://youtu.be/test','processing_mode':'fake'})
    def test_story_selection_without_full_window_vision(self):
        c={'start':0,'end':20,'impact':10,'title':'Unexpected answer','titles':['Unexpected answer'],'ratings':{k:90 for k in p.WEIGHTS},'rating_reasons':{k:'Observed' for k in p.WEIGHTS},'penalties':{k:0 for k in p.PENALTIES},'story_pattern':'question_answer','setup':'Question','payoff':'Answer','evidence':'Question and actual reply','style':'podcast'}
        args=types.SimpleNamespace(model='model',viral_preset='auto',score=85,processing_mode='smart')
        speech=[{'start':0,'end':20,'text':'An interesting question and answer'}]
        frames=[{'t':i,'motion':0.,'face':False,'dark':False} for i in range(20)]
        with patch.object(p,'scan',return_value=frames),patch.object(p,'audio',return_value=[.1]*20),patch.object(viral,'visual_context') as v,patch.object(viral,'cached_selection',return_value={'clips':[c]}):
            r=viral.select(args,Path('unused'),speech,20,0,0,[],0);self.assertEqual(r[0]['score'],90);self.assertEqual(r[0]['story_pattern'],'question_answer');v.assert_not_called()
            self.assertEqual(viral.select(args,Path('unused'),[],20,0,0,[],0),[])
    def test_review_new_weights(self):
        r={'accept':True,'metadata_grounded':True,'reason':'Observed','opening':'Question','payoff':'Answer','evidence':'Speech','ratings':{k:90 for k in p.WEIGHTS},'rating_reasons':{k:'Evidence' for k in p.WEIGHTS},'penalties':{k:0 for k in p.PENALTIES}}
        result=editorial_review.validate(r,85,visual_available=False,speech_available=True,optimized=True)
        self.assertEqual(result['score_weights'],p.WEIGHTS)
        with self.assertRaises(ValueError):editorial_review.validate({**r,'penalties':{**r['penalties'],'missing_context':10}},85,visual_available=False,speech_available=True,optimized=True)
    def test_rolling_preview_reuses_previous_transcript(self):
        with tempfile.TemporaryDirectory() as td,patch.object(publisher,'CONFIG',Path(td)/'cache'):
            root=Path(td); roll=smart_replay.RollingPreview(root/'rolling');roll.root.mkdir();calls=[]
            def fetch(args,job,folder,a,b,kind):
                calls.append((a,b));folder.mkdir();f=folder/'section.mkv';f.write_bytes(str(a).encode());return f
            args=types.SimpleNamespace(whisper='m',language='');stage=lambda *a,**kw:None
            def join(a,b,work): f=work/'combined.mkv';f.write_bytes(b'join');return f
            words=[{'start':1,'end':2,'text':'hello','words':[{'word':'hello','start':1,'end':2}]}]
            with patch.object(smart_replay,'fetch',side_effect=fetch),patch.object(smart_replay,'transcribe',return_value=words) as transcribe,patch.object(smart_replay,'duration',side_effect=lambda x:120 if x.name=='combined.mkv' else 60),patch.object(smart_replay,'stream_signature',return_value=['same']),patch('live.combine',side_effect=join):
                for i in range(2):
                    work=root/f'w{i}';work.mkdir();result=roll.load(args,root,work,i,i*60,(i+1)*60,stage)
                self.assertEqual(result[1][1]['words'][0]['start'],61);self.assertEqual(result[2],0);self.assertEqual(calls,[(0,60),(60,120)]);self.assertEqual(transcribe.call_count,2)
    def test_pause_stop_and_resume(self):
        with tempfile.TemporaryDirectory() as td:
            job=Path(td); changes=[]; (job/'pause').touch()
            with patch.object(smart_replay.time,'sleep',side_effect=lambda _: (job/'pause').unlink()):
                self.assertTrue(smart_replay.wait_if_paused(job,lambda **kw:changes.append(kw)))
            self.assertEqual(changes[0]['stage'],'paused');self.assertIn('Resuming',changes[-1]['message'])
            (job/'pause').touch();(job/'stop').touch();self.assertFalse(smart_replay.wait_if_paused(job,lambda **kw:None))
    @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg needed')
    def test_waveform_alignment_real_audio(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);a=root/'a.wav';b=root/'b.wav';c=root/'wrong.wav';rate=8000
            rng=np.random.default_rng(9);x=(rng.normal(0,.11,rate*20)*32767).astype('<i2');delta=640
            def write(path,arr):
                with wave.open(str(path),'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(rate);f.writeframes(arr.tobytes())
            write(a,x);write(b,x[3*rate+delta:15*rate+delta]);write(c,(rng.normal(0,.11,rate*12)*32767).astype('<i2'))
            self.assertAlmostEqual(p.audio_alignment(a,b,3,12),.08,places=2);self.assertIsNone(p.audio_alignment(a,c,3,12))
    @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg needed')
    def test_real_scan_cache_and_short_render(self):
        import viral_reframe
        with tempfile.TemporaryDirectory() as td,patch.object(publisher,'CONFIG',Path(td)/'cache'):
            root=Path(td); source=root/'source.mp4';master=root/'master.mp4';out=root/'out.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=320x180:r=15','-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','11','-c:v','libx264','-threads','2','-c:a','aac',str(source)],check=True)
            first=p.scan(source,0,11,1);self.assertEqual(len(first),11)
            with patch('performance.subprocess.check_output',side_effect=AssertionError('Cache must be used')): self.assertEqual(first,p.scan(source,0,11,1))
            clip={'start':0,'end':11,'viral_style':'minimal','processing_mode':'smart'}
            m=viral_reframe.render(source,master,[],clip,True);self.assertEqual(m['shot_count'],1)
            viral.decorate(master,out,[],{**clip,**m},'off',False,True)
            q=viral.validate_export(out,[],'off');self.assertTrue(10<=q['duration']<=12);self.assertEqual(q['black_seconds'],0)

if __name__=='__main__':unittest.main()
