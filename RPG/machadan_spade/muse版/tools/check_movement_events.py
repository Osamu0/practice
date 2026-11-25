#!/usr/bin/env python3
"""Check M51 movement thresholds, quiet passages and real context/commit paths."""
from __future__ import annotations
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
sys.dont_write_bytecode = True


def check(root):
    sys.path.insert(0, str(root / 'tools'))
    import movement_events as me
    import response_contract as rc
    cases = []
    for style, area, threshold in [('normal','town',2),('normal','road',2),('stroll','town',4),
                                   ('wander','town',8),('wander','road',4),('idle','town',4),('direct','town',0)]:
        result = me.plan(style,area)
        assert result['threshold'] == threshold
        assert sum(value <= result['threshold'] for value in range(1,11)) == threshold
        cases.append(style+'-'+area+'-exact-d10-rate')
    for urgency in ('player_rush','quest_time_pressure','medical_emergency'):
        for style in ('normal','stroll','wander'):
            assert me.plan(style,'town',urgency)['roll_required'] is False
            cases.append('no-roll-'+urgency+'-'+style)
    for style in me.STYLES:
        assert not me.plan(style,'dungeon')['roll_required']
        cases.append('dungeon-exclusion-'+style)
    assert me.from_args(SimpleNamespace(movement_style='wander',movement_urgency='none',location_kind='town'),{'depth':1},['event'])['threshold']==0
    cases.append('saved-dungeon-depth-overrides-town-argument')
    api = SimpleNamespace(RuntimeProblem=ValueError, _fixed_tape_value=lambda die,cursor: [1,5,8,2][cursor] if 0<=cursor<4 else None)
    before={'runtime_state':{'scene_id':'event','ero_scene':False},'world_state':{'depth':None,'location':'通り'},'dice_state':{'dice_cursor_d10':0}}
    after=copy.deepcopy(before);after['dice_state']['dice_cursor_d10']=2
    draft={'schema':rc.SCHEMA,'main_text':'文'*650,'choices':['立ち止まって様子を見る','そのまま目的地へ向かう'],
           'system_blocks':['d10 = 1','d10 = 5'],'movement':{'style':'normal','location_kind':'town'},
           'random_event_roll':{'die':'d10','result':1,'cursor':0},'random_event_type_roll':{'die':'d10','result':5,'cursor':1}}
    assert rc.validate(api,draft,after,before)['movement_check']['occurred']
    cases.append('hit-validates-occurrence-type-and-cursors')
    def bad(label, payload, state=after, previous=before):
        try: rc.validate(api,payload,state,previous)
        except ValueError: cases.append(label)
        else: raise AssertionError('invalid movement accepted: '+label)
    bad('invented-dice-result',{**draft,'random_event_roll':{'die':'d10','result':2,'cursor':0}})
    bad('missing-type-after-hit',{**draft,'random_event_type_roll':None})
    bad('same-cursor-used-twice',{**draft,'random_event_type_roll':{'die':'d10','result':1,'cursor':0}})
    bad('uncommitted-cursor',{**draft},before,before)
    bad('missing-dice-display',{**draft,'system_blocks':[]})
    bad('ten-is-not-display-for-one',{**draft,'system_blocks':['d10 = 10','d10 = 5']})
    bad('no-c7-on-m51-hit',{**draft,'c7_roll':{'result':2}})
    miss_before=copy.deepcopy(before);miss_before['dice_state']['dice_cursor_d10']=2
    miss_after=copy.deepcopy(miss_before);miss_after['dice_state']['dice_cursor_d10']=3;miss_after['world_state']['location']='ギルド'
    quiet={**draft,'main_text':'石畳を抜けると、ギルドの扉が見えてきた。\n店先の呼び声を背に、中へ入る。',
           'system_blocks':['d10 = 8'],'random_event_roll':{'die':'d10','result':8,'cursor':2}}
    quiet.pop('random_event_type_roll')
    assert rc.validate(api,quiet,miss_after,miss_before)['profile']=='passage'
    cases.append('quiet-move-does-not-require-650-characters')
    bad('miss-does-not-draw-type',{**quiet,'random_event_type_roll':{'die':'d10','result':2,'cursor':3}},miss_after,miss_before)
    for style,urgency in [('direct','none'),('normal','quest_time_pressure')]:
        urgent={**quiet,'movement':{'style':style,'location_kind':'town','urgency':urgency},'system_blocks':[]}
        urgent.pop('random_event_roll')
        state=copy.deepcopy(before);state['runtime_state']['scene_id']='quest';state['world_state']['location']='ギルド'
        assert rc.validate(api,urgent,state,before)['profile']=='passage'
        cases.append('short-arrival-without-roll-'+style+'-'+urgency)
        bad('suppressed-roll-is-rejected-'+style,{**urgent,'random_event_roll':draft['random_event_roll']},state,before)
    bad('arrival-story-keeps-normal-length',{**quiet,'movement':{**quiet['movement'],'arrival_scene':True}},miss_after,miss_before)
    with tempfile.TemporaryDirectory(prefix='machadan-movement-') as temp:
        package=Path(temp)/'machadan_muse_package';game=package/'machadan_spade';clone=game/'muse版'
        shutil.copytree(root,clone,ignore=shutil.ignore_patterns('saves','state','__pycache__','*.pyc'),copy_function=shutil.copyfile)
        for name in ('VERSION.txt','RUNTIME_MANIFEST.json'):shutil.copyfile(root.parent/name,game/name)
        sys.path.insert(0,str(clone/'tools'))
        spec=importlib.util.spec_from_file_location('movement_probe_runtime',clone/'tools/machadan_runtime.py')
        rt=importlib.util.module_from_spec(spec);sys.modules[spec.name]=rt;spec.loader.exec_module(rt);parser=rt.build_parser()
        def command(*args):
            parsed=parser.parse_args(list(map(str,args)));value=parsed.handler(parsed)
            if isinstance(value,tuple):
                if value[0]:raise rt.RuntimeProblem(str(value[1]))
                return value[1]
            return value
        save=clone/'saves/probe.yaml';command('new-save','--campaign-id','movement-probe','--output',save)
        data=rt.load_yaml(save);data['world_state'].update(location='ギルド',time_of_day='朝');rt.atomic_write(save,rt.dump_yaml(data))
        for style,urgency,expected in [('normal','none',2),('wander','none',8),('direct','none',0),('normal','quest_time_pressure',0)]:
            stem=style+'-'+urgency;out=clone/f'state/runtime/{stem}.md';prepared=out.with_suffix('.prepared.yaml')
            result=command('prepare-context','--scene','event','--phase','create','--save',save,'--output',out,
                           '--candidate-save-output',prepared,'--location-kind','town','--movement-style',style,'--movement-urgency',urgency)
            assert result['movement_event_plan']['threshold']==expected
            receipt=json.loads(Path(result['receipt']).read_text())
            assert not any(row['resource']=='EVENT_INVENTORY_STATE' for row in receipt['sources'])
            cp=json.loads(Path(result['changes_template']).read_text());assert cp['response']['movement']['style']==style
            assert 'Movement event plan' in out.read_text()
            assert '街をぶらつく案内' in out.read_text()  # Milka persona is actually loaded at the guild.
            cases.append('real-context-and-no-stock-'+stem)
            if style=='normal' and urgency=='none':normal=(prepared,Path(result['changes_template']))
        prepared,changes=normal;payload=json.loads(changes.read_text())
        payload['operations']=[{'op':'replace','path':'/dice_state/dice_cursor_d10','value':2}]
        payload['response']=draft;changes.write_text(json.dumps(payload,ensure_ascii=False))
        candidate=clone/'state/runtime/final.yaml'
        args=['finish-turn','--current',save,'--prepared',prepared,'--changes',changes,'--output',candidate,'--transaction-id','movement-one','--turn',1]
        original=save.read_bytes()
        try: command(*args,'--inventory-use','events:forbidden-travel-stock')
        except rt.RuntimeProblem as exc:
            assert 'EV在庫' in str(exc) and save.read_bytes()==original
        else:raise AssertionError('movement consumed event inventory')
        cases.append('real-finish-rejects-event-stock-without-saving')
        result=command(*args);assert result['response_check']['movement_check']['occurred']
        committed=rt.load_yaml(save);assert committed['dice_state']['dice_cursor_d10']==2 and 'movement' not in committed
        command(*args);assert rt.load_yaml(save)==committed
        cases+=['real-finish-commits-roll-cursors-without-new-save-fields','same-movement-retry-does-not-redraw']
    return {'ok':True,'cases':len(cases),'checked':cases,'new_model_calls':0,'live_save_modified':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path(__file__).resolve().parent.parent)
    try:result=check(p.parse_args().root)
    except Exception as exc:result={'ok':False,'error':repr(exc)}
    print(json.dumps(result,ensure_ascii=False));raise SystemExit(0 if result['ok'] else 1)
