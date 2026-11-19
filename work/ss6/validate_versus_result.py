#!/usr/bin/env python3
"""Compare the default Japanese result tasks and transition scheduler against the native port."""
import argparse
from collections import Counter
from functools import lru_cache
import json
from pathlib import Path
import subprocess
import tempfile

from mips_probe import Probe, signed
from round_entry_oracle import buffered_stdout
from validate_dash_motion import ASSETS, ELF, PIN, ROOT, digest
from validate_finishing_blow import mirror
from validate_input_features import PADS
from validate_input_lifecycle import Boundary

REPORT = ROOT/'outputs/ss6-feasibility/versus_result_validation.json'
G, T, PAGE = 0x4c3808, 0x1239da0, 0x4ca1b0
ALPHA, DELTA, LIMIT = 0x3ec734, 0x3ec738, 0x3d3aa0
WIN, DRAW, AFTER_WIN, AFTER_DRAW = 0x135e30, 0x138340, 0x1c60c8, 0x1e8850
STACK, RET, HANDLE = 0x1fff000, 0x1ffff00, 0x1d00000
DRIVER = r'''
#include "versus_result.hpp"
#include "match_ending.hpp"
#include <iostream>
int main() {
    ss6::VersusResultState s;
    char op;int a,b;
    while(std::cin>>op>>a>>b) {
        if(op=='I') {
            ss6::MatchEndState e;e.winner08=a;e.result8c=b;
            ss6::enterVersusResult(s,e,{0,0});
        } else ss6::updateVersusResult(s,{unsigned(a),unsigned(b)});
        std::cout<<unsigned(s.scene)<<' '<<unsigned(s.nextScene)<<' '<<s.winner<<' '
                 <<s.lastWinner<<' '<<s.streak<<' '<<s.gameMode<<' '<<s.presentationReady<<' '
                 <<s.frame<<' '<<s.backgroundFrame<<' '<<s.messageFrame<<' '<<s.endFrame<<' '
                 <<s.messageDone<<' '<<s.glyphLimit<<' '<<s.draw.frame<<' '
                 <<s.draw.backgroundFrame<<' '<<s.draw.glyphLimit<<' '<<s.fadePhase<<' '
                 <<s.fadeLevel<<' '<<s.fadeAlpha<<' '<<s.fadeWhite<<' '<<s.draw.whiteFlash<<'\n';
    }
}
'''

class Original:
    def __init__(self):
        self.p=Probe(ELF.read_bytes(), finite_model=True)
        buffered_stdout(self.p)
        self.calls=Counter()
        self.instructions=0
        self.run(0x124d58)
        self.p.write(T-8,HANDLE,4)

    def run(self,addr,*args,until=()):
        stop=Boundary(*until)
        val,n=self.p.run(addr,args,limit=500000,stop_before=stop)
        self.calls[hex(addr)]+=1
        self.instructions+=n
        if until:
            assert stop.stopped in until, (hex(addr),until)
        return val

    def final(self,winner,quote):
        p=self.p
        p.write(G,3,4)
        p.write(G+8,winner,4)
        p.write(G+0x10,1,4)
        p.write(G+0x8c,quote,4)
        for reg,value in [(17,G),(19,0x4c0000),(20,2),(21,0)]:
            p.put(reg,value)
        p.write(STACK+0x30,RET,8)
        # Directly after the development-console log. All branch decisions,
        # streak accounting and the 1252f0 transition request execute here.
        self.run(0x145668)
        self.scene=p.read(T+20,4)
        assert self.scene==(DRAW if winner==-1 else WIN)
        assert [p.read(T+i,4) for i in (0,4,8,12,16)]==[2,1,0,0,0x139778]
        self.queued=0
        self.ready=False
        self.draw=(0,0,0)
        self.actor_ticks=0
        self.white_flash=False
        self.winner,self.quote=winner,quote
        self.fading()

    def fading(self):
        p=self.p
        if p.read(T+4,4):
            # At phase 2 count 2 the priority-60 scene task invokes the two
            # function pointers. Stop at the teardown call, never execute
            # graphics / CD- or audio-OS code as if it were an EE fixture.
            midpoint=p.read(T+4,4)==2 and p.read(T+8,4)==2
            self.run(0x1251d0,HANDLE,until=(0x125264,) if midpoint else ())
            if midpoint:
                assert p.registers[14]==p.read(T+16,4)
                if self.queued:
                    self.scene=self.queued
                    self.ready=False
                else:
                    self.ready=True
                    if self.scene==WIN:
                        p.put(20,0x1f00000)
                        self.run(0x135eb4,until=(0x135ef4,))
                        self.descriptor=self.run(0x1a3070,0,2,self.quote)
                        p.write(PAGE+24,self.descriptor,4)
                        p.write(LIMIT,0,4)
                    else:p.write(0x4ca204,0,4)
        self.alpha=p.read(ALPHA,4)
        self.run(0x116b9c,until=(0x116bf0,0x116bf4))

    def tick(self,edges):
        p=self.p
        for i,edge in enumerate(edges):p.write(PADS+i*12+4,edge,4)
        if self.ready and self.scene==WIN:
            self.run(0x136000,until=(0x1360fc,))
            frame=p.read(PAGE+4,4)
            self.draw=(frame,p.read(PAGE+8,4),p.read(LIMIT,4))
            if frame>=60:
                # A separate original run for this descriptor and limit
                # executes the full 1a2870 text walker. Colour and glyph
                # geometry are checked by validate_versus_result_text.py.
                done=self.text_done(self.descriptor,p.read(LIMIT,4))
                p.write(PAGE,done,4)
            for reg in range(16,21):p.put(reg,0x4d0000)
            p.write(STACK+0x28,RET,8)
            self.run(0x136190)
        elif self.ready and self.scene==DRAW:
            requested=p.read(0x3ebf24,4)
            self.run(0x113aa8)
            self.white_flash=bool(requested and p.read(0x3ec73c,4) and p.read(0x3ec730,4)==0xffffffff)
            self.run(0x1387b8,until=(0x138880,))
            frame=p.read(0x4ca204,4)
            if frame==80:self.run(0x138e18,frame)
            self.draw=(frame,self.actor_ticks,0)
            self.actor_ticks+=1
            p.put(16,G)
            p.write(STACK+0x10,RET,8)
            self.run(0x138954)
        target=p.read(T+20,4)
        if target in (AFTER_WIN,AFTER_DRAW):
            self.queued=target
            assert p.read(T,4)==1 and p.read(T+12,4)==1
        self.fading()

    @lru_cache(maxsize=1024)
    def text_done(self,descriptor,limit):
        # After full text the printer keeps returning one. Execute the first
        # post-completion cursor once, then reuse that unchanged threshold.
        if limit>64 and limit!=256:
            return self.text_done(descriptor,64)
        p=self.p
        p.write(0x3a9c20,0x1a00000,4)
        p.write(0x32ce08,1,4)
        p.write(0x43d064,256,4)
        old=p.read(LIMIT,4)
        p.write(LIMIT,limit,4)
        val=self.run(0x1a2870,descriptor)
        p.write(LIMIT,old,4)
        return val

    def snapshot(self):
        p=self.p
        scene,next_scene=self.scene,self.queued
        win=self.winner>=0
        # The task's globals initialize only at scene transfer. Its native
        # fields are already zero while the final battle frame fades away.
        if not self.ready and not next_scene: fields=[0]*6
        elif win:fields=[p.read(PAGE+i,4) for i in (4,8,12,16,0)]+[p.read(LIMIT,4)]
        else:fields=[p.read(0x4ca204,4),self.actor_ticks,0,0,0,0]
        return [scene,next_scene,self.winner,signed(p.read(G+12,4),32),p.read(G+0x38,4),p.read(G,4),
                int(self.ready),*fields,*self.draw,p.read(T+4,4),p.read(ALPHA,4),self.alpha,int(p.read(T,4)==1),int(self.white_flash)]

def cpp_driver(tmp):
    cpp=Path(tmp)/'driver.cpp'
    cpp.write_text(DRIVER)
    exe=Path(tmp)/'page'
    subprocess.run(['c++','-std=c++20','-I',str(ROOT/'src'),str(cpp),str(ROOT/'src/versus_result.cpp'),
                    str(ROOT/'src/versus_result_text.cpp'),'-o',exe],check=True)
    return exe

def check_case(exe,winner,quote,mode):
    oracle=Original()
    commands=[f'I {winner} {quote}']
    oracle.final(winner,quote)
    rows=[oracle.snapshot()]
    first_page=first_draw=queued=transferred=None
    for tick in range(1,1250):
        edges=[0,0]
        f=rows[-1][7]
        if oracle.ready:
            if mode=='start':
                if f in (14,15,16):edges[1-winner]=8
                if f in (15,17):edges[winner]=8|0x200
            elif mode=='hurry':
                if f in (58,60,62):edges[1-winner]=0x607
                if f in (59,61,63):edges[winner]=0x200
            elif mode=='draw-skip':
                if f in (29,31):edges[0]=4
                if f==30:edges=[8,4]
        commands.append(f'T {edges[0]} {edges[1]}')
        oracle.tick(edges)
        row=oracle.snapshot();rows.append(row)
        if row[6] and first_page is None:first_page=tick
        if oracle.ready and row[7]==1 and first_draw is None:first_draw=tick
        if row[1] and queued is None:queued=tick
        if row[0] in (AFTER_WIN,AFTER_DRAW) and transferred is None:transferred=tick
        if transferred is not None and row[16]==0:break
    assert first_page==14 and first_draw==15 and queued<transferred and row[16]==0
    got=subprocess.run([exe],input='\n'.join(commands)+'\n',text=True,capture_output=True,check=True)
    got=[list(map(int,line.split())) for line in got.stdout.splitlines()]
    for i,(expected,actual) in enumerate(zip(rows,got,strict=True)):
        assert expected==actual,(winner,quote,mode,i,commands[i],expected,actual)
    return dict(winner=winner,quote=quote,mode=mode,compared=len(rows),first_page_setup=first_page,
                first_page_draw=first_draw,queued=queued,transfer=transferred,target=hex(row[0]),
                original_calls=oracle.calls,original_instructions=oracle.instructions)

def streaks(exe):
    o=Original()
    scores=[0]*23+[1,1,-1,1,0,-1]
    rows=[]
    for w in scores:
        o.final(w,0);rows.append(o.snapshot()[3:6])
    result=subprocess.run([exe],input=''.join(f'I {w} 0\n' for w in scores),text=True,capture_output=True,check=True)
    assert [list(map(int,line.split()))[3:6] for line in result.stdout.splitlines()]==rows
    return len(rows)

def load_replay(exe,winner,pads):
    args=[exe,ASSETS,'--result-fields']
    if winner<0:args+=['--round-time','60']
    data=''.join(f'1 {l} {r}\n' for l,r in pads)
    res=subprocess.run(args,input=data,text=True,capture_output=True,check=True)
    return [line.split() for line in res.stdout.splitlines()]

def physical(edge):
    # Normalized fighter buttons are rebound to software controller bits
    # for a menu task, which reads the original pad instead of combat input.
    result=edge&0xf8
    for i,b in enumerate((0x400,0x200,2,4,0x400000,0x800000,0x100000,0x200000)):
        if edge & (0x100<<i):result|=b
    return result

def live(exe,winner,mode):
    if winner<0:pads=[(0,0)]*24000
    else:
        approach=[(128,0)]*70+[(0,0)]*3+[(1024,0)]+[(0,0)]*220
        pads=[(0,0)]*500+approach*19
        if winner:pads=[(mirror(b),mirror(a)) for a,b in pads]
    rows=load_replay(exe,winner,pads)
    start=next(i for i,r in enumerate(rows) if r[2]=='1')
    assert int(rows[start][25])==winner
    quote=int(rows[start][26])
    pads=pads[:start+1]
    oracle=Original()
    oracle.final(winner,quote)
    expected=[oracle.snapshot()]
    last=pads[-1]
    for _ in range(1000):
        held=[0,0]
        if oracle.ready and not oracle.queued:
            f=expected[-1][7]
            if mode=='start':
                if f in (15,17):held[winner]=8
                if f==16:held[1-winner]=8
            elif mode=='hurry':
                if f in (59,61,63):held[winner]=0x200
                if f in (58,60,62):held[1-winner]=0x200
            elif mode=='draw-skip':
                if f==29 or f==31:held[0]=0x800
                if f==30:held=[8,0x800]
        edge=[physical(held[i]&~last[i]) for i in range(2)]
        pads.append(tuple(held));last=held
        oracle.tick(edge)
        expected.append(oracle.snapshot())
        if oracle.scene in (AFTER_WIN,AFTER_DRAW) and not oracle.p.read(T+4,4):break
    assert oracle.scene in (AFTER_WIN,AFTER_DRAW)
    rows=load_replay(exe,winner,pads)
    for offset,(r,e) in enumerate(zip(rows[start:],expected,strict=True)):
        actual=list(map(int,r[23:34]))
        want=[e[0],e[1],e[2],quote,e[4],e[13],e[14],e[15],e[7],e[10],e[11]]
        assert actual==want,(winner,mode,start+offset+1,actual,want)
    return dict(mode=mode,winner=winner,quote=quote,terminal_battle_update=start+1,
                battle_hits=[int(rows[start][10]),int(rows[start][20])],
                round_wins=[int(rows[start][12]),int(rows[start][22])],
                compared_result_updates=len(expected),successor=hex(oracle.scene))

def palette_samples():
    from validate_versus_result_text import CACHE, PACKETS
    o=Original()
    p=o.p
    q=o.run(0x1a3070,0,2,0)
    samples=[]
    for tone in (0xff000000,0xffffffff):
        for level in (0,64,128,255,256):
            for a,v in [(0x3a9c20,CACHE),(0x32ce08,1),(0x43d064,256),(LIMIT,1),(0x3ebf2c,1),
                        (0x3ebf18,2),(ALPHA,level),(0x3ec730,tone),(0x345178,0),(0x345180,0)]:
                p.write(a,v,4)
            p.write(0x43ab70,0xf741,2)
            o.run(0x1a2870,q)
            font=p.read(PACKETS+8,4)
            border=o.run(0x117288,0xff000000)&0xffffffff
            o.run(0x116588)
            transformed=p.read(0x11e7980,4)
            dest=tone&255
            expected=0x80000000
            for j,bit in enumerate((10,5,0)):
                base=(0xf741>>bit)&31
                v=(base*(256-level)+(dest>>3)*level)>>8
                expected|=(v<<3)<<(8*j)
            assert transformed==expected
            assert border==(0xff000000|((dest*level)>>8)*0x10101)
            assert font==(0x80000000|(((((255*(256-level)+dest*level)>>8)+1)//2)*0x10101))
            samples.append(dict(tone=hex(tone),level=level,clut_1555_input='0xf741',
                                clut_8888_output=hex(transformed),black_flat_quad_output=hex(border),
                                white_font_packet_rgbaq_low=hex(font)))
    return dict(samples=samples,source='116588 palette RGB555 interpolation; 1148f0/117288 8-bit flat primitives; 113028/117318 text vertex modulation; forced opaque 640x480 quad at 113b28/110b28 when 113aa8 found alpha=256 and transition flag 2, or a prior 117170 one-shot. A generic SDL framebuffer blend is only an approximation of intermediate colours.')

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--exe',type=Path,default=ROOT/'work/ss6/build-native/ss6-match-replay')
    args=parser.parse_args()
    assert digest(ELF)==PIN
    with tempfile.TemporaryDirectory() as tmp:
        exe=cpp_driver(tmp)
        modes=[(n%2,n,'natural') for n in range(16)]
        modes += [(s,s,mode) for s in range(2) for mode in ('start','hurry')]
        modes += [(-1,0,'natural'),(-1,0,'draw-skip')]
        cases=[check_case(exe,*args) for args in modes]
        streak_count=streaks(exe)
        live_cases=[live(args.exe,w,m) for w,m in ((0,'natural'),(1,'natural'),(0,'start'),(1,'hurry'),(-1,'natural'),(-1,'draw-skip'))]
    text=Probe(ELF.read_bytes())
    def asset_string(ptr):
        end=text.memory.index(0,ptr)
        return bytes(text.memory[ptr:end]).decode('shift_jis')
    intro=[asset_string(text.read(0x4efc10+4*i,4)) for i in range(5)]
    assert intro[0].startswith('時はさかのぼること') and '御前試合' in intro[3]
    assert asset_string(text.read(0x5852b4,4))=='rank_obj'
    branches=dict(source_configuration=dict(game_mode=3,ps2_submode=0,field_1c=0,winning_player_field_18=0,
                                             last_entrant=1,secret_unlocks=False),
                  winning_source='0x1362d8:0x136328; 1c60c8 schedules 1c6400, 1c6208 reads the five Edo Tenmei tournament prologue lines from 4efc10, then 1a26b0 displays the selected character dialogue.',
                  tied_source='Task_GameOver 1387b8 checks the opposite of game field +10, then at frame 300 runs 1e6180. The default profile queues 1e8850: starts rank_obj, builds the ranking arrays and name-entry font.',
                  optical_and_successor_scenes='Timing ends at the handoff. No BIOS, asynchronous disc latency or implementation of the receiving prologue / ranking screen is implied.')
    report=dict(status='passed',elf_sha256=PIN,branches=branches,fade_colours=palette_samples(),
                ps2_versus_menu_comparison=dict(report='versus_mode2_heavy_comparison.json',submode=2,post_match_labels=['CHARACTER SELECT','CONTINUE','RETURN TO TITLE'],
                checks='Both slots and five armed heavy attack trajectories, original hit/guard, round-end transition and between-match scores. Does not compare all characters, front-end options, stages, sounds or an entire PS2 session.'),scope='Default fixed local versus; original post-log final branch and streak, priority-60 transition phases, alpha integration, original winner input and frame clocks, original printer completion and GameOver input/exit. Optical loads, graphics, audio, and successors are outside this numeric comparison.',
                cases=cases,streak_sequence_length=streak_count,official_match_replays=live_cases,match_binary_sha256=digest(args.exe))
    REPORT.write_text(json.dumps(report,indent=2)+'\n')
    print(len(cases),'result paths;',sum(c['compared'] for c in cases),'ticks;',streak_count,'successive outcomes')

if __name__=='__main__':
    main()
