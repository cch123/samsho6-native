#!/usr/bin/env python3
"""Match the native submode-2 menu to the full Japanese menu update and pad repeat."""
from concurrent.futures import ProcessPoolExecutor
from collections import Counter
import json
from pathlib import Path
import subprocess
import tempfile

from mips_probe import Probe,signed
from round_entry_oracle import buffered_stdout
from validate_dash_motion import ASSETS,ELF,PIN,ROOT,digest
from validate_input_lifecycle import Boundary
from validate_versus_result import T,G,HANDLE,ALPHA,mirror,physical

REPORT=ROOT/'outputs/ss6-feasibility/console_versus_menu_validation.json'
MENU=0x582fb8
SELECT,REMATCH,TITLE=0x128008,0x139760,0x127940
DRIVER=r'''
#include "console_versus_menu.hpp"
#include <iostream>
int main(){
    ss6::ConsoleVersusMenu s; char op; int a,b,c,e;
    while(std::cin>>op>>a>>b>>c>>e) {
        if(op=='I')s.enter(a,{unsigned(b),unsigned(c)},e);
        if(op=='B'){s.session.wins={a,c};s.session.losses={b,e};}
        if(op=='S')s.samplePads({unsigned(a),unsigned(b)},{unsigned(c),unsigned(e)});
        std::array<int,2> sounds{-1,-1};
        if(op=='T')sounds=s.tick();
        if(op=='R'){ss6::ConsoleVersusMenu next;next.inheritRematch(s);s=next;}
        auto& d=s.draw;auto& ss=s.session;
        std::cout<<s.active<<' '<<unsigned(s.pending)<<' '<<unsigned(s.destination)<<' '<<s.fadeAlpha<<' '
                 <<d.visible<<' '<<d.frame<<' '<<d.borderFrame<<' '<<d.selection<<' '<<d.dialog<<' '
                 <<d.choice<<' '<<d.backgroundAlpha<<' '<<d.panelAlpha<<' '<<d.textAlpha<<' '
                 <<d.phase2b3c<<' '<<d.helpRevision<<' '<<d.helpChanged<<' '<<ss.lastEntrant<<' '
                 <<ss.lastWinner<<' '<<ss.streak<<' '<<ss.wins[0]<<' '<<ss.losses[0]<<' '
                 <<ss.wins[1]<<' '<<ss.losses[1];
        for(auto v:ss.defeatedCharacters)std::cout<<' '<<v;
        // Compact the two ports exactly as the game's audio RPC observes them.
        if(sounds[0]<0)std::swap(sounds[0],sounds[1]);
        std::cout<<' '<<sounds[0]<<' '<<sounds[1]<<'\n';
    }
}
'''

class Oracle:
    def __init__(self):
        self.p=Probe(ELF.read_bytes(),finite_model=True)
        p=self.p;buffered_stdout(p)
        for a,v in [(T-8,HANDLE),(G,3),(G+0xa0,2),(0x3ec73c,1),(0x43d064,256),
                    (0x32ce08,1),(0x3a9c20,0x1a00000),(0x443150,1)]:
            p.write(a,v,4)
        self.calls=Counter();self.instructions=0;self.help=0
        self.run(0x112570);self.run(0x124d58)
        p.write(G,3,4);p.write(G+0xa0,2,4);p.write(G+0x10,1,4);p.write(G+0x14,1,4)
        self.draw=[0,0,0,0,0,1,0,0,0,0,0,0]
        self.active=self.pending=self.destination=self.alpha=0
        self.sounds=[]
        self.last=[0,0];self.frame=0;self.border=0

    def run(self,pc,*args,stop=(),observe=None):
        boundary=Boundary(*stop) if stop else ()
        val,n=self.p.run(pc,args,limit=1500000,stop_before=boundary,observe=observe)
        if stop:assert boundary.stopped in stop
        self.calls[hex(pc)]+=1;self.instructions+=n;return val

    def enter(self,winner,cs,record):
        p=self.p
        p.write(G+8,winner,4);p.write(G+0xa0,2,4);p.write(G,3,4)
        for i,c in enumerate(cs):p.write(0x456890+48*i,c,4)
        if record:self.run(0x124da0)
        self.run(0x1daec0)
        assert p.read(0x123a0c8,4)==1 and p.read(G+0xa4,4)==0
        self.active=1;self.pending=self.destination=0
        self.help+=1
        self.frame=0
        self.draw=[0,0,0,0,0,1,0,0,0,0,0,0]

    def sample(self,words):
        for i,w in enumerate(words):
            self.p.write(0x443568+4*i,w,4);self.p.write(0x443570+4*i,self.last[i],4)
            self.run(0x117fd8,i)
        self.last=list(words)

    def tick(self):
        self.sounds=[]
        p=self.p
        self.alpha=p.read(ALPHA,4)
        if p.read(T+4,4):
            midpoint=p.read(T+4,4)==2 and p.read(T+8,4)==2
            # The real request's teardown pointer is reached. The loading,
            # audio and content of successor scenes have their own tests.
            self.run(0x1251d0,HANDLE,stop=(0x1db2e0,) if midpoint else ())
            if midpoint:self.destination=p.read(T+20,4)
        if self.active and not self.pending:
            oldhelp=self.help;info={}
            ready_phase=p.read(0x582b3c,4)
            def obs(pc):
                if pc==0x1e7b70:
                    assert p.registers[4]&0xffffffff==0xffffffff
                    self.sounds.append(p.registers[5])
                elif pc==0x1cebb0:self.help+=1
                elif pc==0x1145c0 and p.registers[31]==0x1db0cc:
                    info['back']=p.registers[8]>>24 & 255
                elif pc==0x1db850:info['panel']=p.registers[4]
                elif pc==0x1db630:info['text']=p.registers[5]
            # The global fullscreen suppression flag skips GS submission. All
            # menu, art helper and font control-flow instructions run intact.
            p.write(0x3ec73c,1,4)
            for a in (0x345178,0x345180):p.write(a,0,4)
            self.run(0x1dafa0,observe=obs)
            if p.read(MENU+8,4):self.pending=p.read(T+20,4)
            self.draw=[1,self.frame,self.border,p.read(MENU,4),p.read(MENU+4,4),p.read(MENU+12,4),
                       info['back'],info['panel'],info['text'],ready_phase,self.help,int(oldhelp!=self.help)]
            self.frame+=1;self.border+=1
        elif self.active:self.draw[0]=0
        self.run(0x116b9c,stop=(0x116bf0,0x116bf4))

    def inherit(self):
        assert self.destination==REMATCH
        self.active=self.pending=self.destination=0;self.draw[0]=0

    def row(self):
        p=self.p
        return [self.active,self.pending,self.destination,self.alpha,*self.draw,
                signed(p.read(G+0x10,4),32),signed(p.read(G+12,4),32),p.read(G+0x38,4),
                *[p.read(G-16+4*i,4) for i in range(4)],*[p.read(G+0x3c+4*i,4) for i in range(20)]]

def check(spec):
    exe,kind,side=spec
    o=Oracle();cmd=[];exp=[]
    def record(op,*args):
        cmd.append(' '.join(map(str,[op,*args,*([0]*(4-len(args)))])));exp.append(o.row()+((o.sounds+[-1,-1])[:2] if op=='T' else [-1,-1]))
    def enter(w,cs=(0,0),score=1):
        o.enter(w,cs,score);record('I',w,*cs,score)
    def tick(l=0,r=0):
        edges=(l&~o.last[0],r&~o.last[1]);o.sample((l,r));record('S',l,r,*edges)
        o.tick();record('T')
    def own(k,other=0):tick(*((other,k) if side else (k,other)))
    def tap(k):own(k);tick()
    # Pad state (and its held-direction repeat age) can start before the
    # final battle dispatch creates the result overlay.
    if kind=='repeat':
        for _ in range(7):own(0x20)
    enter(-1 if kind=='title' else side)
    for i in range(45):
        if kind=='repeat':own(0x20)
        else:own(0x20a if i in (0,44) else 0)
    ticks_to_request=None
    if kind=='repeat':
        for _ in range(23):own(0x20)
        tap(0);tap(0x80);tap(0x40);tap(0x10|0x20);tap(0x80|0x200)
    elif kind=='both':
        tick()
        # P1 advances, then P2 confirms the newly selected Continue item.
        tick(0x20,0x200)
    elif kind=='rematch':
        tick();tap(0x20);tap(0x200)
    elif kind=='select':
        tick();tap(0x200);tap(4);tap(8);tap(0x200);tap(0x200);tap(0x80);tap(0x200)
    elif kind=='title':
        tick();tap(0x10);tap(0x200);tap(0x200);tap(0x200);tap(0x40);tap(0x200)
    if kind!='repeat':
        assert o.pending==(REMATCH if kind in ('both','rematch') else SELECT if kind=='select' else TITLE),(kind,side,o.draw,o.pending)
        for _ in range(20):
            if o.destination:break
            tick()
        assert o.destination==o.pending
        start=next(i for i,v in enumerate(exp) if v[1])
        end=next(i for i,v in enumerate(exp) if v[2])
        ticks_to_request=(end-start)//2
        assert ticks_to_request==15
        if kind=='rematch':
            o.inherit();record('R')
            for _ in range(14):tick()
            # Near-maximum counters isolate the 999 cap without simulating
            # a thousand matches. Distinct loser IDs expose ring addressing
            # and wrap after twenty consecutive wins.
            scores=(998,998,998,998)
            for i,v in enumerate(scores):o.p.write(G-16+4*i,v,4)
            record('B',*scores)
            for n,winner in enumerate([side]*23+[side^1,-1]):
                enter(winner,(n%35,(n+9)%35))
            enter(side,score=0)
    native=subprocess.run([exe],input='\n'.join(cmd)+'\n',text=True,capture_output=True,check=True)
    actual=[list(map(int,line.split())) for line in native.stdout.splitlines()]
    for i,(a,b) in enumerate(zip(actual,exp,strict=True)):
        assert a==b,(kind,side,i,cmd[i],[(k,v,w) for k,(v,w) in enumerate(zip(a,b,strict=True)) if v!=w])
    return dict(case=kind,first_player=side,menu_callbacks=o.calls['0x1dafa0'],snapshots=len(exp),
                fade_to_successor=ticks_to_request,original_calls=dict(o.calls),instructions=o.instructions)

def live(winner):
    """Replay an actual match; compare its post-battle overlay with a running EE task."""
    exe=ROOT/'work/ss6/build-native/ss6-match-replay'
    args=[exe,ASSETS,'--vs-menu-fields']
    if winner<0:
        args+=['--round-time','60']
        pads=[(0,0)]*12600
    else:
        approach=[(128,0)]*70+[(0,0)]*3+[(1024,0)]+[(0,0)]*220
        pads=[(0,0)]*500+approach*19
        if winner:pads=[(mirror(b),mirror(a)) for a,b in pads]
    def replay(masks):
        data=''.join(f'1 {a} {b}\n' for a,b in masks)
        return [r.split() for r in subprocess.run(args,input=data,capture_output=True,
                                                   text=True,check=True).stdout.splitlines()]
    start=next(i for i,r in enumerate(replay(pads)) if r[24]=='1')
    pads=pads[:start+1]
    o=Oracle()
    # The actual ending posture and held directions persist into this task.
    # A 40-tick suffix exceeds the initial repeat delay of every direction.
    for sample in pads[-40:]:o.sample(tuple(physical(p) for p in sample))
    o.enter(winner,(0,0),True)
    def fields():
        d=o.draw;p=o.p
        return ([o.active,d[0],d[1],d[3],d[4],d[5],o.pending,o.destination,o.alpha]
                +[p.read(G-16+4*i,4) for i in range(4)]
                +[signed(p.read(G+12,4),32),p.read(G+0x38,4),p.read(G+16,4),
                  d[10],d[2],d[7],d[8],d[6]])
    wanted=[fields()]
    side=1 if winner==1 else 0
    seq=[0]*45
    # Normalized M (0x200) is the physical confirmation button in both
    # ports. Default negative choice makes the first selection reversible.
    if winner>0:seq += [0x10,0,0x200,0,0x80,0,0x200]
    elif winner==0:seq += [0x200,0,0x400,0,0x200,0,0x40,0,0x200]
    else:seq += [0x20,0,0x200]
    seq += [0]*35
    rematched=False
    for k in seq:
        pad=(0,k) if side else (k,0);pads.append(pad)
        o.sample(tuple(physical(v) for v in pad));o.tick()
        if o.destination==REMATCH:
            rematched=True
            o.inherit()
        wanted.append(fields())
    expected_dest=TITLE if winner>0 else SELECT if winner==0 else REMATCH
    if winner>=0:assert o.destination==expected_dest
    else:assert rematched
    rows=replay(pads)[start:]
    original_fighters=rows[0][3:23]
    for i,(r,w) in enumerate(zip(rows,wanted,strict=True)):
        columns=[*range(24,40),44,45,46,47,48]
        got=[int(r[k]) for k in columns]
        assert got==w,(winner,i,[(k,a,b) for k,a,b in zip(columns,got,w,strict=True) if a!=b])
        if int(r[23])==1:
            assert r[3:23]==original_fighters and r[2]=='1',(winner,i,'paused fighters')
    if winner<0:
        assert rows[-1][23]=='2' and rows[-1][2]=='0' and rows[-1][12]==rows[-1][22]=='0'
    return dict(winner=winner,battle_frame=start+1,hits=[int(rows[0][10]),int(rows[0][20])],
                completed_round_wins=[int(rows[0][12]),int(rows[0][22])],
                overlay_updates=len(wanted)-1,successor=hex(expected_dest),
                matches_after_handoff=int(rows[-1][23]))

def main():
    assert digest(ELF)==PIN
    replay=ROOT/'work/ss6/build-native/ss6-match-replay'
    initial_digest=digest(replay)
    with tempfile.TemporaryDirectory() as tmp:
        cpp=Path(tmp)/'check.cpp';exe=Path(tmp)/'check'
        cpp.write_text(DRIVER)
        subprocess.run(['c++','-std=c++20','-I',ROOT/'src',cpp,ROOT/'src/console_versus_menu.cpp','-o',exe],check=True)
        with ProcessPoolExecutor(4) as pool:
            cases=list(pool.map(check,((exe,k,side) for k in ('rematch','select','title','repeat','both') for side in range(2))))
            matches=list(pool.map(live,(0,1,-1)))
    assert digest(replay)==initial_digest
    REPORT.write_text(json.dumps(dict(status='passed',elf_sha256=PIN,native_sha256=initial_digest,cases=cases,actual_matches=matches,scope='Original complete 1daec0 entry, both raw software pad samplers 117fd8, whole 1dafa0 menu update and reached helpers, 124da0 counters, priority-60 1251d0 transition and alpha accumulation. Graphics DMA suppressed in this logical fixture. Three match-replay runs play P1 wins, P2 wins and natural draws from round one, freeze the fighters, and match EE menu inputs/visual state through the successor handoff. Character selection and title content are outside this comparison.'),indent=2)+'\n')
    print(len(cases),'EE/native menu traces;',sum(c['snapshots'] for c in cases),'snapshots; both sides, all 3 destinations and directional repeat')

if __name__=='__main__':main()
