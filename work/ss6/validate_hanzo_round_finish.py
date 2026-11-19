#!/usr/bin/env python3
"""Deliver lethal Hanzo grabs and ninjutsu through real pads in rounds one and two."""
import argparse
from hashlib import sha256
import json
import struct

from validate_finishing_blow import actor,stats,put,CHILD,EVENT,OBJECTS
from validate_haohmaru_flask import children
from validate_hanzo_specials import pads,RES,BUILD,ROOT
from validate_nakoruru_combat import MixedContactOracle
from validate_rimururu_session import choose
from validate_stage01_session import trace

OUT=ROOT/'outputs/ss6-feasibility'
STATES=(74,78,64,91)


def verdict(seat,state,prev,now,objects):
    roster=(0,3) if seat else (3,0)
    check=MixedContactOracle(roster)
    p=check.probe
    for s in range(2):
        check.install_player(prev,s)
        p.write(actor(s)+0x10c,int(s==seat and state==91),4)
        put(p,stats(s),list(zip((12,24,28,32),map(int,prev[75+4*s:79+4*s]))))
    source=actor(seat)
    if state==64:
        # Read the live kind-2 object as published before contact. Its own
        # descriptor supplies the category even if its owner changes state.
        obj=next(o for o in children(objects) if o[0xcc//4]==2 and o[0xd0//4]==11)
        struct.pack_into('<80I',p.memory,CHILD,*obj)
        p.write(CHILD+0x118,source,4)
        body=CHILD;category=p.run(0x14dc00,[body])[0]
    else:
        body=OBJECTS[seat];category=p.run(0x14dac8,[source])[0]
    seen=[]
    _,instructions=p.run(0x1576e8,[source,body,EVENT,int(state!=64),0,0,int(state in (74,91))],
        limit=500000,observe=lambda pc:seen.append(hex(pc)) if pc in (0x14dc00,0x14dac8) else None)
    outcome=[p.read(stats(seat)+off,4) for off in (28,32)]
    assert seen,(state,seat,"classification was already latched")
    assert outcome==list(map(int,now[77+4*seat:79+4*seat])),(state,outcome,now)
    assert category==(13 if state==91 else 10) and outcome==([0,0] if state==91 else [5,0])
    return dict(category=category,outcome=outcome,original_classifier_calls=seen,original_instructions=instructions)


def exercise(assets,seat,state,final_round):
    pair=lambda a,b=0:(b,a) if seat else (a,b)
    forward=(128,64)[seat]
    attack=[pair(forward,forward^192)]*45+[pair(1024)]+[pair(0)]*84
    plan,start=pads(seat,state,'near')
    opening=plan[:1250]
    base,victim=3+10*seat,3+10*(seat^1)
    # Choose a real low-HP moment. Holding forward with both players keeps
    # them in range without setting coordinates, life, rage or capture state.
    attacks=opening+attack*35
    raw=trace(assets,attacks,'--select-fields')
    low=next(i for i,r in enumerate(raw) if i>=len(opening) and r[1]=='4'
             and int(r[base+9])==int(final_round) and 0<int(r[victim+6])<=15)
    route=attacks[:low+1]+[pair(0)]*190+plan[1250:]
    command=low+191+start-1250
    route += [pair(0)]*1000
    rs=trace(assets,route,'--finish-fields')
    ko=next(i for i,r in enumerate(rs) if i>=command and r[victim+6]=='0')
    prev,now=rs[ko-1:ko+1]
    assert int(prev[victim+6])>0 and now[base:base+2]==['1',str(state)]
    assert now[victim:victim+2]==['2',str({64:63,74:82,78:96,91:84}[state])]
    # Scripted slams publish the finish before commitLife applies their
    # queued damage on the next visit. Compare 1576e8 at its first latch.
    column=23+26*seat+7
    latch=next(i for i in range(command,ko+1) if int(rs[i][column])&0x08000000)
    assert ko-latch in (0,1)
    o=trace(assets,route[:latch],'--whirlwind-fields')[-1] if state==64 else None
    check=verdict(seat,state,rs[latch-1],rs[latch],o)
    assert any(r[1]=='5' and r[victim+6]=='0' for r in rs[ko:ko+10])
    assert any(r[1]=='8' and int(r[base+9])==int(final_round)+1 for r in rs[ko:])
    if final_round:
        menu=trace(assets,route,'--vs-menu-fields')
        finish=next(i for i in range(ko,len(menu)) if menu[i][25]=='1')
        assert (int(menu[finish][base+9]),int(menu[finish][victim+9]))==(2,0)
        ready=route[:finish+1]+[pair(0)]*71
        # The winning seat chooses RESELECT. Both actors must unlock and
        # leave the capture for the menu to accept the dialog and new scene.
        new_lineup=(1,3) if seat else (3,2)
        selection=choose(new_lineup,0)
        if seat:
            # After a set the losing seat confirms both stage settings.
            for at in (279,309,354):selection[at]=selection[at][::-1]
        change=ready+[pair(1024),pair(0),pair(128),pair(0),pair(1024)]+[pair(0)]*15+selection
        changed=trace(assets,change,'--select-fields')[-1]
        assert tuple(map(int,changed[25:36:10]))==new_lineup and changed[23:25]==['2','0'],(seat,state,changed)
        next_event=dict(menu_update=finish+1,reselected_lineup=new_lineup)
    else:
        play=next(i for i in range(ko,len(rs)) if rs[i][1]=='4' and rs[i][base+9]=='1' and rs[i][victim+6]=='200')
        assert rs[play][base+6]=='200' and rs[play][base]==rs[play][victim]=='0'
        # Press an actual slash on both sides after the next round has opened.
        again_pads=route[:play+1]+[pair(0)]*15+[(256,256)]+[(0,0)]*105
        post=trace(assets,again_pads,'--select-fields')
        assert post[-106][3:5]==post[-106][13:15]==['1','0']
        assert post[-1][3]==post[-1][13]=='0'
        next_event=dict(next_playable_round_update=play+1,both_accepted_normal=True)
    return dict(seat=seat+1,state=state,round=int(final_round)+1,ko_update=ko+1,finish_latch_update=latch+1,prior_life=int(prev[victim+6]),
                attacking_action=int(now[base+2]),victim_action=int(now[victim+2]),**check,**next_event)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--package',action='store_true');args=parser.parse_args()
    assets=OUT/'native-viewer/assets' if args.package else RES
    exe=BUILD/'ss6-match-replay';digest=sha256(exe.read_bytes()).hexdigest()
    cases=[exercise(assets,s,state,final) for final in (False,True) for s in (0,1) for state in STATES]
    assert digest==sha256(exe.read_bytes()).hexdigest()
    (OUT/'hanzo-round-finish-validation.json').write_text(json.dumps(dict(status='passed',packaged_assets=args.package,
        replay_sha256=digest,cases=cases),indent=2)+'\n')
    print(len(cases),'lethal round paths')


if __name__=='__main__':main()
