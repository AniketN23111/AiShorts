import json, tempfile, unittest, subprocess, shutil, sys, types
from pathlib import Path
from unittest.mock import patch, MagicMock
import app, live, creator_edit, source_fallback
from shorts import duration

class V7(unittest.TestCase):
    def test_plan_preserves_spoken_ranges(self):
        seg=[dict(start=0,end=5,text='setup'),dict(start=8,end=13,text='payoff'),dict(start=14,end=20,text='reaction')]
        pieces,holes=creator_edit.edit_plan(seg,0,20)
        self.assertEqual(len(holes),1)
        self.assertTrue(all(not any(min(b,s['end'])>max(a,s['start']) for s in seg) for a,b in holes))
        mapped=creator_edit.remap(seg,pieces)
        self.assertEqual([s['text'] for s in mapped],['setup','payoff','reaction'])
        self.assertLess(mapped[-1]['end'],20)
    def test_local_ui_validation(self):
        with tempfile.TemporaryDirectory() as t:
            f=Path(t)/'video.mp4'; f.touch()
            data={'source_type':'local','local_path':str(f),'authorized':True,'edit_style':'dynamic'}
            self.assertEqual(app.validate(data)[0],str(f))
            with self.assertRaises(ValueError):app.validate({**data,'local_path':str(f)+'.missing'})
            with self.assertRaises(ValueError):app.validate({**data,'authorized':False})
    def test_hls_playlist_with_fragment_metadata(self):
        row=dict(url='https://example.com/live/playlist.m3u8',protocol='m3u8_native',vcodec='avc1',acodec='aac',fragments=[{'url':'chunk'}])
        self.assertEqual(live.select_source({'is_live':True,'formats':[row]})[1],[row])
        with self.assertRaises(RuntimeError):live.select_source({'is_live':True,'formats':[{**row,'url':'https://example.com/fragment.mp4'}]})
        with self.assertRaises(RuntimeError):live.select_source({'is_live':True,'formats':[{**row,'has_drm':True}]})
    def test_audio_protects_reactions(self):
        seg=[dict(start=0,end=5,text='A'),dict(start=9,end=20,text='B')]
        self.assertEqual(creator_edit.edit_plan(seg,0,20,[])[1],[])
        self.assertTrue(creator_edit.edit_plan(seg,0,20,[(6,8)])[1])
    def test_native_replay_command(self):
        cmd=source_fallback.native_command('https://youtu.be/example',Path('/tmp/video'))
        self.assertIn('--ignore-config',cmd)
        self.assertIn('--abort-on-unavailable-fragments',cmd)
        self.assertIn('!is_live & !is_upcoming',cmd)
        self.assertNotIn('--allow-unplayable-formats',cmd)
    def test_native_fallback_only_accessible_replay(self):
        row=dict(format_id='dash',url='https://example.com/manifest',protocol='http_dash_segments',height=720,vcodec='avc1',acodec='aac',fragments=[{'url':'x'}])
        ydl=MagicMock(); ex=ydl.return_value.__enter__.return_value.extract_info
        pkg=types.ModuleType('yt_dlp');pkg.YoutubeDL=ydl
        utils=types.ModuleType('yt_dlp.utils');utils.DownloadError=type('DownloadError',(Exception,),{})
        with patch.dict(sys.modules,{'yt_dlp':pkg,'yt_dlp.utils':utils}):
            ex.return_value={**row,'formats':[row],'live_status':'was_live'}
            with self.assertRaises(source_fallback.NativeReplayRequired):live.resolve_source('https://youtu.be/example')
            ex.return_value={**row,'formats':[row],'live_status':'is_live'}
            with self.assertRaises(RuntimeError) as err:live.resolve_source('https://youtu.be/example')
            self.assertNotIsInstance(err.exception,source_fallback.NativeReplayRequired)
            ex.side_effect=utils.DownloadError('members-only')
            with self.assertRaises(RuntimeError) as err:live.resolve_source('https://youtu.be/example')
            self.assertNotIsInstance(err.exception,source_fallback.NativeReplayRequired)
    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'ffmpeg required')
    def test_dynamic_real_render(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t); src=p/'src.mp4'; dst=p/'short.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=320x180:r=15','-f','lavfi','-i','sine=frequency=440','-af',"volume=0:enable='between(t,2,4)'",'-t','6','-c:v','libx264','-c:a','aac',str(src)],check=True)
            seg=[dict(start=0,end=2,text='Setup'),dict(start=4,end=6,text='Punchline')]
            meta=creator_edit.render_dynamic(src,dst,seg,dict(start=0,end=6,hook='Wait for it!'),'fit',True,True)
            self.assertEqual(meta['jump_cuts'],1)
            self.assertLess(duration(dst),6)
            self.assertIn('Punchline',dst.with_suffix('.srt').read_text())
            self.assertNotIn('Wait for it!',dst.with_suffix('.srt').read_text())
            import publisher; publisher.inspect_video(dst)
    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'ffmpeg required')
    def test_punch_in_export(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t); src=p/'src.mp4'; dst=p/'short.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=320x180:r=10','-f','lavfi','-i','sine=frequency=440','-t','4','-c:v','libx264','-c:a','aac',str(src)],check=True)
            with patch('creator_edit.edit_plan',return_value=([(0,2),(2,4)],[])):
                meta=creator_edit.render_dynamic(src,dst,[dict(start=0,end=4,text='Dialogue')],dict(start=0,end=4,hook='Hook'),'crop',True,False)
            self.assertEqual(meta['shot_count'],2)
            self.assertAlmostEqual(duration(dst),4,delta=.2)

if __name__=='__main__': unittest.main()
