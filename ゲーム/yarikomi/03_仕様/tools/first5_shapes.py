"""最初の5分（パラメータ表 13.3 #14）：割れ目の形を変えた仮の盤面で、「板だけでは渡れず、重り（石）があると渡れる」形があるかを探す（game-spec-balance、2026-11-19）。
使い方：python3 03_仕様/tools/first5_shapes.py   （数秒。見つかった形を HIT で出し、最後に数を出す）
盤面はすべて【仮】。課題の中身は 07（game-design-world）で作る。
"""
from rules_sim import *
T={"板":[(0,0,"plank",None)],"板2":[(i,0,"plank",None) for i in range(2)],"板3":[(i,0,"plank",None) for i in range(3)],
"板3＋西端に石":[(i,1,"plank",None) for i in range(3)]+[(0,0,"stoneWeight",None)],
"板2＋西端に石":[(i,1,"plank",None) for i in range(2)]+[(0,0,"stoneWeight",None)],
"石":[(0,0,"stoneWeight",None)],"小石":[(0,0,"pebble",None)]}
def mk(wx, ws, gw, es, depth):
    rows=[]
    for y in range(7):
        r=""
        for x in range(7):
            if x<wx: r+="#" if y>ws else "."
            elif x<wx+gw: r+="#" if (depth is not None and y>ws+depth) else "."
            else: r+="#" if y>es else "."
        rows.append(r)
    objs=list(["."*7]*7); objs[ws]="L"+"."*6
    return dict(kind="cross", goal=(6,es), map=rows, objs=objs)
hits=[]
n_seen=0
for wx in (2,3,4):
 for ws in (3,4):
  for gw in (1,2,3):
   if wx+gw>6: continue
   for es in range(ws-2, ws+2):
    if es<1 or es>5: continue
    for depth in (None,2):
      ch=mk(wx,ws,gw,es,depth); n_seen+=1
      if solve(build(ch,Cfg()),depth=10)[0] is not None: continue
      if any(solve(build(ch,Cfg(),tools=[T[t]]),depth=10)[0] is not None for t in ("板","板2","板3","小石")): continue
      if solve(build(ch,Cfg(),tools=[T["板2"],T["板"]]),depth=12)[0] is not None: continue
      ok={t:solve(build(ch,Cfg(),tools=[T[t]]),depth=10)[0] for t in ("板3＋西端に石","板2＋西端に石","石")}
      ok["板3+石"]=solve(build(ch,Cfg(),tools=[T["板3"],T["石"]]),depth=12)[0]
      ok["板2+石"]=solve(build(ch,Cfg(),tools=[T["板2"],T["石"]]),depth=12)[0]
      if any(v is not None for v in ok.values()):
        hits.append((wx,ws,gw,es,depth,ok)); print("HIT",wx,ws,gw,es,depth,ok); print("\n".join(ch["map"]))
print(f"見た形 {n_seen} 通り、重りが要る形 {len(hits)} 通り")
