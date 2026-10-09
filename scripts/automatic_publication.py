"""Independent unattended policy; never executes private code or artifact content."""
from datetime import date
import json
import math
import os
from pathlib import Path
import re
import tempfile
import urllib.error
import urllib.request

import download_approved_artifact as download
import source_policy
import official_cftc
from verify_static_site import APPROVED_HISTORY, CURRENCIES, FILES, MAX_BYTES, checksum, extract_verified_archive, sha256, unique_object, verify_site

WORKFLOW = '.github/workflows/automatic-weekly.yml'
PREFLIGHT_WORKFLOW = '.github/workflows/automatic-preflight.yml'
SITE_REPO = 'alioqwdehn-sudo/forex-cot-site'
STATE_BRANCH = 'automatic-published'
APPROVED_ASSETS = {
    'index.html':'828bdfda1f4acfb00642b9b403c21d284a83bf0edeb0547c11c8c0c91c7aa9a9',
    'data-source.js':'8a5e56db04e666631eb9ff91f5f3656013e22ba5b37bfa85f209a8910e11190d',
    '.nojekyll':'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
}
PAIR_CURRENCIES = dict(zip(('AUD-USD','GBP-USD','USD-CAD','EUR-USD','USD-JPY','NZD-USD','USD-CHF','USD-BRL','USD-MXN','USD-ZAR'),CURRENCIES))


def read_json(path):
    return json.loads(Path(path).read_bytes(),object_pairs_hook=unique_object)


def verify_contract(site, manifest):
    """Validate all ten complete series, pair aliases, dates and finite numbers."""
    site=Path(site)
    inv=manifest.get('inventory')
    if not isinstance(inv,dict) or set(inv)!=set(CURRENCIES): raise ValueError('Incomplete inventory')
    currencies=read_json(site/'data/currencies.json')
    if currencies!={'currencies':list(CURRENCIES),'count':10}: raise ValueError('Currency contract mismatch')
    total=0
    for currency in CURRENCIES:
        payload=read_json(site/f'data/cot/{currency}.json')
        rows=payload.get('data')
        if payload.get('currency')!=currency or payload.get('weeks_requested')!='all' or not isinstance(rows,list) or not rows:
            raise ValueError('Incomplete MAX response')
        dates=[r.get('date') for r in rows]
        if any(not isinstance(d,str) or date.fromisoformat(d).isoformat()!=d or date.fromisoformat(d).weekday()!=1 for d in dates):
            raise ValueError('Invalid response date')
        if len(set(dates))!=len(dates) or dates!=sorted(dates,reverse=True): raise ValueError('Duplicate or unordered history')
        if any((date.fromisoformat(a)-date.fromisoformat(b)).days!=7 for a,b in zip(dates,dates[1:])): raise ValueError('Gapped history')
        expected={'records':len(rows),'first_date':dates[-1],'latest_date':dates[0]}
        if inv[currency]!=expected or payload.get('weeks_returned')!=len(rows): raise ValueError('History count/date mismatch')
        for row in rows:
            if set(row)!={'date','open_interest','open_interest_change','dealer','asset_manager','leveraged_money','other_reportables','non_reportables'}:
                raise ValueError('Invalid record contract')
            values=[row['open_interest'],row['open_interest_change']]
            for group in ('dealer','asset_manager','leveraged_money','other_reportables','non_reportables'):
                if set(row[group])!={'long','short','net','long_change','short_change','net_change','long_pct_oi','short_pct_oi'}:
                    raise ValueError('Invalid group contract')
                values.extend(row[group].values())
            # Old verified history can contain nulls; new weekly validation in
            # the trusted source is stricter. Booleans/NaN are never numeric data.
            if any(v is not None and (type(v) not in (int,float) or not math.isfinite(v)) for v in values):
                raise ValueError('Invalid numeric history')
        total+=len(rows)
    if total!=manifest['record_count']: raise ValueError('Total history count mismatch')
    for pair,currency in PAIR_CURRENCIES.items():
        cur=read_json(site/f'data/cot/{currency}.json')
        response=read_json(site/f'data/pair/{pair}.json')
        cur.pop('currency')
        base,quote=pair.split('-')
        if response!=dict(cur,pair=pair.replace('-','/'),base=base,quote=quote,cot_currency=currency):
            raise ValueError('Pair alias mismatch')
    expected_pairs=[dict(pair=p.replace('-','/'),base=p.split('-')[0],quote=p.split('-')[1],cot_currency=c) for p,c in PAIR_CURRENCIES.items()]
    pairs=read_json(site/'data/pairs.json')
    if pairs.get('count')!=10 or sorted(pairs.get('pairs',[]),key=lambda p:p['pair'])!=sorted(expected_pairs,key=lambda p:p['pair']):
        raise ValueError('Pair list mismatch')
    ready=read_json(site/'data/ready.json')
    if ready!={'status':'ready','history':{c:dict(currency=c,**v) for c,v in inv.items()}}: raise ValueError('Readiness contract mismatch')
    health=read_json(site/'data/health.json')
    if (set(health)!={'name','status','database','currencies','pairs','endpoints'} or
        health.get('name')!='Forex COT API' or health.get('status')!='online' or
        health.get('currencies')!=10 or health.get('pairs')!=10 or
        not isinstance(health.get('database'),str) or not re.fullmatch('[A-Za-z0-9_. -]{1,200}\\.db',health['database']) or
        health.get('endpoints')!=['/api/currencies','/api/cot/<currency>?weeks=6','/api/pairs','/api/pair/<pair>?weeks=6']):
        raise ValueError('Health contract mismatch')


def release_decision(site, run, *, previous_site=None, preflight=False):
    if run.get('head_sha') not in source_policy.APPROVED_SOURCE_COMMITS:
        raise ValueError('Source commit is not explicitly approved')
    generation=read_json(Path(site)/'data/generation.json')
    verify_site(site,generation['history_sha256'],automatic=True)
    if generation.get('assets')!=APPROVED_ASSETS:
        raise ValueError('Frontend assets changed; explicit code review required')
    verify_contract(site,generation)
    source_policy.verify_baseline(Path(site),read_json,CURRENCIES)
    release=generation.get('release',{})
    chain=release.get('chain')
    if (release.get('mode')!=('preflight' if preflight else 'production') or
        release.get('source_repository_id')!=download.REPOSITORY_ID or release.get('source_workflow')!=(PREFLIGHT_WORKFLOW if preflight else WORKFLOW)
        or release.get('source_run_id')!=run['id'] or release.get('source_head_sha')!=run['head_sha']
        or release.get('anchor_history_sha256')!=APPROVED_HISTORY): raise ValueError('Release provenance mismatch')
    if not isinstance(chain,list) or len(chain)<2 or chain[0]!=APPROVED_HISTORY or chain[-1]!=generation['history_sha256'] or len(set(chain))!=len(chain):
        raise ValueError('Unanchored release lineage')
    for h in chain: checksum(h)
    checksum(release.get('official_sha256'))
    if not re.fullmatch('[0-9a-f]{40}',release.get('mirror_commit','')): raise ValueError('Invalid mirror provenance')
    if release.get('previous_history_sha256')!=chain[-2] or generation['record_count']!=910+10*(len(chain)-1):
        raise ValueError('Invalid lineage growth')
    if any(v['latest_date']!=release.get('report_date') for v in generation['inventory'].values()): raise ValueError('Report date mismatch')
    if previous_site is None:
        previous={'history_sha256':APPROVED_HISTORY,'record_count':910,'inventory':{
            c:{'records':91,'first_date':'2025-01-07','latest_date':'2026-09-29'} for c in CURRENCIES}}
    else:
        previous=read_json(Path(previous_site)/'data/generation.json')
        verify_site(previous_site,previous['history_sha256'],automatic=True)
        verify_contract(previous_site,previous)
        source_policy.verify_baseline(Path(previous_site),read_json,CURRENCIES)
        if previous.get('assets')!=APPROVED_ASSETS: raise ValueError('Previously published frontend policy changed')
    oldhash=previous['history_sha256']
    if oldhash==generation['history_sha256']: return False
    if oldhash not in chain[:-1]: raise ValueError('Stale, unrelated or rollback release rejected')
    weeks=chain.index(generation['history_sha256'])-chain.index(oldhash)
    if generation['record_count']!=previous['record_count']+10*weeks: raise ValueError('Unexpected growth')
    for c in CURRENCIES:
        old,new=previous['inventory'][c],generation['inventory'][c]
        if new['records']!=old['records']+weeks or new['first_date']!=old['first_date'] or (date.fromisoformat(new['latest_date'])-date.fromisoformat(old['latest_date'])).days!=7*weeks:
            raise ValueError('Currency history lost or gapped')
        if previous_site is not None:
            oldrows=read_json(Path(previous_site)/f'data/cot/{c}.json')['data']
            newrows=read_json(Path(site)/f'data/cot/{c}.json')['data']
            if newrows[weeks:]!=oldrows: raise ValueError('Previously published history was rewritten')
    official_cftc.verify_new_rows(Path(site),read_json,Path(previous_site) if previous_site else None)
    return True


def get_previous(destination):
    """Public data-only branch is the durable receipt; no private credential."""
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args): return None
    opener=urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(f'https://api.github.com/repos/{SITE_REPO}/git/ref/heads/{STATE_BRANCH}',timeout=60) as r:
            head=json.loads(r.read(65536))['object']['sha']
    except urllib.error.HTTPError as e:
        if e.code==404: return ''
        raise ValueError('Cannot determine published state') from None
    if not re.fullmatch('[0-9a-f]{40}',head): raise ValueError('Invalid state commit')
    destination=Path(destination)
    destination.mkdir()
    total=0
    for name in sorted(FILES):
        with opener.open(f'https://raw.githubusercontent.com/{SITE_REPO}/{head}/{name}',timeout=60) as r:
            content=r.read(MAX_BYTES+1)
        total+=len(content)
        if total>MAX_BYTES: raise ValueError('Oversized previous site')
        target=destination/name
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(content)
    return head


def trusted_run(run,*,preflight=False):
    return (run.get('repository',{}).get('id')==download.REPOSITORY_ID and
            run.get('head_repository',{}).get('id')==download.REPOSITORY_ID and
            run.get('path')==(PREFLIGHT_WORKFLOW if preflight else WORKFLOW) and
            run.get('head_branch')=='main' and run.get('event') in (('workflow_dispatch',) if preflight else ('schedule','workflow_dispatch')) and
            run.get('status')=='completed' and run.get('conclusion')=='success' and
            run.get('head_sha') in source_policy.APPROVED_SOURCE_COMMITS)


def poll(token):
    if not source_policy.APPROVED_SOURCE_COMMITS: raise ValueError('No reviewed source commit is approved')
    # Bounded pagination includes successful no-op runs without hiding an older
    # recoverable artifact. Latest trusted artifact first; receipts prevent replay.
    for page in range(1,6):
        runs=download.api_json(f'{download.API}/workflows/automatic-weekly.yml/runs?branch=main&status=success&per_page=100&page={page}',token)['workflow_runs']
        for run in runs:
            if not trusted_run(run): continue
            artifacts=download.api_json(f"{download.API}/runs/{run['id']}/artifacts?per_page=100",token)
            name=f"automatic-site-{run['id']}-{run['head_sha']}"
            matches=[a for a in artifacts['artifacts'] if a.get('name')==name and a.get('expired') is False]
            if not matches: continue
            if len(matches)!=1 or artifacts['total_count']>100: raise ValueError('Ambiguous polled artifacts')
            archive_hash=checksum(matches[0].get('digest','').removeprefix('sha256:'))
            download.select_artifact(run,artifacts['artifacts'],str(run['id']),name,archive_hash,
                workflow_path=WORKFLOW,events=('schedule','workflow_dispatch'),automatic=True)
            return str(run['id'])
        if len(runs)<100: break
    return None


def execute(*,preflight=False):
    token=os.environ.pop('COT_SOURCE_READ_TOKEN','')
    if not token: raise ValueError('Missing source Actions read credential')
    run_id=os.environ.get('SOURCE_RUN_ID','') if preflight else poll(token)
    if run_id is None:
        with open(os.environ['GITHUB_OUTPUT'],'a',encoding='utf-8') as f: f.write('publish=false\n')
        print('No recoverable approved production artifact; nothing published.')
        return
    if not re.fullmatch('[1-9][0-9]{0,19}',run_id): raise ValueError('Invalid run ID')
    run=download.api_json(f'{download.API}/runs/{run_id}',token)
    if not trusted_run(run,preflight=preflight): raise ValueError('Unapproved source run')
    artifacts=download.api_json(f'{download.API}/runs/{run_id}/artifacts?per_page=100',token)
    prefix='preflight' if preflight else 'automatic'
    name=f"{prefix}-site-{run_id}-{run.get('head_sha','')}"
    matches=[a for a in artifacts['artifacts'] if a.get('name')==name]
    if len(matches)!=1 or artifacts['total_count']>100: raise ValueError('Ambiguous release artifact')
    archive_hash=matches[0].get('digest','').removeprefix('sha256:')
    checksum(archive_hash)
    selected=download.select_artifact(run,artifacts['artifacts'],run_id,name,archive_hash,
        workflow_path=PREFLIGHT_WORKFLOW if preflight else WORKFLOW,
        events=('workflow_dispatch',) if preflight else ('schedule','workflow_dispatch'),automatic=True,artifact_prefix=prefix)
    with tempfile.TemporaryDirectory() as tmp:
        archive=Path(tmp)/'release.zip'
        download.download_archive(selected['id'],token,archive)
        # Read only this one allowed JSON entry to discover the dynamic hash;
        # full archive structure/digest is checked before any extraction.
        import zipfile
        if archive.stat().st_size>MAX_BYTES or sha256(archive.read_bytes())!=archive_hash: raise ValueError('ZIP digest mismatch')
        with zipfile.ZipFile(archive) as z:
            info=z.getinfo('data/generation.json')
            if info.file_size>1024*1024: raise ValueError('Oversized generation manifest')
            generation=json.loads(z.read(info),object_pairs_hook=unique_object)
        extract_verified_archive(archive,Path('site'),archive_hash,checksum(generation['history_sha256']),automatic=True)
        previous=Path(tmp)/'previous'
        head=get_previous(previous)
        publish=release_decision('site',run,previous_site=previous if head else None,preflight=preflight)
        if preflight: publish=False
    Path('state-head').write_text(head)
    with open(os.environ['GITHUB_OUTPUT'],'a',encoding='utf-8') as f: f.write(f"publish={'true' if publish else 'false'}\n")
    print('Preflight verified; no publishing permitted.' if preflight else
          ('Verified new complete release.' if publish else 'Already published; no upload or deployment.'))


def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--preflight',action='store_true')
    args=parser.parse_args()
    execute(preflight=args.preflight)


if __name__=='__main__':
    try: main()
    except Exception: raise SystemExit('Automatic publication verification failed; no upload/deploy authorized. Check run provenance, digest, lineage, anomaly or source credential.') from None
