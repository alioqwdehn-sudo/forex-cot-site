"""Polling/preflight/security tests. All reports, tokens and histories are synthetic."""
import copy
import csv
import hashlib
from datetime import date
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from test_automatic_publication import fixture,update_response,write_manifest
import automatic_publication as auto
import download_approved_artifact as download
import official_cftc as official
import source_policy as policy


def report(day='2026-10-06',long=100,change=0,*,header=False):
    rows=[]
    for market in official.MARKETS.values():
        row=['0']*87;row[0],row[2],row[7],row[86]=market,day,'1000','FutOnly'
        for li,si,lc,sc,lp,sp in official.GROUPS.values():
            row[li],row[si],row[lc],row[sc],row[lp],row[sp]=str(long),'90',str(change),'0',str(long/10),'9'
        rows.append(row)
    output=io.StringIO();writer=csv.writer(output)
    if header: writer.writerow(['Market_and_Exchange_Names']+['field']*86)
    writer.writerows(rows)
    return output.getvalue().encode()


def archive(*reports,name='FinFut26.txt'):
    output=io.BytesIO()
    header=report(header=True).splitlines(keepends=True)[0]
    with zipfile.ZipFile(output,'w') as z: z.writestr(name,header+b''.join(reports))
    return output.getvalue()


def run(id=123,sha='a'*40,preflight=False):
    return {'id':id,'head_sha':sha,'repository':{'id':download.REPOSITORY_ID},
        'head_repository':{'id':download.REPOSITORY_ID},'head_branch':'main',
        'path':auto.PREFLIGHT_WORKFLOW if preflight else auto.WORKFLOW,
        'event':'workflow_dispatch' if preflight else 'schedule','status':'completed','conclusion':'success'}


def artifact(r,*,preflight=False,expired=False):
    return {'id':456,'name':f"{'preflight' if preflight else 'automatic'}-site-{r['id']}-{r['head_sha']}",
        'expired':expired,'size_in_bytes':1000,'digest':'sha256:'+'b'*64,
        'workflow_run':{'id':r['id'],'repository_id':download.REPOSITORY_ID,
                       'head_repository_id':download.REPOSITORY_ID,'head_sha':r['head_sha']}}


class ReviewedSourcePolicyTests(unittest.TestCase):
    APPROVED_SHA = 'ceb6d3485481d26968a0fd348c6f78828593c545'

    def test_only_exact_reviewed_source_commit_is_approved(self):
        self.assertIsInstance(policy.APPROVED_SOURCE_COMMITS, frozenset)
        self.assertEqual(policy.APPROVED_SOURCE_COMMITS, frozenset({self.APPROVED_SHA}))
        self.assertEqual(len(self.APPROVED_SHA), 40)
        self.assertTrue(auto.trusted_run(run(sha=self.APPROVED_SHA, preflight=True), preflight=True))

    def test_unapproved_source_revisions_and_refs_fail_closed(self):
        for sha in ('a'*40, '0'*40, self.APPROVED_SHA[:-1]+'6',
                    self.APPROVED_SHA.upper(), self.APPROVED_SHA[:-1],
                    'main', 'refs/heads/main', ''):
            with self.subTest(sha=sha):
                candidate=run(sha=sha, preflight=True)
                self.assertFalse(auto.trusted_run(candidate, preflight=True))
                with self.assertRaisesRegex(ValueError, 'not explicitly approved'):
                    auto.release_decision(Path('unused'), candidate, preflight=True)
        with patch.object(download, 'api_json', return_value={'workflow_runs':[run(sha='a'*40)]}) as api:
            self.assertIsNone(auto.poll('synthetic'))
            self.assertEqual(api.call_count, 1)  # No unapproved artifact is requested.

    def test_sha_approval_does_not_replace_preflight_provenance_checks(self):
        candidate=run(sha=self.APPROVED_SHA, preflight=True)
        for key, value in (('head_branch','feature'), ('path',auto.WORKFLOW),
                           ('event','schedule'), ('status','in_progress'),
                           ('conclusion','failure'), ('repository',{'id':0}),
                           ('head_repository',{'id':0})):
            with self.subTest(key=key):
                self.assertFalse(auto.trusted_run(dict(candidate, **{key:value}), preflight=True))
        self.assertFalse(auto.trusted_run(candidate))  # Preflight cannot enter production.


class PollingTests(unittest.TestCase):
    def setUp(self):
        p=patch.object(policy,'APPROVED_SOURCE_COMMITS',frozenset({'a'*40}));p.start();self.addCleanup(p.stop)

    def test_exact_commit_and_fixed_provenance_required(self):
        self.assertTrue(auto.trusted_run(run()))
        for key,value in [('head_sha','b'*40),('head_branch','feature'),('path','other.yml'),('event','pull_request'),('conclusion','failure')]:
            self.assertFalse(auto.trusted_run(dict(run(),**{key:value})))
        self.assertFalse(auto.trusted_run(run(preflight=True)))
        self.assertFalse(auto.trusted_run(run(),preflight=True))

    def test_recovery_polls_past_noop_and_expired_runs(self):
        candidates=[run(id=125),run(id=124),run(id=123)]
        def api(url,token):
            if '/workflows/' in url:return {'workflow_runs':candidates}
            r=next(r for r in candidates if f"/runs/{r['id']}/" in url)
            items=[] if r['id']==125 else [artifact(r,expired=r['id']==124)]
            return {'artifacts':items,'total_count':len(items)}
        with patch.object(download,'api_json',side_effect=api):self.assertEqual(auto.poll('synthetic'),'123')

    def test_pagination_and_no_artifacts(self):
        def api(url,token):
            if '/workflows/' in url:
                return {'workflow_runs':[run(id=200+i) for i in range(100)] if url.endswith('&page=1') else [run()]}
            items=[artifact(run())] if '/runs/123/' in url else []
            return {'artifacts':items,'total_count':len(items)}
        with patch.object(download,'api_json',side_effect=api):self.assertEqual(auto.poll('synthetic'),'123')
        with patch.object(download,'api_json',return_value={'workflow_runs':[]}):self.assertIsNone(auto.poll('synthetic'))

    def test_unapproved_revision_does_not_fetch_artifacts(self):
        with patch.object(download,'api_json',return_value={'workflow_runs':[run(sha='b'*40)]}) as api:
            self.assertIsNone(auto.poll('synthetic'));self.assertEqual(api.call_count,1)
        with patch.object(policy,'APPROVED_SOURCE_COMMITS',frozenset()),self.assertRaises(ValueError):auto.poll('synthetic')

    def test_ambiguous_or_unverifiable_artifact_fails_closed(self):
        for items in ([artifact(run()),artifact(run())],[dict(artifact(run()),digest='bad')]):
            with patch.object(download,'api_json',side_effect=[{'workflow_runs':[run()]},{'artifacts':items,'total_count':len(items)}]):
                with self.assertRaises(ValueError):auto.poll('synthetic')

    def test_production_cannot_select_preflight_artifact(self):
        r=run(preflight=True);a=artifact(r,preflight=True)
        with self.assertRaises(ValueError):download.select_artifact(r,[a],'123',a['name'],'b'*64,workflow_path=auto.PREFLIGHT_WORKFLOW,automatic=True)


class IndependentOfficialTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.site,self.manifest=fixture(self.root/'site')
        self.manifest['release']['official_sha256']=hashlib.sha256(report()).hexdigest()
        write_manifest(self.site,self.manifest)

    def test_all_new_rows_independently_match_official_weekly(self):
        calls=[]
        def fetch(url,**kwargs):calls.append(url);return report()
        official.verify_new_rows(self.site,auto.read_json,today=date(2026,10,9),fetcher=fetch)
        self.assertEqual(calls,[official.WEEKLY])

    def test_multiweek_publication_recovery_uses_official_archive(self):
        site,manifest=fixture(self.root/'future',weeks=94)
        manifest['release']['official_sha256']=hashlib.sha256(report('2026-10-20')).hexdigest();write_manifest(site,manifest)
        calls=[]
        def fetch(url,**kwargs):
            calls.append(url)
            return report('2026-10-20') if url==official.WEEKLY else archive(report(),report('2026-10-13'),report('2026-10-20'))
        official.verify_new_rows(site,auto.read_json,today=date(2026,10,23),fetcher=fetch)
        self.assertEqual(calls,[official.WEEKLY,official.ARCHIVE.format(year=2026)])

    def test_archive_missing_conflicting_or_unsafe_members_rejected(self):
        site,manifest=fixture(self.root/'future',weeks=93)
        manifest['release']['official_sha256']=hashlib.sha256(report('2026-10-13')).hexdigest();write_manifest(site,manifest)
        for raw in (archive(report('2026-10-13')),archive(report(),report('2026-10-13',long=101)),archive(report(),name='../FinFut26.txt')):
            def fetch(url,**kwargs):return report('2026-10-13') if url==official.WEEKLY else raw
            with self.assertRaises(ValueError):official.verify_new_rows(site,auto.read_json,today=date(2026,10,16),fetcher=fetch)

    def test_forged_candidate_does_not_pass_authenticated_source(self):
        payload=auto.read_json(self.site/'data/cot/EUR.json');payload['data'][0]['dealer']['long']=101.
        update_response(self.site,self.manifest,'cot/EUR.json',payload)
        with self.assertRaisesRegex(ValueError,'independent official'):
            official.verify_new_rows(self.site,auto.read_json,today=date(2026,10,9),fetcher=lambda *a,**k:report())

    def test_official_invalid_rows_and_stale_report_rejected(self):
        raw=report();lines=raw.splitlines(keepends=True)
        for invalid in (raw.replace(b'FutOnly',b'Combined'),b''.join(lines[:-1]),raw+lines[0],raw.replace(b',1000,',b',nan,',1),raw.replace(b',10.0,',b',99,',1)):
            with self.assertRaises(ValueError):official.parse(invalid)
        with self.assertRaises(ValueError):official.verify_new_rows(self.site,auto.read_json,today=date(2026,10,17),fetcher=lambda *a,**k:raw)

    def test_no_redirect_credentials_or_arbitrary_official_endpoint(self):
        with self.assertRaises(ValueError):official.fetch('https://attacker.example/FinFutWk.txt')
        with patch.object(official.urllib.request.OpenerDirector,'open',side_effect=official.urllib.error.URLError('delay')) as call:
            with self.assertRaises(ValueError):official.fetch(official.WEEKLY,sleep=lambda _:None)
            self.assertEqual(call.call_count,3)

    def test_official_digest_and_unavailable_delivery_cannot_authorize(self):
        self.manifest['release']['official_sha256']='0'*64;write_manifest(self.site,self.manifest)
        with self.assertRaisesRegex(ValueError,'digest'):
            official.verify_new_rows(self.site,auto.read_json,today=date(2026,10,9),fetcher=lambda *a,**k:report())
        with self.assertRaises(ValueError):
            official.verify_new_rows(self.site,auto.read_json,today=date(2026,10,9),fetcher=lambda *a,**k:(_ for _ in ()).throw(ValueError('unavailable')))

    def test_baseline_fingerprint_prevents_first_release_rewrite(self):
        hashes={c:policy.fingerprint(auto.read_json(self.site/f'data/cot/{c}.json')['data'][-91:]) for c in auto.CURRENCIES}
        with patch.object(policy,'BASELINE_FINGERPRINTS',hashes):
            policy.verify_baseline(self.site,auto.read_json,auto.CURRENCIES)
            payload=auto.read_json(self.site/'data/cot/EUR.json');payload['data'][-1]['dealer']['net']=999.
            update_response(self.site,self.manifest,'cot/EUR.json',payload)
            with self.assertRaisesRegex(ValueError,'fingerprint'):policy.verify_baseline(self.site,auto.read_json,auto.CURRENCIES)
        self.assertEqual(policy.fingerprint([1,1.0,None]),policy.fingerprint([1.0,1,None]))


class PreflightTests(unittest.TestCase):
    def test_public_preflight_has_no_deploy_receipt_or_write_job(self):
        root=Path(__file__).resolve().parents[1]
        template=(root/'deploy/automation/automatic-preflight.yml').read_bytes()
        active=(root/'.github/workflows/automatic-preflight.yml').read_bytes()
        self.assertEqual(active,template)
        for workflow in (template,active):
            text=workflow.decode('utf-8')
            for forbidden in ('contents: write','pages:','id-token:','deploy-pages','upload-pages',
                              'upload-artifact','record_publication','schedule:','push:',
                              'pull_request:','workflow_run:','repository_dispatch:',
                              'permission-actions: write','permission-contents:',
                              'COT_AUTOMATION_READY','git push','--poll'):
                self.assertNotIn(forbidden,text)
            self.assertIn('on:\n  workflow_dispatch:\n',text)
            self.assertIn('permissions: {}',text)
            self.assertIn('contents: read',text)
            self.assertIn("github.ref == 'refs/heads/main'",text)
            self.assertIn('environment: automatic-source',text)
            self.assertIn('repositories: forex-cot-platform',text)
            self.assertIn('permission-actions: read',text)
            self.assertIn('app-id: ${{ vars.COT_SOURCE_APP_ID }}',text)
            self.assertIn('private-key: ${{ secrets.COT_SOURCE_APP_PRIVATE_KEY }}',text)
            self.assertIn('COT_SOURCE_READ_TOKEN: ${{ steps.installation.outputs.token }}',text)
            self.assertIn('run: python3 -E -s scripts/automatic_publication.py --preflight',text)
        production=(root/'deploy/automation/automatic-pages.yml').read_text()
        self.assertIn('schedule:',production);self.assertNotIn('inputs.source_run_id',production)
        self.assertNotIn('secrets.COT_SOURCE_READ_TOKEN',production)

    def test_preflight_execute_emits_publish_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);output=root/'outputs';old=Path.cwd()
            os.chdir(root)
            try:
                r=run(preflight=True);a=artifact(r,preflight=True)
                def archive_download(id,token,path):path.write_bytes(b'synthetic zip')
                generation={'history_sha256':'c'*64}
                info=type('Entry',(),{'file_size':100})()
                with patch.dict(os.environ,{'SOURCE_RUN_ID':'123','COT_SOURCE_READ_TOKEN':'synthetic','GITHUB_OUTPUT':str(output)}),\
                     patch.object(policy,'APPROVED_SOURCE_COMMITS',frozenset({'a'*40})),\
                     patch.object(download,'api_json',side_effect=[r,{'artifacts':[a],'total_count':1}]),\
                     patch.object(download,'download_archive',side_effect=archive_download),\
                     patch.object(auto,'sha256',return_value='b'*64),\
                     patch('zipfile.ZipFile') as z,\
                     patch.object(auto,'extract_verified_archive'),\
                     patch.object(auto,'get_previous',return_value=''),\
                     patch.object(auto,'release_decision',return_value=True) as decision:
                    z.return_value.__enter__.return_value.getinfo.return_value=info
                    z.return_value.__enter__.return_value.read.return_value=json.dumps(generation).encode()
                    auto.execute(preflight=True)
                    self.assertTrue(decision.call_args.kwargs['preflight'])
                self.assertEqual(output.read_text(),'publish=false\n')
            finally:os.chdir(old)


if __name__=='__main__':unittest.main()
