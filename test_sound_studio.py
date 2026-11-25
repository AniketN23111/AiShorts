import unittest,tempfile,subprocess,json,time
from pathlib import Path
from unittest.mock import patch
import sound_studio as ss
import publisher
from viral import decorate,validate_export

class SoundStudioTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name);self.patch=patch.object(publisher,'CONFIG',self.base/'config');self.patch.start()
    def tearDown(self):self.patch.stop();self.temp.cleanup()
    def fixture(self,name='music.wav',kind='music',platforms=None,license='original',freq=440):
        f=self.base/name
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i',f'aevalsrc=0.12*sin(2*PI*{freq}*t)*(0.2+0.8*lt(mod(t\\,0.5)\\,0.06)):s=22050','-t','24' if kind=='music' else '0.8',str(f)],check=True)
        d={'name':name,'artist':'Test fixture','kind':kind,'license':license,'source_url':'https://www.youtube.com/audiolibrary' if license=='youtube_audio_library' else 'local:original','rights_confirmed':True,'evidence':'Synthetic test file generated locally','platforms':platforms or ['youtube','instagram'],'moods':['funny','unexpected'],'vocals':'instrumental','category':'comedic impact','attribution':'Test fixture credit'}
        f.with_suffix(f.suffix+'.json').write_text(json.dumps(d));return f,d
    def test_import_cache_and_tamper(self):
        f,d=self.fixture(); x=ss.import_folder(self.base);self.assertEqual(x['imported'],[f.name]);r=ss.library()[0];self.assertAlmostEqual(r['analysis']['bpm'],120,delta=3)
        with patch.object(ss,'analyze_audio',side_effect=AssertionError('must reuse cached analysis')):self.assertEqual(ss.import_folder(self.base)['imported'],[f.name])
        (ss.root()/r['file']).write_bytes(b'tampered');self.assertEqual(ss.library(),[])
    def test_license_and_platform_gate(self):
        f,d=self.fixture(platforms=['youtube'],license='youtube_audio_library');d['platforms']=['youtube','instagram'];f.with_suffix(f.suffix+'.json').write_text(json.dumps(d));self.assertEqual(len(ss.import_folder(self.base)['rejected']),1)
        d['platforms']=['youtube'];f.with_suffix(f.suffix+'.json').write_text(json.dumps(d));ss.import_folder(self.base)
        clip={'viral_style':'funny','impact_output':5,'story_pattern':'conversation_comedy'}
        self.assertIsNone(ss.plan(clip,16,{'youtube','instagram'})['music']);p=ss.plan(clip,16,{'youtube'});self.assertIsNotNone(p['music']);self.assertIn('Test fixture credit',ss.ensure_publish({'audio_timeline':p},'youtube','description'))
        with self.assertRaises(ValueError):ss.ensure_publish({'audio_timeline':p},'instagram','description')
    def test_required_license_metadata(self):
        f,d=self.fixture();d['rights_confirmed']=False;f.with_suffix(f.suffix+'.json').write_text(json.dumps(d));self.assertEqual(len(ss.import_folder(self.base)['rejected']),1);self.assertEqual(ss.library(),[])
    def test_rank_and_beat(self):
        self.fixture();self.fixture('other.wav',freq=220);ss.import_folder(self.base)
        clip={'viral_style':'funny','impact_output':5,'story_pattern':'conversation_comedy'};p=ss.plan(clip,16,{'youtube','instagram'});q=ss.plan(clip,16,{'youtube','instagram'},previous=[p['music']['id']]);self.assertNotEqual(p['music']['id'],q['music']['id']);self.assertAlmostEqual(p['beat_aligned_event'],5,places=2)
    def test_real_mix_and_copy_video(self):
        self.fixture();self.fixture('impact.wav','sfx');ss.import_folder(self.base)
        master=self.base/'master.mp4';dest=self.base/'mix.mp4';old=self.base/'old.mp4';remix=self.base/'remix.mp4'
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=size=1080x1920:rate=30','-f','lavfi','-i','sine=f=330:r=48000','-t','16','-c:v','libx264','-preset','ultrafast','-threads','2','-c:a','aac',str(master)],check=True,timeout=90)
        clip={'viral_style':'funny','impact_output':5,'story_pattern':'conversation_comedy'};p=ss.plan(clip,16,{'youtube','instagram'});self.assertIsNotNone(p['sfx']);
        t=time.monotonic();decorate(master,old,[],clip,'off',False,True);baseline=time.monotonic()-t
        t=time.monotonic();decorate(master,dest,[],{**clip,'audio_timeline':p},'off',False,True);new=time.monotonic()-t
        t=time.monotonic();decorate(master,remix,[],{**clip,'audio_timeline':p},'off',False,True,video_base=dest);elapsed=time.monotonic()-t
        def video_hash(path):return subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-map','0:v:0','-c','copy','-f','hash','-']).strip()
        self.assertEqual(video_hash(master),video_hash(dest));self.assertEqual(video_hash(dest),video_hash(remix));validate_export(remix,[],'off');self.assertLess(ss.measure_mix(remix)['true_peak_dbtp'],0);print(f'AUDIO BENCHMARK baseline={baseline:.3f}s director={new:.3f}s remix={elapsed:.3f}s',flush=True)
    def test_reference_local(self):
        p=self.base/'ref.mp4';subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=size=160x90:rate=10','-f','lavfi','-i','sine=f=440','-t','3','-c:v','libx264','-c:a','aac',str(p)],check=True)
        with self.assertRaises(ValueError):ss.reference(p)
        r=ss.reference(p,True);self.assertIn('mixed audio',r['limitations']);self.assertEqual(r,ss.reference(p,True));self.assertEqual(ss.references()[0]['id'],r['id'])
if __name__=='__main__':unittest.main()
