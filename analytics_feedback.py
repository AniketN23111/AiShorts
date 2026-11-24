"""Optional manual refresh, local feedback summary from owned uploaded videos."""
import json,datetime,sys,statistics
import publisher

def feedback(channel):
    p=publisher.CONFIG/'analytics-feedback.json'
    if not channel or not p.exists(): return ''
    try:
        d=json.loads(p.read_text()); return d['summary'] if d['channel']==channel else ''
    except (ValueError,KeyError): return ''

def refresh(expected_channel=None):
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    ch=publisher.channel(publisher.service());
    if expected_channel and ch['id']!=expected_channel: raise ValueError('Analytics channel changed')
    p=publisher.CONFIG/'public-uploads.json'
    records=[r for r in json.loads(p.read_text()) if r['channel']==ch['id'] and r['state']=='uploaded'] if p.exists() else []
    creds=Credentials.from_authorized_user_file(str(publisher.TOKEN)); scope='https://www.googleapis.com/auth/yt-analytics.readonly'
    if not creds.has_scopes([scope]): raise ValueError('Run python publisher.py connect-analytics first.')
    if not creds.valid: creds.refresh(Request())
    api=build('youtubeAnalytics','v2',credentials=creds,cache_discovery=False)
    today=datetime.date.today(); rows=[]
    for r in records[-20:]:
        report=api.reports().query(ids='channel==MINE',startDate=(today-datetime.timedelta(days=90)).isoformat(),endDate=(today-datetime.timedelta(days=2)).isoformat(),metrics='views,averageViewPercentage',filters='video=='+r['id']).execute()
        if report.get('rows'):
            views,ret=report['rows'][0]
            if views>=100: rows.append({'duration':r['duration'],'views':views,'retention':ret})
    groups={k:[r['retention'] for r in rows if lo<=r['duration']<hi] for k,lo,hi in [('15–25s',0,25),('25–35s',25,35),('35–45s',35,46)]}
    usable=[(k,statistics.mean(v),len(v)) for k,v in groups.items() if len(v)>=3]
    summary='Observed average view percentages by duration; weak directional evidence, not causal: '+', '.join(f'{k}: {m:.1f}% (n={n})' for k,m,n in usable) if usable else ''
    publisher.secure_write(publisher.CONFIG/'analytics-feedback.json',json.dumps({'channel':ch['id'],'summary':summary,'sample':rows,'date':today.isoformat()})); print(summary or 'Insufficient performance data; no adjustment.')
def maybe_refresh(channel):
    p=publisher.CONFIG/'analytics-feedback.json'
    if p.exists():
        try:
            data=json.loads(p.read_text())
            if data.get('channel')==channel and data.get('date')==datetime.date.today().isoformat(): return
        except (OSError,ValueError): pass
    refresh(channel)
if __name__=='__main__': refresh()
