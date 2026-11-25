"""Meta Facebook Login for Business Reels publisher; credentials never reach UI."""
import argparse, contextlib, datetime, fcntl, getpass, json, re, time
from pathlib import Path
from urllib.parse import urlsplit
import requests
import publisher
from auto_publish import digest, quality, near_duplicate

class InstagramError(RuntimeError): pass

def config_path(): return publisher.CONFIG/'instagram-token.json'

def load_config():
    try: data=json.loads(config_path().read_text())
    except (OSError, ValueError): raise InstagramError('Connect Instagram in Terminal: python instagram_publisher.py connect') from None
    if not re.fullmatch(r'\d+',str(data.get('account_id',''))) or not re.fullmatch(r'v\d+\.\d+',str(data.get('version',''))) or not data.get('token'): raise InstagramError('Invalid Instagram configuration; reconnect in Terminal.')
    return data

def response_json(response):
    try: result=response.json()
    except ValueError: raise InstagramError(f'Meta returned HTTP {response.status_code} without JSON.') from None
    if not response.ok or 'error' in result:
        err=result.get('error',{}); code=err.get('code','unknown'); sub=err.get('error_subcode','none')
        raise InstagramError(f'Meta API rejected request (HTTP {response.status_code}, code {code}, subcode {sub}). Check permissions, token expiry and account status.')
    return result

def graph(cfg,method,path,params=None):
    if not re.fullmatch(r'\d+(?:/(?:media|media_publish))?',path): raise InstagramError('Invalid Meta resource ID.')
    try:
        kwargs={'params' if method=='GET' else 'data':params or {}}
        response=requests.request(method,f"https://graph.facebook.com/{cfg['version']}/{path}",headers={'Authorization':'Bearer '+cfg['token']},timeout=(15,60),allow_redirects=False,**kwargs)
        return response_json(response)
    except requests.RequestException: raise InstagramError('Meta API connection failed or timed out.') from None

def account(cfg=None):
    cfg=cfg or load_config(); data=graph(cfg,'GET',cfg['account_id'],{'fields':'id,username'})
    if str(data.get('id'))!=cfg['account_id'] or not data.get('username'): raise InstagramError('Instagram account could not be verified.')
    return {'id':cfg['account_id'],'username':str(data['username'])}

def caption_for(clip):
    # Instagram does not use a separate video title; reuse the verified editorial metadata.
    title=re.sub(r'(?<!\w)#[\w]+','',str(clip.get('title',''))).strip()
    raw=[str(x) for x in clip.get('hashtags',[]) if isinstance(x,str)]
    tags=[]
    for tag in raw+['#Reels']:
        if re.fullmatch(r'#[\w]+',tag) and tag.casefold() not in ('#shorts','#youtubeshorts') and tag.casefold() not in [x.casefold() for x in tags]: tags.append(tag)
    desc=str(clip.get('description','')).strip(); prompt=str(clip.get('comment_prompt','')).strip()
    parts=[title,desc,prompt,('Source: '+clip['source_url']) if clip.get('source_url') else '']
    suffix=' '.join(tags[:5]); body='\n\n'.join(dict.fromkeys(x for x in parts if x))
    return body[:max(0,2200-len(suffix)-2)].rstrip()+ ('\n\n'+suffix if suffix else '')

@contextlib.contextmanager
def ledger():
    root=publisher.CONFIG; root.mkdir(mode=0o700,parents=True,exist_ok=True); file=root/'instagram-uploads.json'
    with (root/'instagram-uploads.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        records=json.loads(file.read_text()) if file.exists() else []
        def save(): publisher.secure_write(file,json.dumps(records,ensure_ascii=False,indent=2))
        yield records,save

def transfer(cfg,container,uri,path):
    u=urlsplit(uri)
    if u.scheme!='https' or u.netloc!='rupload.facebook.com' or not u.path.startswith('/ig-api-upload/') or u.path.rstrip('/').split('/')[-1]!=container: raise InstagramError('Unexpected upload endpoint; blocked for safety.')
    try:
        with path.open('rb') as f:
            r=requests.post(uri,headers={'Authorization':'OAuth '+cfg['token'],'offset':'0','file_size':str(path.stat().st_size),'Content-Type':'application/octet-stream'},data=f,timeout=(15,180),allow_redirects=False)
            if response_json(r).get('success') is not True: raise InstagramError('Meta did not confirm video transfer.')
    except requests.RequestException: raise InstagramError('Instagram video transfer failed or timed out.') from None

def publish(path,clip,args,caption=None):
    path=Path(path)
    if not args.authorized or clip['score']<args.score: raise ValueError('Instagram requires reuse authorization and score threshold.')
    if not 1<=args.daily_limit<=30: raise ValueError('Invalid daily publishing limit.')
    if path.stat().st_size>300*1024*1024: raise ValueError('Reel exceeds local 300 MiB safety cap.')
    cfg=load_config(); ch=account(cfg)
    if ch['id']!=args.instagram_account: raise ValueError('Instagram account changed; publishing blocked.')
    q=quality(path); key=digest(path); source=clip.get('source_identity',''); a,b=clip['start'],clip['end']; day=datetime.date.today().isoformat()
    caption=caption_for(clip) if caption is None else str(caption).strip()
    from sound_studio import ensure_publish
    caption=ensure_publish(clip,'instagram',caption)
    if not caption or len(caption)>2200: raise ValueError('Instagram caption must be 1–2200 characters.')
    with ledger() as (records,save):
        for r in records:
            if r['account']!=ch['id']: continue
            same=r['sha256']==key or (source and r.get('source')==source and min(b,r['end'])-max(a,r['start'])>.5)
            if not same and abs(float(r.get('duration',0))-q['duration'])<=2: same=near_duplicate(r.get('fingerprint'),clip.get('fingerprint'))
            if same: return {'state':'duplicate' if r['state']=='uploaded' else 'uncertain','id':r.get('id'),'message':'Existing or unresolved Reel; no duplicate publish request sent.'}
        if sum(r['account']==ch['id'] and r['day']==day for r in records)>=args.daily_limit: return {'state':'limit','message':'Daily Instagram publishing limit reached.'}
        r={'account':ch['id'],'sha256':key,'source':source,'start':a,'end':b,'day':day,'state':'pending','duration':q['duration'],'fingerprint':clip.get('fingerprint')}; records.append(r);save()
        try:
            created=graph(cfg,'POST',ch['id']+'/media',{'media_type':'REELS','upload_type':'resumable','caption':caption,'share_to_feed':'true'})
            container=str(created['id']); r['container']=container;save()
            if not re.fullmatch(r'\d+',container): raise InstagramError('Invalid container ID.')
            transfer(cfg,container,created.get('uri') or f"https://rupload.facebook.com/ig-api-upload/{cfg['version']}/{container}",path)
            for attempt in range(60):
                status=graph(cfg,'GET',container,{'fields':'status_code'}).get('status_code')
                if status=='FINISHED': break
                if status in ('ERROR','EXPIRED','PUBLISHED'): raise InstagramError('Unexpected container state: '+status)
                time.sleep(5)
            else: raise InstagramError('Instagram processing timed out.')
            # Do not retry a possibly successful publish request; a lost response can otherwise duplicate a Reel.
            r['state']='publishing';save()
            result=graph(cfg,'POST',ch['id']+'/media_publish',{'creation_id':container}); media=str(result['id'])
            if not re.fullmatch(r'\d+',media): raise InstagramError('Unexpected media ID.')
            r.update(state='uploaded',id=media);save()
        except Exception as exc:
            # Pre-publish failures cannot create a visible Reel; allow a new container on a later manual retry.
            if r['state']=='pending': records.remove(r);save()
            else: r['state']='uncertain';save()
            if isinstance(exc,InstagramError): raise
            raise InstagramError('Instagram publishing failed; check the ledger before retrying.') from None
        receipt={'state':'uploaded','id':media}
        try:
            permalink=graph(cfg,'GET',media,{'fields':'permalink'}).get('permalink','')
            u=urlsplit(permalink)
            if u.scheme=='https' and u.hostname in ('www.instagram.com','instagram.com'): receipt['url']=permalink
        except InstagramError: pass
        publisher.secure_write(path.with_suffix('.instagram.json'),json.dumps(receipt));return receipt

def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['connect','status','disconnect']);a=p.parse_args()
    if a.command=='disconnect': config_path().unlink(missing_ok=True);print('Local Instagram credentials removed.');return
    try:
        if a.command=='connect':
            cfg={'account_id':input('Instagram professional account ID: ').strip(),'version':input('Graph API version [v26.0]: ').strip() or 'v26.0','token':getpass.getpass('Facebook Page access token (hidden): ').strip()}
            if not re.fullmatch(r'\d+',cfg['account_id']) or not re.fullmatch(r'v\d+\.\d+',cfg['version']) or not cfg['token']: raise InstagramError('Invalid account ID, version or token.')
            info=account(cfg);publisher.secure_write(config_path(),json.dumps(cfg));print('Connected @'+info['username']+' · '+info['id'])
        else: print(json.dumps(account()))
    except InstagramError as exc: p.exit(1,str(exc)+'\n')
if __name__=='__main__':main()
