"""Authorized API metrics and user-provided CSV. No invented performance data."""
import csv, datetime, io, json, math, re, statistics, sys
import publisher

METRICS=('views','retention','average_view_duration','likes','comments','shares','subscribers_gained')

def feedback(channel):
    p=publisher.CONFIG/'analytics-feedback.json'
    if not channel or not p.exists(): return ''
    try:
        d=json.loads(p.read_text()); return d['summary'] if d['channel']==channel else ''
    except (ValueError,KeyError): return ''

def summarize(rows):
    qualified=[r for r in rows if r.get('views',0)>=100 and r.get('retention') is not None]
    groups={k:[r['retention'] for r in qualified if lo<=r.get('duration',0)<hi] for k,lo,hi in [('15–25s',15,25),('25–35s',25,35),('35–45s',35,46)]}
    for field in ('style','caption_style','hook_band','cta_present','topic'):
        for key in {str(r[field]) for r in qualified if r.get(field) is not None}:
            groups[field+' '+key]=[r['retention'] for r in qualified if str(r.get(field))==key]
    usable=[f'{k}: {statistics.mean(v):.1f}% average viewed (n={len(v)})' for k,v in sorted(groups.items()) if len(v)>=3]
    # Aggregate only observed metrics; missing counts remain unknown.
    known=[r for r in qualified if r.get('subscribers_gained') is not None]
    if len(known)>=3 and sum(r['views'] for r in known)>0:
        usable.append(f"Observed overall subscriber gain per 1,000 views: {1000*sum(r['subscribers_gained'] for r in known)/sum(r['views'] for r in known):.2f} (n={len(known)})")
    return 'Observed performance, directional not causal; only groups with at least three videos and 100 views each: '+'; '.join(usable) if usable else ''

def save(channel,rows,source):
    today=datetime.date.today(); summary=summarize(rows)
    data={'channel':channel,'summary':summary,'sample':rows,'date':today.isoformat(),'source':source}
    publisher.secure_write(publisher.CONFIG/'analytics-feedback.json',json.dumps(data,ensure_ascii=False));return data

def import_csv(channel,content):
    if not re.fullmatch(r'UC[A-Za-z0-9_-]{22}',channel): raise ValueError('Enter a valid YouTube channel ID (UC plus 22 characters).')
    reader=csv.DictReader(io.StringIO(content.lstrip('\ufeff')))
    required={'video_id','duration',*METRICS}
    if not required.issubset(reader.fieldnames or []): raise ValueError('CSV missing columns: '+', '.join(sorted(required-set(reader.fieldnames or []))))
    rows=[]; ids=set()
    for row in reader:
        if len(rows)>=500: raise ValueError('Import at most 500 video rows.')
        vid=str(row['video_id']).strip()
        if not re.fullmatch(r'[A-Za-z0-9_-]{11}',vid) or vid in ids: raise ValueError('Invalid or repeated YouTube video ID in CSV.')
        ids.add(vid); values={}
        for field in ('duration',*METRICS):
            try:v=float(row[field])
            except (ValueError,TypeError):raise ValueError('Invalid numeric value for '+field) from None
            if not math.isfinite(v) or v<0 or field=='duration' and v<=0:raise ValueError('Invalid numeric value for '+field)
            values[field]=v
        rows.append({'video_id':vid,**values,'style':str(row.get('style',''))[:40] or None,'caption_style':str(row.get('caption_style',''))[:40] or None,'hook_band':str(row.get('hook_band',''))[:40] or None,'cta_present':{'true':True,'false':False,'1':True,'0':False}.get(str(row.get('cta_present','')).lower()),'topic':str(row.get('topic',''))[:60] or None,'source':'user_import'})
    if not rows:raise ValueError('CSV contains no measured rows.')
    return save(channel,rows,'user_import')

def refresh(expected_channel=None):
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    ch=publisher.channel(publisher.service())
    if expected_channel and ch['id']!=expected_channel: raise ValueError('Analytics channel changed')
    p=publisher.CONFIG/'public-uploads.json'
    records=[r for r in json.loads(p.read_text()) if r['channel']==ch['id'] and r['state']=='uploaded'] if p.exists() else []
    creds=Credentials.from_authorized_user_file(str(publisher.TOKEN)); scope='https://www.googleapis.com/auth/yt-analytics.readonly'
    if not creds.has_scopes([scope]): raise ValueError('Run python publisher.py connect-analytics first.')
    if not creds.valid: creds.refresh(Request())
    api=build('youtubeAnalytics','v2',credentials=creds,cache_discovery=False)
    today=datetime.date.today(); rows=[]; dates={'startDate':(today-datetime.timedelta(days=90)).isoformat(),'endDate':(today-datetime.timedelta(days=2)).isoformat()}
    for r in records[-20:]:
        report=api.reports().query(ids='channel==MINE',**dates,metrics='views,averageViewPercentage,averageViewDuration,likes,comments,shares,subscribersGained',filters='video=='+r['id']).execute(num_retries=2)
        if report.get('rows'):
            vals=report['rows'][0]; headers=[x['name'] for x in report.get('columnHeaders',[])]; metrics=dict(zip(headers,vals)) if headers else dict(zip(('views','averageViewPercentage','averageViewDuration','likes','comments','shares','subscribersGained'),vals))
            if metrics.get('views') is None: continue
            ratings=r.get('ratings') or {}; hook=ratings.get('hook')
            entry={'video_id':r['id'],'duration':r['duration'],'views':metrics['views'],'retention':metrics.get('averageViewPercentage'),'average_view_duration':metrics.get('averageViewDuration'),'likes':metrics.get('likes'),'comments':metrics.get('comments'),'shares':metrics.get('shares'),'subscribers_gained':metrics.get('subscribersGained'),'style':r.get('viral_style'),'caption_style':r.get('caption_style'),'hook_band':('90+' if hook>=90 else 'under 90') if isinstance(hook,(int,float)) else None,'cta_present':r.get('cta_displayed'),'topic':r.get('topic'),'source':'youtube_api'}
            rows.append(entry)
    # Separate retention report where the channel/video supports it. Never substitute estimates.
    for row in rows[-5:]:
        try:
            curve=api.reports().query(ids='channel==MINE',**dates,metrics='audienceWatchRatio,relativeRetentionPerformance',dimensions='elapsedVideoTimeRatio',filters='video=='+row['video_id']).execute(num_retries=1)
            row['retention_curve']=[{'fraction':x[0],'watch_ratio':x[1],'relative_retention':x[2]} for x in curve.get('rows',[]) if len(x)==3]
        except Exception: row['retention_curve']=[]
    data=save(ch['id'],rows,'youtube_api'); print(data['summary'] or 'Insufficient performance data; no adjustment.');return data

def maybe_refresh(channel):
    p=publisher.CONFIG/'analytics-feedback.json'
    if p.exists():
        try:
            data=json.loads(p.read_text())
            if data.get('channel')==channel and (data.get('source')=='user_import' or data.get('date')==datetime.date.today().isoformat()): return
        except (OSError,ValueError): pass
    refresh(channel)
if __name__=='__main__':
    if len(sys.argv)==4 and sys.argv[1]=='import':
        from pathlib import Path
        print(import_csv(sys.argv[2],Path(sys.argv[3]).read_text())['summary'] or 'Imported metrics; insufficient samples for feedback.')
    else: refresh()
