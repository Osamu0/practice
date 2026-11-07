#!/usr/bin/env python3
"""Reproducible v4.13 balance benchmarks, including expedition attrition.

Offline analysis only. Never invoked by the per-turn runtime or full doctor.
Uses the unchanged opposed/damage rules from combat_balance_probe.
"""
from __future__ import annotations
import argparse
import json
import random
from dataclasses import replace
from pathlib import Path
from statistics import mean
from functools import lru_cache
from combat_balance_probe import (Blueprint,Unit,CampaignProfile,campaign_party,_active,_pick_player_target,
    _pick_enemy_target,_hurt,_damage,_roll_2d10,_expected_attack,opposed_probability,
    _record_campaign_fire_damage)

ROOT=Path(__file__).resolve().parent.parent

@lru_cache(maxsize=1)
def data():
    return json.loads((ROOT/"運用/戦闘調整データ.json").read_text())

def catalog(variant="after"):
    result={}
    for row in data()["enemies"]:
        s,d,i,sp,t,ch,lp=row[variant]
        key=row["id"]
        result[key]=Blueprint(row["name"],lp,s,d,i,sp,t,
            threat=row["threat"],cunning=key in {"stalker","cat","knight","assassin","wizard","lich","queen","arachne"},
            attack_kind="magic" if key=="novice" else "physical",
            magic_cost=2 if key=="novice" else 0,magic_power=3 if key=="novice" else 0,
            multiattack=2 if key in {"bee_queen","assassin"} else 1,
            penetration=key in {"knight","golem","chief","ogre","minotaur"},
            regeneration=5 if key=="lich" else 0,
            rage_at=.5 if key in {"orc","ogre"} else .3 if key=="minotaur" else 0,
            rage_strength=3 if key=="orc" else 6 if key=="ogre" else 10 if key=="minotaur" else 0,
            frontline=key!="wizard")
    return result

def profiles(floor,size=3,prepared=True):
    band={1:2,2:2,3:4,4:4,5:6,6:6,7:7,8:8,9:9}[floor]
    rows=campaign_party(band,size=size,growth_mode="sparse",prepared=True,allocation="accuracy_focused")
    # Supplies are paid separately below. Ordinary gear is identical between comparison cases.
    return [replace(p,spec=replace(p.spec,healing_potions=1 if prepared else 0)) for p in rows]

def new_carry(rows,stocked):
    return {"party":[Unit.from_blueprint(p.spec) for p in rows],
            "ether":{p.spec.name:int(stocked and p.spec.initial_job in {"mage","priest"}) for p in rows},
            "awakening":0,"herbs":2 if stocked else 0,"antidotes":2 if stocked else 0,
            "poison":{},"armor_wear":{},"weapon_wear":{},"special_escape":False}

def policy(keys,cat,variant="after"):
    return {"keys":keys,"giant_windup":True,"queen_shared_cooldown":True,"queen_whip_windup":True,
            "cover_mode":"paid","no_fire":False,"finite_innate_mp":True,"permanent_regen_counter":True,
            "weak_shadow":True,"lich_bolt":True,"catalog":cat,"group_combo":variant=="after",
            "ether_amount":data()["ether"][variant]["normal"]["mp"]}

def fight(profiles: list[CampaignProfile], enemy_specs: list[Blueprint],
                       policy: dict, floor: int, rng: random.Random, round_limit: int = 60, stocked: bool = False, carry=None) -> dict:
    if carry is None:
        carry = new_carry(profiles, stocked)
    party = carry["party"]
    for unit in party:
        # Battle-limited skills refresh; LP/MP and actual supplies do not.
        fresh = Unit.from_blueprint(unit.spec)
        for key in ("grit_remaining", "strong_remaining", "sweep_remaining", "focus_remaining", "vital_remaining", "first_aid_remaining"):
            setattr(unit, key, getattr(fresh, key))
        unit.first_aid_targets = set()
        unit.observed_healer = False
    start_mp = sum(u.mp for u in party)
    start_ether = sum(carry["ether"].values())
    start_awakening = carry["awakening"]
    damage_taken = 0
    hp_healed = 0
    enemy_actions = 0
    mp_added = 0
    healer_casts = 0
    party_ids = {id(u) for u in party}
    enemies = [Unit.from_blueprint(p) for p in enemy_specs]
    profile_map = {p.spec.name:p for p in profiles}
    # State is transient to this battle; no canonical save or generated fact.
    states = {}
    enemy_keys = {id(u):key for u,key in zip(enemies,policy["keys"])}
    def state(u):
        return states.setdefault(id(u),dict(poison=carry["poison"].get(u.spec.name,0) if id(u) in party_ids else 0,bleed=0,bound=False,bind_dot=0,
                    bind_source=None,bind_fail=0,controlled=False,channel=False,channel_lp=0,
                    meteor_cd=0,mental_cd=0,mental_last=None,mental_wait=set(),summoned=0,defending=False,covered=False,
                    ether=carry["ether"].get(u.spec.name,0),revived=False,
                    last_summon=-99,whip_pending=False,whip_cd=0,burn=0,fire_seen=False,regen_disabled=False,breaks=2,armor_broken=False,turns=0))
    ever_down=False; casts=controls=interrupts=0
    awakenings=carry["awakening"]
    def status_roll(target, threshold):
        threshold += -2 if target.spec.speed >=20 else -1 if target.spec.speed>=15 else 1 if target.spec.speed<=5 else 0
        if target.spec.initial_job in {"warrior","priest"}: threshold-=1
        return rng.randint(1,10)<=max(1,min(9,threshold))
    def hurt(target, amount):
        nonlocal damage_taken
        before = target.lp
        _hurt(target, amount)
        if id(target) in party_ids:
            damage_taken += before - target.lp
    def attack(actor,target,kind="physical",power=0,accuracy=0,damage=0,crit=19,pierce=False,cover=False):
        original_actor,original_target=actor.spec,target.spec
        shaman_buff=int(enemy_keys.get(id(actor))=="goblin" and any(e.active and enemy_keys.get(id(e))=="shaman" for e in enemies))
        actor.spec=replace(actor.spec,penetration=pierce,strength=actor.spec.strength+shaman_buff,technique=actor.spec.technique+accuracy+shaman_buff)
        target.spec=replace(target.spec,speed=target.spec.speed-(3 if state(target)["bound"] else 0)+(2 if state(target)["defending"] else 0),
                            defense=target.spec.defense+(2 if state(target)["defending"] else 0)-state(target).get("bat_debuff",0))
        first,second=rng.randint(1,10),rng.randint(1,10)
        attack_roll=first+second
        margin=actor.spec.technique+attack_roll-target.spec.speed-_roll_2d10(rng)
        hit,graze=margin>=0,-2<=margin<0
        dealt=0
        if hit or graze:
            dealt=_damage(actor,target,rng,hit and attack_roll>=crit,kind,cover,damage,power) if hit else 2
            key=enemy_keys.get(id(target))
            if kind=="physical" and key in {"petite","slime_queen","jelly"}:
                dealt=max(2,(dealt+1)//2)
            if kind=="magic" and key=="golem":dealt*=2
            if kind=="physical" and key=="golden" and first!=second:dealt=0
            hurt(target,dealt)
        actor.spec,target.spec=original_actor,original_target
        return {"hit":hit,"graze":graze,"damage":dealt,"critical":hit and attack_roll>=crit,"margin":margin}
    def choose_spell(actor,target):
        p=profile_map[actor.spec.name]
        choices=[]
        for name,gate,cost,power,critical in (("bolt",7,2,3,19),("fireball",11,4,5,19),("thunder",19,9,8,18)):
            if name=="fireball" and target.spec.regeneration and policy.get("no_fire"):continue
            if name in p.spells and actor.spec.intelligence>=gate and actor.mp>=max(1,cost-p.efficiency):
                c=max(1,cost-p.efficiency)
                bonus=p.catalyst_power if name=="fireball" or p.gear.startswith("sage") else 0
                # Expected damage per MP, with a modest urgency weight to avoid
                # wasting the entire fight on cheap minimum-damage bolts.
                raw=actor.spec.intelligence+power+bonus-target.spec.intelligence
                score=_expected_attack(actor.spec.technique-target.spec.speed,raw,0,critical,target.lp)/(c**.5)
                choices.append((score,name,c,power+bonus,critical))
        if target.spec.regeneration and not state(target)["fire_seen"] and not state(target)["regen_disabled"]:
            fire=[row for row in choices if row[1]=="fireball"]
            if fire:return fire[0]
        return max(choices) if choices else None
    for rnd in range(1,round_limit+1):
        order=sorted([(u.spec.speed,1,u,"party") for u in party if u.active]+
                     [(u.spec.speed,0,u,"enemy") for u in enemies if u.active],key=lambda r:(-r[0],r[1],r[2].spec.name))
        for _,_,actor,side in order:
            if not actor.active:continue
            a=state(actor);a["turns"]+=1
            a["defending"]=False
            if a["burn"]:hurt(actor,a["burn"]);a["burn"]=0
            if not actor.active:continue
            if not _active(enemies) or not _active(party):break
            if actor.skip_actions:
                actor.skip_actions-=1
            elif a["controlled"]:
                allies=[u for u in party if u.active and u is not actor]
                if allies:attack(actor,min(allies,key=lambda u:u.lp))
                a["controlled"]=False
            elif side=="party":
                p=profile_map[actor.spec.name]
                # A caster may keep casting while bound. A bleeding bind is
                # escaped when its DOT makes remaining bound obviously costly.
                fallen=[u for u in party if not u.active and not state(u)["revived"]]
                incoming_whip=any(u.active and state(u)["whip_pending"] for u in enemies)
                incoming_meteor=any(u.active and state(u)["channel"] for u in enemies)
                returning_from_cover=a["covered"] and not incoming_meteor
                if returning_from_cover:a["covered"]=False
                if returning_from_cover and actor.spec.frontline and policy.get("cover_mode")=="paid":
                    pass # standard action returns the frontline to melee range
                elif incoming_meteor and policy.get("cover_mode")=="paid" and not a["bound"]:
                    a["covered"]=True # standard action to reach previously identified full cover
                elif stocked and awakenings and fallen:
                    victim=min(fallen,key=lambda u:0 if u.spec.role=="healer" else 1 if u.spec.frontline else 2)
                    victim.lp=1;state(victim)["revived"]=True;awakenings-=1
                elif a["bound"] and a["bind_source"] is not None and (a["bind_dot"] or actor.spec.initial_job not in {"mage","priest"}):
                    source=a["bind_source"]
                    if actor.spec.strength+a["bind_fail"]+_roll_2d10(rng)>=source.spec.strength+_roll_2d10(rng):
                        a["bound"]=False;a["bind_dot"]=0;a["bind_fail"]=0
                    else:a["bind_fail"]+=3
                elif actor.healing_potions and actor.spec.lp-actor.lp>=min(20,actor.spec.lp*.4):
                    actor.healing_potions-=1;before=actor.lp;actor.lp=min(actor.spec.lp,actor.lp+20);hp_healed+=actor.lp-before
                elif stocked and a["ether"] and actor.mp<=max(1,p.efficiency):
                    a["ether"]-=1;before=actor.mp;actor.mp=min(actor.spec.intelligence,actor.mp+policy.get("ether_amount",5));mp_added+=actor.mp-before
                elif policy.get("guard_whip",False) and incoming_whip and not a["bound"] and actor.spec.role!="healer":
                    a["defending"]=True
                elif actor.spec.role=="healer":
                    poisoned=[u for u in _active(party) if state(u)["poison"]]
                    wounded=[u for u in _active(party) if u.lp<u.spec.lp]
                    emergency=any(u.lp<=max(8,u.spec.lp*.35) for u in wounded)
                    if poisoned and actor.mp>=max(1,1-p.efficiency) and not emergency:
                        actor.mp-=max(1,1-p.efficiency);state(poisoned[0])["poison"]=0
                    elif wounded:
                        target=min(wounded,key=lambda u:u.lp/u.spec.lp);missing=target.spec.lp-target.lp
                        heal_cost=max(1,2-p.efficiency)
                        if missing>=8 and actor.mp>=heal_cost and actor.spec.intelligence>=7:
                            actor.mp-=heal_cost;healing=min(missing,actor.spec.intelligence+5+rng.randint(1,6));target.lp+=healing;hp_healed+=healing;healer_casts+=1;actor.observed_healer=True
                        elif missing>=4 and actor.first_aid_remaining and target.spec.name not in actor.first_aid_targets:
                            actor.first_aid_remaining-=1;actor.first_aid_targets.add(target.spec.name)
                            healing=min(missing,rng.randint(1,6)+2);target.lp+=healing;hp_healed+=healing;actor.observed_healer=True
                        else:attack(actor,_pick_player_target(actor,enemies))
                    else:attack(actor,_pick_player_target(actor,enemies))
                elif actor.spec.initial_job=="mage":
                    target=_pick_player_target(actor,enemies)
                    choice=choose_spell(actor,target)
                    if choice:
                        _,name,cost,power,critical=choice;actor.mp-=cost;casts+=1
                        accuracy=2 if actor.focus_remaining else 0
                        actor.focus_remaining=max(0,actor.focus_remaining-1)
                        result=attack(actor,target,"magic",power,accuracy,crit=critical)
                        if name=="fireball":
                            _record_campaign_fire_damage(result,state(target),bool(policy.get("permanent_regen_counter")))
                    else:attack(actor,target)
                else:
                    target=_pick_player_target(actor,enemies);buff=p.dragon_slayer and (target.spec.threat=="strong" or enemy_keys.get(id(target)) in {"minotaur","lich","queen"})
                    accuracy,damage=(2,5) if buff else (0,0)
                    if p.armor_break and a["breaks"] and not state(target)["armor_broken"]:
                        a["breaks"]-=1;result=attack(actor,target,accuracy=accuracy-2,damage=damage+2)
                        if result["hit"]:target.spec=replace(target.spec,defense=target.spec.defense-2);state(target)["armor_broken"]=True
                    else:
                        delta=actor.spec.technique+accuracy-target.spec.speed
                        raw=actor.spec.strength-target.spec.defense
                        strong=(actor.strong_remaining and _expected_attack(delta-2,raw,damage+3,19,target.lp)>_expected_attack(delta,raw,damage,19,target.lp))
                        if strong:actor.strong_remaining-=1
                        attack(actor,target,accuracy=accuracy-(2 if strong else 0),damage=damage+(3 if strong else 0))
                # A normal action resolves the anti-chain-control protection.
                for enemy in enemies:state(enemy)["mental_wait"].discard(id(actor))
            else:
                key=enemy_keys[id(actor)]
                enemy_actions += 1
                target=_pick_enemy_target(actor,party)
                if key=="chief" and actor.lp<=actor.spec.lp*.3 and not a.get("anger"):
                    for ally in enemies:
                        if ally.active:ally.spec=replace(ally.spec,strength=ally.spec.strength+1,defense=ally.spec.defense+1,intelligence=ally.spec.intelligence+1,speed=ally.spec.speed+1,technique=ally.spec.technique+1)
                    a["anger"]=True
                if a["channel"]:
                    if a["channel_lp"]-actor.lp>=actor.spec.lp*.25:
                        interrupts+=1;a["channel"]=False;a["meteor_cd"]=3
                    else:
                        for victim in list(_active(party)):attack(actor,victim,"magic",cover=(policy.get("cover_mode")=="free" or state(victim)["covered"]))
                        a["channel"]=False;a["meteor_cd"]=3
                elif key in {"wizard","wizard_summon","lich"} and a["meteor_cd"]==0 and a["turns"]%4==1 and actor.mp>=14:
                    actor.mp-=14
                    a["channel"]=True;a["channel_lp"]=actor.lp
                elif key=="queen" and a["whip_pending"]:
                    for victim in list(_active(party)):
                        result=attack(actor,victim)
                        if result["hit"] and status_roll(victim,3):state(victim)["bleed"]=2
                    a["whip_pending"]=False;a["whip_cd"]=3
                elif key=="queen" and policy.get("queen_whip_windup") and a["whip_cd"]==0 and a["turns"]>1:
                    a["whip_pending"]=True
                elif key in {"lich","queen"} and a["mental_cd"]==0 and (not policy.get("finite_innate_mp") or actor.mp>=4):
                    possible=[u for u in _active(party) if id(u)!=a["mental_last"] and id(u) not in a["mental_wait"]]
                    victim=min(possible,key=lambda u:u.spec.intelligence) if possible else None
                    if victim is not None:
                        if policy.get("finite_innate_mp"):actor.mp-=4
                        bonus=actor.spec.intelligence if key=="lich" else (24 if policy["queen_shared_cooldown"] else 41)
                        if bonus+_roll_2d10(rng)>=victim.spec.intelligence+_roll_2d10(rng):
                            controls+=1
                            if key=="queen" and a["turns"]%2:
                                hurt(victim,15);victim.skip_actions=max(1,victim.skip_actions)
                            else:state(victim)["controlled"]=True
                        a["mental_last"]=id(victim);a["mental_wait"].add(id(victim))
                        a["mental_cd"]=3 if key=="lich" or policy["queen_shared_cooldown"] else 0
                    else:attack(actor,target)
                elif key=="queen" and a["summoned"]<2 and rnd-a["last_summon"]>=2 and (not policy.get("finite_innate_mp") or actor.mp>=6) and not any(u.active and u not in enemies[:len(enemy_specs)] for u in enemies):
                    summoned=policy["catalog"]["shadow"]
                    if policy.get("finite_innate_mp"):actor.mp-=6
                    if policy.get("weak_shadow"):summoned=policy["catalog"]["shadow"]
                    elif policy["queen_shared_cooldown"]:summoned=replace(summoned,intelligence=23,technique=16)
                    enemies.append(Unit.from_blueprint(replace(summoned,name=f"夢魔の影{a['summoned']+1}")))
                    enemy_keys[id(enemies[-1])]="shadow" if policy.get("weak_shadow") else "wizard_summon"
                    a["summoned"]+=1;a["last_summon"]=rnd
                elif key in {"alraune","arachne"} and a["turns"]%2==1:
                    for victim in _active(party):
                        if status_roll(victim,5):state(victim).update(bound=True,bind_dot=0,bind_source=actor)
                elif key in {"young","mature"} and a["turns"]%3==1:
                    if actor.spec.intelligence+_roll_2d10(rng)>=target.spec.intelligence+_roll_2d10(rng):
                        target.skip_actions=max(target.skip_actions,1);controls+=1
                elif key=="moth":
                    for victim in _active(party):
                        if status_roll(victim,3):state(victim)["poison"]=3
                elif key in {"ogre","minotaur"} and policy["giant_windup"] and a["turns"]%4==1:
                    pass # one fully visible wind-up action
                else:
                    if key=="slime_queen" and a["summoned"]<2 and actor.lp <= actor.spec.lp*(.66 if a["summoned"]==0 else .33) and len(_active(enemies))<len(party)+1:
                        spec=policy["catalog"]["small_slime"]
                        enemies.append(Unit.from_blueprint(spec));enemy_keys[id(enemies[-1])]="small_slime"
                        a["summoned"]+=1
                    elif key=="slime_queen":
                        for victim in list(_active(party)):attack(actor,victim,"magic")
                    elif key=="bee_queen" and a["summoned"]<2 and actor.lp<=actor.spec.lp*(.75 if a["summoned"]==0 else .5) and len(_active(enemies))<len(party)+1:
                        spec=policy["catalog"]["worker"]
                        enemies.append(Unit.from_blueprint(spec));enemy_keys[id(enemies[-1])]="worker"
                        a["summoned"]+=1
                    elif key=="queen" and not policy.get("queen_whip_windup"):
                        for victim in list(_active(party)):
                            result=attack(actor,victim)
                            if result["hit"] and status_roll(victim,3):state(victim)["bleed"]=2
                    elif key=="lich" and policy.get("lich_bolt") and actor.mp>=2:
                        actor.mp-=2;attack(actor,target,"magic",power=3)
                    else:
                        pierce=actor.spec.penetration and (not policy["giant_windup"] or a["turns"]%4==2)
                        swings=actor.spec.multiattack
                        if key in {"goblin","worker"} and policy.get("group_combo") and a["turns"]%3==0 and any(u.active and u is not actor and enemy_keys.get(id(u)) in ({"goblin","shaman","tamer"} if key=="goblin" else {"worker","bee_queen"}) for u in enemies):swings=2
                        checked=set()
                        for strike in range(swings):
                            if not _active(party):break
                            target=_pick_enemy_target(actor,party)
                            cost=actor.spec.magic_cost if actor.spec.attack_kind=="magic" else 0
                            attack_kind=actor.spec.attack_kind
                            if cost and actor.mp<cost:attack_kind="physical"
                            elif cost:actor.mp-=cost
                            result=attack(actor,target,attack_kind,power=actor.spec.magic_power if attack_kind=="magic" else 0,pierce=pierce)
                            if result["hit"] and id(target) not in checked:
                                checked.add(id(target))
                                poison=3 if key in {"toad","assassin"} else 4 if key in {"snake","arachne"} else 0
                                if poison and status_roll(target,5 if key=="snake" else 3):state(target)["poison"]=poison
                                if key=="bee_queen" and status_roll(target,3):target.skip_actions=max(1,target.skip_actions)
                                if key=="minotaur" and pierce and status_roll(target,3):target.skip_actions=max(1,target.skip_actions)
                                if key=="bat" and status_roll(target,3):state(target)["bat_debuff"]=1
                                if key=="lamia" and a["turns"]%3==0 and status_roll(target,3):state(target).update(bound=True,bind_dot=5,bind_source=actor)
                                if key in {"petite","jelly"} and status_roll(target,3):
                                    field="defense" if key=="petite" else "strength"
                                    cap=2 if field=="defense" else 3 if floor<4 else 5
                                    ledger=carry["armor_wear"] if field=="defense" else carry["weapon_wear"]
                                    wear=ledger.get(target.spec.name,0)
                                    if wear<cap:
                                        ledger[target.spec.name]=wear+1
                                        target.spec=replace(target.spec,**{field:max(0,getattr(target.spec,field)-1)})
                if actor.spec.regeneration and not a["fire_seen"] and not a["regen_disabled"]:actor.lp=min(actor.spec.lp,actor.lp+actor.spec.regeneration)
                a["fire_seen"]=False;a["meteor_cd"]=max(0,a["meteor_cd"]-1);a["mental_cd"]=max(0,a["mental_cd"]-1);a["whip_cd"]=max(0,a["whip_cd"]-1)
            if actor.active:hurt(actor,a["poison"]+a["bleed"]+(a["bind_dot"] if a["bound"] else 0))
            ever_down|=any(u.lp==0 for u in party)
        if rnd>=3:
            for enemy in enemies:
                if enemy.active and enemy_keys[id(enemy)]=="golden":
                    enemy.lp=0;carry["special_escape"]=True
        if not _active(party) or not _active(enemies):break
    else:rnd=round_limit+1
    assert all(u.mp>=0 for u in party+enemies)
    for unit in party:
        carry["ether"][unit.spec.name]=state(unit)["ether"]
        carry["poison"][unit.spec.name]=state(unit)["poison"]
    carry["awakening"]=awakenings
    return dict(damage_taken=damage_taken,hp_healed=hp_healed,enemy_actions=enemy_actions,
                escaped=carry["special_escape"],
                mp_actual_spent=start_mp-sum(u.mp for u in party)+mp_added,
                ether_actual_used=start_ether-sum(carry["ether"].values()),healer_casts=healer_casts,
                member_lp=[u.lp for u in party],member_mp=[u.mp for u in party],
                someone_lp0=ever_down,party_loss=not _active(party),unresolved=rnd>round_limit,
                rounds=min(rnd,round_limit),remaining_lp=sum(u.lp for u in party),
                mp_spent=start_mp-sum(u.mp for u in party)+mp_added,
                ethers_used=start_ether-sum(carry["ether"].values()),
                awakenings_used=(1-awakenings) if stocked else 0,casts=casts,controls=controls,interrupts=interrupts)


BOSSES={1:'wolf',2:'snake',3:'slime_queen',4:'chief',5:'bee_queen',6:'arachne',7:'minotaur',8:'lich',9:'queen'}
ROUTES={
 1:(["goblin","goblin","goblin"],["bat","goblin"]),
 2:(["toad","goblin"],["shaman","goblin"]),
 3:(["imp","petite"],["young","petite"]),
 4:(["orc","moth"],["orc","weak_orc"]),
 5:(["cat","worker"],["jelly","worker"]),
 6:(["lamia","alraune"],["mature"]),
 7:(["lamia","alraune"],["mature"]),
 8:(["wizard"],["mimic"]),
 9:(["shadow","shadow"],["shadow"]),
}

def interlude(carry,rows,prepared,before_boss=False):
    # Fire holders can restore a fallen holder to LP1 after a won battle.
    alive=[u for u in carry['party'] if u.lp>0]
    if not alive:return {'healing':0,'mp':0,'healing_casts':0}
    for u in carry['party']:
        if u.lp==0:u.lp=1
    spent=0;healed=0;healing_casts=0
    healer=next((u for u in carry['party'] if u.spec.role=='healer' and u.lp>0),None)
    for u in carry['party']:
        if carry['poison'].get(u.spec.name):
            if healer and healer.mp>=1:
                healer.mp-=1;spent+=1
            elif carry['antidotes']:
                carry['antidotes']-=1
            elif carry['herbs']:
                carry['herbs']-=1;old=u.lp;u.lp=min(u.spec.lp,u.lp+10);healed+=u.lp-old
            else:
                # With no treatment, one exposed travel turn is a conservative
                # additional cost, rather than quietly clearing poison.
                u.lp=max(0,u.lp-carry['poison'][u.spec.name]);continue
            carry['poison'][u.spec.name]=0
    if prepared:
        while carry['herbs'] and any(u.spec.lp-u.lp>=10 for u in carry['party'] if u.lp>0):
            u=max((u for u in carry['party'] if u.lp>0),key=lambda u:u.spec.lp-u.lp)
            carry['herbs']-=1;old=u.lp;u.lp=min(u.spec.lp,u.lp+10);healed+=u.lp-old
        while any(u.healing_potions for u in carry['party']) and any(u.spec.lp-u.lp>= (12 if before_boss else 20) for u in carry['party'] if u.lp>0):
            u=max((u for u in carry['party'] if u.lp>0),key=lambda u:u.spec.lp-u.lp)
            donor=next(v for v in carry['party'] if v.healing_potions)
            donor.healing_potions-=1;old=u.lp;u.lp=min(u.spec.lp,u.lp+20);healed+=u.lp-old
    if healer:
        p=next(p for p in rows if p.spec.name==healer.spec.name);cost=max(1,2-p.efficiency)
        while healer.mp>=cost and any(u.spec.lp-u.lp>=8 for u in carry['party'] if u.lp>0):
            u=max((u for u in carry['party'] if u.lp>0),key=lambda u:u.spec.lp-u.lp)
            healer.mp-=cost;spent+=cost;healing_casts+=1;old=u.lp;u.lp=min(u.spec.lp,u.lp+healer.spec.intelligence+5+3)
            healed+=u.lp-old
    return {'healing':healed,'mp':spent,'healing_casts':healing_casts}

def route_trial(floor,variant,prepared,rng,size=None):
    size=size or (2 if floor<=3 else 3)
    rows=profiles(floor,size,prepared)
    carry=new_carry(rows,prepared)
    if prepared and floor>=4:
        for p in rows:
            if p.spec.initial_job=="mage":carry["ether"][p.spec.name]=2
    initial_ether=sum(carry["ether"].values())
    carry['antidotes']=0 if floor==1 else carry['antidotes']
    c=catalog(variant)
    # The route is a benchmark, not an encounter quota in live exploration.
    route=[*ROUTES[floor],(BOSSES[floor],)] if floor<9 else [(BOSSES[floor],)]
    if floor==4:route[-1]=['chief']+['weak_orc']*(size-1)
    if floor==7:route=[['knight'],['ogre'],['minotaur']]
    if size==2:
        route=[list(k)[:3] for k in route]
    battles=[];interlude_mp=0;interlude_heals=0;entry_lp=None;entry_mp=None
    for position,keys in enumerate(route):
        if position==len(route)-1:
            entry_lp=[u.lp for u in carry['party']];entry_mp=[u.mp for u in carry['party']]
        p=policy(list(keys),c,variant)
        result=fight(rows,[c[k] for k in keys],p,floor,rng,stocked=prepared,carry=carry)
        battles.append(result)
        if result['party_loss'] or result['unresolved']:break
        if position<len(route)-1:
            recovery=interlude(carry,rows,prepared,before_boss=position==len(route)-2)
            interlude_mp+=recovery['mp'];interlude_heals+=recovery['healing_casts']
            if not any(u.lp>0 for u in carry['party']):break
    won=len(battles)==len(route) and not battles[-1]['party_loss'] and not battles[-1]['unresolved']
    hp_used=size-sum(u.healing_potions for u in carry['party']) if prepared else 0
    ether_used=initial_ether-sum(carry['ether'].values())
    prices=data()['ether'][variant]
    cost=50*hp_used + prices['normal']['price']*ether_used + 10*((2 if prepared else 0)-carry['herbs']) + 20*((2 if prepared and floor>1 else 0)-carry['antidotes'])
    return dict(win=won,ever_down=any(x['someone_lp0'] for x in battles) or any(u.lp==0 for u in carry['party']),before_boss=entry_lp is not None,
                boss_entry_lp=entry_lp or [0]*size,boss_entry_mp=entry_mp or [0]*size,
                remaining_lp=[u.lp for u in carry['party']],remaining_mp=[u.mp for u in carry['party']],
                rounds=sum(x['rounds'] for x in battles),damage=sum(x['damage_taken'] for x in battles),
                attack_casts=sum(x['casts'] for x in battles),healing_casts=interlude_heals+sum(x['healer_casts'] for x in battles),
                mp_spent=interlude_mp+sum(x['mp_actual_spent'] for x in battles),casts=interlude_heals+sum(x['casts']+x['healer_casts'] for x in battles),
                ether_used=ether_used,hp_used=hp_used,cost=cost,battles=battles)

def aggregate(results):
    entry=[x for x in results if x['before_boss']]
    size=len(results[0]['remaining_lp'])
    return {'trials':len(results),'win_rate':mean(x['win'] for x in results),
            'someone_lp0_rate':mean(x['ever_down'] for x in results),
            'timeout_rate':mean(any(b['unresolved'] for b in x['battles']) for x in results),
            'boss_reach_rate':len(entry)/len(results),
            'boss_entry_lp_mean':[mean(x['boss_entry_lp'][i] for x in entry) if entry else 0 for i in range(size)],
            'boss_entry_mp_mean':[mean(x['boss_entry_mp'][i] for x in entry) if entry else 0 for i in range(size)],
            'remaining_lp_mean':[mean(x['remaining_lp'][i] for x in results) for i in range(size)],
            'remaining_mp_mean':[mean(x['remaining_mp'][i] for x in results) for i in range(size)],
            **{key:mean(x[key] for x in results) for key in ('rounds','damage','mp_spent','casts','ether_used','hp_used','cost','attack_casts','healing_casts')},
            'stages':[{'rounds':mean(x['battles'][i]['rounds'] for x in results if len(x['battles'])>i),
                       'damage_per_round':sum(x['battles'][i]['damage_taken'] for x in results if len(x['battles'])>i)/max(1,sum(x['battles'][i]['rounds'] for x in results if len(x['battles'])>i))}
                      for i in range(max(len(x['battles']) for x in results))]}

def report(trials=1000,seed=413006,individual_trials=200):
    out={'version':'4.13.0','seed':seed,'trials_per_route':trials,'route_is_not_live_quota':True,
         'routes':[],'individual':[],
         'limitations':['固定の代表配分・購入装備・少量の能力の実を明記したオフライン試算。自動成長や入場条件ではない。',
             '1〜8Fは通常・強敵戦2回＋ボス、9Fはクイーン戦のみの比較経路。実プレイに戦闘ノルマを設けない。逃走判断・全地形・全自作技能・実機の文体は対象外。',
             '各戦闘でLP/MP/消耗品を引継ぎ、戦闘回数制限のある技能だけ回復。戦闘間の火によるLP1蘇生と有償の回復を明示。',
             '回復の試算では戦闘間の癒しd6だけ3を固定して控えめに見積もる。戦闘中と他の判定は独立ダイス。',
             '精神主体のUniqueは通常攻撃と3手番に1回の行動妨害を試算上の方針とする。原本に使用頻度が未定義のため実ゲームの新規確定仕様にはしない。',
             '通常遭遇で双方が認識している状態から開始する。奇襲・5Fの暗闇・全ての敵AI・自作技能を網羅した保証ではない。召喚・毒・拘束・連撃・物理耐性・全体魔法・再生対策は扱う。',
             '新しい確率をゲームに追加せず、シミュレーションの結果で実プレイの出目や敵判断を操作しない。']}
    for variant in ('before','after'):
        for floor in range(1,10):
            for prepared in (False,True) if floor==1 else (True,):
                rng=random.Random(f'{seed}:{variant}:{floor}:{prepared}')
                results=[route_trial(floor,variant,prepared,rng) for _ in range(trials)]
                rows=profiles(floor,2 if floor<=3 else 3,prepared)
                out['routes'].append(dict(floor=floor,variant=variant,prepared=prepared,party=[{**p.__dict__,'spec':p.spec.__dict__} for p in rows],**aggregate(results)))
    for row in data()['enemies']:
        floor=row['floor'];size=2 if floor<=3 else 3;rows=profiles(floor,size,True)
        for variant in ('before','after'):
            cat=catalog(variant);rng=random.Random(f'{seed}:individual:{row["id"]}:{variant}')
            results=[fight(rows,[cat[row['id']]],policy([row['id']],cat,variant),floor,rng,stocked=True) for _ in range(individual_trials)]
            out['individual'].append(dict(id=row['id'],name=row['name'],floor=floor,variant=variant,trials=individual_trials,
                win_rate=mean(not x['party_loss'] and not x['unresolved'] and not x['escaped'] for x in results),
                escape_rate=mean(x['escaped'] for x in results),
                someone_lp0=mean(x['someone_lp0'] for x in results),rounds=mean(x['rounds'] for x in results),
                damage_per_round=sum(x['damage_taken'] for x in results)/max(1,sum(x['rounds'] for x in results))))
    return out

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--trials',type=int,default=1000);p.add_argument('--seed',type=int,default=413006);p.add_argument('--individual-trials',type=int,default=200);p.add_argument('--output',type=Path)
    args=p.parse_args()
    result=report(args.trials,args.seed,args.individual_trials);text=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if args.output:args.output.write_text(text)
    else:print(text)
if __name__=='__main__':main()
