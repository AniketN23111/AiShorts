import json, tempfile, unittest, types, sys, subprocess, shutil
from pathlib import Path
from unittest.mock import patch, Mock, MagicMock
import gaming, auto_publish, app, publisher, smart_replay

class GamingTests(unittest.TestCase):
    def test_region(self):
        self.assertEqual(auto_publish.parse_region('0.7,0.1,0.2,0.3'),(.7,.1,.2,.3))
        for bad in ['0.9,0.1,0.2,0.3','nan,0,0.2,0.3','0,0,0,0']:
            with self.assertRaises(ValueError): auto_publish.parse_region(bad)
    def test_preview_range(self):
        cmd=smart_replay.section_command('https://youtu.be/example',Path('/tmp'),0,120,'preview')
        self.assertIn('height<=360',cmd[cmd.index('-f')+1]); self.assertIn('--download-sections',cmd)
    def test_public_requires_confirmation(self):
        data=dict(url='https://youtu.be/example',authorized=True,edit_style='gaming',auto_public=True,channel_id='UCtest',audience='no',public_confirm=True)
        app.validate(data)
        for k,v in [('authorized',False),('channel_id',''),('audience',''),('public_confirm',False),('edit_style','clean')]:
            with self.assertRaises(ValueError): app.validate({**data,k:v})
    def test_selection_visual_and_metadata(self):
        raw={'clips':[dict(start=2,end=22,title='A'*100,description='Actual conversation',hashtags=['#Valorant'],reason='payoff',score=92,impact=12)]}
        frames=[dict(t=i,motion=.1,face=False,dark=False) for i in range(30)]
        response=MagicMock();response.__enter__.return_value.read.return_value=json.dumps({'response':json.dumps(raw)})
        with patch.object(gaming,'sample',return_value=(frames,None)),patch.object(gaming,'audio_features',return_value=[.12]*30),patch.object(gaming.urllib.request,'urlopen',return_value=response):
            result=gaming.select([], 'model',30,0,0,[],85,1,Path('unused'))
            self.assertEqual(len(result),1); self.assertLessEqual(len(result[0]['title']),100);self.assertIn('#Shorts',result[0]['title']);self.assertEqual(result[0]['hook'],'')
    def test_missing_or_dominant_facecam_is_skipped(self):
        clip=dict(start=0,end=16,impact=-1)
        frames=[dict(t=i,motion=.1,face=False,dark=False) for i in range(16)]
        with patch.object(gaming,'sample',return_value=(frames,None)):
            with self.assertRaises(gaming.SplitLayoutUnavailable): gaming.render(Path('unused'),Path('unused'),[],clip,True)
        cam={'region':(.65,.05,.3,.4),'track':[(i,.7,.1,.1,.2) for i in range(16)]}
        frames[0]['dominant_face']=True
        with patch.object(gaming,'sample',return_value=(frames,cam)):
            with self.assertRaises(gaming.SplitLayoutUnavailable): gaming.render(Path('unused'),Path('unused'),[],clip,True)
    def test_stale_facecam_is_skipped(self):
        frames=[dict(t=i,motion=.1,face=True,dark=False) for i in range(16)]
        cam={'region':(.65,.05,.3,.4),'track':[(i,.7,.1,.1,.2) for i in range(5)]}
        with patch.object(gaming,'sample',return_value=(frames,cam)):
            with self.assertRaisesRegex(gaming.SplitLayoutUnavailable,'throughout'):
                gaming.render(Path('unused'),Path('unused'),[],dict(start=0,end=16,impact=-1),True)
    @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg needed')
    def test_render_split_order_and_pixels(self):
        import cv2
        with tempfile.TemporaryDirectory() as t:
            p=Path(t); source=p/'input.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=320x180:r=15,drawbox=x=208:y=10:w=96:h=72:color=red:t=fill','-f','lavfi','-i','sine=frequency=440','-t','16','-c:v','libx264','-c:a','aac',str(source)],check=True)
            region=(.65,10/180,.3,.4); dest=p/'split.mp4'
            frames=[dict(t=i/2,motion=.1,face=True,dark=False) for i in range(32)]
            cam={'region':region,'track':[(i/2,.75,.16,.07,.13) for i in range(32)]}
            with patch.object(gaming,'sample',return_value=(frames,cam)):
                meta=gaming.render(source,dest,[dict(start=0,end=16,text='Speech')],dict(start=0,end=16,impact=6),True,region)
            self.assertTrue(meta['facecam']); self.assertEqual(meta['layout'],'gameplay_top_streamer_bottom'); self.assertFalse(dest.with_suffix('.srt').exists());self.assertGreater(auto_publish.quality(dest)['duration'],15)
            cap=cv2.VideoCapture(str(dest)); cap.set(cv2.CAP_PROP_POS_MSEC,6500); ok,frame=cap.read();cap.release()
            self.assertTrue(ok);self.assertEqual(frame.shape[:2],(1920,1080))
            top=frame[480,540];bottom=frame[1440,540]
            self.assertGreater(int(top[0]),int(top[2])+100); self.assertGreater(int(bottom[2]),int(bottom[0])+100)
            # The webcam area is removed from the gameplay panel, not duplicated.
            self.assertLess(int(frame[450,850,2]),100)
    def test_public_and_duplicate(self):
        with tempfile.TemporaryDirectory() as t,patch.object(publisher,'CONFIG',Path(t)),patch.object(publisher,'service') as service,patch.object(publisher,'channel',return_value={'id':'UCtest','title':'Test'}),patch.object(auto_publish,'quality',return_value={'duration':25}),patch.dict(sys.modules,{'googleapiclient':types.ModuleType('googleapiclient'),'googleapiclient.http':types.SimpleNamespace(MediaFileUpload=Mock())}):
            p=Path(t)/'short.mp4'; p.write_bytes(b'test'); api=service.return_value;req=api.videos.return_value.insert.return_value;req.next_chunk.return_value=(None,{'id':'vid','status':{'privacyStatus':'public'}})
            args=types.SimpleNamespace(authorized=True,made_for_kids='no',score=85,publish_channel='UCtest',daily_limit=6)
            clip=dict(title='Great play #Shorts',score=95,start=1,end=26,source_identity='youtube:abc',tags=['Gaming'])
            self.assertEqual(auto_publish.publish(p,clip,args)['visibility'],'public');self.assertEqual(api.videos.return_value.insert.call_args.kwargs['body']['status']['privacyStatus'],'public')
            self.assertEqual(auto_publish.publish(p,clip,args)['state'],'duplicate'); self.assertEqual(api.videos.return_value.insert.call_count,1)
            p2=Path(t)/'different.mp4';p2.write_bytes(b'different');req.next_chunk.side_effect=OSError('lost response')
            new={**clip,'start':50,'end':75,'title':'Another highlight #Shorts'}
            with self.assertRaises(RuntimeError):auto_publish.publish(p2,new,args)
            self.assertEqual(auto_publish.publish(p2,new,args)['state'],'uncertain');self.assertEqual(api.videos.return_value.insert.call_count,2)
if __name__=='__main__':unittest.main()
