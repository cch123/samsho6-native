#!/usr/bin/env python3
"""Select every released opponent, win two rounds as either Hanzo, and continue the same match-up."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tempfile

from validate_rimururu_session import choose,win
from validate_selected_combat import BUILD,CAPTURE,LIB,OUT,ROOT,SOURCE,capture,fixture
from validate_stage01_session import again,trace


def set_result(assets,opponent,seat):
    roster=(opponent,3) if seat else (3,opponent)
    arena=(opponent+seat)%2
    opening=choose(roster,arena)
    menu_ready=win(assets,opening,seat)
    replay=again(menu_ready)
    rows=trace(assets,replay,'--select-fields')
    source,target=3+10*seat,3+10*(seat^1)
    # Capture the lethal visit of both rounds. Mirrored slots also have to
    # get their own score and return to 200 life at the new match boundary.
    knockouts=[]
    for i in range(len(opening),len(menu_ready)):
        prev,now=rows[i-1:i+1]
        if int(prev[target+6])>0 and int(now[target+6])==0:
            assert int(now[source+6])==200
            knockouts.append(dict(tick=i+1,attacking_action=int(now[source+2]),
                defender_state=int(now[target+1]),previous_life=int(prev[target+6])))
    assert len(knockouts)==2 and all(ko['attacking_action'] in (189,190) for ko in knockouts)
    wins=sorted({int(r[source+9]) for r in rows[len(opening):len(menu_ready)]})
    assert wins==[0,1,2]
    assert all(r[target+9]=='0' for r in rows[len(opening):len(menu_ready)])
    new=next(i for i,r in enumerate(rows) if r[23]=='2')
    entered=rows[new]
    assert entered[source+6]==entered[target+6]=='200' and entered[source+9]==entered[target+9]=='0'
    current=rows[-1]
    assert current[23:25]==['2','0'] and current[1]=='4'
    assert (int(current[25]),int(current[35]))==roster
    assert (int(current[26]),int(current[36]),int(current[52]),int(current[53]))==(5,5,arena,0)
    return dict(lineup=roster,winner=seat+1,arena=arena,knockouts=knockouts,
                score=wins,continue_match_number=2,continue_tick=new+1),opening


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--package',action='store_true')
    args=parser.parse_args()
    viewer=(OUT/'native-viewer' if args.package else BUILD)/'ss6-viewer'
    assets=OUT/'native-viewer/assets' if args.package else SOURCE
    tracked=(viewer,BUILD/'ss6-match-replay',LIB)
    digests=[sha256(p.read_bytes()).hexdigest() for p in tracked]
    stats=Counter();sets=[]
    with tempfile.TemporaryDirectory() as directory:
        work=Path(directory);src=work/'capture.cpp';src.write_text(CAPTURE);exe=work/'capture'
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',src,LIB,'-o',exe],check=True)
        for opponent in range(4):
            for seat in (0,1):
                result,opening=set_result(assets,opponent,seat)
                roster=result['lineup']
                p=fixture((*roster,51))
                for bank,name in enumerate(('01HitFlash.bin','02Guard.bin','03etc.bin'),1):
                    at=0x4a4810+(bank-1)*0x3da0;p.memory[at:at+0x3da0]=(SOURCE/name).read_bytes()
                result['comparison']=capture(exe,viewer,assets,work,p,roster,opening,len(opening)-1,
                    dict(slot=seat,action=0,steps=[]),stats)
                sets.append(result)
    assert digests==[sha256(p.read_bytes()).hexdigest() for p in tracked], 'Runtime changed during validation'
    report=dict(status='passed',packaged=args.package,viewer_sha256=digests[0],replay_sha256=digests[1],
                runtime_library_sha256=digests[2],sets=sets,draw_counts=dict(stats))
    path=OUT/'hanzo-session-validation.json'
    path.write_text(json.dumps(report,indent=2)+'\n')
    print(f'{len(sets)} sets, {sum(len(s["knockouts"]) for s in sets)} KOs, {len(sets)} continues and Japanese draw comparisons')


if __name__=='__main__':main()
