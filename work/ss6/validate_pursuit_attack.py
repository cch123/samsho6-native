#!/usr/bin/env python3
"""Verify the downed pursuit input, armed/unarmed leap, contacts and recovery."""
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import json
import shutil
import struct
import subprocess
import tempfile

from validate_collisions import ACTORS, OBJECTS, QUEUE
from validate_dash_motion import ASSETS, ELF, PIN, PROBE, ROOT, digest
from validate_directional_slash import setup_actor
from validate_combined_slash import initialize_pools
from validate_haohmaru_special import ContactOracle

REPORT=ROOT/'outputs/ss6-feasibility/pursuit_attack_validation.json'
REPLAY=PROBE.parent/'ss6-match-replay'

def read(exe, args, commands):
    out=subprocess.run([exe,ASSETS,*args],input='\n'.join(commands)+'\n',text=True,capture_output=True,check=True)
    return [r.split() for r in out.stdout.splitlines()]

def variant(args):
    probe,slot,armed=args
    actor=setup_actor(slot);p=actor.p
    body=(280,380)[slot];other=(380,280)[slot]
    for obj,x in ((actor.o,body),(actor.o+0x1000,other)):
        struct.pack_into('<f',p.memory,obj+0x40,x)
    flags=p.read(actor.a+0x23c,4)
    if not armed:flags&=~0x1000
    previous=p.read(actor.a+0x244,4)
    p.write(actor.a+0x23c,flags,4)
    p.write(actor.a+0x190,1,2);p.write(actor.a+0x192,33,2)
    commands=[f'reset {slot} {slot} {body} {other}','combat',f'posture {flags} {previous}','attack 33']
    want=[]
    for tick in range(140):
        record=actor.frame(0)
        cols=(0,2,3,*range(12,19),*range(54,58),*range(62,70))
        want.append([record[i] for i in cols]);commands.append('pad 0 0')
        if tick>3 and record[0]==0 and record[54]==int(not armed):break
    assert tick<139
    native=read(probe,[],commands)[4:]
    for i,(row,exp) in enumerate(zip(native,want,strict=True)):
        assert [int(row[j]) for j in cols]==exp,(slot,armed,i,exp,[row[j] for j in cols])
    return dict(player=slot+1,armed=armed,action=225 if armed else 226,ticks=len(want),original_instructions=actor.instructions)

def install_stage_facing(actor):
    # The standalone actor oracle normally has a fixed left/right ordering.
    # The sweep crosses the opponent, so run the original stage facing block
    # after body movement, before physical directions are normalized.
    original_slice=actor.slice
    def facing_slice(start,end):
        if start==0x1428f4:
            p=actor.p
            for i,(a,o) in enumerate(((actor.a,actor.o),(actor.other,actor.o+0x1000))):
                p.write(0x1fff010+4*i,a,4);p.write(0x1fff020+4*i,o,4)
            p.put(12,actor.o)
            start=0x1427f0
        original_slice(start,end)
    actor.slice=facing_slice

def playback(args):
    exe,slot,delay,armed=args
    target=1-slot;forward=(128,64)[slot]
    initial=[(500,0)]
    if not armed:initial.extend([(1,forward|8),(125,0)])
    initial.extend([(45,forward),(2,0)])
    sweep=forward|32|2048;attack=(forward^192)|32|1024
    held=[sweep]+[0]*delay+[attack]+[0]*121
    rows=read(exe,['--whirlwind-fields'],['%d %d %d'%((n,0,h) if slot else(n,h,0)) for n,h in initial+[(1,h) for h in held]])[len(initial)-1:]
    # Start the Japanese players in their normal action just before the sweep.
    # Supply the published stage X prior to each visit, preserving movement,
    # controller, callback, animation, contact history and damage timelines.
    actors=[setup_actor(i) for i in range(2)]
    if not armed:
        source=actors[slot]
        source.p.write(source.a+0x23c,source.p.read(source.a+0x23c,4)&~0x1000,4)
        assert not (int(rows[0][23+26*slot+5])&0x1000)
    for actor in actors:install_stage_facing(actor)
    geo=ContactOracle();p=geo.probe;initialize_pools(p)
    out=p.read(p.read(0x5d1bf8,4)+8,4)
    for off in (0,16):p.write(out+off,0x19e0000,4)
    instructions=0
    def run(pc,*argv):
        nonlocal instructions
        val,n=p.run(pc,argv,limit=1200000);instructions+=n
        return val
    contacts=[];begin=None;attacker_idle=None;victim_idle=None;actions=[];callbacks=[]
    press=delay+2
    for tick,(old,now,mask) in enumerate(zip(rows,rows[1:],held),1):
        # Collect against both complete previous-frame JDG sets in source order.
        hit=False
        if int(old[5+slot*10]) in (200,208,225,226):
            for i in (0,1):geo.install_player(old,i)
            p.write(0x12d2698,0,4)
            for pair in (OBJECTS,OBJECTS[::-1]):run(0x1536e8,*pair)
            run(0x1544a0)
            for idx in range(p.read(0x12d2698,4)):
                e=QUEUE+108*idx
                if p.read(e,4)!=7 or p.read(e+0x40,4)!=OBJECTS[slot]:continue
                if p.read(OBJECTS[slot]+0x104,4)&0x06000000:continue
                raw=p.read(e+0x20,4);guard=run(0x155850,e)
                assert guard==0 and raw in (16,25)
                run(0x155a88,e,1,0)
                original=ACTORS+target*0xf2c
                life=p.read(original+0xa38,4);state=p.read(original+0x192,2)
                assert int(old[9+target*10])-int(now[9+target*10])==life
                assert int(now[14 if target else 4])==state
                contacts.append(dict(tick=tick,raw=raw,route=7,damage=life,reaction=state,
                                     auxiliary=p.read(e+0x10,4),victim_action=int(old[5+10*target]),
                                     victim_step=int(old[6+10*target])))
                for i,actor in enumerate(actors):
                    a=ACTORS+0xf2c*i
                    offsets=[0x1b0,0x1b4]
                    if i==target:offsets += [0x18c,0x190,0x230,0x23c,0x244,0x250,0x254,0x258,0xa38]
                    for off in offsets:actor.p.write(actor.a+off,p.read(a+off,4),4)
                hit=True;break
        assert int(now[10+10*slot])-int(old[10+10*slot])==int(hit),(slot,delay,tick)
        for i,source in enumerate(actors):
            other=1-i;b=3+i*10;ob=3+other*10;f=23+26*i;of=23+26*other
            q=source.p
            q.write(source.o+0x40,int(old[f]),4)
            q.write(source.o+0x1040,int(old[of]),4)
            q.write(source.o+0x1044,int(old[of+1]),4)
            q.write(source.o+0x1038,int(old[of+2]),4)
            q.write(source.other+0x194,int(old[ob])|int(old[ob+1])<<16,4)
            q.write(source.other+0x19a,int(old[of+10]),1)
            q.write(source.other+0x23c,int(old[of+5]),4)
            q.write(source.other+0x244,int(old[of+7]),4)
            q.write(source.b+0x144,abs(int(float(old[b+4]))-int(float(old[ob+4]))),4)
            snap=source.frame(mask if i==slot else 0)
            c=88+27*i
            if i==slot and int(now[b+2])==225+int(not armed) and begin is None:begin=tick
            # Before the pursuit, the contact oracle establishes the actual
            # sweep/down sequence. Check both full clocks from the pursuit.
            if i==slot and (begin is None or attacker_idle is not None):continue
            if i==target and (begin is None or victim_idle is not None):continue
            cmp=[snap[0],*snap[54:57],*snap[12:19],snap[69]]
            actual=[int(now[b])|int(now[b+1])<<16,*map(int,now[b+2:b+4]),int(now[c+11]),
                    *map(int,now[c:c+7]),int(now[f+1])]
            assert cmp==actual,(slot,delay,tick,press,i,[(j,x,y) for j,(x,y) in enumerate(zip(cmp,actual)) if x!=y])
            if i==slot:
                if not callbacks or callbacks[-1][1]!=snap[12]:callbacks.append([tick,snap[12]])
                if snap[54]==int(not armed):attacker_idle=tick
            else:
                if not actions or actions[-1][1]!=snap[54]:actions.append([tick,snap[54]])
                if snap[54]==0:victim_idle=tick
    assert begin is not None and attacker_idle is not None and victim_idle is not None
    assert [(h['raw'],h['damage'],h['reaction']) for h in contacts]==([(25,11,60),(16,18 if armed else 11,61)] if delay==60 else [(25,11,60)])
    assert [cb for _,cb in callbacks]==[0x16b5b8,0x16b6b8,0x16b7d8,0x16b8c8,0x169a50,0]
    return dict(player=slot+1,armed=armed,delay_after_sweep=delay,press=press,attack_start=begin,contacts=contacts,
                attacker_idle=attacker_idle,victim_idle=victim_idle,victim_actions=actions,callback_changes=callbacks,
                original_instructions=instructions+sum(a.instructions for a in actors))

def fatal(args):
    exe,slot=args
    target=1-slot
    forward=(128,64)[slot];reverse=forward^192
    # Reach low life with five actual heavy hits, then move both combatants
    # back from the wall. The finished production match never receives writes.
    heavy=[(65,forward,0),(5,0,0),(1,1024,0),(90,0,0)]
    setup=[(500,0,0)]+heavy*5+[(360,reverse,0),(5,0,0),(97,0,reverse),(5,0,0),
                                (137,forward,0),(2,0,0),(1,forward|32|2048,0),(58,0,0),(1,reverse|32|1024,0)]
    commands=['%d %d %d'%((n,b,a) if slot else (n,a,b)) for n,a,b in setup+[(1,0,0)]*558]
    full=read(exe,['--whirlwind-fields'],commands)
    resource=read(exe,['--round-time','0'],commands)
    finished=read(exe,['--finish-fields'],commands)
    off=len(setup)-1;rows=full[off:];timed=resource[off:]
    vital=9+10*target;winner_base=3+10*slot;loser_base=3+10*target
    assert [int(full[i][vital]) for i in range(4,21,4)]==[162,127,92,57,24]
    assert int(rows[0][vital])==14
    impact=next(t for t,r in enumerate(rows) if int(r[vital])==0)
    assert int(rows[impact-1][vital])==14 and int(rows[impact][10+10*slot])==7
    g=ContactOracle();p=g.probe;initialize_pools(p)
    stdout=p.read(p.read(0x5d1bf8,4)+8,4)
    for off_ in (0,16):p.write(stdout+off_,0x19e0000,4)
    for i in range(2):g.install_player(rows[impact-1],i)
    ins=0
    def call(pc,*argv,stops=()):
        nonlocal ins
        val,n=p.run(pc,argv,stop_before=stops,limit=1200000);ins+=n;return val
    p.write(0x12d2698,0,4)
    call(0x1536e8,OBJECTS[slot],OBJECTS[target]);call(0x1544a0)
    assert p.read(0x12d2698,4)==1 and p.read(QUEUE,4)==7 and p.read(QUEUE+0x20,4)==16
    assert call(0x155850,QUEUE)==0
    call(0x155a88,QUEUE,1,0)
    live=ACTORS+0xf2c*target
    damage=p.read(live+0xa38,4)
    assert p.read(live+0x190,4)==(61<<16|2) and damage>=14
    winner_actor=ACTORS+0xf2c*slot
    record=p.read(0x4d3d00,4)+0x254+slot*0x108
    finish=[p.read(record+x,4) for x in (0x1c,0x20)]
    assert finish==list(map(int,finished[off+impact][77+4*slot:79+4*slot]))
    assert int(rows[impact][23+26*slot+8])&0x80000==p.read(winner_actor+0x248,4)&0x80000==0x80000
    # Verify the entire Japanese hurt callback until its KO hold. Whole battle
    # input above supplies all health loss; this separate EE actor fixture gets
    # exactly that hit request and damage, avoiding dependence on a global
    # presentation clock while independently exercising the original KO branch.
    actor=setup_actor(target);q=actor.p
    for off_ in (0x18c,0x190,0x230,0x23c,0x244,0x250,0x254,0x258,0xa30,0xa38,0x1b0,0x1b4):
        q.write(actor.a+off_,p.read(live+off_,4),4)
    first_hold=None;source_phases=[]
    for tick in range(54):
        snap=actor.frame(0)
        assert snap[0]==(61<<16|2) and q.read(actor.a+0xa30,4)==0
        phase=(snap[54],snap[12],snap[17])
        if phase not in source_phases:source_phases.append(phase)
        if phase==(418,0x169a50,7) and first_hold is None:first_hold=tick
    assert first_hold is not None
    # The independent KO watchdog also treats 2/61 as a protected state.
    q.write(actor.a+0x1ec,0x25800,4)
    actor.run(0x149980,actor.a);actor.run(0x14b880,actor.a)
    assert q.read(actor.a+0x190,4)==0xffffffff
    fatal_rows=[r for r in rows[impact:] if int(r[loser_base])==2 and int(r[loser_base+1])==61]
    c=88+27*target
    native_phases=[]
    for r in fatal_rows:
        phase=tuple(map(int,(r[loser_base+2],r[c],r[c+5])))
        if phase not in native_phases:native_phases.append(phase)
    assert native_phases==source_phases and all(int(r[loser_base+1]) not in (30,31) for r in rows[impact:])
    # Use the real scored HP and ordinary versus rules in the original round
    # result/next-round helpers. These helpers also establish where state 15
    # is requested and whether the final match screen would be entered.
    battle=p.read(0x4d3d00,4); won=ACTORS+0xf2c*slot
    for i in range(2):
        a=ACTORS+i*0xf2c;player=battle+0x254+i*0x108
        p.write(battle+0x24c+4*i,a,4);p.write(a+0xa30,int(rows[impact][9+10*i]),4)
        p.write(a+0xa34,200,4);p.write(player+0x28,0,4);p.write(player+0x2c,2,4)
        p.write(0x1fff000+4*i,a,4);p.write(0x1fff020+4*i,player,4)
    p.put(18,battle);call(0x143ce0,stops=(0x143d54,0x143d58))
    assert p.read(battle+0x24,4)==slot and p.registers[22]==15
    assert [p.read(battle+0x254+i*0x108+0x28,4) for i in range(2)]==[int(i==slot) for i in range(2)]
    winner_tick=next(t for t,r in enumerate(timed) if int(r[winner_base+9])==1)
    assert [int(timed[winner_tick][i]) for i in (1,27,28)]==[5,15,slot]
    p.write(live+0x23c,q.read(actor.a+0x23c,4),4)
    p.write(live+0x190,-1,4)
    call(0x1441e0,battle)
    assert p.read(live+0x190,4)==(15<<16|2)
    corpse_tick=next(t for t,r in enumerate(rows) if int(r[loser_base+1])==15)
    assert int(rows[corpse_tick][1])==7 and int(rows[corpse_tick][loser_base+2])==50
    p.write(battle,8,4);p.write(battle+0x18,0,4)
    for a in (won,live):p.write(a+0x244,0x40000000,4);p.write(a+0x2f0,0,4)
    call(0x144570,battle)
    assert p.read(battle+0x18,4)==1 and p.read(battle,4)==0
    next_tick=next(t for t,r in enumerate(timed) if int(r[26])==1 and int(r[1])==4)
    assert all(int(timed[next_tick][9+i*10])==200 for i in range(2))
    assert [int(timed[next_tick][12+i*10]) for i in range(2)]==[int(i==slot) for i in range(2)]
    return dict(player=slot+1,prefix_heavy_hits=5,sweep_remaining_life=14,original_damage=damage,
                impact_tick_after_input=impact+1,winner_tick_after_input=winner_tick+1,
                corpse_tick_after_input=corpse_tick+1,second_round_active_tick=next_tick+1,
                hurt_sequence=source_phases,outcome_fields=finish,original_instructions=ins+actor.instructions)

def main():
    assert digest(ELF)==PIN
    with tempfile.TemporaryDirectory() as tmp:
        exe=Path(tmp)/'replay';probe=Path(tmp)/'probe'
        shutil.copy2(REPLAY,exe);shutil.copy2(PROBE,probe)
        with ProcessPoolExecutor(max_workers=4) as pool:
            modes=list(pool.map(variant,[(probe,s,a) for s in range(2) for a in (False,True)]))
            matches=list(pool.map(playback,[(exe,s,d,a) for s in range(2) for d in (60,65) for a in (True,False)]))
            knockouts=list(pool.map(fatal,[(exe,s) for s in range(2)]))
        data=dict(status='passed',elf_sha256=PIN,validator_sha256=digest(Path(__file__)),replay_sha256=digest(exe),
                  variants=modes,matches=matches,knockouts=knockouts,original_instructions=sum(r['original_instructions'] for r in modes+matches+knockouts),
                  scope='Resource 00 / system 0, both sides. Two natural fatal sequences compare original damage, KO hold, lethal-hit classification, round result, corpse request and next-round selection with the native match returning to play. Raw input sweep followed by hit or whiff pursuit. Original pairwise collision/guard/damage plus two original actor clocks through recovery. Positions from the preceding native stage frame; armed/unarmed launch and fixed-point movement compared separately.')
    REPORT.write_text(json.dumps(data,indent=2)+'\n')
    print('4 callback trajectories, 8 hit/whiff replays and 2 full pursuit KO rounds PASS')

if __name__=='__main__':main()
