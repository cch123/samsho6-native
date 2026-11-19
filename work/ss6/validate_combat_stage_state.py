#!/usr/bin/env python3
"""SLPS_255.59 stage-zero scheduler, seven scenery records and combat-camera timing."""
from collections import Counter
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from extract_versus_result_layout import canvas
from validate_dash_motion import ASSETS,ELF,PIN,ROOT,digest
from validate_input_lifecycle import Boundary
from mips_probe import signed

EXE=ROOT/'work/ss6/build-native/ss6-match-replay'
REPORT=ROOT/'outputs/ss6-feasibility/combat_stage_state_validation.json'
ROWS=(1,2,15,16,18,21,22)
PROJECTION=(0x4a2a58,0x4a2a5c,0x4a2a60,0x4a2a6c,0x4a2a68)
DELTA=0x46a908
DRIVER=r'''
#include "combat_stage_state.hpp"
#include <bit>
#include <iostream>
int main() {
    ss6::CombatStageState stage;ss6::StageCamera c;
    char op;
    unsigned d,x,y,w;
    while(std::cin>>op>>d>>x>>y>>w) {
        if(op=='V'){
            c.x=std::bit_cast<float>(x);c.y=std::bit_cast<float>(y);c.width=std::bit_cast<float>(w);c.publish();
            stage.visit(c,d);
        }
        if(op=='R'){ss6::CombatStageState next;next.inheritRematch(stage);stage=next;}
        std::cout<<stage.visible;
        for(float f:{stage.camera.projectionX,stage.camera.projectionY,stage.camera.depth,
                      stage.camera.depthOffset,stage.camera.verticalOffset})std::cout<<' '<<std::bit_cast<unsigned>(f);
        for(auto a:stage.layers)std::cout<<' '<<a.elapsed<<' '<<a.picture<<' '<<a.step;
        std::cout<<'\n';
    }
}
'''

def bits(f):return struct.unpack('<I',struct.pack('<f',f))[0]

class Oracle:
    def __init__(self):
        self.p=p=canvas()
        p.write(0x50e048,0x60000000,4);p.write(0x510ce8,p.read(0x652c4c,4),4)
        for slot,bank in ((4,32),(5,32),(6,48),(7,48)):p.run(0x10add8,(slot,bank))
        for addr in (DELTA,0x1239d84,0x1239d88):p.write(addr,256,4)
        self.visible=False
        self.objects=[p.read(p.read(0x513138+r*0x48+0x28,4),4) for r in ROWS]
        assert len(set(self.objects))==7
        self.calls=Counter()
        self.instructions=0
        self.slice_calls=self.full_calls=0
        p.write(0x4d3d00,0x1b00000,4)
        self.call(0x112570)
        self.install(False)

    def call(self,pc,*args,stop=(),observe=None):
        boundary=Boundary(*stop) if stop else ()
        val,n=self.p.run(pc,args,limit=500000,stop_before=boundary,observe=observe)
        self.calls[hex(pc)]+=1;self.instructions+=n
        if stop:assert boundary.stopped in stop
        return val

    def install(self,rematch,cancel=True):
        p=self.p
        if rematch and cancel:
            self.call(0x11e3a0,0xfa1);self.call(0x112a70,0xfa1)
        # Constructor prefix through creation of priority 10, then post-I/O
        # tail through its return. the RAM fixture supplies the palettes/texture slots.
        # The tail itself decides whether to clear the seven animation objects.
        self.call(0x1a7690,stop=(0x1a76bc,))
        p.put(17,0x510000);p.write(0x1fff820,0x1ffff00,8)
        self.call(0x1a77b4)
        assert p.read(0x5137b0,4)==1
        self.visible=False

    def snapshot(self):
        p=self.p
        proj=[p.read(a,4) for a in PROJECTION] if self.visible else list(map(bits,(320,120,-400,0,-120)))
        out=[int(self.visible),*proj]
        for o in self.objects:out.extend((signed(p.read(o,4),32),p.read(o+4,4),p.read(o+44,4)))
        return out

    def sample(self,full):
        p=self.p
        self.visible=True
        if full:
            self.call(0x114e80)
            self.call(0x112838)
            self.full_calls+=1
        else:
            # Same comparison as a whole 1a7810 on selected visits. For
            # long real-time matches the clock slice stops before projection
            # and texture submission, after advancing the very same EE RAM.
            for i in ROWS:
                row=0x513138+i*0x48
                p.put(16,row)
                self.call(0x1a7ce8,stop=(0x1a7b40,))
            self.slice_calls+=7

def synthetic(driver):
    o=Oracle();p=o.p
    cmd=['I 0 0 0 0'];expected=[o.snapshot()]
    o.call(0x11e520) # priority 5 publishes delta before the stage at priority 10
    sequence=[(256,False)]*64+[(0,False)]*4+[(64,False)]*80+[(128,False)]*16+[(256,True)]*12
    sequence += [(256,False)]*35+[(24*256,False)]*35+[(256,False)]*8
    for n,(scale,paused) in enumerate(sequence):
        if n==211:
            before=o.snapshot()[6:]
            o.install(True)
            assert o.snapshot()[6:]==before
            cmd.append('R 0 0 0 0');expected.append(o.snapshot())
        eye=(336.5 if n%17<3 else 320,170.25 if n%9<4 else 120,444 if n%7<2 else 320)
        p.floats[12:15]=list(map(bits,eye));o.call(0x122ed8)
        p.write(0x46a940,paused,4);p.write(0x1239d84,256,4);p.write(0x1239d88,scale,4)
        full=n%11==0 or n in (210,211,212)
        if not full:o.call(0x11e708)
        o.sample(full)
        delta=p.read(DELTA,4)
        assert delta==(0 if paused else scale),(n,scale,paused,delta)
        cmd.append('V '+' '.join(map(str,(delta,*map(bits,eye)))));expected.append(o.snapshot())
    native=subprocess.run([driver],input='\n'.join(cmd)+'\n',text=True,capture_output=True,check=True)
    for i,(a,b) in enumerate(zip(native.stdout.splitlines(),expected,strict=True)):
        assert list(map(int,a.split()))==b,(i,cmd[i],a,b)
    return dict(ticks=len(sequence),projected_snapshots=len(expected),full_scheduler_draws=o.full_calls,
                original_clock_slices=o.slice_calls,original_calls=dict(o.calls),instructions=o.instructions)

def replay(args,trace):
    data=''.join(f'1 {left} {right}\n' for left,right in args)
    result=subprocess.run([EXE,ASSETS,'--mode','versus',trace],input=data,text=True,capture_output=True,check=True)
    return [r.split() for r in result.stdout.splitlines()]

def actual():
    # Twelve ordinary standing heavy hits win the first-to-two match.
    # The final uninterrupted neutral suffix lets the postmatch menu open.
    pads=[(0,0)]*500+([(128,0)]*70+[(0,0)]*3+[(1024,0)]+[(0,0)]*220)*19
    menu=replay(pads,'--vs-menu-fields')
    start=next(i for i,r in enumerate(menu) if int(r[24]))
    pads=pads[:start+1]+[(0,0)]*50+[(32,0),(0,0),(512,0)]+[(0,0)]*25
    rows=replay(pads,'--stage-fields');meters=replay(pads,'--rage-fields');menu=replay(pads,'--vs-menu-fields')
    walls=replay(pads,'--wall-fields')
    o=Oracle();p=o.p
    counts=Counter();cats={};sampled=set();last=[[0]*52,[0]*51,[0]*49]
    last[0][50:52]=[256,256]
    for i,(r,me,m,w) in enumerate(zip(rows,meters,menu,walls,strict=True)):
        old_s,old_g,old_m=last;last=(r,me,m)
        # 5 precedes 10; requests created by 50 can only change next frame.
        if int(old_s[1])==4 and not int(old_m[24]):o.call(0x11e708)
        if int(m[23])==2 and int(old_m[23])==1:
            o.call(0x11e600);o.install(True);counts['rematch_handoff']+=1
        else:
            state=int(r[1])
            category=('menu' if int(old_m[24]) else 'pause' if int(old_g[49]) else
                      'slow' if int(old_s[51])!=256 else f'round_state_{state}')
            if category not in cats:cats[category]=i+1
            # Original raw previous-camera projection, intentionally distinct
            # from the camera after this update's movement/zoom. Bounds may
            # adjust camera.x/y after 146870 published; clamp via 122ed8.
            eye=[bits(320),bits(120),bits(320)] if i==0 or not int(old_s[23]) else [int(v) for v in walls[i-1][-12:-9]]
            p.floats[12:15]=eye;o.call(0x122ed8)
            use=category not in sampled
            if use:sampled.add(category)
            o.sample(use)
            counts[category]+=1
            # The KO pause branch calls 11f588, whose clock write differs
            # from 11f5a0. The latter always recomputes the global delta on
            # ordinary frames even after 11e600 removed the priority-5 task.
            if int(old_m[24]):o.call(0x11f5a0,1)
            elif int(me[49]):o.call(0x11f588,1)
            else:
                o.call(0x11f5a0,0)
                p.write(0x1239d88,int(r[51]),4)
                if int(old_s[1])!=5 and state==5:o.call(0x11e600)
        assert int(r[50])==p.read(DELTA,4),(i+1,'post-owner delta',r[50],p.read(DELTA,4))
        got=list(map(int,r[23:50]));want=o.snapshot()
        assert got==want,(i+1,'stage',[(k,a,b) for k,(a,b) in enumerate(zip(got,want)) if a!=b],r[50:52])
    assert counts['rematch_handoff']==1 and counts['pause'] and counts['slow'] and counts['menu']
    return dict(replayed_updates=len(rows),first_postmatch_battle_tick=start+1,
                round_categories=dict(counts),first_update_by_category=cats,full_scheduler_draws=o.full_calls,
                original_clock_slices=o.slice_calls,instructions=o.instructions)

def camera_motion():
    # Synchronized jumps lift the vertical center; retreat to opposite walls
    # opens the camera; one participant then advances and pans the center.
    pads=[(0,0)]*500+[(16,16)]+[(0,0)]*65+[(64,128)]*70+[(0,0)]*3
    pads += [(16|128,0)]+[(0,0)]*8+[(1024,0)]+[(0,0)]*62+[(128,0)]*90
    o=Oracle();p=o.p
    stage=replay(pads,'--stage-fields');world=replay(pads,'--wall-fields')
    centers=[set() for _ in PROJECTION]
    for i,row in enumerate(stage):
        xyz=list(map(bits,(320,120,320))) if not i else list(map(int,world[i-1][-12:-9]))
        p.floats[12:15]=xyz;o.call(0x122ed8)
        got=list(map(int,row[24:29]));want=[p.read(a,4) for a in PROJECTION]
        assert got==want,(i+1,got,want)
        for v,values in zip(want,centers):values.add(struct.unpack('<f',struct.pack('<I',v))[0])
    assert all(len(values)>1 for values in centers)
    return dict(updates=len(stage),unique_projection_values=[len(v) for v in centers],
                ranges=[[min(v),max(v)] for v in centers],instructions=o.instructions)

def game_over(skip):
    from round_entry_oracle import buffered_stdout
    from validate_versus_result import Original,AFTER_DRAW,G
    args=[EXE,ASSETS,'--mode','fixed-versus','--round-time','60']
    def run(trace,commands):
        out=subprocess.run([*args,trace],input=''.join(f'{n} {a} {b}\n' for n,a,b in commands),
                           text=True,capture_output=True,check=True)
        return [line.split() for line in out.stdout.splitlines()]
    # Find the terminal battle boundary through the public match API. Seed
    # the independent EE animation descriptors with that exact published
    # snapshot, so a stale reset-to-zero page cannot pass by coincidence.
    end=next(i+1 for i,r in enumerate(run('--result-fields',[(1,0,0)]*12600)) if int(r[2]))
    commands=[(end,0,0)]
    r=run('--stage-fields',commands)[0]
    q=Oracle();p=q.p;buffered_stdout(p);p.write(G,3,4)
    q.visible=True
    for a,v in zip(PROJECTION,r[24:29]):p.write(a,int(v),4)
    for n,o in enumerate(q.objects):
        for off,v in zip((0,4,44),r[29+3*n:32+3*n]):p.write(o+off,int(v),4)
    assert any(int(v) for v in r[29:50])
    p.write(DELTA,int(r[50]),4)
    page=Original();page.final(-1,0)
    expected=[q.snapshot()];setup=first_gray=transfer=0
    selectors=[];deltas=[];first=None
    for tick in range(1,430):
        edge=skip and page.ready and page.draw[0]==38
        commands.append((1,2048 if edge else 0,0))
        q.sample(tick in (1,13,14,15,16,54,290))
        sample=q.snapshot();expected.append(sample)
        before=page.ready
        if before and not first_gray:
            first_gray=tick
            first=sample[6:]
        page.tick([4 if edge else 0,0])
        if page.ready and not before:
            setup=tick
            before_reload=sample[6:]
            # Teardown runs unmodified until its trailing debug-console tail.
            # It cancels old tagged tasks without clearing scenery descriptors.
            boundary=Boundary(0x1398b8)
            _,n=p.run(0x139778,limit=2200000,stop_before=boundary)
            assert boundary.stopped==0x1398b8
            q.instructions+=n;q.calls['139778..1398b8']+=1
            assert q.snapshot()[6:]==before_reload
            deltas.append(p.read(DELTA,4));assert deltas[-1]==256
            p.put(17,0);p.write(G+4,0,4);p.write(G+0x34,0,4)
            q.call(0x1383ac,stop=(0x1a7690,));selectors.append(p.read(G+4,4))
            q.install(True,cancel=False)
            q.call(0x13847c,stop=(0x1384cc,))
            assert [p.read(a,4) for a in (*PROJECTION,0x4a2a64)]==list(map(bits,(320,120,-400,0,-120,-160)))
            assert q.snapshot()[6:]==before_reload
        if page.scene==AFTER_DRAW:
            transfer=tick
            break
    assert setup==14 and first_gray==15 and transfer and selectors==[0]
    for i,(row,want) in enumerate(zip(run('--stage-fields',commands),expected,strict=True)):
        got=list(map(int,row[23:50]));assert got==want,(skip,i,got,want)
    return dict(skip=skip,final_battle_tick=end,remaining_fight_stage_visits=setup,
                first_gray_visit=first_gray,successor_update=transfer,first_gray_layer_state=first,
                stage_delta_after_original_teardown=deltas[0],full_draws=q.full_calls,instructions=q.instructions)

def main():
    assert digest(ELF)==PIN
    initial=digest(EXE)
    with tempfile.TemporaryDirectory() as tmp:
        src=ROOT/'src';cpp=Path(tmp)/'stage.cpp';driver=Path(tmp)/'stage'
        cpp.write_text(DRIVER)
        subprocess.run(['c++','-std=c++20','-O2','-I',src,cpp,src/'combat_stage_state.cpp',src/'game_random.cpp',src/'stage_camera.cpp',src/'scalar_float.cpp','-o',driver],check=True)
        tested=synthetic(driver)
    live=actual()
    moving=camera_motion()
    draw=[game_over(False),game_over(True)]
    assert digest(EXE)==initial
    REPORT.write_text(json.dumps(dict(status='passed',original_sha256=PIN,native_sha256=initial,component=tested,battle=live,combat_camera=moving,game_over=draw,
        scope='Complete original scheduler 112838, gauge 11e708 and stage-zero callback 1a7810 on sampled draws. Original inner clock blocks on remaining updates. Match camera samples use previous native input to original 122ed8. Stage loader verified before and after texture I/O; animation buffers, cursor, elapsed 8.8 clocks and picture IDs persist across a round and CONTINUE. Geometry/color/hardware raster and wall-clock refresh are separate from these logic comparisons.'),indent=2)+'\n')
    print('Passed stage clock:',tested,live)

if __name__=='__main__':main()
