#!/usr/bin/env python3
"""Installation-only parity and craft/material floor audit. No dice or saves."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path


def check(root):
    cases=[]
    data=json.loads((root/'運用/戦闘調整データ.json').read_text())
    rows=data['enemies']
    assert len(rows)==40 and len({r['id'] for r in rows})==40
    assert set(r['floor'] for r in rows)==set(range(1,10))
    cases.append('all-40-individuals-all-nine-floors')
    numerical=(root/'運用/数値正本.md').read_text()
    bestiary=(root/'生成/Monster_Bestiary.md').read_text()
    sheet=(root/'運用/ダンジョン数値化シート.md').read_text()
    for row in rows:
        assert all(type(x) is int and x>=0 for x in row['after']) and len(row['after'])==7
        vector='/'.join(map(str,row['after']))
        assert vector in numerical,('numerical',row['id'])
        assert f"| {row['id']} | {row['floor']} | {row['name']} | {vector} |" in sheet,('sheet',row['id'])
        tagged=' / '.join(f'{k}:{v}' for k,v in zip(data['stat_order'],row['after']))
        assert tagged in bestiary,('bestiary',row['id'])
        cases.append('three-sources:'+row['id'])
    for key in ['goblin','worker']:
        assert next(r for r in rows if r['id']==key).get('group_combo_every')==3
    assert next(r for r in rows if r['id']=='golden')['before']==next(r for r in rows if r['id']=='golden')['after']
    cases.append('limited-group-combo-and-rare-exception')
    item=(root/'世界/Item_Database.md').read_text()
    assert '**エーテル:** (80G) MP+8' in item
    assert '**エーテル（大）:** (180G) MP+16' in item
    assert data['ether']['after']=={'normal':{'price':80,'mp':8},'large':{'price':180,'mp':16}}
    cases.append('ether-prices-recovery')
    audit=json.loads((root/'運用/素材照合_v4_13_0.json').read_text())
    source=(root/'生成/ドロップ表.md').read_text()
    for name,saved in audit['materials'].items():
        hits=[{'floor':int(f),'enemy':enemy} for f,enemy,drop in re.findall(r'(?m)^- ([1-9])F (.+?) → (.+)$',source) if name in drop]
        assert hits==saved['sources'],('material-source-drift',name)
        assert min(x['floor'] for x in hits)==saved['earliest_combat_floor']
        cases.append('material-source:'+name)
    for recipe in audit['recipes']:
        earliest=max(audit['materials'][m]['earliest_combat_floor'] for m in recipe['all'])
        assert earliest==recipe['earliest_combat_floor'],('recipe-floor',recipe['id'],earliest)
        for material in recipe['all']:
            assert material in item
        cases.append('recipe-floor:'+recipe['id'])
    # The exceptions are explicit review items, not guesses about secret recipes.
    assert len(audit['unresolved'])>=3
    return {'ok':True,'cases':len(cases),'checked':cases,'source_mutated':False,
            'material_review_items':audit['unresolved']}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path(__file__).resolve().parent.parent)
    a=p.parse_args()
    try:r=check(a.root)
    except Exception as exc:r={'ok':False,'error':str(exc)}
    print(json.dumps(r,ensure_ascii=False))
    return 0 if r['ok'] else 1
if __name__=='__main__':raise SystemExit(main())
