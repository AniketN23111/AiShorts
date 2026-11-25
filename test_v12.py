import json, tempfile, types, unittest
from pathlib import Path
from unittest.mock import patch
import app, editorial_review, viral, analytics_feedback, publisher

class V12(unittest.TestCase):
    def review(self):
        return {'accept':True,'metadata_grounded':True,'reason':'Independent assessment','opening':'An actual question','payoff':'The answer resolves it','evidence':'Recorded speech','ratings':{k:90 for k in viral.WEIGHTS},'rating_reasons':{k:'Observed in the candidate' for k in viral.WEIGHTS}}
    def test_review_gate_and_score(self):
        r=self.review();good=editorial_review.validate(r,85,visual_available=False,speech_available=True)
        self.assertEqual(good['score'],90);self.assertFalse(good['editorial_review']['visual_evidence'])
        for change in ({'metadata_grounded':False},{'accept':False},{'ratings':{k:60 for k in viral.WEIGHTS}},{'rating_reasons':{}},{'opening':''}):
            with self.assertRaises(ValueError):editorial_review.validate({**r,**change},85,visual_available=True,speech_available=True)
    def test_actual_clip_clock_excludes_outside_words(self):
        segments=[{'start':0,'end':20,'text':'before useful after','words':[{'start':1,'end':2,'word':'before'},{'start':6,'end':7,'word':'useful'},{'start':19,'end':20,'word':'after'}]}]
        args=types.SimpleNamespace(model='local',score=85)
        with patch.object(viral,'visual_context',return_value=''),patch.object(viral,'model_request',return_value=json.dumps(self.review())) as model:
            editorial_review.assess(args,Path('test.mp4'),segments,{'start':5,'end':18,'title':'question'})
            prompt=model.call_args.args[1]; self.assertIn('useful',prompt); self.assertNotIn('"text": "before',prompt); self.assertNotIn('useful after',prompt)
    def test_chat_file_and_time_filter(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'chat.jsonl';p.write_text('\n'.join(json.dumps(r) for r in [{'time':1,'message':'old'},{'time':12,'message':'funny'},{'time':25,'message':'later'}]))
            self.assertEqual(editorial_review.chat_path(p),p);self.assertEqual(viral.chat_context(10,20,p),[{'t':2.0,'message':'funny'}])
            with self.assertRaises(ValueError):editorial_review.chat_path(Path(d)/'missing.jsonl')
    def test_library_real_files_and_receipts(self):
        with tempfile.TemporaryDirectory() as d,patch.object(app,'OUTPUT',Path(d)):
            job='a'*32;folder=Path(d)/job/'20261125_000001_000001';folder.mkdir(parents=True)
            (folder/'short_01.mp4').write_bytes(b'test');(folder/'short_01.instagram.json').write_text('{"state":"uploaded","id":"123"}')
            (folder/'clips.json').write_text(json.dumps([{'file':'short_01.mp4','score':90},{'file':'short_02.mp4','score':99},{'file':'../secret'}]))
            self.assertEqual(app.library()[0]['count'],1);self.assertEqual(app.read_clips(job)[0]['instagram_publishing']['id'],'123')
            with self.assertRaises(ValueError):app.read_clips('../')
    def test_feedback_optional_attributes(self):
        header='video_id,duration,views,retention,average_view_duration,likes,comments,shares,subscribers_gained,style,caption_style,hook_band,cta_present,topic\n'
        rows='\n'.join(f'abcdefghij{i},25,100,90,22.5,2,1,2,1,gaming,off,90+,false,gaming' for i in range(3))
        with tempfile.TemporaryDirectory() as d,patch.object(publisher,'CONFIG',Path(d)):
            result=analytics_feedback.import_csv('UC'+'x'*22,header+rows)
            self.assertIn('topic gaming',result['summary']);self.assertIn('10.00',result['summary']);self.assertIs(result['sample'][0]['cta_present'],False)
    def test_review_rejects_before_render(self):
        args=types.SimpleNamespace(viral_review=True,edit_style='gaming')
        with patch.object(editorial_review,'assess',side_effect=ValueError('Rejected')):
            with self.assertRaisesRegex(ValueError,'Rejected'):viral.render(args,Path('source'),Path('output'),[],{'viral_style':'gaming'})

if __name__=='__main__': unittest.main()
