#!/usr/bin/env python3
"""Compare physical Japanese preset 0 to SDL virtual pads in the production versus loop."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shlex
import struct
import subprocess
import tempfile

from mips_probe import Probe
from validate_dash_motion import ASSETS, ELF, PIN, ROOT, digest
from validate_input_features import FEATURES, PADS
from validate_versus_heavy import BUILD, DUMMY, PKG, pixels
from validate_shin_specials import objects

HERE=Path(__file__).resolve().parent
REPORT=ROOT/'outputs/ss6-feasibility/versus_gamepads_validation.json'
ZAN_REPORT=REPORT.with_name('zan_gamepads_validation.json')
BUTTONS=('L2','R2','L1','R1','Triangle','Circle','Cross','Square','Select','L3','R3','Start','Up','Right','Down','Left')
# The first eight values are the independent normalized inputs of NativeMatch's
# replay API. The physical comparison goes through 1034a8 and does not use them.
SOFTWARE=(32768,8192,16384,4096,512,1024,2048,256,0,0,0,8,16,128,32,64)
KEYS={'J':(0,7),'I':(1,5),'L':(0,5),'O':(1,7)}


def run(args,**kwargs):
    p=subprocess.run(args,capture_output=True,text=True,timeout=90,**kwargs)
    if p.returncode:raise RuntimeError(f'{args[0]} exited {p.returncode}\n{p.stdout[-1800:]}\n{p.stderr[-1800:]}')
    return p.stdout


class Original:
    def __init__(self):
        assert digest(ELF)==PIN
        self.p=Probe(ELF.read_bytes())
        calls=[]
        _,self.operations=self.p.run(0x177118,observe=lambda pc:calls.append(pc) if pc in (0x178d38,0x178e50) else None)
        assert calls==[0x178d38,0x178e50,0x178d38,0x178e50],calls
        self.defaults=[struct.unpack_from('<8I',self.p.memory,0x4eaac0+32*s) for s in range(2)]
        assert self.defaults[0]==self.defaults[1]==(1024,512,2,4,4194304,8388608,1048576,2097152)
        self.physical=struct.unpack_from('<16I',self.p.memory,0x345448)
        self.calls=0

    def features(self,slot,held,pressed):
        p=self.p
        for off,bits in ((0,held),(4,pressed)):p.write(0x3aa0a0+0x60*slot+off,bits,4)
        buf,n=p.run(0x1034a8,[slot]);self.operations+=n
        assert buf==0x114ec30+52*slot
        for off,src in ((0,8),(4,16)):p.write(PADS+12*slot+off,p.read(buf+src,4),4)
        _,n=p.run(0x177908,[slot,slot,slot,0,0,-1]);self.operations+=n
        self.calls+=1
        def packed(off,length):return sum(int(bool(p.read(FEATURES+off+4*j,4)))<<j for j in range(length))
        return (packed(0x16c,6),packed(0x18,6),packed(0x14c,8))


def virtual_value(bit,down):
    if bit<2:return 32767 if down else -32768
    return int(down)


def op(slot,bit,down):
    return f'{slot}.{bit}={virtual_value(bit,down)}'


def normalized(physical):
    return sum(bit for j,bit in enumerate(SOFTWARE) if physical&(1<<j))


class Inputs:
    """Track physical levels per connected pad and apply keyboard ownership before PS2 decoding."""
    def __init__(self):
        self.seats=[0,None]
        self.devices={0:0}
        self.keys=[0,0]
        self.edge=[0,0]

    def current(self):
        return [(self.devices[s] if s is not None else 0)|self.keys[i] for i,s in enumerate(self.seats)]

    def apply(self,action):
        previous=self.current()
        if action[0] in '+-':
            dev=int(action[1:])
            if action[0]=='+':self.devices[dev]=0
            else:
                del self.devices[dev]
                self.seats=[None if x==dev else x for x in self.seats]
            for d in self.devices:
                if d not in self.seats and None in self.seats:self.seats[self.seats.index(None)]=d
        elif action[0]=='K':
            side,bit=KEYS[action[1:-1]]
            if action[-1]=='+':self.keys[side]|=1<<bit
            else:self.keys[side]&=~(1<<bit)
        else:
            physical,value=action.split('=');device,bit=map(int,physical.split('.'))
            # SDL's signed virtual axis maps raw 0 -> 16383, raw +1 -> 16384.
            if (int(value)>=1 if bit<2 else int(value)!=0):self.devices[device]|=1<<bit
            else:self.devices[device]&=~(1<<bit)
        for s,h in enumerate(self.current()):self.edge[s]|=h&~previous[s]


def evaluate(harness,work,original,name,lines,*,match=None,special_slot=None,spirit='zan',captures=(),assets=None):
    setup=work/'start.pad';setup.write_text('500 0 0\n')
    sequence=work/'gamepad.input';sequence.write_text('\n'.join(lines)+'\n')
    if assets is None:assets=PKG/'assets' if special_slot is not None else ASSETS
    flags=[] if special_slot is None else [f'--p{special_slot+1}-spirit',spirit]
    capture_args=[value for frame in captures for value in ('--capture',str(frame),work/f'pad-{frame}.bmp')]
    actual=run([harness,assets,setup,sequence,*flags,*capture_args],env=DUMMY)
    scene=[list(map(int,l.split()[1:])) for l in actual.splitlines() if l.startswith('render ')]
    events=list(map(int,next(l for l in actual.splitlines() if l.startswith('events ')).split()[1:]))
    assert len(scene)==len(lines)+1 and scene[0][:2]==[0,500]
    expected=Inputs();tick=500;replay=['500 0 0']
    for frame,line in enumerate(lines,1):
        parts=line.split()
        for token in parts[:-1]:expected.apply(token)
        assert parts[-1].startswith('N');count=int(parts[-1][1:]);tick+=count
        words=scene[frame]
        assert words[:2]==[frame,tick],(name,frame,line,words)
        held=expected.current()
        for side in range(2):
            # 177908's published held/edge/absolute-direction fields for the
            # last simulated tick are independent of earlier four-tick latches.
            want=original.features(side,held[side],expected.edge[side] if count==1 else 0)
            got=tuple(words[8+9*side:11+9*side])
            assert want==got,(name,frame,side,line,hex(held[side]),expected.edge,want,got)
        replay.append(f'{count} {normalized(held[0])} {normalized(held[1])}')
        expected.edge=[0,0]
    assert events[0]>=2 and (events[2] or events[4]),(name,events)
    result=dict(name=name,visits=len(lines),ticks=tick-500,sdl_events=events)
    if special_slot is not None:
        options=['--mode','versus',*flags]
        reference=run([BUILD/'ss6-match-replay',assets,*options,'--shin-fields'],input='\n'.join(replay)+'\n').splitlines()
        images={}
        for frame,(got,row) in enumerate(zip(scene,reference,strict=True)):
            ref=row.split()
            for side,(_,blades) in enumerate(objects(ref)):
                k=3+10*side;c=23+26*side
                want=list(map(int,ref[k:k+3]+ref[k+6:k+9]))
                assert got[2+9*side:8+9*side]==want,(name,frame,side,'fighter',got,want)
                floor=[b[0] for b in blades if b[0] in (466,467)]
                assert len(floor)<=1
                fields=[{'zan':2,'ten':3,'zero':4,'ken':5}[spirit] if side==special_slot else 0,int(ref[c+16]),int(ref[c+17]),int(bool(int(ref[c+5])&0x1000)),floor[0] if floor else 0]
                assert got[20+5*side:25+5*side]==fields,(name,frame,side,'weapon and gauge',got,fields)
            if frame in captures:
                cutoff=work/'reference.pad'
                cutoff.write_text('\n'.join(replay[:frame+1])+'\n')
                target=work/'reference.bmp'
                run([PKG/'ss6-viewer','--assets',assets,*options,'--match-replay',cutoff,'--snapshot',target],env=DUMMY)
                actual_pixels=pixels(work/f'pad-{frame}.bmp')
                assert actual_pixels==pixels(target),(name,frame,'window pixels')
                images[frame]=hashlib.sha256(actual_pixels).hexdigest()
        return result,scene,images
    if match:
        # These scenarios hold buttons until a simulated tick; a normalized
        # replay can therefore independently check every observed fighter state.
        reference=run([BUILD/'ss6-match-replay',ASSETS,'--mode','versus'],input='\n'.join(replay)+'\n').splitlines()
        for frame,(got,ref) in enumerate(zip(scene,reference,strict=True)):
            ref=ref.split()[:23]
            for i in range(2):
                k=3+10*i
                want=list(map(int,ref[k:k+3]+ref[k+6:k+9]))
                assert got[2+9*i:8+9*i]==want,(name,frame,i,want,got)
        i,act,hp,enemy_hits=match
        sample=scene[-1];actors=[sample[2+9*s:8+9*s] for s in range(2)]
        assert actors[i][2]==act,(name,match,actors)
        if hp is not None:assert actors[1-i][3]==hp and actors[i][4]==enemy_hits,(name,match,actors)
        if name.endswith('dual-guard'):
            assert actors[i][5]==1 and actors[1-i][0:3]==[2,2,288],(name,actors)
        result['final_actors']=actors
    return result


def mapping_steps():
    steps=['+1 N1']
    for bit in range(len(BUTTONS)):
        other=(bit+5)%len(BUTTONS)
        steps += [f'{op(0,bit,True)} {op(1,other,True)} N1','N1',
                  f'{op(0,bit,False)} {op(1,other,False)} N1']
    for bit in (0,1):
        for value in [-32768,-1,0,1,2,32767,1,0,-1,-32768]:
            steps.append(f'0.{bit}={value} 1.{bit}={value} N1')
    # The chord remains a separate physical input while one constituent is
    # already held; releasing either owner must preserve the other owner's level.
    steps += ['0.7=1 1.5=1 N1','0.2=1 1.1=32767 N1','0.7=0 1.5=0 N1',
              '0.2=0 1.1=-32768 N1','0.7=1 0.7=0 1.5=1 1.5=0 N1','N1',
              'KJ+ KI+ N1','0.7=1 1.5=1 N1','KJ- KI- N1','0.7=0 1.5=0 N1',
              '0.7=1 1.5=1 N1','KJ+ KI+ N1','0.7=0 1.5=0 N1','KJ- KI- N1',
              '0.15=1 0.14=1 1.13=1 1.12=1 N1','0.15=0 0.14=0 1.13=0 1.12=0 N1']
    return steps


def gameplay(slot):
    front=(13,15)[slot];back=28-front
    def change(count,*changes):
        return ' '.join([*[op(slot,b,state) for b,state in changes],f'N{count}'])
    startup=['+1 N1']
    return [
        ('close-heavy',startup+[change(50,(front,1)),change(4,(front,0)),change(1,(5,1)),change(20,(5,0))],(slot,189,162,1)),
        ('dual-guard',startup+[change(50,(front,1)),change(4,(front,0)),
                               f'{op(slot,5,1)} {op(1-slot,front,1)} N1',change(20,(5,0))],(slot,189,200,0)),
        ('L1-combined',startup+[change(1,(2,1))],(slot,264,None,0)),
        ('R2-forward-throw',startup+[change(70,(front,1)),change(1,(1,1)),change(3,(front,0),(1,0))],(slot,232,200,0)),
        ('R1-parry',startup+[change(1,(14,1)),change(1,(front,1)),change(1,(14,0),(3,1))],(slot,126,None,0)),
        ('L1-632146-special',startup+[change(1,(front,1)),change(1,(14,1)),change(1,(front,0)),
                                      change(1,(back,1)),change(1,(14,0)),change(1,(back,0),(front,1),(2,1))],(slot,592,None,0)),
        ('Start-discard',startup+[change(1,(front,1),(11,1))],(slot,135,None,0))]


def zan_segments(slot,case):
    front,enemy_front=(13,15) if not slot else (15,13)
    r1,l1=3,2
    if case=='R1-evade':
        return [(1,[r1],[],'evade'),(7,[],[],'evade-pose'),(32,[],[],'ready')]
    if case=='R1-cross':
        return [(80,[front],[],None),(4,[],[],None),(1,[front,r1],[],'cross'),(14,[],[],'cross-pose'),(50,[],[],'ready')]
    if case=='R1-air-block':
        return [(40,[front],[enemy_front],None),(8,[],[],None),(1,[12],[12],'jump'),
                (11,[],[],None),(1,[],[5],'opponent-heavy'),(3,[],[],None),(1,[r1],[],'guard'),
                (10,[],[],'blocked'),(70,[],[],'ready')]
    chord=[l1] if case=='L1-charge-and-disarm' else [7,4]
    return [(1,chord,[],'start-charge'),(5,chord,[],'charging'),(169,chord,[],'before-full'),
            (1,chord,[],'full'),(100,[],[],None),(75,[front],[],None),(5,[],[],None),
            (1,[14],[],None),(1,[14,front],[],None),(1,[front,*chord],[],'special'),
            (100,[],[],'flying-weapon'),(160,[],[],'ground-weapon')]


def zan_run(exe,work,original,slot,case):
    # Give SDL one pump to publish player two before pressing a button,
    # so its first shoulder press is a device event on both seats.
    steps=['+1 N1'];labels={};previous=[set(),set()]
    for n,ours,theirs,label in zan_segments(slot,case):
        desired=[set(ours),set(theirs)]
        if slot:desired.reverse()
        tokens=[]
        for i,(was,now) in enumerate(zip(previous,desired)):
            tokens += [op(i,k,False) for k in sorted(was-now)]
            tokens += [op(i,k,True) for k in sorted(now-was)]
        previous=desired
        steps.append(' '.join([*tokens,f'N{n}']))
        if label:labels[label]=len(steps)

    # The original port decoder is sampled for every rendered milestone.
    # Check the human controller's effects also survive through the actual
    # window renderer, by replaying the same levels in the shipping binary.
    pictures={'evade-pose','cross-pose','blocked','full','flying-weapon','ground-weapon'}
    selected=[i for label,i in labels.items() if label in pictures]
    name=f'P{slot+1}-{case}'
    result,rows,hashes=evaluate(exe,work,original,name,steps,special_slot=slot,captures=selected)
    def fighter(label,who=slot):
        row=rows[labels[label]]
        return row[2+9*who:8+9*who]
    def meter(label,who=slot):
        row=rows[labels[label]]
        return row[20+5*who:25+5*who]
    if case in ('R1-evade','R1-cross'):
        state,clip=(45,72) if case=='R1-evade' else (35,74)
        assert fighter('evade' if state==45 else 'cross')[:3]==[0,state,clip]
        assert fighter('ready')[:4]==[0,0,0,200]
    elif case=='R1-air-block':
        assert fighter('jump')[:3]==[0,19,14] and fighter('opponent-heavy',1-slot)[:3]==[1,10,211]
        assert fighter('guard')[:3]==[0,8,308] and fighter('blocked')[:4]==[2,6,308,200]
        assert fighter('blocked',1-slot)[4:]==[0,1] and fighter('ready')[:4]==[0,0,0,200]
    else:
        assert fighter('start-charge')[:3]==[0,46,156] and fighter('charging')[:3]==[0,46,158]
        assert meter('before-full')[1:3]==[0,47045] and meter('full')[1:3]==[1,47104]
        assert fighter('special')[:3]==[1,78,625]
        assert fighter('flying-weapon')[4:]==[1,0] and fighter('flying-weapon',1-slot)[3]==148
        assert meter('flying-weapon',1-slot)[3:]==[0,466]
        assert meter('ground-weapon',1-slot)[3:]==[0,467]
        assert fighter('ground-weapon',1-slot)[:4]==[0,0,1,148]
    result['milestones']={label:dict(update=rows[i][1],player=fighter(label),other=fighter(label,1-slot),
                                     rage=meter(label)[1:3],other_armed=bool(meter(label,1-slot)[3]),
                                     other_weapon=meter(label,1-slot)[4]) for label,i in labels.items()}
    result['packaged_pixel_sha256']={label:hashes[i] for label,i in labels.items() if i in hashes}
    return result


def validate_zan(exe,work,original):
    viewer=PKG/'ss6-viewer'
    assert digest(viewer)==digest(BUILD/'ss6-viewer')
    cases=['R1-evade','R1-cross','R1-air-block','L1-charge-and-disarm','Square-Triangle-charge-and-disarm']
    traces=[zan_run(exe,work,original,slot,case) for slot in range(2) for case in cases]
    for i in [0,len(cases)]:
        # The two physical layouts differ in shoulder/face events. Compare
        # their published game state and finished pixels at every milestone.
        l1,faces=traces[i+3:i+5]
        for field in ('milestones','packaged_pixel_sha256'):assert l1[field]==faces[field]
    report=dict(status='passed',scope='Two SDL3 virtual gamepads, shipping versus window, Japanese preset 0. '
                'The uninstrumented packaged viewer independently replays each captured state. The 640x480 '
                'pixel comparison excludes the paused test label. No physical controller was connected.',
                buttons=dict(system='R1',chord='L1',separate=['Square','Triangle']),
                state_fields=['table','state','action','life','hits','guards'],
                original_sha256=PIN,original_physical_samples=original.calls,
                original_instructions=original.operations,viewer_sha256=digest(viewer),
                replay_sha256=digest(BUILD/'ss6-match-replay'),runtime_sha256=digest(BUILD/'libss6-runtime.a'),
                harness_sha256=digest(HERE/'sdl_gamepad_input_test.cpp'),validator_sha256=digest(Path(__file__)),
                cases=traces)
    ZAN_REPORT.write_text(json.dumps(report,indent=2)+'\n')
    shots=sum(len(case['packaged_pixel_sha256']) for case in traces)
    print(f'{len(traces)} Zan controller window runs, {original.calls} PS2 samples, {shots} packaged frames PASS')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--zan-only',action='store_true',help='Run only the two-seat Zan controller suite')
    args=parser.parse_args()
    original=Original()
    with tempfile.TemporaryDirectory(prefix='ss6-virtual-gamepads-') as temp:
        work=Path(temp);exe=work/'gamepads'
        sdl=shlex.split(run(['pkg-config','--cflags','--libs','sdl3']))
        run([*shlex.split(os.environ.get('CXX','c++')),'-std=c++20','-O2','-I',ROOT/'src',
             HERE/'sdl_gamepad_input_test.cpp',BUILD/'libss6-runtime.a',*sdl,'-o',exe])
        validate_zan(exe,work,original)
        if args.zan_only:return
        original=Original()
        traces=[evaluate(exe,work,original,'all-inputs-and-keyboard-sharing',mapping_steps())]
        hot=['+1 N1','0.7=1 1.5=1 N1','+2 2.4=1 N1','-0 N1','2.4=0 N1',
             'KJ+ 2.7=1 N1','-2 N1','+0 N1','0.7=1 N1','KJ- N1','0.7=0 1.5=0 N1',
             '-1 N1','+2 2.6=1 N1','2.6=0 N1']
        topology=evaluate(exe,work,original,'disconnect-waiting-pad-and-keyboard',hot)
        assert topology['sdl_events'][0]>=5 and topology['sdl_events'][1]>=3,topology
        traces.append(topology)
        for slot in range(2):
            for name,steps,expected in gameplay(slot):
                traces.append(evaluate(exe,work,original,f'P{slot+1}-{name}',steps,match=expected))
        report=dict(status='passed',sdl_version=run(['pkg-config','--modversion','sdl3']).strip(),
                    scope='SDL virtual joysticks on the real SDL3 gamepad subsystem and shipping versus window event loop. No physical USB/Bluetooth controller, console or rumble was exercised. Signed virtual trigger threshold validated at 0/+1 (mapped 16383/16384).',
                    elf_sha256=PIN,physical_ps2_words=dict(zip(BUTTONS,original.physical)),
                    default_bindings=original.defaults,elf_calls_per_slot_sample=['1034a8','177908 (including 177310)'],
                    elf_sampled_player_frames=original.calls,elf_instructions=original.operations,
                    production_files={f:digest(ROOT/'src'/f) for f in ['viewer.cpp','versus_gamepads.hpp','native_match.hpp']},
                    native_runtime_sha256=digest(BUILD/'libss6-runtime.a'),validator_sha256=digest(Path(__file__)),
                    harness_sha256=digest(HERE/'sdl_gamepad_input_test.cpp'),sdl_event_order=['added','removed','press','release','axis'],cases=traces)
    REPORT.write_text(json.dumps(report,indent=2)+'\n')
    print(f'{len(traces)} SDL virtual-controller window runs, {original.calls} original pad samples PASS')


if __name__=='__main__':main()
