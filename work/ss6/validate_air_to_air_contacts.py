#!/usr/bin/env python3
"""Play air-to-air slashes and execute the original two-player contact pass on both body poses."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from functools import cache
from hashlib import sha256
import json
import subprocess

from validate_collisions import ACTORS, OBJECTS, QUEUE
from validate_nakoruru_combat import MixedContactOracle
from validate_selected_combat import BUILD, OUT, SOURCE, prefix, ROOT
from validate_select_session import encode
from validate_shin_evasion import setup_state
from validate_weapon_handling import initialize_effects, setup

# Physical A/C edges after both jump buttons. Check the actual height delta
# against a no-attack flight independently of these chosen input timings.
EDGES = (((6,12,15),(6,9,12)),((6,18,21),(6,9,12)),
         ((6,9,12),(6,12,15)),((6,12,18),(6,12,15)))
PHASES = ('rising','apex','falling')


@cache
def opening(lineup):
    return encode(list(map(tuple,prefix(lineup))))


def route(assets, who, victim, side, strength, defender_jump, press, diagonal, approach, trade=False):
    def pair(own,other):
        return (other,own) if side else (own,other)
    moves = []
    for tick in range(143):
        own = (16 | (128,64)[side]*diagonal) if tick==1 else strength if tick==press else 0
        other = 16 if tick==defender_jump else strength if trade and tick==press else 0
        moves.append(pair(own,other))
    log = opening(pair(who,victim))+f'{approach} 128 64\n'+'1 0 0\n'*7+''.join(f'1 {a} {b}\n' for a,b in moves)
    proc = subprocess.run([BUILD/'ss6-match-replay',assets,'--mode','select','--whirlwind-fields'],
                          input=log,text=True,capture_output=True,check=True)
    return [line.split() for line in proc.stdout.splitlines()[-len(moves)-1:]],moves


def original_hits(rows,lineup):
    oracle = MixedContactOracle(lineup)
    p = oracle.probe
    initialize_effects(p)
    hits = []
    instructions = 0
    for tick,(prev,now) in enumerate(zip(rows,rows[1:])):
        for slot in range(2):
            oracle.install_player(prev,slot)
            p.write(ACTORS+0xf2c*slot+0x10c,5,4)
        p.write(0x12d2698,0,4)
        for pair in (OBJECTS,OBJECTS[::-1]):
            _,n=p.run(0x1536e8,pair,limit=50000)
            instructions+=n
        changed = [slot for slot in range(2) if now[10+10*slot]!=prev[10+10*slot]]
        queue = [QUEUE+i*108 for i in range(p.read(0x12d2698,4))]
        if not any(p.read(event,4)==7 for event in queue):
            assert not changed
            continue
        accepted=[]
        def enter(pc):
            if pc==0x155a88:
                event=p.registers[4]
                accepted.append([event,OBJECTS.index(p.read(event+0x40,4))])
            elif pc==0x14d198:
                accepted[-1].extend(p.registers[6:10])
        # Both contacts must run on the same original actor pair in the order
        # chosen by 154678. Resolving each attack in isolation loses the
        # other player's meter contribution on a simultaneous hit.
        _,n=p.run(0x154678,limit=500000,observe=enter)
        instructions+=n
        assert sorted(item[1] for item in accepted)==changed,(tick,accepted,changed)
        for event,slot,character,raw,part,counter in accepted:
            dest=1-slot
            actor=ACTORS+dest*0xf2c
            damage=p.read(actor+0xa38,4)
            reaction=p.read(actor+0x192,2)
            assert int(prev[9+10*dest])-damage==int(now[9+10*dest])
            assert p.read(actor+0x124,4)==int(now[40+26*dest])
            assert (p.read(actor+0x190,2),reaction)==tuple(map(int,now[3+10*dest:5+10*dest]))==(2,74)
            hits.append(dict(tick=tick,attacker=slot,raw=p.read(event+32,4),damage=damage,reaction=reaction,
                character=character,part=part,counter=counter,
                metadata=[p.read(actor+off,1) for off in (0x250,0x251,0x252,0x254)]))
    return hits,instructions


def recipient(rows,pads,hit,victim,slot):
    src,_ = setup(slot,victim)
    setup_state(src,5,0,rows[0],slot,False)
    p,a,o,ob=src.p,src.a,src.o,src.o+0x1000
    opp=1-slot
    col,other,core,cb=23+26*slot,23+26*opp,3+10*slot,88+27*slot
    for tick,(keys,prev,now) in enumerate(zip(pads,rows,rows[1:])):
        # The external stage supplies X after walls/pushboxes and its
        # cross-up flag. The original recipient consumes the real pad and
        # integrates its own vertical motion, ACT, clock and callbacks.
        p.write(o+0x40,int(prev[col]),4)
        p.write(a+0x24c,int(prev[col+9]),1)
        for off,j in ((0x40,0),(0x44,1),(0x38,2),(0x104,3),(0x108,4)):
            p.write(ob+off,int(prev[other+j]),4)
        p.write(src.b+0x144,abs(int(float(prev[7]))-int(float(prev[17]))),4)
        p.write(src.other+0x194,int(prev[3+10*opp])|(int(prev[4+10*opp])<<16),4)
        p.write(src.other+0x19a,int(prev[other+10]),1)
        for off,j in ((0x23c,5),(0x240,6),(0x244,7),(0x248,8)):
            p.write(src.other+off,int(prev[other+j]),4)
        p.write(ob+0x24,int(prev[5+10*opp]),4)
        p.write(ob+0x28,int(prev[6+10*opp]),4)
        if tick==hit['tick']:
            src.run(0x14d198,a,ob,hit['character'],hit['raw'],hit['part'],hit['counter'])
            for off,v in zip((0x250,0x251,0x252,0x254),hit['metadata']):
                p.write(a+off,v,1)
            p.write(a+0xa38,hit['damage'],4)
        v=src.frame(keys[slot])
        if tick<hit['tick']:
            continue
        got=[int(now[core])|int(now[core+1])<<16,*map(int,now[core+2:core+4]),
             int(now[cb+11]),*map(int,now[cb:cb+3]),*map(int,now[cb+8:cb+10]),int(now[col+1])]
        want=[v[0],v[54],v[55],v[56],*v[12:15],v[19],v[20],v[69]]
        assert got==want,(slot,victim,hit['tick'],tick,[(j,x,y) for j,(x,y) in enumerate(zip(got,want)) if x!=y])
        if v[0]==0 and v[54]==0:
            return dict(idle_tick=tick,matched_recovery_updates=tick-hit['tick']+1,
                        original_instructions=src.instructions)
    raise AssertionError('Recipient never returned to armed idle')


def case(job):
    assets,who,victim,side,key,jump,press,diagonal,spacing,kind,continuous=job
    lineup=(victim,who) if side else (who,victim)
    args=(assets,who,victim,side,key,jump,press,diagonal,spacing)
    rows,pads=route(*args,trade=kind=='trade')
    hits,ins=original_hits(rows,lineup)
    assert len(hits)==(2 if kind=='trade' else 1),(job,hits)
    hit=next(h for h in hits if h['attacker']==side)
    tick=hit['tick'];v=13-10*side
    clean,_=route(assets,who,victim,side,0,jump,press,diagonal,spacing)
    flight=[float(r[v+5]) for r in clean]
    y=flight[tick];peak=max(flight)
    assert y==float(rows[tick][v+5]) and y>0
    phase='apex' if peak-y<=1 else 'rising' if y<flight[tick+1] else 'falling'
    if kind in PHASES:
        assert kind==phase,(job,phase)
    if kind=='cross':
        assert (float(rows[tick][7])-float(rows[tick][17]))>0
    if kind=='trade':
        assert hits[0]['tick']==hits[1]['tick']
    original=recipient(rows,pads,hit,victim,1-side) if continuous else None
    return dict(lineup=lineup,attacker=side+1,button='A' if key==256 else 'C',scenario=kind,phase=phase,
                height=y,baseline_peak=peak,source_tick=press,defender_jump_tick=jump,contacts=hits,
                collision_instructions=ins,recipient=original)


def main():
    cli=argparse.ArgumentParser();cli.add_argument('--package',action='store_true');args=cli.parse_args()
    assets=OUT/'native-viewer/assets' if args.package else SOURCE
    jobs=[]
    for who in range(4):
        for side in (0,1):
            for strength,key in enumerate((256,1024)):
                foe=2 if who==2 and key==256 else (who+1)%4
                for phase,press in enumerate(EDGES[who][strength]):
                    continuous=phase==(who+side+strength)%3
                    jobs.append((assets,who,foe,side,key,1,press,0,43,PHASES[phase],continuous))
            if who==2:
                for key,jump,press,spacing in ((256,19,18,14),(1024,1,21,24)):
                    jobs.append((assets,who,3,side,key,jump,press,1,spacing,'cross',True))
        for key in (256,1024):
            jobs.append((assets,who,who,0,key,1,10,0,43,'trade',False))
    with ProcessPoolExecutor(4) as pool:
        checks=list(pool.map(case,jobs))
    report=dict(status='passed',package=args.package,elf_sha256=sha256((SOURCE.parent/'SLPS_255.59').read_bytes()).hexdigest(),
        replay_sha256=sha256((BUILD/'ss6-match-replay').read_bytes()).hexdigest(),cases=checks,
        scope='Real pads from player select, both actors airborne. Japanese two-body geometry and complete queued contact resolution on published poses. Continuous original recipient recovery per fighter, strength and seat and on cross-ups. Horizontal stage positions and the cross-up flag are supplied to the EE.')
    (OUT/'air-to-air-contact-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(len(checks),'air-to-air paths,',sum(len(c['contacts']) for c in checks),'original body contacts')


if __name__=='__main__':
    main()
