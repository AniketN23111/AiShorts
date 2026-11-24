"""Local Google OAuth and explicit uploads (legacy helper; Gaming Pro uses auto_publish.py). No secrets in the browser."""
import argparse, json, os, subprocess, threading
from pathlib import Path
ROOT=Path(__file__).resolve().parent
CONFIG=Path.home()/'.config'/'m4-shorts-studio'
TOKEN=CONFIG/'token.json'
SCOPES=['https://www.googleapis.com/auth/youtube.upload','https://www.googleapis.com/auth/youtube.readonly']
LOCK=threading.Lock()
def secure_write(path, data):
    CONFIG.mkdir(mode=0o700,parents=True,exist_ok=True)
    path.parent.mkdir(exist_ok=True,parents=True)
    tmp=path.with_suffix('.tmp')
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as f: f.write(data)
    os.chmod(tmp,0o600); os.replace(tmp,path)
def service():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    if not TOKEN.is_file(): raise ValueError('Connect your channel in Terminal: python publisher.py connect')
    creds=Credentials.from_authorized_user_file(str(TOKEN))
    if creds.expired and creds.refresh_token:
        creds.refresh(Request()); secure_write(TOKEN,creds.to_json())
    if not creds.valid: raise ValueError('Reconnect your YouTube account in Terminal.')
    return build('youtube','v3',credentials=creds,cache_discovery=False)
def channel(api):
    items=api.channels().list(part='snippet',mine=True).execute().get('items',[])
    if len(items)!=1: raise ValueError('Select a single YouTube channel when authorizing.')
    return {'id':items[0]['id'],'title':items[0]['snippet']['title']}
def connect(analytics=False):
    from google_auth_oauthlib.flow import InstalledAppFlow
    client=CONFIG/'client_secrets.json'
    if not client.is_file(): raise ValueError(f'Put your Desktop OAuth JSON at {client}')
    if 'installed' not in json.loads(client.read_text()): raise ValueError('Use a Desktop OAuth client JSON, not a Web client.')
    creds=InstalledAppFlow.from_client_secrets_file(str(client),SCOPES+(['https://www.googleapis.com/auth/yt-analytics.readonly'] if analytics else [])).run_local_server(host='localhost',port=0,access_type='offline',prompt='consent')
    secure_write(TOKEN,creds.to_json())
    info=channel(service()); print('Connected:',info['title'],info['id'])
def inspect_video(path):
    raw=subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height:format=duration','-of','json',str(path)])
    info=json.loads(raw); v=info['streams'][0]; duration=float(info['format']['duration'])
    if not (0<duration<=180 and 0<v['width']<=v['height']): raise ValueError('Upload requires a square or vertical video of at most 3 minutes. Choose 9:16 when clipping.')
def upload(path,data):
    from googleapiclient.http import MediaFileUpload
    if data.get('approved') is not True or type(data.get('made_for_kids')) is not bool: raise ValueError('Confirm content rights, review and audience before uploading.')
    title=str(data.get('title','')).strip(); desc=str(data.get('description','')).strip()
    if not 1<=len(title)<=100 or len(desc.encode('utf-8'))>5000 or any(x in title+desc for x in '<>'): raise ValueError('Invalid title or description (100 characters / 5000 UTF-8 bytes; no angle brackets).')
    inspect_video(path)
    with LOCK:
        receipt=path.with_suffix('.upload.json'); pending=path.with_suffix('.upload.pending')
        if receipt.exists(): return json.loads(receipt.read_text())
        if pending.exists(): raise ValueError('Previous upload outcome uncertain. Check YouTube Studio before retrying; remove the .upload.pending marker only if no video was created.')
        api=service(); actual=channel(api)
        if actual['id']!=data.get('channel_id'): raise ValueError('Channel changed; refresh channel identity and review again.')
        request=api.videos().insert(part='snippet,status',body={'snippet':{'title':title,'description':desc,'categoryId':'22'},'status':{'privacyStatus':'public','selfDeclaredMadeForKids':data['made_for_kids']}},media_body=MediaFileUpload(str(path),mimetype='video/mp4',chunksize=8*1024*1024,resumable=True))
        pending.touch(exist_ok=False)
        response=None
        while response is None: _,response=request.next_chunk(num_retries=3)
        result={'id':response['id'],'channel':actual,'visibility':'public','url':'https://studio.youtube.com/video/'+response['id']+'/edit'}
        secure_write(receipt,json.dumps(result)); pending.unlink(); return result
if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('action',choices=['connect','connect-analytics','status','disconnect']); a=p.parse_args()
    if a.action in ('connect','connect-analytics'): connect(a.action=='connect-analytics')
    elif a.action=='status': print(json.dumps(channel(service()),ensure_ascii=False))
    else: TOKEN.unlink(missing_ok=True); print('Local token removed. Revoke access in your Google Account if desired.')
