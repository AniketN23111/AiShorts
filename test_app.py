import json, tempfile, threading, time, unittest, urllib.request, urllib.error
from pathlib import Path
from unittest.mock import Mock, patch
import app

class UI(unittest.TestCase):
    def test_validation(self):
        data={'url':'https://youtu.be/123','authorized':True}
        self.assertEqual(app.validate(data)[1:3],(6,0))
        for d in ({**data,'authorized':False},{**data,'count':101},{**data,'url':'https://evil.com'}):
            with self.assertRaises(ValueError):app.validate(d)
    def test_status(self):
        with tempfile.TemporaryDirectory() as t, patch.object(app,'OUTPUT',Path(t)):
            job={'id':'a'*32,'proc':Mock(),'started':time.time(),'stopped':False}
            folder=Path(t)/job['id'];folder.mkdir()
            (folder/'run.log').write_text('test')
            (folder/'status.json').write_text(json.dumps({'stage':'analyze','progress':40,'eta':'00:00:20'}))
            job['proc'].poll.return_value=None
            s=app.status(job);self.assertEqual((s['stage'],s['progress'],s['eta']),('analyze',40,'00:00:20'))
            child=folder/'20261124_123456_123456';child.mkdir();(child/'short_01.mp4').write_bytes(b'fake')
            (child/'clips.json').write_text(json.dumps([{'file':'short_01.mp4','title':'Test','score':90,'start':0,'end':30}]))
            self.assertEqual(len(app.status(job)['clips']),1)
            job['proc'].poll.return_value=0
            s=app.status(job);self.assertEqual(s['state'],'done');self.assertTrue(s['clips'][0]['video'].endswith('/short_01.mp4'))
    def test_http(self):
        server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        host=f'127.0.0.1:{server.server_port}';base='http://'+host
        th=threading.Thread(target=server.serve_forever,daemon=True);th.start()
        try:
            with patch.object(app,'HOST',host), patch.object(app,'ACTIVE',None), tempfile.TemporaryDirectory() as t, patch.object(app,'OUTPUT',Path(t)):
                self.assertIn(b'AI Shorts Studio',urllib.request.urlopen(base).read())
                self.assertIsNone(json.load(urllib.request.urlopen(base+'/api/status'))['id'])
                req=urllib.request.Request(base+'/api/start',data=b'{}',headers={'Origin':base,'X-Local-UI':'1','Content-Type':'application/json'})
                with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(req)
                self.assertEqual(e.exception.code,400)
                rel='a'*32+'/20261124_123456_123456/short_01.mp4';p=Path(t)/rel;p.parent.mkdir(parents=True);p.write_bytes(b'0123456789')
                req=urllib.request.Request(base+'/media/'+rel,headers={'Range':'bytes=2-5'})
                with urllib.request.urlopen(req) as r:self.assertEqual((r.status,r.read()),(206,b'2345'))
        finally:server.shutdown();server.server_close();th.join()

if __name__=='__main__':unittest.main()
