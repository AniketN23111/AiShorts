import tempfile, unittest, types
from pathlib import Path
from unittest.mock import patch, Mock
import instagram_publisher as ig, publisher, app, live

class InstagramTests(unittest.TestCase):
    def setUp(self):
        self.clip=dict(title='Great play #Shorts',description='A surprising result',hashtags=['#Gaming','#Shorts'],comment_prompt='Did you expect that?',score=95,start=1,end=26,source_identity='youtube:abc')
        self.args=types.SimpleNamespace(authorized=True,score=85,instagram_account='123',daily_limit=6)
    def test_caption(self):
        c=ig.caption_for(self.clip);self.assertIn('#Gaming',c);self.assertIn('#Reels',c);self.assertNotIn('#Shorts',c);self.assertIn('Did you expect',c)
        self.assertLessEqual(len(ig.caption_for({**self.clip,'description':'a'*3000})),2200)
    def test_confirmation(self):
        d=dict(url='https://youtu.be/example',authorized=True,edit_style='gaming',auto_instagram=True,instagram_account='123',instagram_confirm=True)
        app.validate(d)
        for key,val in [('instagram_confirm',False),('instagram_account',''),('authorized',False),('edit_style','clean')]:
            with self.assertRaises(ValueError):app.validate({**d,key:val})
    def test_publish_duplicate_uncertain(self):
        with tempfile.TemporaryDirectory() as td,patch.object(publisher,'CONFIG',Path(td)),patch.object(ig,'load_config',return_value={'version':'v26.0','account_id':'123','token':'secret'}),patch.object(ig,'account',return_value={'id':'123','username':'creator'}),patch.object(ig,'quality',return_value={'duration':25}),patch.object(ig,'graph') as graph,patch.object(ig,'transfer') as transfer:
            p=Path(td)/'short.mp4';p.write_bytes(b'video')
            graph.side_effect=[{'id':'456','uri':'https://rupload.facebook.com/ig-api-upload/v26.0/456'},{'status_code':'FINISHED'},{'id':'789'},{'permalink':'https://www.instagram.com/reel/example/'}]
            result=ig.publish(p,self.clip,self.args);self.assertEqual(result['state'],'uploaded');self.assertEqual(result['id'],'789');self.assertEqual(graph.call_args_list[0].args[3]['media_type'],'REELS');self.assertEqual(transfer.call_count,1)
            self.assertEqual(ig.publish(p,self.clip,self.args)['state'],'duplicate');self.assertEqual(graph.call_count,4)
            p.write_bytes(b'new');new={**self.clip,'start':40,'end':65}
            graph.side_effect=[{'id':'999'},{'status_code':'FINISHED'},ig.InstagramError('connection lost')]
            with self.assertRaises(ig.InstagramError):ig.publish(p,new,self.args)
            self.assertEqual(ig.publish(p,new,self.args)['state'],'uncertain');self.assertEqual(graph.call_count,7)
    def test_transfer_endpoint_blocked(self):
        with patch.object(ig.requests,'post') as post:
            with self.assertRaises(ig.InstagramError):ig.transfer({'token':'x'},'12','https://example.com/ig-api-upload/12',Path('none'))
            post.assert_not_called()
    def test_instagram_only_ranked(self):
        with tempfile.TemporaryDirectory() as td:
            args=types.SimpleNamespace(viral_preset='gaming',viral_full_scan=True,count=1,instagram_account='123',output=Path(td));live.configure_full_scan(args,'replay')
            clips=[{'score':85,'file':'a.mp4'},{'score':96,'file':'b.mp4'}]
            with patch.object(live,'publish_ready') as pub:
                live.publish_ranked(args,Path(td),clips,lambda *a,**k:None)
                self.assertEqual(pub.call_args.args[2]['score'],96);self.assertEqual(pub.call_count,1)
    def test_dual_platform_failure_independent(self):
        with tempfile.TemporaryDirectory() as td,patch('auto_publish.publish',side_effect=RuntimeError('YouTube unavailable')),patch.object(ig,'publish',return_value={'state':'uploaded','id':'789'}):
            args=types.SimpleNamespace(output=Path(td),publish_channel='UCtest',instagram_account='123');c={}
            live.publish_ready(args,Path(td)/'short.mp4',c);self.assertEqual(c['publishing']['state'],'failed');self.assertEqual(c['instagram_publishing']['state'],'uploaded')
if __name__=='__main__': unittest.main()
