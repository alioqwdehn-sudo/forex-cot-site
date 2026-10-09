"""Independent synthetic contracts; imports no private application code."""
import copy
from datetime import date,timedelta
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import automatic_publication as auto
import download_approved_artifact as downloader
import record_publication
import verify_static_site as verifier


def fixture(root,weeks=92):
    root=Path(root);root.mkdir(parents=True)
    responses={'currencies.json':{'currencies':list(verifier.CURRENCIES),'count':10}}
    inventory={}
    for currency in verifier.CURRENCIES:
        rows=[]
        for i in reversed(range(weeks)):
            row={'date':(date(2025,1,7)+timedelta(weeks=i)).isoformat(),'open_interest':1000.,'open_interest_change':0.}
            for g in ('dealer','asset_manager','leveraged_money','other_reportables','non_reportables'):
                row[g]={'long':100.,'short':90.,'net':10.,'long_change':0.,'short_change':0.,'net_change':0.,'long_pct_oi':10.,'short_pct_oi':9.}
            rows.append(row)
        responses[f'cot/{currency}.json']={'currency':currency,'weeks_requested':'all','weeks_returned':weeks,'data':rows}
        inventory[currency]={'records':weeks,'first_date':rows[-1]['date'],'latest_date':rows[0]['date']}
    pairs=[]
    for pair,currency in auto.PAIR_CURRENCIES.items():
        base,quote=pair.split('-');info={'pair':pair.replace('-','/'),'base':base,'quote':quote,'cot_currency':currency}
        cur=copy.deepcopy(responses[f'cot/{currency}.json']);cur.pop('currency')
        responses[f'pair/{pair}.json']=dict(cur,**info);pairs.append(info)
    responses['pairs.json']={'count':10,'pairs':pairs}
    responses['ready.json']={'status':'ready','history':{c:dict(currency=c,**v) for c,v in inventory.items()}}
    responses['health.json']={'name':'Forex COT API','status':'online','database':'synthetic.db','currencies':10,'pairs':10,
        'endpoints':['/api/currencies','/api/cot/<currency>?weeks=6','/api/pairs','/api/pair/<pair>?weeks=6']}
    assets={'index.html':b'<html>synthetic</html>','data-source.js':b'/* fixture */','.nojekyll':b''}
    files={}
    for name,value in responses.items():
        raw=json.dumps(value,sort_keys=True,allow_nan=False).encode()+b'\n'
        p=root/'data'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw);files[name]=verifier.sha256(raw)
    for name,raw in assets.items():(root/name).write_bytes(raw)
    chain=[verifier.APPROVED_HISTORY]+[f'{i:064x}' for i in range(1,weeks-90)]
    manifest={'format':1,'history_sha256':chain[-1],'record_count':10*weeks,'inventory':inventory,'files':files,
        'assets':{name:verifier.sha256(raw) for name,raw in assets.items()},'release':{
        'source_repository_id':downloader.REPOSITORY_ID,'source_workflow':auto.WORKFLOW,'source_run_id':123,'source_head_sha':'a'*40,
        'anchor_history_sha256':verifier.APPROVED_HISTORY,'previous_history_sha256':chain[-2],'chain':chain,
        'official_sha256':'b'*64,'mirror_commit':'c'*40,'report_date':inventory['EUR']['latest_date']}}
    write_manifest(root,manifest)
    return root,manifest


def write_manifest(root,manifest):
    (root/'data/generation.json').write_text(json.dumps(manifest),encoding='utf-8')


def update_response(root,manifest,name,value):
    p=root/'data'/name;p.write_text(json.dumps(value),encoding='utf-8')
    manifest['files'][name]=verifier.sha256(p.read_bytes());write_manifest(root,manifest)


class AutomaticTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.site,self.manifest=fixture(self.root/'candidate')
        self.asset_policy=patch.object(auto,'APPROVED_ASSETS',dict(self.manifest['assets']))
        self.asset_policy.start();self.addCleanup(self.asset_policy.stop)
        self.run={'id':123,'head_sha':'a'*40}

    def test_new_release_exact_inventory_and_manual_policy_unchanged(self):
        self.assertTrue(auto.release_decision(self.site,self.run))
        self.assertEqual(len([p for p in self.site.rglob('*') if p.is_file()]),28)
        with self.assertRaises(ValueError):verifier.verify_site(self.site,self.manifest['history_sha256'])
        self.assertFalse(auto.release_decision(self.site,self.run,previous_site=self.site))

    def test_next_release_preserves_all_rows_and_skips_publication_delays(self):
        future,_=fixture(self.root/'future',weeks=94)
        self.assertTrue(auto.release_decision(future,self.run,previous_site=self.site))

    def test_reject_old_release_after_newer_publication(self):
        future,_=fixture(self.root/'future',weeks=93)
        with self.assertRaises(ValueError):auto.release_decision(self.site,self.run,previous_site=future)

    def test_reject_rewritten_old_rows_even_with_recomputed_manifest(self):
        future,manifest=fixture(self.root/'future',weeks=93)
        payload=auto.read_json(future/'data/cot/EUR.json');payload['data'][-1]['asset_manager']['net']=999.
        update_response(future,manifest,'cot/EUR.json',payload)
        pair=auto.read_json(future/'data/pair/EUR-USD.json');pair['data']=payload['data']
        update_response(future,manifest,'pair/EUR-USD.json',pair)
        with self.assertRaisesRegex(ValueError,'rewritten'):auto.release_decision(future,self.run,previous_site=self.site)

    def test_reject_forged_provenance_or_growth(self):
        for key,value in [('source_repository_id',999),('source_workflow','other.yml'),('source_run_id',999),('source_head_sha','b'*40),
                          ('anchor_history_sha256','0'*64),('previous_history_sha256','0'*64),('official_sha256','invalid'),('report_date','2026-01-01')]:
            manifest=copy.deepcopy(self.manifest);manifest['release'][key]=value;write_manifest(self.site,manifest)
            with self.subTest(key=key),self.assertRaises(ValueError):auto.release_decision(self.site,self.run)
        write_manifest(self.site,self.manifest)

    def test_frontend_change_requires_review_even_when_checksums_match(self):
        (self.site/'index.html').write_bytes(b'<html>unreviewed code</html>')
        self.manifest['assets']['index.html']=verifier.sha256((self.site/'index.html').read_bytes())
        write_manifest(self.site,self.manifest)
        # The approved policy is immutable, independent from mutable manifest.
        with self.assertRaisesRegex(ValueError,'Frontend'):auto.release_decision(self.site,self.run)

    def test_reject_nonfinite_duplicate_gapped_partial_and_wrong_pair(self):
        for mutation in ('nan','duplicate','gap','partial','pair'):
            root,manifest=fixture(self.root/mutation)
            if mutation=='pair':
                payload=auto.read_json(root/'data/pair/EUR-USD.json');payload['cot_currency']='GBP';name='pair/EUR-USD.json'
            else:
                payload=auto.read_json(root/'data/cot/EUR.json');name='cot/EUR.json'
                if mutation=='nan':payload['data'][0]['open_interest']=float('nan')
                elif mutation=='duplicate':payload['data'][1]=payload['data'][0]
                elif mutation=='gap':payload['data'].pop(1)
                elif mutation=='partial':payload['data'][0].pop('dealer')
            update_response(root,manifest,name,payload)
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):auto.release_decision(root,self.run)

    def test_automatic_artifact_must_be_successful_fixed_main_run_and_digest(self):
        run={'id':123,'repository':{'id':downloader.REPOSITORY_ID},'head_repository':{'id':downloader.REPOSITORY_ID},
            'head_branch':'main','event':'schedule','status':'completed','conclusion':'success','head_sha':'a'*40,'path':auto.WORKFLOW}
        name='automatic-site-123-'+'a'*40
        artifact={'id':456,'name':name,'expired':False,'size_in_bytes':1000,'digest':'sha256:'+'b'*64,
            'workflow_run':{'id':123,'repository_id':downloader.REPOSITORY_ID,'head_repository_id':downloader.REPOSITORY_ID,'head_sha':'a'*40}}
        kwargs=dict(workflow_path=auto.WORKFLOW,events=('schedule','workflow_dispatch'),automatic=True)
        self.assertEqual(downloader.select_artifact(run,[artifact],'123',name,'b'*64,**kwargs)['id'],456)
        for key,value in [('event','pull_request'),('head_branch','feature'),('conclusion','failure'),('status','in_progress'),('path','other.yml')]:
            with self.assertRaises(ValueError):downloader.select_artifact(dict(run,**{key:value}),[artifact],'123',name,'b'*64,**kwargs)

    def test_receipt_tree_contains_only_28_allowed_public_files(self):
        calls=[]
        def git(*args,**kwargs):
            calls.append(args)
            return ('a'*40+'\n').encode()
        with patch.object(record_publication,'git',side_effect=git):
            record_publication.record(self.site,'b'*40,'synthetic-token')
        paths=[args[-1].split(',',2)[-1] for args in calls if args[0]=='update-index']
        self.assertEqual(set(paths),verifier.FILES)
        self.assertTrue(calls[-1][1].endswith('b'*40))
        self.assertFalse(any('synthetic-token' in str(c) for c in calls))

    def test_no_new_active_workflow_or_weekly_page_variable_dependency(self):
        root=Path(__file__).resolve().parents[1]
        self.assertFalse((root/'.github/workflows/automatic-pages.yml').exists())
        text=(root/'deploy/automation/automatic-pages.yml').read_text()
        self.assertIn('# INACTIVE TEMPLATE',text)
        self.assertIn('group: approved-pages-artifact',text)
        self.assertNotIn('PAGES_PUBLISH_ENABLED',text)
        self.assertIn('if: needs.artifact.outputs.publish',text)


if __name__=='__main__':unittest.main()
