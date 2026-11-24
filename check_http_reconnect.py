import sys, tempfile, subprocess, threading, re, socket
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
sys.path.insert(0,'.')
import live
with tempfile.TemporaryDirectory() as tmp:
 p=Path(tmp)
 subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=640x360:rate=25','-f','lavfi','-i','sine=frequency=440','-t','12','-c:v','libx264','-g','25','-c:a','aac','-movflags','+faststart',str(p/'input.mp4')],check=True)
 data=(p/'input.mp4').read_bytes(); hits=[]
 class H(BaseHTTPRequestHandler):
  def log_message(self,*args): pass
  def do_GET(self):
   start=int(re.match(r'bytes=(\d+)-',self.headers.get('Range','bytes=0-')).group(1)); hits.append(start)
   self.send_response(206 if self.headers.get('Range') else 200)
   self.send_header('Content-Length',str(len(data)-start)); self.send_header('Accept-Ranges','bytes'); self.send_header('Content-Type','video/mp4')
   if self.headers.get('Range'): self.send_header('Content-Range',f'bytes {start}-{len(data)-1}/{len(data)}')
   self.end_headers()
   if len(hits)==1:
    self.wfile.write(data[start:len(data)//3]); self.wfile.flush(); self.connection.shutdown(socket.SHUT_RDWR); self.connection.close()
   else:
    try: self.wfile.write(data[start:])
    except (BrokenPipeError,ConnectionResetError): pass
 server=ThreadingHTTPServer(('127.0.0.1',0),H); t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
 try:
  cmd=live.capture_command([{'url':f'http://127.0.0.1:{server.server_port}/input.mp4'}],3,0)
  result=subprocess.run(cmd,cwd=p,capture_output=True,text=True,timeout=35)
  print('return:',result.returncode,'requests:',hits,'segments:',len(live.closed_segments(p)), 'log:',result.stderr)
  assert result.returncode==0 and len(hits)>1 and len(live.closed_segments(p))==4
 finally: server.shutdown();server.server_close()
