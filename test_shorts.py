import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import shorts
from youtube_source import validate_url, eta

class Tests(unittest.TestCase):
    def test_urls(self):
        for url in ['https://www.youtube.com/watch?v=123','https://youtu.be/123','https://www.youtube.com/live/123']:
            self.assertEqual(validate_url(url),url)
        for url in ['https://evil.com','https://youtube.com.evil.com/watch?v=x','https://www.youtube.com/playlist?list=x']:
            with self.assertRaises(ValueError): validate_url(url)
    def test_eta(self):
        self.assertEqual(eta(63),'00:01:03')
        self.assertEqual(eta(None),'estimating')
    def test_select(self):
        seg=[{'start':i*10,'end':i*10+10,'text':'test'} for i in range(9)]
        result=[{'first':0,'last':2,'title':'good','score':90},{'first':1,'last':3,'title':'overlap','score':80},{'first':4,'last':6,'title':'second','score':85},{'first':7,'last':7,'title':'too short','score':99}]
        with patch('shorts.ask_ai',return_value=result):
            got=shorts.select(seg,'mock',6,90)
        self.assertEqual([c['title'] for c in got],['good','second'])
    def test_srt(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'test.srt'
            shorts.write_srt(p,[{'start':9,'end':12,'text':'hello'}],10,20)
            self.assertIn('00:00:00,000 --> 00:00:02,000',p.read_text())

if __name__=='__main__': unittest.main()
