#!/usr/bin/env python3
"""Japanese character/spirit/arena selection through the next-scene request: the two-seat VS
menu page, the single-seat ARCADE (1/2) and SURVIVAL (0xb/0xc) pages, the one-pad PRACTICE
(9/10) page and the arcade challenger page (mode 3, submode 1)."""
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import json
import random
import struct
import subprocess
import tempfile

from mips_probe import Probe, signed
from validate_dash_motion import ELF, PIN, ROOT, digest

REPORT = ROOT/'outputs/ss6-feasibility/character_select_validation.json'
DRIVER = r'''
#include "character_select.hpp"
#include <iostream>
int main(int n,char**v){
    ss6::CharacterSelect a; a.stageOwner=std::stoi(v[1]); a.random.librarySeed=std::stoull(v[2]);
    if(std::stoi(v[3])){a.stageOption=1;a.seats[0].palette=0x50003;a.seats[1].palette=0x60002;}
    if(n>4){const int owner=a.stageOwner;a.configure(std::stoi(v[4]));if(a.mode!=9&&a.mode!=10)a.stageOwner=owner;a.submode=std::stoi(v[5]);a.seats[0].spirit=std::stoi(v[6]);a.seats[1].spirit=std::stoi(v[7]);}
    std::array<ss6::NormalizedPadSample,2> pads{};
    unsigned x,y;while(std::cin>>x>>y){
        const unsigned next[]{x,y};
        for(int j=0;j<2;++j){pads[j].pressed=next[j]&~pads[j].held;pads[j].held=next[j];}
        a.tick(pads);
        auto put=[](auto x){std::cout<<x<<' ';};
        put(a.frame);put(a.remaining);put(a.firstChooser);put(a.spiritRequested);put(a.complete);
        put(a.characterDirectorVisible?a.drawFrame:-1);put(a.spiritDirectorVisible?a.spiritDrawFrame:-1);
        put(a.stageCursor);put(a.stageOption);put(a.random.librarySeed);
        for(unsigned j=0;j<2;++j){
            auto& c=a.seats[j];auto& s=a.spirits[j];
            for(auto x:{c.phase,c.count,c.present?c.cell:0,c.selected,c.palette,int(c.committed),c.drawPhase,c.drawCount,int(c.drawPortrait),int(c.controls)})put(x);
            for(auto x:{s.phase,s.count,s.choiceCount,s.cursor,s.progress,s.secondary,s.drawPhase,s.drawCount,s.drawCursor,s.drawProgress,(n>4||s.progress)?a.seats[j].spirit:0})put(x);
        }
        put(a.audio.size());for(auto s:a.audio){put(s.bank);put(s.tone);}
        put(a.countdownPaused);put(a.handoverDelay);
        for(unsigned j=0;j<2;++j){
            auto& c=a.seats[j];auto& s=a.spirits[j];
            put(c.previewLoaded);put(c.randomChosen);put(s.active);
            put(c.previewRestarted?c.previewCharacter:-1);put(c.previewRestarted?c.previewAction:-1);
        }
        std::cout<<'\n';
    }
}
'''
# External boundaries. The actor/selection dispatchers, input, geometry's phase
# completion returns, both task pools, timer/PRNG and selection tables execute
# from the ELF. Graphics code is validated separately against the CS/GS assets.
LEAVES = (
    0x109f08,0x10add8,0x112f08,0x112f30,0x1132c0,0x113f98,0x1142d8,
    0x1145c0,0x1148f0,0x114d88,0x1159d0,0x115ae0,0x116200,0x116268,
    0x1163c0,0x116478,0x1170d8,0x117170,0x117de8,0x118320,0x118420,
    0x11c248,0x11d668,0x11d908,0x1207d8,0x122e98,0x122eb8,0x1252f0,
    0x129cf8,0x12d188,0x135300,0x1353a0,0x152988,0x17e038,
    0x1c2420,0x1e79c8,0x1e7b70,0x1e7ba0,0x1e7c00,0x1e7d60,0x318358,0x323050)
# Single-seat pages only. 11d4f8 reloads the common object file from disc; 11d6c8/11d868/
# 11d730 animate and submit the large fighter object (its 11d668/11d908 setup is already a
# leaf); 12d860/12d9e0/12d410 are text panels. 17a2c8/1c2420/1bc1a8 belong to the arcade
# schedule that the ARCADE exit prepares for the next scene.
SINGLE_LEAVES = (0x11d4f8,0x11d6c8,0x11d868,0x11d730,0x12d410,0x12d860,0x12d9e0,0x17a2c8,0x1c2420,0x1bc1a8)
SUBMODE = {1:1,2:1,3:1,6:2,9:3,10:3,11:4,12:4}
EXIT = {1:(0x12f800,0x1c60c8),2:(0x12f800,0x1c60c8),11:(0x129110,0x139760),12:(0x129110,0x139760)}
class Source:
    def __init__(self,owner,seed,reselect=False,mode=6,submode=None,spirits=None):
        self.p=p=Probe(ELF.read_bytes(),finite_model=True)
        self.mode=mode;self.exit=EXIT.get(mode,(0x12f800,0x125e10))
        for pc in LEAVES+(() if mode in (3,6,9,10) else SINGLE_LEAVES):
            p.memory[pc:pc+8]=struct.pack('<II',0x03e00008,0x0000102d)
        p.run(0x1113e8,[0x43d058])
        for c in range(40,49):p.write(0x43d06e+c,0,1)  # the native port presents every character unlocked
        for pc in (0x1123a8,0x112570,0x11e290,0x127eb0):
            p.run(pc,limit=200000)
        p.write(0x443150,1,4);p.write(0x4c3808,mode,4);p.write(0x4c38a8,SUBMODE[mode] if submode is None else submode,4)
        for j,spirit in enumerate(spirits or ()):p.write(0x456898+j*48,spirit,4)
        p.write(0x4c3818,owner,4);self.seed=p.read(0x5d1bf8,4)+0xa8
        if reselect:
            p.write(0x4c3828,1,4)
            for j,col in enumerate((0x50003,0x60002)):p.write(0x456894+j*48,col,4)
        p.write(self.seed,seed,8);p.run(0x128008,limit=500000)
        self.last=[0,0];self.requested=0;self.complete=0;self.visits=0;self.preview=[[-1,-1],[-1,-1]]
        self.drawSpirit=[[0,0,5,0] for _ in range(2)]
        self.grid=[p.read(0x4c82a8+i*4,4) for i in range(48)]
        assert [p.read(0x4c8838+4*i,4) for i in (0,1,3)]==[8,6,48],'unlocked layout'
    def observe(self,pc):
        p=self.p;r=p.registers
        if pc==0x12a418:
            self.drawChar[r[4]]=[*r[5:9]]
        elif pc==0x1309a8:
            s=r[4];self.drawSpirit[s]=[*r[5:7],p.read(0x4c8d40+s*52,4),p.read(0x4c8d44+s*52,4)]
        elif pc==0x1129c8 and r[4]==0x12eee8:self.requested=1
        elif pc==0x1252f0:
            assert r[4:8]==[1,1,*self.exit],[hex(x) for x in r[4:8]];self.complete=1
        elif pc==0x1293d0:self.preview[r[4]]=[r[5],r[6]]
        elif pc==0x128470:self.charFrame=p.read(0x4c8290,4)
        elif pc==0x12f100:self.spiritFrame=p.read(0x4c8290,4)
        elif pc in (0x1e7b70,0x1e7ba0):
            self.audio.extend((signed(r[4],64),r[5]))
    def step(self,pads):
        p=self.p;self.drawChar=[[0]*4 for _ in range(2)];self.audio=[]
        self.preview=[[-1,-1],[-1,-1]]
        self.charFrame=self.spiritFrame=-1
        for s,h in enumerate(pads):
            p.write(0x443568+4*s,h,4);p.write(0x443570+4*s,self.last[s],4);p.run(0x117fd8,[s])
        self.last=list(pads);_,count=p.run(0x112838,limit=400000,observe=self.observe)
        self.visits+=count
        # Before 12eee8/12f8e8 the public cursor defaults describe the incoming
        # factory page; its visible flag and choiceCount remain zero.
        age=p.read(0x4c8d18,4)|p.read(0x4c8d4c,4)
        stage=p.read(0x4c8d80,4) if self.requested and (age or p.read(0x4c8288,4)==1200) else 10
        a=[p.read(0x4c8290,4),p.read(0x4c8288,4)-p.read(0x4c8280,4),
           signed(p.read(0x4c38a4,4),32),self.requested,self.complete,
           self.charFrame,self.spiritFrame,stage,p.read(0x4c3828,4),p.read(self.seed,8)]
        for s in range(2):
            ss=s*4; data=0x456890+s*48;sp=0x4c8d18+s*52
            commit=p.read(data+16,4);progress=p.read(sp+44,4);n=p.read(sp,4)
            a += [p.read(0x1239e28+ss,4),p.read(0x1239e20+ss,4),p.read(0x4c82a0+ss,4),
                  p.read(data,4) if commit else -1,p.read(data+4,4),commit,*self.drawChar[s],
                  p.read(0x1239e78+ss,4),p.read(0x1239e70+ss,4),n,p.read(sp+40,4) if n else 5,
                  progress,p.read(sp+48,4),*self.drawSpirit[s],p.read(data+8,4)]
        self.extra=[p.read(0x4c8284,4),signed(p.read(0x4c8294,4),32)]
        for s in range(2):
            self.extra += [p.read(0x1239e38+4*s,4),p.read(0x4568b4+s*48,4),p.read(0x4c8d88+4*s,4),*self.preview[s]]
        return a+[len(self.audio)//2,*self.audio]

def make_case(name):
    owner,seed=0,1
    inputs=[[0,0] for _ in range(420)]
    def key(seat,t,word):inputs[t-1][seat]=word
    if name in ('opposite','reselect'):
        # P1: Haohmaru. P2: Nakoruru. P2 makes the first confirmation.
        owner=1;key(0,66,32)
        for t,word in ((65,64),(76,64),(88,16),(90,16),(92,512)):
            key(1,t,word)
        key(0,99,1024)
    elif name=='random-mirror':
        seed=455
        # Both seats pick the unlocked grid's only random tile (cell 41: two columns back, three rows up).
        for s in range(2):
            key(s,64,64 if not s else 128);key(s,76,64 if not s else 128);key(s,88,16);key(s,90,16);key(s,92,16)
            key(s,99,0x400000|0x80000|0x100000)
    elif name=='all-cells':
        inputs=[[0,0] for _ in range(840)]
        tick=65
        for col in range(8):
            for seat in range(2):
                for row in range(6):key(seat,tick+row*2,32)
                if col<7:key(seat,tick+12,128 if not seat else 64)
            tick+=25
        for seat in range(2):key(seat,tick,0x80000|4)
    elif name=='stages':
        inputs=[[0,0] for _ in range(750)]
        for s in (0,1):key(s,72,1024)
    elif name=='palette':
        for s in range(2):key(s,70,32);key(s,74,2)
    elif name=='kuroko':
        # P1: Start, then moves during and after the 21-update wipe, Kuroko confirmed.
        # P2: toggles off mid-wipe and on again, then confirms Kuroko on the random cell.
        key(0,66,8);key(0,72,32);key(0,90,128);key(0,96,32);key(0,104,1024)
        key(1,66,8);key(1,71,8);key(1,78,8);key(1,102,64);key(1,104,64);key(1,106,16);key(1,108,16);key(1,110,16);key(1,116,2)
    elif name=='repeat':
        for s in range(2):
            for t in range(62,103):key(s,t,128|32)
            key(s,125,0x100000|4)
    else:raise ValueError(name)
    shift=220 if name=='all-cells' else 0
    steps={'opposite':(2,-2),'reselect':(2,-2),'palette':(0,1),'random-mirror':(3,-1),'repeat':(-1,0),'all-cells':(-3,-2),'stages':(1,-1),'kuroko':(1,-1)}[name]
    for s,n in enumerate(steps):
        for k in range(abs(n)):key(s,shift+224+s*7+k*15,128 if n>0 else 64)
        key(s,shift+274+s*9,1024)
    for t,w in ((310,128),(313,64),(316,128),(320,2),(339,128),(375,4)):
        if name!='stages' or t<339:key(owner,shift+t,w)
    if name=='stages':
        for n in range(11):key(owner,339+31*n,128)
        key(owner,684,1024)
    return owner,seed,inputs

# Pad words: 0x10 up, 0x20 down, 0x40 left, 0x80 right, 8 Start, the five confirmations
# 0x400/0x200/2/4/0x400000 and their 0x80000/0x100000 modifiers.
WORDS=(0x10,0x20,0x40,0x80,0x10,0x20,0x40,0x80,0x50,0xa0,8,0x400,0x200,2,4,0x400000,
       0x80400,0x100200,0x180002,0x100004,0x80000,0x100000,1,0x800)
BURSTS=((600,612),(700,712),(900,912),(1000,1012),(1150,1162),(1300,1500))
def random_inputs(seed,frames):
    """Random held words with random hold lengths. Confirmations are rare outside the fixed
    bursts, which walk every page of every mode to its exit with random buttons/modifiers."""
    rng=random.Random(seed);inputs=[[0,0] for _ in range(frames)]
    for seat in (0,1):
        t=0
        while t<frames:
            gap=rng.randrange(1,14);hold=rng.choice((1,1,1,2,3,5,12,24,30))
            word=rng.choice(WORDS) if rng.random()<.8 else 0
            if word&0x400607 and rng.random()<.97:word=rng.choice((0x10,0x20,0x40,0x80,8))
            for k in range(t+gap,min(frames,t+gap+hold)):inputs[k][seat]=word
            t+=gap+hold
    for start,end in BURSTS:
        for t in range(start,min(end,frames)):
            for seat in (0,1):
                inputs[t][seat]=rng.choice((0x400,0x200,2,4,0x400000))|rng.choice((0,0x80000,0x100000,0x180000)) if t%3==0 else 0
    return inputs

def make_mode_case(name):
    """name = <kind>-<mode>[-<seed>]. Scripted single-seat cases wait for the countdown gate
    (pad input starts 61 visits after the page opened in ARCADE/SURVIVAL)."""
    kind,mode,*rest=name.split('-');mode=int(mode);seed=int(rest[0]) if rest else 7
    case=dict(name=name,mode=mode,submode=SUBMODE[mode],owner=0,seed=seed,spirits=(0,0),reselect=False)
    seat=int(mode in (2,10,12));other=seat^1
    if mode in (9,10):case['owner']=other   # 1cd44c: gameData+10 = practising seat ^ 1
    inputs=[[0,0] for _ in range(3400 if kind=='timeout' else 1500)]
    def key(t,word,pad=seat):inputs[t-1][pad]=word
    if kind=='random':
        inputs=random_inputs(seed*131+mode,1500)
    elif kind=='timeout':
        # A few early moves, then no confirmation: both countdowns expire.
        key(130,0x20);key(140,0x80);key(1990,0x80);key(2010,0x40)
        for t in range(1,3400,5):inputs[t][other]=WORDS[t%len(WORDS)]
    elif kind=='single':
        # Random tile (cell 41) with its RNG-cycled fighter, the Kuroko view on and off, a
        # wrapped move, then an alternate-pose custom-colour confirmation.
        left,right=(0x40,0x80) if not seat else (0x80,0x40)
        key(80,0x20);key(100,0x400)                      # ignored: the countdown gate is still closed
        key(124,left);key(136,left);key(148,0x20);key(150,0x20);key(152,0x20)
        key(180,8);key(190,0x20);key(215,8);key(230,right);key(243,0x10);key(250,8);key(280,8)
        for t in range(300,330):key(t,0x20|left)
        confirm={1:0x180200,2:0x400000,11:0x400,12:0x100004}[mode]
        if mode==12:key(345,8);key(380,0x10)
        if mode==11:
            for k,t in enumerate(range(340,400,12)):key(t,left)
            key(402,0x10)                                 # back on the random tile
        key(420,confirm|(confirm&0x180000));key(419,confirm&0x180000)
        for k in range(6):key(520+12*k,0x80 if k<4 else 0x40)
        key(600,2)
        for t in range(1,1500,5):inputs[t][other]=WORDS[t%len(WORDS)]   # the absent seat's pad is never read
    elif kind=='practice':
        # One pad: own fighter, ten-visit hand-over, the dummy's fighter (mirrored for seat
        # 1), both spirits, then the stage; the other pad carries noise.
        key(66,0x20);key(70,0x40);key(84,8);key(110,0x80);key(125,0x10);key(130,0x100200)
        for t in range(131,150):key(t,0x40)               # held across the hand-over delay
        key(160,0x80);key(172,0x20);key(176,8);key(200,8);key(204,0x10);key(210,0x80002)
        for k in range(3):key(330+12*k,0x80)
        key(370,0x400);key(371,0x40)
        for k in range(2):key(380+12*k,0x40)
        key(410,2);key(425,0x80);key(460,0x40);key(495,0x40);key(530,0x400)
        for t in range(1,1500,5):inputs[t][other]=WORDS[t%len(WORDS)]
    elif kind=='challenger':
        # Arcade challenger page: mode 3 with the arcade submode, running countdowns, the
        # other seat's spirit cursor on its current spirit, and no stage page.
        case.update(owner=1,spirits=(3,2))
        key(125,0x20,0);key(128,0x40,1);key(140,0x400,0);key(150,0x80200,1)
        key(280,0x80,0);key(284,0x40,1);key(300,0x400,0);key(310,2,1)
        key(330,0x80,1);key(336,0x40,1);key(340,0x80,1);key(350,0x200,1)
    elif kind=='expire':
        # The same page with no input: three countdowns (fighters, spirits, item option).
        case.update(owner=1,spirits=(1,4));inputs=[[0,0] for _ in range(4000)]
    else:raise ValueError(name)
    case['inputs']=inputs
    return case

def check(args):
    exe,name=args
    if name[-1].isdigit():case=make_mode_case(name)
    else:
        owner,seed,inputs=make_case(name)
        case=dict(name=name,mode=6,submode=2,owner=owner,seed=seed,inputs=inputs,spirits=(0,0),reselect=name=='reselect')
    owner,seed,inputs,mode=case['owner'],case['seed'],case['inputs'],case['mode']
    src=Source(owner,seed,case['reselect'],mode,case['submode'],case['spirits'])
    stream=''.join(f'{a} {b}\n' for a,b in inputs)
    rows=subprocess.check_output([exe,str(owner),str(seed),str(int(case['reselect'])),str(mode),str(case['submode']),
                                  *map(str,case['spirits'])],input=stream,text=True).splitlines()
    history=[];last=None;visited=[set(),set()];stages=set();previews=0;expired=0
    for frame,(pads,line) in enumerate(zip(inputs,rows),1):
        expected=src.step(pads)+src.extra;row=list(map(int,line.split()))
        if row!=expected:
            differences=[(j,b,a) for j,(a,b) in enumerate(zip(expected,row)) if a!=b]
            raise AssertionError((name,frame,pads,differences,'native',row,'ELF',expected))
        for j in (0,1):visited[j].add(row[12+21*j])
        if row[20+21*owner] in (20,22,23,24,25):stages.add(row[7])
        previews+=sum(row[-7+5*j]>=0 for j in (0,1));expired+=row[1]==0
        state=tuple(row[i] for i in (10,20,31,41))
        if state!=last:history.append([frame,*state]);last=state
        if src.complete:
            if name=='all-cells':assert [len(c) for c in visited]==[48,48]
            if name=='stages':assert stages==set(range(11))
            if name.startswith(('timeout','expire')):assert expired
            return dict(stage_cells=sorted(stages),visited_cells=[len(c) for c in visited],name=name,mode=mode,submode=case['submode'],
                        owner=owner,seed=seed,frames=frame,executed_instructions=src.visits,
                        next_scene=[hex(x) for x in src.exit],fighter_object_loads=previews,expired_visits=expired,
                        characters=[row[13],row[34]],palettes=[row[14],row[35]],spirits=[row[30],row[51]],
                        stage=row[7],stage_option=row[8],state_changes=history)
    raise AssertionError('Next-scene request missing: '+name)

MODE_CASES=['single-1','single-2','single-11','single-12','practice-9','practice-10','challenger-3','timeout-1','timeout-12','expire-3',
            *[f'random-{mode}-{seed}' for mode in (1,2,9,10,11,12) for seed in (1,2,3)],'random-3-1','random-3-2']
def main():
    assert digest(ELF)==PIN
    with tempfile.TemporaryDirectory() as temp:
        test=Path(temp)/'select.cpp';test.write_text(DRIVER);exe=Path(temp)/'select'
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I'+str(ROOT/'src'),str(test),str(ROOT/'src/character_select.cpp'),
                        str(ROOT/'src/game_random.cpp'),str(ROOT/'src/scalar_float.cpp'),'-o',str(exe)],check=True)
        names=['opposite','palette','random-mirror','repeat','all-cells','stages','reselect','kuroko']
        import sys
        if len(sys.argv)>1:names=sys.argv[1:]
        else:names+=MODE_CASES
        with ProcessPoolExecutor(8) as pool:
            results=list(pool.map(check,[(str(exe),name) for name in names]))
    if len(sys.argv)>1:
        for c in results:print(c['name'],c['frames'],c['characters'],c['palettes'],c['spirits'],c['fighter_object_loads'],c['expired_visits'],c['state_changes'][-3:])
        return
    REPORT.write_text(json.dumps(dict(status='passed',elf_sha256=PIN,
        cpp_sha256=digest(ROOT/'src/character_select.cpp'),header_sha256=digest(ROOT/'src/character_select.hpp'),
        scope=SCOPE, cases=results),indent=2)+'\n')
    modes=sorted({c['mode'] for c in results})
    print(f'{len(results)} original/native selection sequences in modes {modes}, {sum(c["frames"] for c in results)} scheduler visits, '
          f'{sum(c["executed_instructions"] for c in results)} instructions through the next-scene request')
SCOPE=('Japanese SLPS-25559 with every character unlocked (8x6 grid, 47-entry random pool, Kuroko Start view, spirit 8 for 44..47; '
       'spirit bytes 43d0d6..d8 and EX byte 43d0ec keep their factory 0). Mode words 6 (VS menu, submode 2), 1/2 (ARCADE, submode 1), '
       '0xb/0xc (SURVIVAL, submode 4), 9/10 (PRACTICE, submode 3) and 3 with submode 1 (arcade challenger). Full original scheduler '
       '112838 with 128008 and nested births, 117fd8 raw pad sampling, countdown task 127f00 including expiry, character/spirit/'
       'setting/stage controls, all reached draw-phase completion decisions, ordered SE requests, 1293d0 fighter-object requests, '
       'P+0x24, 4c8d88 words and the PRACTICE hand-over counter per visit; external graphics, platform I/O and audio driver submitted '
       'at fixture boundaries. Single-seat pages additionally stop at 11d4f8 (disc reload of the common object file), 11d6c8/11d868/'
       '11d730 (fighter object animation and draw), text panels 12d410/12d860/12d9e0 and the arcade schedule calls 17a2c8/1c2420/'
       '1bc1a8 of the exit. Stops at the original 1252f0(1,1,destructor,next): 125e10 two-seat, 1c60c8 ARCADE (first run), 139760 '
       'SURVIVAL; g_GameData+0x18 (challenger freeze) and +0x2c (transition lock) stay 0.')
if __name__=='__main__':main()
