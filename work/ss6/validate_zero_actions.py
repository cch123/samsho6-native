#!/usr/bin/env python3
"""Play Zero directional evasion and meditation through native inputs and the Japanese actor loop."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import json
from itertools import groupby
import os
from pathlib import Path
import shlex
import shutil
import struct
import subprocess
import tempfile

from validate_console_versus_session import OPTIONS
from validate_dash_motion import ASSETS, ELF, PIN, ROOT, digest
from validate_shin_evasion import EXE, replay, setup_state
from validate_haohmaru_special import ContactOracle
from validate_collisions import ACTORS
from validate_weapon_handling import setup

OUT = ROOT/'outputs/ss6-feasibility/zero_actions_validation.json'
MOVES = {1:(58,64),2:(56,60),3:(57,62),4:(60,66),5:(60,66),
         6:(59,68),7:(60,66),8:(60,66),9:(60,66)}
NAMES = ('前転','後転','伏せ','飛び込み','下段避け','怒り爆発','瞑想')


def menu():
    image = ELF.read_bytes()
    def string(pointer):
        start = pointer-0xff000
        return image[start:image.index(0,start)].decode('cp932')
    entries = [tuple(map(string,struct.unpack_from('<III',image,0x3cbea0+20*i))) for i in range(len(NAMES))]
    assert tuple(pair[0] for pair in entries)==NAMES
    assert [pair[2] for pair in entries[:5]]==['I3PLIE','I1PLIE','I2PLIE','I6PLIE','I4PLIE']
    assert 'IAIB同時押し' in entries[-1][2] and '押し続け' in entries[-1][2]
    return entries


def sequence(slot,move,bare):
    front=(128,64)[slot];back=front^192
    def pair(n,own=0,opponent=0):
        return (n,opponent,own) if slot else (n,own,opponent)
    initial=[pair(500)]
    if bare:initial += [pair(1,front|8),pair(135)]
    if isinstance(move,int):
        h={1:back|32,2:32,3:front|32,4:back,5:0,6:front,7:back|16,8:16,9:front|16}[move]
        # Space the fighters away from each other's body and the stage walls.
        spacing = (front,back) if move==1 else (back,front)
        initial += [pair(14,*spacing),pair(8)]
        controls=[4096|h]+[0]*55
    else:
        if move!='empty':
            # Win the partial rage bar by taking a real slash, then let the
            # complete hurt animation recover before pressing both buttons.
            initial += [pair(42,front,back),pair(8),pair(1,0,256),pair(110)]
        if bare:initial += [pair(30,back,front),pair(8)]
        held=1 if move=='tap' else 20 if move=='release-A' or move=='release-B' else 170
        after={'release-A':512,'release-B':256}.get(move,0)
        controls=[768]*held+[after]*10+[0]*12
    return initial,controls,[pair(1,h) for h in controls]


def case(args):
    slot,move,bare=args
    initial,controls,segments=sequence(slot,move,bare)
    rows=replay(slot,'zero',initial+segments)[len(initial)-1:]
    core,c,cb=3+10*slot,23+26*slot,88+27*slot
    source,_=setup(slot);setup_state(source,4,0,rows[0],slot,bare)
    p,a=source.p,source.a
    meditation=isinstance(move,str)
    # Use the same factory save initialization and first-round meter reset
    # as genuine VS. A zero-filled options area loses the 20-point reserve.
    source.run(0x1113e8,OPTIONS)
    source.run(0x14ec28,a+0x10c)
    source.run(0x14ec80,a+0x10c)
    assert p.read(a+0x140,4)==20*256
    p.write(a+0x120,int(rows[0][c+16]),4);p.write(a+0x124,int(rows[0][c+17]),4)
    p.write(a+0xa30,int(rows[0][core+6]),4)
    zero=[]
    if meditation:
        commands=''.join(f'{n} {left} {right}\n' for n,left,right in initial+segments)
        trace=subprocess.run([EXE,ASSETS,'--mode','versus',f'--p{slot+1}-spirit','zero','--zero-fields'],
                             input=commands,capture_output=True,text=True,check=True)
        zero=[list(map(int,line.split()[23+8*slot:31+8*slot])) for line in trace.stdout.splitlines()][len(initial)-1:]
        assert zero[0][1]==p.read(a+0x140,4)
    if meditation and move!='empty':assert 0<int(rows[0][c+17])<0xb800 and int(rows[0][core+6])<200
    previous=None;changes=[];origin=int(rows[0][0]);converting=0
    start_rage=int(rows[0][c+17]);start_amount=p.read(a+0x140,4)
    for tick,(word,now) in enumerate(zip(controls,rows[1:])):
        if meditation:source.run(0x11e760,slot)
        v=source.frame(word)
        actual=[int(now[core])|(int(now[core+1])<<16),*map(int,now[core+2:core+4]),int(now[cb+11]),
                *map(int,now[cb:cb+3]),int(now[c+10]),int(now[c+5])&0x9018,int(now[c]),int(now[c+1])]
        expected=[v[0],v[54],v[55],v[56],*v[12:15],v[4],v[5]&0x9018,v[68],v[69]]
        if meditation:
            actual.extend((int(now[c+17]),zero[tick+1][1]));expected.extend((p.read(a+0x124,4),p.read(a+0x140,4)))
        assert actual==expected,(args,tick,[(j,h,w) for j,(h,w) in enumerate(zip(actual,expected)) if h!=w])
        current=(v[0]>>16,v[54],v[12],bool(v[5]&0x8000))
        if current!=previous:changes.append((tick+1,*current));previous=current
        converting+=bool(v[5]&0x8000)
        if tick>0 and v[0]==0 and v[54]==int(bare):break
    if meditation:
        assert changes[0][1:3]==(62,144+bare) and changes[1][1:3]==(62,146+bare)
        assert changes[1][0]==15 and changes[-1][1:3]==(0,int(bare)),(args,changes)
        if move in ('release-A','release-B'):assert converting==6,(args,converting,changes)
        if move=='deplete':assert p.read(a+0x124,4)==0
    else:
        state,act=MOVES[move];assert changes[0][1:3]==(state,act+bare) and changes[-1][1:3]==(0,int(bare))
    return dict(player=slot+1,command=move,armed=not bare,first_update=origin+1,visits=tick+1,
                timeline=changes,original_instructions=source.instructions,
                rage=[start_rage,p.read(a+0x124,4)],concentration=[start_amount,p.read(a+0x140,4)])


def posture(args):
    slot,name=args
    front=(128,64)[slot];back=front^192
    def pair(n,own=0,opponent=0):return (n,opponent,own) if slot else (n,own,opponent)
    initial=[pair(500),pair(18,back,front),pair(9)]
    startup={'airborne':[16]*10,'crouching':[32]*10,'running':[0,front,0]+[front]*10}[name]
    command=len(startup)
    inputs=startup+[front|4096]+[0]*65
    rows=replay(slot,'zero',initial+[pair(1,h) for h in inputs])[len(initial)-1:]
    source,_=setup(slot);setup_state(source,4,0,rows[0],slot,False)
    base,c=3+slot*10,23+26*slot
    # Both worlds begin in the same idle loop but the match has already
    # advanced through spacing and recovery. Align its current idle record.
    source.p.write(source.o+0x28,int(rows[0][base+3]),4)
    source.p.write(source.o+0x2c,int(rows[0][88+27*slot+11]),4)
    moves=[]
    for t,(held,row) in enumerate(zip(inputs,rows[1:])):
        v=source.frame(held)
        got=(int(row[base+1]),int(row[base+2]),int(row[base+3]),int(row[c]),int(row[c+1]))
        want=(v[0]>>16,v[54],v[55],v[68],v[69])
        assert got==want,(args,t,got,want)
        if not moves or moves[-1][1]!=got[:2]:moves.append((t+1,got[:2]))
        if t>command and not want[0] and not want[1]:break
    if name=='airborne':assert all(state!=59 for _,(state,_) in moves)
    else:assert (command+1,(59,68)) in moves
    assert moves[-1][1]==(0,0)
    return dict(player=slot+1,prior_posture=name,command='6+E',visits=t+1,
                timeline=moves,original_instructions=source.instructions)


class ZeroContacts(ContactOracle):
    def __init__(self,zero_slot):
        super().__init__()
        self.zero_slot=zero_slot

    def install_player(self,row,slot):
        super().install_player(row,slot)
        actor=ACTORS+0xf2c*slot
        self.probe.write(actor+0x10c,4 if slot==self.zero_slot else 0,4)
        if slot==self.zero_slot and self.probe.read(actor+0x23c,4)&0x8000:
            # On a contact update the priority-5 transfer precedes damage
            # awards. The published geometry still belongs to the last update.
            self.probe.write(0x1b80000,4,4)
            self.probe.run(0x11e760,[slot])


def under_attack(args):
    slot,direction,attack,delay=args
    front=(128,64)[slot];back=front^192
    def pair(n,own=0,opponent=0):return (n,opponent,own) if slot else (n,own,opponent)
    evade={0:0,1:4096|32|back,2:4096|32,3:4096|32|front,4:4096|back,6:4096|front}[direction]
    segments=[pair(500),pair(42,front,back),pair(8)]
    segments.extend(pair(1,evade if i==delay else 0,attack if i==0 else 0) for i in range(90))
    rows=replay(slot,'zero',segments)
    contacts=ZeroContacts(slot).contacts(rows,1-slot)
    assert len(contacts)==int(rows[-1][10+10*(1-slot)])
    if not direction:assert len(contacts)==1
    return dict(player=slot+1,direction=direction,attack_pad=attack,delay=delay,
                contacts=contacts,remaining_life=int(rows[-1][9+10*slot]))


def interrupted(args):
    slot,delay=args
    initial,_,_=sequence(slot,'release-A',False)
    front=(128,64)[slot]
    def pair(n,own=0,opponent=0):return (n,opponent,own) if slot else (n,own,opponent)
    initial+=[pair(32,front,front^192),pair(8)]
    seq=[pair(1,768 if i<32 else 0,256 if i==delay else 0) for i in range(100)]
    rows=replay(slot,'zero',initial+seq)[len(initial)-1:]
    contacts=ZeroContacts(slot).contacts(rows,1-slot)
    assert len(contacts)==1
    n=contacts[0]['frame']-int(rows[0][0]);base=3+10*slot;flags=28+26*slot
    assert rows[n-1][base:base+2]==['0','62']
    assert int(rows[n][base])==2 and not int(rows[n][flags])&0x8000
    assert bool(int(rows[n-1][flags])&0x8000)==bool(delay)
    assert rows[-1][base:base+2]==['0','0']
    return dict(player=slot+1,attack_delay=delay,interrupted_action=int(rows[n-1][base+2]),
                contacts=contacts,ending_life=int(rows[-1][base+6]))


def original_limits():
    results=[]
    # These exact boundary inputs cannot all be produced from fresh round
    # health. Exercise the Japanese input, animation and callback together.
    for rage,amount,concentration,remaining in [(0,0,0,False),(1,0xb800,0,False),
                                                (0,1,0xc7ff,True),(0,1,0xc800,False)]:
        s,_=setup(0);p,a=s.p,s.a
        p.write(a+0x10c,4,4);s.run(0x179258,a+0x2c4,a+0x10c)
        for off,value in ((0x120,rage),(0x124,amount),(0x140,concentration)):p.write(a+off,value,4)
        observed=[]
        for i in range(18):
            v=s.frame(768);observed.append([v[0]>>16,v[54],int(bool(v[5]&0x8000))])
        assert observed[:14]==[[62,144,0]]*14 and observed[14]==[62,146,1]
        assert (observed[15]==[62,146,1])==remaining
        results.append(dict(rage_state=rage,rage=amount,concentration=concentration,
                            sustained=remaining,visits=18,instructions=s.instructions))
    return results


def keyboard_checks():
    from validate_versus_heavy import HERE, PKG, run
    from validate_shin_window import keyboard
    from validate_zan_window import verify_keys
    build=EXE.parent
    records=[]
    with tempfile.TemporaryDirectory(prefix='ss6-zero-keys-') as tmp:
        d=Path(tmp);shutil.copy2(PKG/'ss6-viewer',d/'viewer')
        viewer_hash=digest(d/'viewer')
        flags=shlex.split(run(['pkg-config','--cflags','--libs','sdl3'],text=True).stdout)
        run([*shlex.split(os.environ.get('CXX','c++')),'-std=c++20','-O2','-I',ROOT/'src',
             HERE/'sdl_slash_input_test.cpp',build/'libss6-runtime.a',*flags,'-o',d/'keys'])
        for side in (0,1):
            for move in [*MOVES,'sustain','release-A','release-B']:
                initial,_,segments=sequence(side,'release-A' if move=='sustain' else move,False)
                offset=20 if move=='sustain' else 21 if isinstance(move,str) else 5
                tick=sum(n for n,_,_ in initial)+offset
                seq=initial+segments
                actors=verify_keys(d,side,seq,tick,'zero',PKG/'assets')
                want=(62,146) if move=='sustain' else (0,0) if isinstance(move,str) else MOVES[move]
                assert tuple(actors[side][1:3])==want,(side,move,tick,actors)
                records.append(dict(side=side+1,move=move,tick=tick,state_action=want,
                                    keys=keyboard(segments[:offset]),bitmap_sha256=digest(d/'snapshot.bmp')))
    return records,viewer_hash


def gamepad_checks():
    from validate_versus_gamepads import Original,SOFTWARE,evaluate,op
    from validate_versus_heavy import HERE,PKG,run
    oracle=Original();results=[]
    with tempfile.TemporaryDirectory(prefix='ss6-zero-pads-') as tmp:
        work=Path(tmp);harness=work/'pads'
        flags=shlex.split(run(['pkg-config','--cflags','--libs','sdl3'],text=True).stdout)
        run([*shlex.split(os.environ.get('CXX','c++')),'-std=c++20','-O2','-I',ROOT/'src',
             HERE/'sdl_gamepad_input_test.cpp',EXE.parent/'libss6-runtime.a',*flags,'-o',harness])
        for side in (0,1):
            for command in [*MOVES,'release-A','release-B','L1']:
                name='release-A' if command=='L1' else command
                initial,_,seq=sequence(side,name,False)
                events=['+1 N1'];previous=(0,0)
                for masks,group in groupby(initial[1:]+seq,key=lambda row:row[1:]):
                    count=sum(row[0] for row in group)
                    if command=='L1' and masks[side]==768:
                        masks=(0,16384) if side else (16384,0)
                    commands=[op(s,bit,bool(masks[s]&mask)) for s in range(2)
                              for bit,mask in enumerate(SOFTWARE) if (previous[s]^masks[s])&mask]
                    events.append(' '.join([*commands,f'N{count}']))
                    previous=masks
                r,rows,_=evaluate(harness,work,oracle,str(command),events,special_slot=side,
                                  spirit='zero',assets=PKG/'assets')
                actor=2+9*side
                expect=MOVES[command] if isinstance(command,int) else (62,146)
                acted=[x[1] for x in rows if tuple(x[actor+1:actor+3])==expect]
                assert acted and rows[-1][actor:actor+3]==[0,0,0],(side,command,expect)
                results.append(dict(player=side+1,command=command,observed_updates=acted,**r))
    return results


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--without-keyboard',action='store_true')
    args=parser.parse_args()
    assert digest(ELF)==PIN
    help_rows=menu()
    jobs=[(side,move,bare) for side in (0,1) for bare in (False,True)
          for move in [*MOVES,'empty','tap','release-A','release-B','deplete']]
    with ProcessPoolExecutor(max_workers=min(os.cpu_count() or 2,6)) as workers:
        data=list(workers.map(case,jobs))
        combat=list(workers.map(under_attack,[(side,direction,attack,delay)
                    for side in (0,1) for direction in (0,1,2,3,4,6)
                    for attack,delay in ((1024,0),(1056,0),(2080,4))]))
        postures=list(workers.map(posture,[(s,n) for s in (0,1) for n in ('airborne','crouching','running')]))
        interruptions=list(workers.map(interrupted,[(s,d) for s in (0,1) for d in (0,17)]))
    results=dict(japanese_elf_sha256=PIN,replay_sha256=digest(EXE),menu=help_rows,
                 actor_cases=data,combat_cases=combat,postures=postures,interruptions=interruptions,original_limits=original_limits())
    if not args.without_keyboard:
        results['keyboard'],results['viewer_sha256']=keyboard_checks()
        results['gamepads']=gamepad_checks()
        OUT.write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
    print('Verified',len(data),'original actor traces and',len(results.get('keyboard',[])),'keyboard traces.')


if __name__=='__main__':main()
