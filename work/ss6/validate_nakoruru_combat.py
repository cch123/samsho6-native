#!/usr/bin/env python3
"""Compare actual selected Nakoruru attacks against Japanese two-body contact resolution."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from validate_collisions import ACTORS, OBJECTS
from validate_haohmaru_special import ContactOracle, BUILD, RES, ROOT, ELF
from validate_selected_combat import prefix


class MixedContactOracle(ContactOracle):
    def __init__(self, lineup):
        super().__init__()
        self.lineup = lineup
        self.banks = [tuple((RES / f'{key}_{character:02}.bin').read_bytes()
                            for key in ('aid','act','jdg')) for character in lineup]

    def install_player(self, row, slot):
        self.aid, self.act, self.jdg = self.banks[slot]
        super().install_player(row, slot)
        character = self.lineup[slot]
        actor, body = ACTORS + slot * 0xf2c, OBJECTS[slot]
        # 148df8 publishes both resource identities. The damage routine reads
        # the attacker's own ID even when both bodies share an ACT number.
        for offset in (0x114,0xa10,0xa14):
            self.probe.write(actor+offset, character, 4)
        self.probe.write(actor+0xa1c, self.lineup[slot^1], 4)
        for off in (0x14,0x18):
            self.probe.write(body+off, character, 4)
        self.probe.write(body+0x1c, character*5, 4)


def case(replay, lineup, oracle, side, move, strength, outcome):
    who = lambda attack, defend=0: (defend,attack) if side else (attack,defend)
    forward, back = ((128,64),(64,128))[side]
    opening = prefix(lineup)
    # The factory cursor starts on system 5. Both humans choose system 0.
    opening[229] = [128,128]
    log = ['1 %d %d'%tuple(p) for p in opening]
    if outcome!='miss':log += ['40 128 64']
    log += ['30 0 0']
    held = [back,32,back|32|strength] if move=='421' else [32,32|strength] if move=='crouch' else [strength]
    if move=='follow-up':
        # A fresh light edge in the final cancellable records chains to 557.
        # Hitstop makes the four-input-frame buffer land later on a clean hit.
        when=68 if outcome=='guard' else 88
        held=[back,32,back|32|1024]+[0]*(when-3)+[256]
    defend = forward if outcome=='guard' else 0
    for w in held:log.append('1 %d %d'%who(w,defend))
    log.extend(('1 %d %d'%who(0,defend) for _ in range(310 if move=='follow-up' else 145)))
    proc = subprocess.run([replay,RES,'--mode','select','--contact-fields'],input='\n'.join(log)+'\n',text=True,capture_output=True)
    assert proc.returncode==0,(lineup,move,outcome,proc.stderr)
    rows=[r.split() for r in proc.stdout.splitlines()]
    start=len(opening)+(outcome!='miss')+1
    a,b=3+side*10,3+(side^1)*10
    attackrow=rows[start+len(held)-1]
    if move=='follow-up':
        attackrow=next(r for r in rows[start:] if int(r[a+1])==70)
    act=int(attackrow[a+2]); state=int(attackrow[a+1])
    action_sets={'stand':(189,190),'crouch':(195,196),'421':(554+(strength.bit_length()-9),),'follow-up':(557,)}
    assert act in action_sets[move],(move,side,strength,outcome,act)
    original=oracle.contacts(rows[start-5:],side)
    hits,guards=map(int,rows[-1][a+7:a+9]);life=int(rows[-1][b+6])
    assert int(rows[-1][a])==int(rows[-1][b])==0,(side,move,outcome,rows[-1][a:a+10],rows[-1][b:b+10])
    if outcome=='hit':assert hits>0 and guards==0 and life<200,(side,move,hits,guards,life)
    if outcome=='guard':assert guards>0 and hits==0,(side,move,hits,guards,life)
    if outcome=='miss':assert not hits and not guards and life==200,(side,move,hits,guards,life)
    if move=='421' and outcome=='hit':assert hits==strength.bit_length()-8
    if move=='follow-up':assert hits+guards==4
    assert hits+guards==len(original)
    return dict(lineup=lineup,attacker=side+1,move=move,strength=strength,condition=outcome,state=state,
                action=act,target_hp=life,hits=hits,guards=guards,original_contacts=original)


def check_normals(replay,side):
    from itertools import groupby
    from validate_normal_attacks import attack_cases
    lineup=(1-side,side)
    pads=prefix(lineup)
    pads[229]=[128,128]
    opening=['%d %d %d'%(sum(1 for _ in group),*pad) for pad,group in groupby(pads)]
    def own(ticks,key):
        left,right=(0,key) if side else (key,0)
        return f'{ticks} {left} {right}'
    attacker,defender=3+10*side,3+10*(1-side)
    oracle=MixedContactOracle(lineup)
    results=[]
    for state,act,approach,button in attack_cases(side,character=1):
        # The contact oracle checks neighboring updates. Preserve each sample
        # after the approach, including all stops between multi-hit ACT records.
        commands=opening+[own(n,key) for n,key in approach]
        commands += [own(1,button)]+[own(1,0)]*220
        run=subprocess.run([replay,RES,'--mode','select','--contact-fields'],
                           input='\n'.join(commands)+'\n',text=True,capture_output=True,check=True)
        rows=[line.split() for line in run.stdout.splitlines()]
        start=len(opening)+len(approach)
        assert list(map(int,rows[start][attacker:attacker+3]))==[1,state,act],(side,state,act)
        assert rows[-1][attacker:attacker+3]==rows[-1][defender:defender+3]==['0','0','0'],(side,state,act,rows[-1][:23])
        # The closing knockdown can outlast the player's attack. Once that
        # action has ended it cannot supply another attack box from this input.
        last_attack=max(i for i in range(start,len(rows)) if rows[i][attacker]=='1')
        contacts=oracle.contacts(rows[start-5:last_attack+2],side)
        assert len(contacts)==int(rows[-1][attacker+7])>0 and int(rows[-1][defender+6])<200
        results.append(dict(seat=side+1,state=state,act=act,button=button,
                            approach=approach,contacts=contacts,remaining=int(rows[-1][defender+6])))
    return results


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--replay',type=Path,default=BUILD/'ss6-match-replay');ap.add_argument('--normals',action='store_true')
    args=ap.parse_args()
    if args.normals:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(2) as pool:
            cases=[case for group in pool.map(check_normals,(args.replay,args.replay),(0,1)) for case in group]
        report=dict(status='passed',cases=cases,original_contacts=sum(len(r['contacts']) for r in cases),
                    elf_sha256=sha256(ELF.read_bytes()).hexdigest(),replay_sha256=sha256(args.replay.read_bytes()).hexdigest(),
                    scope='Both selected Nakoruru seats versus Haohmaru. All 27 armed ordinary attack variants per seat land and recover using public inputs. Original ACT and JDG contact checks use native trajectories.')
        (ROOT/'outputs/ss6-feasibility/nakoruru_normal_attacks_validation.json').write_text(json.dumps(report,indent=2)+'\n')
        print(len(cases),'selected ordinary attacks,',report['original_contacts'],'original contacts')
        return
    results=[]
    for side in (0,1):
        lineup=(1-side,side);oracle=MixedContactOracle(lineup)
        for move,strengths in [('stand',[1024]),('crouch',[1024]),('421',[256,512,1024]),('follow-up',[1024])]:
            for strength in strengths:
                for outcome in (('hit','guard') if move=='follow-up' else ('hit','guard','miss')):
                    results.append(case(args.replay,lineup,oracle,side,move,strength,outcome))
    report=dict(status='passed',elf_sha256=sha256(ELF.read_bytes()).hexdigest(),replay_sha256=sha256(args.replay.read_bytes()).hexdigest(),
                cases=results,original_contacts=sum(len(r['original_contacts']) for r in results),
                scope='Actual VS human selection and combat on both seats. Unmodified 1536e8→1544a0→155850→155a88 or 155d50 on the published body snapshots, with original ACT and JDG for each fighter. Checks natural hit and guard frames, raw type, reaction, rage and HP through recovery. This contact oracle uses the native movement trajectory.')
    path=ROOT/'outputs/ss6-feasibility/nakoruru_combat_validation.json';path.write_text(json.dumps(report,indent=2)+'\n')
    print(len(results),'fights,',report['original_contacts'],'original contacts')

if __name__=='__main__':main()
