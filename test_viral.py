import os,json,tempfile,unittest,types,subprocess,shutil
from pathlib import Path
from unittest.mock import patch
import viral,app,viral_reframe

class ViralTests(unittest.TestCase):
    def test_exact_weighted_score(self):
        self.assertEqual(sum(viral.WEIGHTS.values()),100)
        self.assertEqual(viral.score({k:80 for k in viral.WEIGHTS}),80)
        ratings={k:0 for k in viral.WEIGHTS};ratings['hook']=100
        self.assertEqual(viral.score(ratings),25)
        for bad in ({}, {**ratings,'hook':float('nan')},{**ratings,'hook':True}):
            with self.assertRaises(ValueError):viral.score(bad)
    def test_context_and_duplicate_gate(self):
        frames=[dict(t=i,motion=.1,face=True,dark=False) for i in range(60)]
        args=types.SimpleNamespace(model='model',viral_preset='auto',score=85,streamer='',game='')
        candidate=dict(start=1,end=30,impact=3,title='Unexpected answer',titles=['Unexpected answer','A thoughtful response'],ratings={k:90 for k in viral.WEIGHTS},rating_reasons={k:'Observed evidence' for k in viral.WEIGHTS},evidence='The transcript answers a question.',style='podcast',hashtags=['#Podcast'],keywords=['discussion'])
        with patch('gaming.sample',return_value=(frames,None)),patch('gaming.audio_features',return_value=[.1]*60),patch.object(viral,'visual_context',return_value=''),patch.object(viral,'cached_selection',return_value={'clips':[candidate]}):
            self.assertEqual(viral.select(args,Path('none'),[],60,0,0,[],1),[])
            speech=[{'start':1,'end':30,'text':'A question and an actual response'}]
            results=viral.select(args,Path('none'),speech,60,0,0,[],1);self.assertEqual(results[0]['score'],90);self.assertEqual(results[0]['viral_style'],'podcast');self.assertIn('#Shorts',results[0]['title'])
            self.assertEqual(viral.select(args,Path('none'),speech,60,0,0,[{'start':0,'end':31}],1),[])
    def test_ass_timing_and_injection(self):
        words=[{'word':'hi','start':.1,'end':.5},{'word':'{\\pos(0,0)}','start':.5,'end':1}]
        ass=viral.build_ass(words,{},16,'karaoke',True)
        self.assertIn('0:00:00.10,0:00:00.50',ass);self.assertIn('pos(490,840)',ass);self.assertNotIn('{\\pos(0,0)}',ass);self.assertNotIn('Dialogue:',viral.build_ass(words,{},16,'off',True))
    def test_new_configuration(self):
        d={'url':'https://youtu.be/example','authorized':True,'viral_preset':'gaming','viral_captions':'karaoke'};app.validate(d)
        for field in ('viral_preset','viral_captions'):
            with self.assertRaises(ValueError):app.validate({**d,field:'invalid'})
    def test_full_scan_and_ranked_publish(self):
        import live
        with tempfile.TemporaryDirectory() as td:
            args=types.SimpleNamespace(viral_preset='gaming',viral_full_scan=True,count=2,publish_channel='UCtest',output=Path(td))
            live.configure_full_scan(args,'replay');self.assertEqual(args.count,0)
            clips=[{'score':x,'file':str(x)+'.mp4'} for x in (85,97,91)]
            with patch.object(live,'publish_ready') as publish:
                live.publish_ranked(args,Path(td),clips,lambda *a,**k:None)
                self.assertEqual([c.args[2]['score'] for c in publish.call_args_list],[97,91])
    def test_import_analytics_and_no_fake_samples(self):
        import analytics_feedback as a,publisher
        with tempfile.TemporaryDirectory() as td,patch.object(publisher,'CONFIG',Path(td)):
            header='video_id,duration,views,retention,average_view_duration,likes,comments,shares,subscribers_gained\n'
            data=a.import_csv('UC'+'x'*22,header+'abcdefghijk,20,100,80,16,5,1,2,1\n')
            self.assertEqual(data['source'],'user_import');self.assertEqual(data['sample'][0]['views'],100);self.assertEqual(data['summary'],'')
            self.assertEqual(a.feedback('UC'+'z'*22),'')
            with self.assertRaises(ValueError):a.import_csv('UC'+'x'*22,header+'abcdefghijk,20,nan,80,16,5,1,2,1\n')
    def test_perceptual_duplicate(self):
        import auto_publish
        a=['0000000000000000','ffffffffffffffff','123456789abcdef0','aaaaaaaaaaaaaaaa','bbbbbbbbbbbbbbbb']
        self.assertTrue(auto_publish.near_duplicate(a,a));self.assertFalse(auto_publish.near_duplicate(a,list(reversed(a))))
    @unittest.skipUnless(shutil.which('ffmpeg'),'ffmpeg required')
    def test_real_caption_export_and_quality(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); source=root/'source.mp4'; master=root/'master.mp4'; dest=root/'output.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=320x180:r=15','-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','16','-c:v','libx264','-threads','2','-c:a','aac',str(source)],check=True)
            clip={'start':0,'end':16,'viral_style':'minimal','hook':'Interesting moment','cta':'More highlights','impact_output':3}
            meta=viral_reframe.render(source,master,[],clip,True)
            words=[{'word':'Test','start':1,'end':1.5,'probability':.99},{'word':'caption','start':1.5,'end':2,'probability':.96}]
            with patch.dict(os.environ,{'SHORTS_AUTHORIZED_MUSIC':'','SHORTS_AUTHORIZED_SFX':''}):viral.decorate(master,dest,words,{**clip,**meta},'karaoke',True,True)
            q=viral.validate_export(dest,words,'karaoke');self.assertGreaterEqual(q['duration'],15);self.assertGreater(q['asr_mean_word_confidence'],.9)
    @unittest.skipUnless(shutil.which('ffmpeg'),'ffmpeg required')
    def test_complete_viral_render_and_variant_with_local_audio(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); source=root/'source.mp4'; dest=root/'pending_short_01.mp4'; tone=root/'authorized-test-tone.wav'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=320x180:r=15','-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','17','-c:v','libx264','-threads','2','-c:a','aac',str(source)],check=True)
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=660:sample_rate=48000','-t','1','-c:a','pcm_s16le',str(tone)],check=True)
            args=types.SimpleNamespace(edit_style='clean',software=True,viral_captions='karaoke',viral_overlays=True,viral_variants=True,whisper='mock',language='en')
            clip={'start':0,'end':17,'viral_style':'minimal','hook':'Interesting moment','cta':'More highlights','comment_prompt':'What happened?','impact':3,'thumbnail_time':5}
            words=[{'word':'Test','start':1,'end':1.5,'probability':.99},{'word':'caption','start':1.5,'end':2,'probability':.96}]
            with patch.object(viral,'words_for',return_value=words),patch.dict(os.environ,{'SHORTS_AUTHORIZED_MUSIC':str(tone),'SHORTS_AUTHORIZED_SFX':str(tone)}):
                result=viral.render(args,source,dest,[],clip)
            self.assertTrue(result['viral']);self.assertTrue(dest.exists());self.assertTrue((root/'short_01_words.json').exists());self.assertTrue((root/'short_01_thumb.jpg').exists());self.assertEqual(len(result['variations']),1);self.assertTrue((root/'short_01_alt.mp4').exists())
if __name__=='__main__':unittest.main()
