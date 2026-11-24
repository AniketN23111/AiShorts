import tempfile, unittest, types, sys
from unittest.mock import patch, MagicMock
from pathlib import Path
import smart_replay as s
import live

class SmartReplay(unittest.TestCase):
    def test_overlap_and_tail(self):
        self.assertEqual(list(s.windows(250,120)),[(0,0,120),(55,120,240),(175,240,250)])
    def test_commands_only_request_ranges(self):
        for audio in (True,False):
            cmd=s.section_command('https://youtu.be/example',Path('/tmp/clip'),60,95,audio)
            self.assertEqual(cmd[cmd.index('--download-sections')+1],'*60.000-95.000')
            self.assertEqual(cmd[cmd.index('-f')+1]=='ba',audio)
            self.assertNotIn('--allow-unplayable-formats',cmd)
            self.assertEqual('--force-keyframes-at-cuts' in cmd,not audio)
        with self.assertRaises(ValueError): s.section_command('https://youtu.be/example',Path('/tmp/clip'),0,300,True)
    def test_probe(self):
        pkg=types.ModuleType('yt_dlp');pkg.YoutubeDL=MagicMock()
        ex=pkg.YoutubeDL.return_value.__enter__.return_value.extract_info
        with patch.dict(sys.modules,{'yt_dlp':pkg}):
            ex.return_value={'live_status':'is_live'};self.assertIsNone(s.probe('https://youtu.be/example'))
            ex.return_value={'live_status':'was_live','duration':100,'title':'Replay'};self.assertEqual(s.probe('https://youtu.be/example'),('Replay',100))
            ex.return_value={'has_drm':True,'duration':100};self.assertRaises(ValueError,s.probe,'https://youtu.be/example')
    def test_incremental_export_and_no_video_for_weak_window(self):
        with tempfile.TemporaryDirectory() as t:
            job=Path(t);out=job/'out';out.mkdir(); calls=[]; updates=[]
            args=types.SimpleNamespace(url='https://youtu.be/example',mode='auto',minutes=0,segment=120,whisper='w',language='',model='m',score=85,count=1,edit_style='clean',layout='fit',software=True,captions=True,keep_source=False)
            def fetch(args,job,folder,start,end,audio):
                calls.append((start,end,audio));folder.mkdir();p=folder/'section.mkv';p.touch();return p
            def render(src,dest,*args,**kwargs):dest.touch();dest.with_suffix('.srt').touch()
            seg=[{'start':55,'end':85,'text':'interesting actual dialogue'}]
            c={'start':55,'end':85,'score':95,'title':'Hook'}
            with patch.object(s,'fetch',side_effect=fetch),patch.object(s,'duration',side_effect=[120,185,30]),patch.object(s,'transcribe',return_value=seg),patch.object(s,'render',side_effect=render):
                s.run_replay(args,job,out,lambda **kw:updates.append(kw),lambda *a,**k:None,live.atomic,MagicMock(side_effect=[[],[c]]),('Replay',500))
            self.assertEqual(calls,[(0,120,True),(55,240,True),(110,140,False)])
            self.assertTrue((out/'short_01.mp4').exists());self.assertIn('audio_first',(out/'clips.json').read_text())
            self.assertEqual(updates[-1]['stage'],'done')
    def test_stop_before_download(self):
        with tempfile.TemporaryDirectory() as t:
            job=Path(t);(job/'stop').touch();args=types.SimpleNamespace(url='https://youtu.be/example')
            with patch.object(s.subprocess,'Popen') as p:
                self.assertIsNone(s.fetch(args,job,job/'audio',0,60,True));p.assert_not_called()
