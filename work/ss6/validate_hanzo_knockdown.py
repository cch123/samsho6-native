#!/usr/bin/env python3
"""Run Japanese fall row zero and the special's real disarm/KO through a selected mirror match."""
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from validate_dash_motion import ELF, PIN, ROOT, digest
from validate_finishing_blow import actor, stats, put, initialize_effects, OBJECTS
from validate_hanzo_projectile_scene import encode
from validate_hanzo_specials import BUILD, pads
from validate_haohmaru_flask import FlaskContacts, children
from validate_knockdown import main as compare_fall
from validate_nakoruru_combat import MixedContactOracle
from validate_selected_combat import prefix

OUT=ROOT/'outputs/ss6-feasibility'
ASSETS=OUT/'native-viewer/assets'
EXE=BUILD/'ss6-match-replay'
class FireContact(FlaskContacts,MixedContactOracle):
    def __init__(self,side):
        super().__init__((3,3));self.side=side
        self.aid,self.act,self.jdg=self.banks[0]
        p=self.probe;initialize_effects(p)
        for fn in (0x1123a8,0x112570,0x11e290):p.run(fn,limit=500000)
        for n,name in enumerate(('01HitFlash.bin','02Guard.bin','03etc.bin')):
            at=0x4a4810+n*0x3da0;p.memory[at:at+0x3da0]=(ASSETS/name).read_bytes()
        for n in range(32):p.write(0x4c3510+n*4,n+1,4)
        output=p.read(p.read(0x5d1bf8,4)+8,4);put(p,output,[(0,0x19e0000),(16,0x19e0000)])
    def install_player(self,row,slot):
        super().install_player(row,slot)
        self.probe.write(actor(slot)+0x10c,2 if self.side==slot else 5,4)
        self.probe.write(actor(slot)+0xa34,200,4)
    def strike(self,last,now,finish_before,finish,blocked=False):
        p=self.probe;side=self.side;victim=1-side
        for s in range(2):
            put(p,stats(s),list(zip((12,24,28,32),map(int,finish_before[75+4*s:79+4*s]))))
        events=self.install(last)
        for e in events:
            obj=p.read(e+0x40,4)
            if (p.read(e,4),p.read(obj+0xcc,4),p.read(obj+0xd0,4),p.read(e+0x68,4))==(7,2,135,OBJECTS[victim]):break
        else:raise AssertionError(('missing original route-7 projectile/body event',events))
        assert p.run(0x14dc00,[obj])[0]==11
        assert p.run(0x1690b0,[3,p.read(obj+0x24,4)])[0]==1
        defense=p.run(0x155850,[e])[0];assert bool(defense)==blocked
        seen=set();_,steps=p.run(0x155d50 if blocked else 0x155a88,[e,0,defense],limit=1000000,observe=lambda pc:seen.add(pc))
        owner,v=actor(side),actor(victim)
        hp=int(last[9+10*victim]);damage=p.read(v+0xa38,4)
        assert int(now[9+10*victim])==max(0,hp-damage),(side,hp,damage,now[9+10*victim])
        assert p.read(owner+0x1b0,4)==p.read(obj+0xdc,4), (side,hp,damage,p.read(e+0x20,4),p.read(owner+0x1b0,4),p.read(obj+0xdc,4),0x1690b0 in seen,int(now[96+27*side]),int(last[96+27*side]))
        assert p.read(owner+0x1b4,4)==int(last[97+27*side])
        p.write(owner+0x1ac,128 if p.read(owner+0x1b4,4) else 256,4);p.run(0x151eb0,[owner])
        assert [p.read(owner+off,4) for off in (0x1b0,0x1b4)]==list(map(int,now[96+27*side:98+27*side]))
        outcome=list(map(int,finish[77+4*side:79+4*side]))
        assert [p.read(stats(side)+off,4) for off in (28,32)]==[i&0xffffffff for i in outcome]
        if hp<=damage:assert outcome==[1,0] and 0x14dc00 in seen
        return dict(hit_tick=int(now[0]),hp_before=hp,original_pending_damage=damage,hp_after=int(now[9+10*victim]),
                    actual_attack_act=724,original_category=11,hitstop=p.read(obj+0xdc,4),raw_type=p.read(e+0x20,4),shared_hitstop_call=0x1690b0 in seen,finish_outcome=outcome,
                    original_instructions=steps)

def replay(seq,trace,dense=True):
    inputs=''.join(f'1 {a} {b}\n' for a,b in seq) if dense else encode(seq)
    res=subprocess.run([EXE,ASSETS,'--mode','select',trace],input=inputs,text=True,capture_output=True)
    assert res.returncode==0,res.stderr
    return [line.split() for line in res.stdout.splitlines()]

def live(side,ko,blocked=False):
    q=prefix((3,3))
    for i in (211,222,233):q[i-1][side]=128
    pair=lambda a,b=0:(b,a) if side else (a,b)
    victim=1-side;v=9+10*victim
    if ko:
        # Wear down the defender before charging the Zan fighter. This leaves
        # the weapon in hand until the projectile clears the original armed bit.
        for n in range(18):
            q += [(128,64)]*40+[pair(0)]*10+[pair(1024)]+[pair(0)]*67
            hp=int(replay(q,'--finish-fields',False)[-1][v])
            if 0<hp<=40:break
        else:raise AssertionError('failed to reach the lethal range')
    move,start=pads(side,90,'near')
    # Chasing the wounded opponent can cross sides. Read the last facing
    # after the charge, then enter a facing-relative quarter circle.
    q+=move[1250:start]
    standing=replay(q,'--finish-fields',False)[-1]
    mirror=bool(int(standing[25+26*side])&0x80000)
    f=64 if mirror else 128
    attack_start=len(q);q += [pair(key,f if blocked else 0) for key in [32,32|f,f|768]+[0]*710]
    objs=replay(q,'--whirlwind-fields');fin=replay(q,'--finish-fields')
    hit=next(i for i in range(attack_start,len(objs)) if int(objs[i][v])<int(objs[i-1][v]))
    a,b=objs[hit-1:hit+1]
    assert any(o[0x24//4]==724 and o[0xd0//4]==135 for o in children(a))
    check=FireContact(side).strike(a,b,fin[hit-1],fin[hit],blocked)
    flags=28+26*victim
    assert int(a[flags])&0x1000 and bool(int(b[flags])&0x1000)==blocked
    def weapons(i):
        extras=replay(q[:i+1],'--shin-fields',False)[-1][len(objs[i]):]
        for player in (0,1):
            count=int(extras[1]);items=[int(extras[2+7*n]) for n in range(count)];extras=extras[2+7*count:]
            if player==victim:return [act for act in items if 460<=act<=471]
    weapon_at_hit=weapons(hit)
    assert bool(weapon_at_hit)!=blocked and not weapons(hit-1),(side,ko,weapon_at_hit)
    pose=3+10*victim
    posture=[(int(r[0]),*map(int,r[pose:pose+3])) for r in objs[hit:]]
    changes=[r for i,r in enumerate(posture) if i==0 or r[1:]!=posture[i-1][1:]]
    if blocked:
        assert changes[0][1:]==(2,0,288) and changes[-1][1]==0
        assert check['shared_hitstop_call'] and check['hitstop']>0
    elif not ko:
        assert changes[0][1:]==(2,62,381)
        assert any(r[1:]==(2,16,49) for r in changes) and any(r[1:]==(2,7,53) for r in changes)
        assert changes[-1][1]==0 and int(objs[-1][v])>0
    else:
        assert changes[0][1:]==(2,62,381) and check['hp_after']==0 and any(r[1:3]==(2,15) for r in changes)
        assert int(objs[-1][v])==200
    return dict(attacker=side+1,lethal=ko,blocked=blocked,contact=check,weapon_acts_at_hit=weapon_at_hit,posture_after_hit=changes)
def main():
    assert digest(ELF)==PIN
    # The production runtime is the probe's only code dependency. No game
    # logic is replaced; the input protocol exposes commits between updates.
    with tempfile.TemporaryDirectory() as t:
        prog=Path(t)/'fall'
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',ROOT/'src/knockdown_probe.cpp',
                        BUILD/'libss6-runtime.a','-o',prog],check=True)
        result=compare_fall(62,prog)
    cases=[live(side,ko,guard) for side in (0,1) for ko,guard in ((False,False),(True,False),(False,True))]
    doc=dict(passed=True,elf=PIN,viewer_sha256=digest(OUT/'native-viewer/ss6-viewer'),replay_sha256=digest(EXE),
             original_fall=result,selected_mirrors=cases)
    (OUT/'hanzo-knockdown-validation.json').write_text(json.dumps(doc,indent=2)+'\n')
    print(cases)

if __name__=='__main__':main()
