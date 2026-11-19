#!/usr/bin/env python3
"""Compare the Japanese menu banks, VS spoken names and Nakoruru voice slots at EE/IOP and PCM."""
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import struct
import subprocess
import tempfile
from functools import cache

from validate_combat_audio import OriginalDriver, Iso, ISO, DRIVER, ROOT, RES, SOURCE, PIN, sha

OUT=ROOT/'outputs/ss6-feasibility/select-audio-validation.json'
DRIVER=DRIVER.replace("if(op=='S'){","if(op=='B'){std::cin>>a>>b;mixer.bindPlayers({unsigned(a),unsigned(b)});}\n        if(op=='S'){")

def selection_cues():
    from validate_character_select import Source
    # Walk the complete factory grid with real pad edges. Branch each cursor
    # position by one tick to confirm it before continuing the grid walk.
    # The hidden random result is confirmed from the EE's chosen ID below.
    seed=next(n for n in range(1000) if (((n*0x5851f42d4c957f2d+1)>>32)&0x7fff)*41>>15==40)
    src=Source(1,seed)
    for _ in range(63):src.step((0,0))
    confirmations={}
    def advance(pads):
        row=src.step(pads)
        if any(pads):
            assert src.audio==[0,2,0,2],(pads,src.audio)
        return row
    for column in range(7):
        for _ in range(6):
            trial=deepcopy(src);cells=[trial.p.read(0x4c82a0+i*4,4) for i in (0,1)]
            assert cells[0]==cells[1]
            row=trial.step((1024,1024))
            for seat,id_col in enumerate((13,34)):
                index=row[id_col];bank,tone=trial.audio[2*seat:2*seat+2]
                assert (bank,tone)==((0,index+3) if index<20 else (1,index-20))
                confirmations[index]=(bank+1,tone)
            advance((32,32));advance((0,0))
        if column<6:
            advance((128,64))
            for _ in range(10):advance((0,0))
    assert set(confirmations)=={*range(40),42}
    return confirmations

def main(assets):
    iso=Iso(ISO);o=OriginalDriver(iso);commands=[];wanted=[];names=[];keysets={};events=Counter()
    @cache
    def group(name,idx):
        stride=0x250 if name=='BVOICE2' else 0x110
        header=iso.read('/VOICE/'+name+'.MSH')[idx*stride:idx*stride+stride]
        sector,_,size,_=struct.unpack_from('<4I',header)
        data=iso.read_at((iso.by_path['/VOICE/'+name+'.MSB']['lba']+sector)*iso.block,size)
        return header,data
    def op(letter,*params):
        value=0
        if letter=='B':
            # 212dd8 installs the three resource IDs and uploads each selected
            # SPU2 short bank and EE voice bank. Keep the subsequent original
            # request lookup, DMA service, IRX dispatcher and registers live.
            for side,idx in enumerate(params):
                o.ee.write(0x59d01c+4*side,idx,4)
                h,d=group('BVOICE2',idx);at=(0x5b010,0xb1010)[side]
                o.spu[at:at+len(d)]=d
                if idx<49:
                    h,d=group('BVOICE1',idx);at=0x1466980+0x76800*side
                    o.ee.memory[at:at+len(d)]=d
        elif letter=='S':value=o.call(0x212fa0,*params)
        elif letter=='V':value=o.call(0x213378,*params)
        elif letter=='T':o.call(0x213660)
        elif letter=='G':o.call(0x213be8,*params)
        elif letter=='K':o.call(0x213bc8,*params)
        elif letter=='R':o.render(params[0])
        else:raise ValueError(letter)
        events[letter]+=1;wanted.append(value);commands.append(' '.join(map(str,[letter,*params])))
        return value
    def name_test(idx,slot):
        h,d=group('BVOICE1',idx);n=struct.unpack_from('<I',h,4)[0]
        q=o.ee.read(0x59d008,4)
        op('V',49,100 if idx==42 else idx+2)
        tone=n-2-(8 if idx==29 else 0)
        size,offset=struct.unpack_from('<2I',h,16+8*tone)
        req=0x15539b0+q*16
        assert o.ee.read(0x15539a0+q*4,4)==slot
        assert o.ee.read(req,4)==0x1466980+slot*0x76800+offset and o.ee.read(req+8,4)==size
        assert bytes(o.ee.memory[o.ee.read(req,4):o.ee.read(req,4)+size])==d[offset:offset+size]
        for _ in range(3):op('T')
        # Three visits to 213660 have keyed the desired physical voice. Silence
        # the *other* lane first so a channel swap produces a PCM difference.
        assert slot+2 in o.voices
        # Render the complete name at the streamed SPU2 pitch, including its
        # end block and release. Checking only the attack misses bad offsets
        # that share the initial silence or run into the following sample.
        frames=(size//16*28*0x1000+0x760)//0x761+16
        op('K',3-slot);op('R',frames);op('G',2);op('R',7)
        names.append(dict(character=idx,physical=slot+2,tone=tone,bytes=size,stereo_frames=frames,sha256=sha(d[offset:offset+size])))
    op('B',51,52)
    for idx in (51,52):
        h,d=group('BVOICE2',idx);assert (assets/f'vs_sounds_{idx}.bin').read_bytes()==h+d
    # 12acb8 keys the common-bank click as each portrait tile opens. The
    # confirmation tuples below came from real 112838 visits on each cell.
    choices=selection_cues()
    for bank,tone in [(0,24),(1,0),(1,1),(1,2),*choices.values()]:
        h,d=group('BVOICE2',50+bank);size,off=struct.unpack_from('<2I',h,16+8*tone)
        key=op('S',bank,tone);v=1+2*key
        assert o.registers[v|0x2040]==(0x5010,0x5b010,0xb1010)[bank]+off
        assert o.registers[v|0x200]==0x3b0
        assert key in range(14,22)
        op('R',2200);op('G',1);op('R',7)
    for idx in (*range(40),42):
        h,d=group('BVOICE1',idx)
        if idx:assert (assets/f'vs_voice_{idx:02}.bin').read_bytes()==h+d
        for slot in range(2):
            other=int(idx==0)
            op('B',*( (other,idx) if slot else (idx,other) ));name_test(idx,slot)
    # The name of character 29 uses a stream after its eight resident entries.
    # Exercise both sides of that threshold, independently of the name alias.
    for slot in range(2):
        op('B',*((0,29) if slot else (29,0)))
        for n in range(10):
            key=op('V',29,n)
            if n<8:
                assert key==1
                h,d=group('BVOICE1',49);_,off=struct.unpack_from('<2I',h,16+8*(n+4))
                assert any(o.registers.get((1+2*k)|0x2040)==0x146010+off for k in range(14,22))
            else:
                assert key==-1
                for _ in range(3):op('T')
            op('R',2133);op('G',3);op('R',7)
    # Real 01 in both seats has separate short-bank addresses and two stream
    # channels. With two matching characters 213418 always prefers P1.
    for pair in ((1,0),(0,1),(1,1)):
        op('B',*pair)
        for slot,c in enumerate(pair):
            h,d=group('BVOICE2',c);n=struct.unpack_from('<I',h,4)[0]
            if c:assert (assets/'vs_sounds_01.bin').read_bytes()==h+d
            for tone in range(n):
                key=op('S',slot+1,tone);v=1+2*key;off=struct.unpack_from('<I',h,20+8*tone)[0]
                assert o.registers[v|0x2040]==(0x5b010,0xb1010)[slot]+off
                op('R',213);op('G',1);op('R',7)
            for tone in range(struct.unpack_from('<I',group('BVOICE1',c)[0],4)[0]):
                pending=o.ee.read(0x59d008,4);op('V',c,tone)
                assert o.ee.read(0x15539a0+pending*4,4)==pair.index(c)
                for _ in range(3):op('T')
                op('R',423);op('G',2);op('R',7)
        keysets[str(pair)]=True
    with tempfile.TemporaryDirectory() as d:
        w=Path(d);src=w/'audio.cpp';exe=w/'audio';out=w/'pcm';src.write_text(DRIVER)
        subprocess.run(['c++','-std=c++20','-O2','-I',SOURCE,src,SOURCE/'combat_audio.cpp',SOURCE/'combat_music.cpp',
                        SOURCE/'combat_sound_bank.cpp','-o',exe],check=True)
        p=subprocess.run([exe,assets,out],input='\n'.join(commands)+'\n',text=True,capture_output=True)
        if p.returncode:raise RuntimeError(p.stderr)
        actual=list(map(int,p.stdout.split()))
        for i,(got,want) in enumerate(zip(actual,wanted,strict=True)):assert got==want,(commands[i],got,want)
        audio=out.read_bytes()
        if audio!=o.pcm:
            i=next((n for n,(a,b) in enumerate(zip(audio,o.pcm)) if a!=b),None)
            raise AssertionError(('PCM byte',i,'time frame',i//4 if i is not None else None,len(audio),len(o.pcm)))
    files=[assets/n for n in ('combat_sound_bank.bin','vs_sounds_01.bin','vs_sounds_51.bin','vs_sounds_52.bin')]
    files.extend(assets/f'vs_voice_{i:02}.bin' for i in (*range(1,40),42))
    report=dict(status='passed',asset_directory=str(assets),asset_sha256={f.name:sha(f.read_bytes()) for f in files},ee_sha256=PIN,irx_sha256=o.irx_hash,names=names,menu_confirmations=choices,seat_pairs=keysets,
                ee_instructions=o.ee_steps,iop_instructions=o.iop_steps,rpc=o.ops,key_ons=o.keys,operations=events,
                stereo_frames=len(audio)//4,pcm_sha256=sha(audio),mixer_source_sha256=sha((SOURCE/'combat_audio.cpp').read_bytes()),
                scope='Japanese factory 0..39 and hidden random outcome 42, both seats. Menu bank51/52 click/confirm/spoken cues, character names from 213378(49,...), character29 resident/stream split, both Nakoruru SE and streamed slots and mirror priority. Original EE+IRX with original disc bytes, SPU2 model versus native mixer PCM; no hardware recording.')
    OUT.write_text(json.dumps(report,indent=2)+'\n');print(len(names),'name routes',o.keys,'key-ons',len(audio)//4,'stereo frames')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--assets',type=Path,default=RES);main(parser.parse_args().assets)
