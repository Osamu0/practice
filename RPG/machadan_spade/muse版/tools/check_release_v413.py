#!/usr/bin/env python3
"""Delivery-only literal/doc workflow verification; never a per-turn check."""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
sys.dont_write_bytecode=True


def check(root):
    cases=[]
    from extract_anchors import build_index
    index=build_index(root)
    frozen=json.loads((root/'tools/verbatim_templates.json').read_text())
    for item in frozen['anchors']:
        found=next((a for a in index['files'][item['path']]['anchors'] if a['id']==item['id']),None)
        assert found and found['sha256']==item['sha256'],('verbatim-anchor-changed',item['id'])
        cases.append('verbatim:'+item['id'])
    for rel,expected in frozen['files'].items():
        assert hashlib.sha256((root/rel).read_bytes()).hexdigest()==expected,('frozen-file-changed',rel)
        cases.append('unchanged:'+rel)
    manual=(root/'運用/Command_Manual.md').read_text()
    section=manual.split('#### Command D:',1)[1].split('#### ',1)[0]
    declared=re.findall(r'(?m)^\s*\* `([^`]+)`\s*$',section)
    assert frozen['chekyun_literal'] in declared,'Chekyun quote literal differs'
    cases.append('chekyun-exact-quoted-declaration')
    with tempfile.TemporaryDirectory(prefix='machadan-release-') as temporary:
        game=Path(temporary)/'machadan_spade';clone=game/'muse版'
        shutil.copytree(root,clone,ignore=shutil.ignore_patterns('state','saves','__pycache__','*.pyc'),copy_function=shutil.copyfile)
        for name in ('VERSION.txt','RUNTIME_MANIFEST.json'):shutil.copyfile(root.parent/name,game/name)
        sys.path.insert(0,str(clone/'tools'))
        spec=importlib.util.spec_from_file_location('release_probe_runtime',clone/'tools/machadan_runtime.py')
        api=importlib.util.module_from_spec(spec);sys.modules[spec.name]=api;spec.loader.exec_module(api)
        parser=api.build_parser()
        def command(*args):
            parsed=parser.parse_args(list(map(str,args)));value=parsed.handler(parsed)
            if isinstance(value,tuple):
                if value[0]:raise AssertionError(value[1])
                return value[1]
            return value
        save=clone/'saves/release.yaml'
        command('new-save','--campaign-id','release-v413-fixture','--output',save)
        base=api.load_yaml(save);base['player']['gold']=20000
        base['world_state'].update(day=4,time_of_day='夜',quest_active='書類配達',quest_rank='D')
        card={'quest_id':'doc-delivery','name':'書類配達','immutable_hash':'','progress':{'stage':'settle'},'amendments':[],
              'reward_contract':{'settlement_id':'DOC-SETTLEMENT','offered':True,'payer':'依頼人',
                  'components':[{'component_id':'gold-1','kind':'gold','detail':{'amount':300},'state':'offered'}],
                  'delivery_plan':[]}}
        card['immutable_hash']=api._quest_hash(card);base['world_state']['quest_card']=card
        assert not api.validate_save_data(base)[0]
        # Optional new passage fields are absent in this old-v3 fixture.
        old=copy.deepcopy(base);old['game_version']='4.12.0';old['content_manifest_hash']='legacy-fixture-manifest'
        old['custom_preserved_field']={'notes':['do not rebuild the campaign']}
        migrated,changes=api.migrate_data(old)
        for key in ('campaign_id','player','party','inventory','world_state','skills','fire_state','transaction','custom_preserved_field'):
            assert migrated[key]==old[key],('old-v3-game-data-changed',key)
        assert migrated['schema_version']==3 and migrated['game_version']==api.package_version()
        assert api.validate_save_data(migrated)==([],[]),api.validate_save_data(migrated)
        assert 'passage_ticks' not in migrated['world_state']['dungeon_run']
        cases.append('old-v3-metadata-refresh-preserves-game-and-optional-field-absence')
        sample={'skill_id':'custom-skill-check','name':'検証用技能','category':'check','tier':'basic','stage':1,
                'state':'reserve','uses':None,'timing':'check','action_cost':0,'effect':'固定の検証用定義',
                'from':'custom','origin_job':None,'requirements':[]}
        errors=[];api._validate_skill_records([sample],'skills',errors);assert not errors,errors
        missing=copy.deepcopy(sample);del missing['origin_job']
        errors=[];api._validate_skill_records([missing],'skills',errors);assert any('missing origin_job' in e for e in errors)
        sample['from']='job';errors=[];api._validate_skill_records([sample],'skills',errors);assert any('origin_job' in e for e in errors)
        cases.extend(['custom-origin-job-null-valid','origin-job-key-always-required','job-origin-must-name-job'])
        api.atomic_write(save,api.dump_yaml(base))
        prepared=clone/'state/runtime/reward.prepared.yaml'
        api.atomic_write(prepared,api.dump_yaml(base))
        locations={'MACHADAN_TOOL':str(clone/'tools/machadan_runtime.py'),'TASK_SAVE':str(save),
                   'TASK_PREPARED':str(prepared),'TASK_DRAFT':str(prepared.with_name('reward.draft.yaml')),
                   'TASK_FINAL':str(prepared.with_name('reward.final.yaml')),
                   'TASK_EFFECT':str(prepared.with_name('reward.effect.json')),'TASK_TX':'release-reward-one'}
        previous={key:os.environ.get(key) for key in locations};os.environ.update(locations)
        try:
            doc=(root/'運用/実務手順例.md').read_text()
            blocks=re.findall(r'```python\n(.*?)\n```',doc,re.S)
            assert len(blocks)==2,'expected the two executable reward examples'
            exec(compile(blocks[0],str(root/'運用/実務手順例.md')+':reward','exec'),{})
            effect=subprocess.run([sys.executable,'-B',locations['MACHADAN_TOOL'],'reward-effect','--current',str(save),
                '--candidate',locations['TASK_DRAFT'],'--target','player.gold'],text=True,capture_output=True,check=True)
            Path(locations['TASK_EFFECT']).write_text(effect.stdout)
            parsed=json.loads(effect.stdout)
            assert parsed['amount']==300 and len(parsed['before_sha256'])==64 and len(parsed['after_sha256'])==64
            exec(compile(blocks[1],str(root/'運用/実務手順例.md')+':effect','exec'),{})
            command('validate-save',locations['TASK_FINAL'])
            command('commit-save','--current',save,'--candidate',locations['TASK_FINAL'],
                    '--transaction-id',locations['TASK_TX'],'--turn',1)
        finally:
            for key,value in previous.items():
                if value is None:os.environ.pop(key,None)
                else:os.environ[key]=value
        reward=api.load_yaml(save)
        assert reward['player']['gold']==20300 and reward['world_state']['quest_card'] is None
        assert reward['world_state']['reward_ledger'][0]['status']=='settled'
        cases.extend(['doc-reward-python-exact','reward-effect-real-stdout','reward-terminal-card-null'])
        overnight=copy.deepcopy(reward);debt=overnight['debt_state'];tx='release-inn-one'
        before=debt['principal'];debt['principal']+=200;overnight['player']['debt']=debt['principal']
        debt['collection_ledger'].append({'collection_id':tx,'transaction_id':tx,'event_kind':'charge','collection_day':4,
          'contract_id_before':debt['contract_id'],'contract_id_after':debt['contract_id'],
          'principal_before_payment':before,'principal_after_resolution':debt['principal'],
          'charge_amount':200,'reason':'inn','source_id':'night4-player'})
        overnight['world_state'].update(day=5,time_of_day='朝');debt['collection_pending']=True
        bad=copy.deepcopy(overnight);bad['debt_state']['collection_pending']=False
        assert api._validate_debt_transition(reward,bad,tx),'due-date advance without pending accepted'
        output=prepared.with_name('inn.final.yaml');api.atomic_write(output,api.dump_yaml(overnight))
        command('validate-save',output)
        command('commit-save','--current',save,'--candidate',output,'--transaction-id',tx,'--turn',2)
        owed=api.load_yaml(save)
        assert owed['debt_state']['principal']==10200 and owed['debt_state']['collection_pending']
        assert owed['player']['gold']==20300
        cases.extend(['inn-charge-ledger-and-both-principals','same-commit-due-day-pending','reject-due-day-without-pending'])
        before_bytes=save.read_bytes();view=api._status_snapshot(owed);view2=api._status_snapshot(owed)
        assert view==view2 and save.read_bytes()==before_bytes
        assert 'finance_forecast' in view and view['finance_forecast']['no_further_payment_penalty']==100
        cases.append('finance-view-idempotent-read-only')
        for payment,label in ((500,'period-paid'),(0,'unpaid'),(10200,'full-contract-payoff')):
            trial_save=clone/f'saves/{label}.yaml';api.atomic_write(trial_save,api.dump_yaml(owed))
            candidate=prepared.with_name(label+'.yaml');ct='release-collection-'+label
            command('resolve-debt-collection','--save',trial_save,'--payment',payment,'--output',candidate,'--transaction-id',ct)
            command('validate-save',candidate)
            command('commit-save','--current',trial_save,'--candidate',candidate,'--transaction-id',ct,'--turn',3)
            final=api.load_yaml(trial_save);debt=final['debt_state']
            assert not debt['collection_pending'] and debt['next_collection_day']==10
            if payment==10200:assert debt['principal']==50000 and debt['contract_cycle_index']==1
            elif payment==500:assert debt['principal']==9700
            else:assert debt['principal']==10300
            assert final['player']['debt']==debt['principal']
            cases.append('collection:'+label)
    return {'ok':True,'cases':len(cases),'checked':cases,'source_mutated':False,
            'scope':'synthetic v3 fixtures; documented gold-only settlement; no actual campaign supplied'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path(__file__).resolve().parent.parent);a=p.parse_args()
    try:r=check(a.root)
    except Exception as exc:r={'ok':False,'error':repr(exc)}
    print(json.dumps(r,ensure_ascii=False));return 0 if r['ok'] else 1
if __name__=='__main__':raise SystemExit(main())
