"""Independent official TFF Futures-Only verification; never imports source code."""
import csv
import hashlib
from datetime import date, datetime, timezone
import io
import math
import re
import time
import urllib.error
import urllib.request
import zipfile

WEEKLY='https://www.cftc.gov/dea/newcot/FinFutWk.txt'
ARCHIVE='https://www.cftc.gov/files/dea/history/fut_fin_txt_{year}.zip'
MARKETS=dict(zip(('AUD','GBP','CAD','EUR','JPY','NZD','CHF','BRL','MXN','ZAR'),(
 'AUSTRALIAN DOLLAR','BRITISH POUND','CANADIAN DOLLAR','EURO FX','JAPANESE YEN',
 'NZ DOLLAR','SWISS FRANC','BRAZILIAN REAL','MEXICAN PESO','SO AFRICAN RAND')))
MARKETS={c:m+' - CHICAGO MERCANTILE EXCHANGE' for c,m in MARKETS.items()}
GROUPS={'dealer':(8,9,25,26,42,43),'asset_manager':(11,12,28,29,45,46),
        'leveraged_money':(14,15,31,32,48,49),'other_reportables':(17,18,34,35,51,52),
        'non_reportables':(22,23,39,40,56,57)}


def fetch(url,*,limit=2*1024*1024,sleep=time.sleep):
    if url!=WEEKLY and not re.fullmatch(r'https://www\.cftc\.gov/files/dea/history/fut_fin_txt_[0-9]{4}\.zip',url):
        raise ValueError('Unexpected official endpoint')
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args): return None
    for attempt in range(3):
        try:
            request=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 Forex-COT-Independent-Verification'})
            with urllib.request.build_opener(NoRedirect).open(request,timeout=60) as response:
                raw=response.read(limit+1)
                if response.status!=200 or not raw or len(raw)>limit: raise ValueError('Invalid official response')
                return raw
        except (urllib.error.URLError,TimeoutError):
            if attempt==2: raise ValueError('Official source unavailable after retries') from None
            sleep(5*(attempt+1))


def parse(raw,*,archive=False):
    if not raw or len(raw)>64*1024*1024: raise ValueError('Invalid official CSV size')
    rows=list(csv.reader(io.StringIO(raw.decode('utf-8-sig',errors='strict')),strict=True))
    if archive:
        if not rows or len(rows[0])!=87 or rows[0][0].strip()!='Market_and_Exchange_Names':
            raise ValueError('Unexpected official archive schema')
        rows=rows[1:]
    result={};seen=set();dates=set();reverse={m:c for c,m in MARKETS.items()}
    for rawrow in rows:
        if not rawrow: continue
        if len(rawrow)!=87 or rawrow[86].strip()!='FutOnly': raise ValueError('Invalid Futures-Only row')
        text=rawrow[2].strip()
        try: report=date.fromisoformat(text)
        except ValueError:
            if not archive: raise
            report=datetime.strptime(text,'%m/%d/%Y').date()
            if report.strftime('%m/%d/%Y')!=text: raise ValueError('Noncanonical archive date')
        if report.weekday()!=1: raise ValueError('Non-Tuesday official report')
        day=report.isoformat();market=rawrow[0].strip();key=(market,day)
        if key in seen: raise ValueError('Duplicate official market/date')
        seen.add(key);dates.add(day)
        if market not in reverse: continue
        def number(index):
            value=float(rawrow[index].strip())
            if not math.isfinite(value): raise ValueError('Invalid official number')
            return value
        row={'date':day,'open_interest':number(7),'open_interest_change':number(24)}
        oi=row['open_interest']
        if oi<=0 or oi!=int(oi): raise ValueError('Invalid official open interest')
        for group,(long,short,lc,sc,lp,sp) in GROUPS.items():
            lv,sv,ld,sd,lpercent,spercent=map(number,(long,short,lc,sc,lp,sp))
            if any(v!=int(v) for v in (lv,sv,ld,sd)) or any(v<0 or v>oi for v in (lv,sv)):
                raise ValueError('Invalid official position')
            if any(not 0<=p<=100 or abs(p-v/oi*100)>0.11 for v,p in ((lv,lpercent),(sv,spercent))):
                raise ValueError('Invalid official percentage')
            row[group]={'long':lv,'short':sv,'net':lv-sv,'long_change':ld,'short_change':sd,
                        'net_change':ld-sd,'long_pct_oi':lpercent,'short_pct_oi':spercent}
        result[(reverse[market],day)]=row
    if not archive and len(dates)!=1: raise ValueError('Mixed weekly report dates')
    for day in dates:
        if {c for c,d in result if d==day}!=set(MARKETS): raise ValueError('Incomplete official report')
    return result


def archive_rows(raw,year):
    if len(raw)>8*1024*1024: raise ValueError('Oversized official ZIP')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        entries=z.infolist()
        expected=f'FinFut{year%100:02d}.txt'
        if len(entries)!=1 or entries[0].filename.lower()!=expected.lower() or entries[0].is_dir() or entries[0].file_size>64*1024*1024:
            raise ValueError('Unexpected official archive member')
        # In-memory read only: no extraction or execution, including symbolic links.
        records=parse(z.read(entries[0]),archive=True)
    if any(date.fromisoformat(day).year!=year for _,day in records): raise ValueError('Wrong archive year')
    return records


def verify_new_rows(site,read_json,previous_site=None,*,today=None,fetcher=fetch):
    today=today or datetime.now(timezone.utc).date()
    needed={};previous={}
    for currency in MARKETS:
        rows=read_json(site/f'data/cot/{currency}.json')['data']
        oldrows=read_json(previous_site/f'data/cot/{currency}.json')['data'] if previous_site else rows[-91:]
        count=len(rows)-len(oldrows)
        for row in rows[:count]: needed[(currency,row['date'])]=row
        previous[currency]=oldrows[0]
    if not needed: return
    latest=max(day for _,day in needed)
    if not 3<=(today-date.fromisoformat(latest)).days<=10: raise ValueError('Stale/premature official release')
    raw=fetcher(WEEKLY)
    manifest=read_json(site/'data/generation.json')
    if hashlib.sha256(raw).hexdigest()!=manifest['release']['official_sha256']:
        raise ValueError('Independent official delivery digest differs from source release')
    weekly=parse(raw)
    if any(day!=latest for _,day in weekly): raise ValueError('Latest official report differs; await a current release')
    missing=set(needed)-set(weekly)
    records=dict(weekly)
    for year in sorted({date.fromisoformat(day).year for _,day in missing}):
        history=archive_rows(fetcher(ARCHIVE.format(year=year),limit=8*1024*1024),year)
        if any(k in weekly and weekly[k]!=row for k,row in history.items()): raise ValueError('Official archive/weekly conflict')
        records.update(history)
    for key,row in needed.items():
        if records.get(key)!=row: raise ValueError('Candidate differs from independent official CFTC row')
    for currency in MARKETS:
        prior=previous[currency]
        for key in sorted(k for k in needed if k[0]==currency):
            row=needed[key]
            if abs(row['open_interest']/prior['open_interest']-1)>0.5: raise ValueError('Official open interest anomaly')
            if row['open_interest']-prior['open_interest']!=row['open_interest_change']: raise ValueError('Official OI delta mismatch')
            for group in GROUPS:
                for side in ('long','short'):
                    if row[group][side]-prior[group][side]!=row[group][side+'_change']: raise ValueError('Official position delta mismatch')
            prior=row
