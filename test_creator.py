import tempfile, unittest, json, subprocess, shutil, sys, types
from pathlib import Path
from unittest.mock import patch, Mock
import shorts, publisher
class Creator(unittest.TestCase):
    def test_editorial(self):
        c=shorts.editorial({'title':'T'*150,'hook':'  Wait   what? ','hashtags':['#Funny','#Funny','bad tag','']})
        self.assertEqual(len(c['title']),90);self.assertEqual(c['hook'],'Wait what?');self.assertEqual(c['hashtags'],['#Funny','#badtag'])
    @unittest.skipUnless(shutil.which('ffmpeg'),'ffmpeg required')
    def test_render_hook(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t); src=p/'src.mp4'; dst=p/'short.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=320x180:r=10','-f','lavfi','-i','sine=frequency=440','-t','1','-c:v','libx264','-c:a','aac',str(src)],check=True)
            shorts.render(src,dst,[dict(start=0,end=1,text='Actual dialogue')],dict(start=0,end=1,hook='Wait, what?'),'fit',True,True)
            publisher.inspect_video(dst)
            self.assertIn('Actual dialogue',dst.with_suffix('.srt').read_text());self.assertNotIn('Wait, what?',dst.with_suffix('.srt').read_text())
            with self.assertRaises(ValueError):publisher.inspect_video(src)
    def test_legacy_public_upload(self):
        # Mock the Google API; no network or credentials.
        with tempfile.TemporaryDirectory() as t, patch.object(publisher,'CONFIG',Path(t)), patch.object(publisher,'inspect_video'),patch.object(publisher,'service') as service,patch.object(publisher,'channel',return_value={'id':'channel','title':'Test'}),patch.dict(sys.modules,{'googleapiclient':types.ModuleType('googleapiclient'),'googleapiclient.http':types.SimpleNamespace(MediaFileUpload=Mock())}):
            p=Path(t)/'short.mp4';p.touch(); api=service.return_value; request=api.videos.return_value.insert.return_value; request.next_chunk.return_value=(None,{'id':'video'})
            data=dict(title='Test',description='Description',approved=True,made_for_kids=False,channel_id='channel')
            with self.assertRaises(ValueError):publisher.upload(p,{**data,'approved':False})
            with self.assertRaises(ValueError):publisher.upload(p,{**data,'channel_id':'wrong'})
            self.assertEqual(publisher.upload(p,data)['id'],'video'); self.assertEqual(api.videos.return_value.insert.call_args.kwargs['body']['status']['privacyStatus'],'public')
            publisher.upload(p,data); self.assertEqual(api.videos.return_value.insert.call_count,1)
if __name__=='__main__':unittest.main()
