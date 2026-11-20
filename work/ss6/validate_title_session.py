#!/usr/bin/env python3
"""Compare title/VS navigation to SLPS-25559, then play through the shipping results screen twice."""
import argparse
import json
import struct
import subprocess
import tempfile
from hashlib import sha256
from pathlib import Path

import numpy as np
from PIL import Image
from validate_console_title_art import fixture, original_frame
from validate_console_versus_menu import Oracle, physical
from validate_versus_result import ALPHA, T, HANDLE
from validate_versus_heavy import ROOT, HERE, BUILD, PKG, DUMMY
from validate_select_session import encode
from validate_rimururu_session import win, choose

OUT=ROOT/'outputs/ss6-feasibility'
ELF=HERE/'extracted/SLPS_255.59'
ZERO=(0,0)

def trace(assets,mode,field,pads):
    encoded=''.join(f'1 {a} {b}\n' for a,b in pads)
    result=subprocess.run([BUILD/'ss6-match-replay',assets,'--mode',mode,field],input=encoded,
                          text=True,capture_output=True,check=True)
    return [line.split() for line in result.stdout.splitlines()]

class TitleSource(Oracle):
    def __init__(self,returning):
        super().__init__()
        # Execute the real title entry, menu handlers, repeat logic, two-pad arbitration
        # and transition task. Rendering, RPC/IO and the next scene have separate checks.
        p=self.p
        p.run(0x1113e8,[0x43d058])
        for addr in (0x1142d8,0x1163c0,0x116478,0x10add8,0x1e79c8,0x1e7c00,0x1b9e00,0x1ba920,
                     0x1bc1a8,0x1c4e08,0x1132c0,0x323050,0x1cd778,0x1cd818,0x1cdac8,0x127df0,
                     0x1e7b70,0x1e7d60,0x1b6570,0x127d70,0x128008,0x139778):
            p.memory[addr:addr+8]=struct.pack('<II',0x03e00008,0x0000102d)
        p.write(0x3aa160,3,4)
        for a in (0x4c8278,0x4c827c):p.write(a,1 if returning else 2,4)
        if returning:
            # Enter from the results task via its real black transition and
            # teardown. The busy word is set here and cleared by 1252ec when
            # the fade finishes, before either menu port accepts CANCEL.
            p.write(0x582af8,0,4)  # VS was the last mode selected.
            p.write(0x582fbc,4,4)
            self.run(0x1252f0,2,0,0x1db2e0,0x127940)
            entered=[]
            for _ in range(24):
                self.run(0x1251d0,HANDLE,observe=lambda pc:entered.append(pc) if pc==0x127940 else None)
                self.run(0x116b9c,stop=(0x116bf0,0x116bf4))
                if entered:break
            assert entered and p.read(0x4c3834,4)==1
        else:self.run(0x127940)
        assert p.read(0x582af8,4)==(0 if returning else 5)
        self.selected=False

    def advance(self,pads):
        p=self.p
        self.sample(tuple(physical(x) for x in pads))
        draw=[];events=[];new_scene=[]
        def watch(pc):
            if pc in (0x127df0,0x1cd818,0x1cdac8):
                draw[:]=[int(pc!=0x127df0),p.read(0x582af8,4),p.read(0x582b00,4),p.read(0x582b08,4),
                         p.read(0x4c8268,4),p.read(0x4c826c,4)]
            elif pc==0x128008:new_scene.append(pc)
            elif pc==0x1e7b70:events.append((0,(p.registers[4]+1)&0xffffffff,p.registers[5]))
            elif pc==0x1e7d60:events.append((1,p.registers[4],p.registers[5]))
        alpha=p.read(ALPHA,4)
        if not self.selected:self.run(0x127a88,observe=watch)
        if p.read(T+4,4):self.run(0x1251d0,HANDLE,observe=watch)
        self.run(0x116b9c,stop=(0x116bf0,0x116bf4))
        self.selected|=bool(new_scene)
        return draw,alpha,self.selected,events

def pair(seat,word):return (0,word) if seat else (word,0)

def navigation(seat):
    # Release and re-enter from the mode screen, press both directions, and hold
    # DOWN through the wrap and disabled NETWORK row. The other port confirms VS.
    p=[ZERO]*32+[pair(seat,8)]+[ZERO]*15+[pair(seat,16|32)]+[ZERO]*16+[pair(seat,256)]
    p += [ZERO]*8+[pair(seat^1,8)]+[ZERO]*16
    p += [pair(seat,32)]*85+[ZERO]*19
    return p

def oracle_check(assets,seat):
    pads=navigation(seat)
    src=TitleSource(False)
    refs=[src.advance(row) for row in pads]
    while src.p.read(0x582af8,4)!=0:
        extra=[pair(seat,32)]+[ZERO]*16
        refs.extend(src.advance(row) for row in extra);pads.extend(extra)
    tail=[pair(seat^1,1024)]+[ZERO]*30
    refs.extend(src.advance(row) for row in tail);pads+=tail
    rows=trace(assets,'title','--title-fields',pads)
    audio=trace(assets,'title','--sound-fields',pads)
    for n,(ref,row,sound) in enumerate(zip(refs,rows,audio,strict=True)):
        draw,alpha,selected,events=ref
        actual=list(map(int,row[23:]))
        assert actual[0]==int(not selected) and actual[8]==int(selected),(seat,n,ref,actual)
        if not selected:
            # The debug idle counter can reset inside the P2 cancel visit before
            # the mode submission. Only the title page reads it for display.
            size=5 if draw[0] else 6
            assert actual[1:1+size]==draw[:size],(seat,n,draw,actual)
        assert actual[7]==alpha,(seat,n,alpha,actual)
        if not selected:
            raw=list(map(int,sound[26:]))
            ui=[tuple(raw[i:i+3]) for i in range(0,len(raw),3) if raw[i] in (0,1)]
            assert ui==events,(seat,n,ui,events)
    assert rows[-1][32:34]==[str(src.p.read(0x4c3818+4*i,4)) for i in range(2)]==[str(seat)]*2
    return len(rows)

class Display:
    def __init__(self,assets,viewer,temp):
        self.assets,self.viewer,self.temp=assets,viewer,temp
        self.p,self.tex=fixture(assets)
        self.cache={};self.frames={}

    def check(self,mode,sequence,name,menu,first,prompt,level=0,white=False):
        replay=self.temp/'title-replay.txt';replay.write_text(encode(sequence))
        out=self.temp/'frame.bmp'
        subprocess.run([self.viewer,'--assets',self.assets,'--mode',mode,'--match-replay',replay,'--snapshot',out],
                       env=DUMMY,capture_output=True,check=True)
        actual=np.asarray(Image.open(out).convert('RGBA'))
        original,_,_=original_frame(self.p,self.tex,menu,first,0,0,0,0,prompt,level,white,self.cache)
        scale=actual.shape[0]//480
        assert actual.shape==(480*scale,640*scale,4)
        wanted=np.repeat(np.repeat(original,scale,axis=0),scale,axis=1)
        assert np.array_equal(actual,wanted),(name,actual.shape,int(np.any(actual!=wanted,axis=2).sum()))
        self.frames[name]=sha256(original.tobytes()).hexdigest()
        return self.frames[name]

def play_set(assets,display,seat):
    # Enable stage items in the old set to make the title reset observable.
    old=choose((0,3),0)
    old[265][1]=128
    ready=win(assets,old,seat)
    to_title=[pair(seat,16),ZERO,pair(seat,1024),ZERO,pair(seat,128),ZERO,pair(seat,1024)]
    pads=ready+to_title+[ZERO]*32
    oldrows=trace(assets,'select','--title-fields',pads)
    title_at=next(i for i,r in enumerate(oldrows) if r[23]=='1')
    assert title_at>len(ready) and oldrows[title_at][24:26]==['1','0']
    assert oldrows[len(ready)-1][34:38]==(['0','1','1','0'] if seat else ['1','0','0','1'])
    source=TitleSource(True)
    for j,pad in enumerate(pads[title_at+1:]):
        draw,alpha,_,_=source.advance(pad)
        if seat==0 and j in (0,3,8,10):
            display.check('select',pads[:title_at+2+j],f'black-{j}',True,draw[1],0,alpha)
    assert source.p.read(0x4c3834,4)==0
    menu_image=display.check('select',pads,f'menu-{seat}',True,0,0)
    cancel=pads+[pair(seat,256)]
    display.check('select',cancel,f'cancel-{seat}',True,0,0)
    idle=cancel+[ZERO]*(120-len(cancel)%120)
    display.check('select',idle,f'after-cancel-{seat}',False,5,1)
    # Both original ports are already joined, so RETURN TO TITLE highlights VS.
    # At speed zero the midpoint is the fifteenth visit, counting confirmation.
    start=pair(seat,1024)
    prefix=pads+[start]+[ZERO]*14
    for j,pad in enumerate(prefix[len(pads):]):
        draw,alpha,selected,_=source.advance(pad)
        if seat==0 and j in (1,4,9,12):
            assert not selected
            display.check('select',prefix[:len(pads)+j+1],f'white-{j}',True,draw[1],0,alpha,True)
    grid=trace(assets,'select','--select-fields',prefix)[-1]
    assert grid[24]=='1' and grid[46]==str(seat^1) and grid[51]=='256',grid
    assert grid[28:33]==['2','1','-1','0','5'] and grid[38:43]==grid[28:33],grid
    assert grid[53:56]==['0','0','0']
    new=choose((2,0),0)
    if seat:
        # The stage owner is P1 when P2 confirmed VS. Only transfer
        # the four post-spirit stage commands, leaving both fighters' choices alone.
        for i in (279,309,354,379):new[i][0],new[i][1]=new[i][1],new[i][0]
    after=prefix+new
    attack=[(128,0)]*45+[(1024,0)]+[ZERO]*84
    rows=trace(assets,'select','--select-fields',after+attack)
    end=rows[len(after)-1]
    assert end[23:26]==['2','0','2'] and end[35]=='0' and end[52:56]==['0','0','0','0'],end
    assert end[12]==end[22]=='0' and end[9]==end[19]=='200'
    assert any(int(r[19])<200 for r in rows[len(after):])
    return dict(winner=seat,postmatch_title_tick=title_at+1,mode_menu_rgba=menu_image,
                character_select_tick=len(prefix),second_lineup=[2,0],second_defender_life=int(rows[-1][19]))

def main():
    cli=argparse.ArgumentParser();cli.add_argument('--package',action='store_true');args=cli.parse_args()
    assets=PKG/'assets' if args.package else HERE/'extracted/resources'
    viewer=(PKG if args.package else BUILD)/'ss6-viewer'
    if args.package:assert sha256(viewer.read_bytes()).digest()==sha256((BUILD/'ss6-viewer').read_bytes()).digest()
    checks=[oracle_check(assets,seat) for seat in (0,1)]
    with tempfile.TemporaryDirectory() as tmp:
        display=Display(assets,viewer,Path(tmp))
        for n,prompt in ((1,1),(59,1),(60,0),(119,0),(120,1)):
            display.check('title',[ZERO]*n,f'cold-{n}',False,5,prompt)
        display.check('title',[ZERO]*10+[(0,8)],'start-edge',False,5,1)
        display.check('title',[ZERO]*10+[(0,8),ZERO],'mode-after-start',True,5,0)
        sets=[play_set(assets,display,seat) for seat in (0,1)]
    assert sets[0]['mode_menu_rgba']==sets[1]['mode_menu_rgba']
    report=dict(status='passed',original_sha256=sha256(ELF.read_bytes()).hexdigest(),viewer_sha256=sha256(viewer.read_bytes()).hexdigest(),
                original_input_and_transition_frames=checks,completed_sets=sets,original_sdl_frames=display.frames)
    (OUT/'title-session-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))

if __name__=='__main__':main()
