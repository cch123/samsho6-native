#!/usr/bin/env python3
"""Test armed Haohmaru's 623 command during a dash on both sides."""
import hashlib
import itertools
import json

from validate_haohmaru_special import (
    ROOT, ELF, SOURCE_HASH, ContactOracle, actor_trace, pads_for, run_native,
)


def battle(state, slot, outcome, oracle):
    forward, back=(128,64) if slot==0 else (64,128)
    guard=forward if outcome=='guard' else 0
    spacing=(110,back,forward) if outcome=='whiff' else (16,forward,back)
    commands=[(500,0,0),spacing,(30,0,0)]
    commands += [(1,held,guard) for held in pads_for(state,slot)]
    activation=len(commands)-1
    commands += [(1,0,guard)]*280
    if slot:
        commands=[(n,b,a) for n,a,b in commands]
    rows=run_native('ss6-match-replay',[' '.join(map(str,r)) for r in commands],'--rising-fields')
    attacker=3+10*slot;target=3+10*(1-slot)
    assert rows[activation][attacker:attacker+3]==['1',str(state),str(568+state-71)]
    assert rows[-1][attacker:attacker+3]==['0','0','0']
    fx=75+5*slot;body=23+26*slot
    visible=[r for r in rows if int(r[fx])]
    assert visible and all(r[fx:fx+2]==['1',str(571+state-71)] for r in visible)
    assert all(r[fx+3:fx+5]==r[body:body+2] for r in visible)
    assert rows[-1][fx]=='0'
    contacts=oracle.contacts(rows,slot)
    after=200
    for event in contacts:
        assert bool(event['defense'])==(outcome=='guard')
        after-=event['damage']
    assert bool(contacts)==(outcome!='whiff')
    assert after==int(rows[-1][target+6])
    if outcome=='guard':
        assert after==200-len(contacts)
    if outcome=='hit':
        assert rows[-1][target:target+3]==['0','0','0']
        if state==73:
            assert any(e['raw']==34 and e['target_state']==72 for e in contacts)
    return dict(state=state,player=slot+1,outcome=outcome,contacts=contacts,final_opponent_life=after,trail_first=int(visible[0][0]),trail_last=int(visible[-1][0]))


def main():
    assert hashlib.sha256(ELF.read_bytes()).hexdigest()==SOURCE_HASH
    traces=[]
    for state,slot in itertools.product((71,72,73),range(2)):
        ticks,ins,actions=actor_trace(state,slot)
        traces.append(dict(table=1,state=state,player=slot+1,ticks=ticks,instructions=ins,actions=actions))
    for slot in range(2):
        ticks,ins,actions=actor_trace(72,slot,fall=True)
        traces.append(dict(table=2,state=72,player=slot+1,ticks=ticks,instructions=ins,actions=actions))
    oracle=ContactOracle()
    matches=[battle(state,slot,outcome,oracle) for state,slot,outcome in
             itertools.product((71,72,73),range(2),('hit','guard','whiff'))]
    # Equal input templates give different attacks at two adjacent dash
    # ages. Use the original human route to independently select the move.
    from validate_dash_motion import Original
    boundary=[]
    for strength,slot,held_ticks in itertools.product(range(3),range(2),(12,13)):
        source=Original(slot)
        forward=(128,64)[slot]
        held=[0,forward,0]+[forward]*held_ticks+[32,32|forward|(256<<strength)]
        for bits in held:
            original=source.frame(bits)
        commands=['500 0 0']+[f'1 {bits if slot==0 else 0} {bits if slot else 0}' for bits in held]
        rows=run_native('ss6-match-replay',commands)
        state,action=map(int,rows[-1][4+10*slot:6+10*slot])
        assert (state,action)==(original[0]>>16,original[54])
        assert state==(68 if held_ticks==12 else 71)+strength
        boundary.append(dict(player=slot+1,strength=strength,held_ticks=held_ticks,state=state,action=action))
    report=dict(status='passed',elf_sha256=SOURCE_HASH,actor_traces=traces,match_replays=matches,adjacent_dash_gate=boundary,
                scope='Armed resource00 local human system0. Double-tap forward, hold dash, then down, down-forward plus slash. Actor traces compare native and original callbacks, ACT/motion/clock/registry until standing idle. Real two-player replays use both facings, three strengths, hits, guards and misses. Original 1536e8,1544a0,155850 and damage/guard prefix check each successful world contact on the published actor/geometry snapshots. The native match draw queue checks each registered trail follows its displayed owner. Adjacent 12/13-tick dash gates are compared against the source human route. Relative X/camera and a whole hardware frame are outside this oracle.')
    (ROOT/'outputs/ss6-feasibility/running_rising_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f'{len(traces)} original/native actor traces, {sum(t["ticks"] for t in traces)} ticks, {len(matches)} native matches')


if __name__=='__main__':
    main()
