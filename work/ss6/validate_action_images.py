#!/usr/bin/env python3
"""Check selected native composites against an independent pixel traversal."""
import hashlib
import json
import struct
import subprocess
from functools import lru_cache
from pathlib import Path
from validate_assets import png

ROOT=Path(__file__).resolve().parents[2]
ASSETS=ROOT/'work/ss6/extracted/resources'
OUT=ROOT/'outputs/ss6-feasibility'


def main():
    aid,act,pil,idx,maps,tiles,pal=[(ASSETS/f).read_bytes() for f in
        ['aid_00.bin','act_00.bin','pil_00.bin','idx_00.bin','map_00.bin','chr_00.bin','pal_all.bin']]
    binary=ROOT/'work/ss6/build-native/ss6-viewer'
    scratch=ROOT/'work/ss6/actions/comparison.rgba'
    @lru_cache(None)
    def image(index):
        entry,=struct.unpack_from('<I',idx,index*4)
        bank,offset=entry>>24,entry&0xffffff
        assert bank<=1
        tw,th=maps[offset:offset+2]
        w,h=tw*8,th*8
        colors=[]
        for c, in struct.iter_unpack('<H',pal[bank*32:bank*32+32]):
            colors.append(bytes((((c>>10)&31)*255//31,((c>>5)&31)*255//31,(c&31)*255//31,255 if c&0x8000 else 0)))
        pixels=bytearray()
        for y in range(h):
            for x in range(w):
                tx,ty=x//8,y//8
                slot=(ty//2)*tw*2+(tx//2)*4+(ty%2)*2+tx%2
                tile=int.from_bytes(maps[offset+2+slot*3:offset+5+slot*3],'little')
                packed=tiles[tile*32+y%8*4+x%8//2]
                pixels.extend(colors[(packed>>(x%2*4))&15])
        return w,h,pixels

    def compose(record,mirror=False):
        parts=[]
        for ref in struct.unpack_from('<5h',act,record*60+4):
            if ref:
                cell,x,y,z,tint,flags,unknown=struct.unpack_from('<4hI2H',pil,(ref-1)*16)
                assert flags&0x7ff0==0x10 and tint==0xff808080
                if cell: parts.append((flags&15,cell-1,x,y,flags))
        canvas=bytearray(200*140*4)
        for _,cell,px,py,flags in sorted(parts,key=lambda part:part[0]):
            w,h,pixels=image(cell)
            # Read source in reverse for local horizontal flip, as opposed to
            # the C++ implementation's reflected destination coordinates.
            for y in range(h):
                for x in range(w):
                    sx=w-1-x if bool(flags&0x8000)!=mirror else x
                    c=pixels[(y*w+sx)*4:(y*w+sx+1)*4]
                    if not c[3]: continue
                    # Independent per-cell transform from 0x121858/0x121d70;
                    # unlike C++, do not reflect an already composed canvas.
                    dx=(110-px-w if mirror else 90+px)+x
                    dy=128-py+y
                    # The legacy fixed crop may clip the lowest pixels in
                    # victory498. This is a preview bound, not a sprite edit.
                    if not (0<=dx<200 and 0<=dy<140):continue
                    canvas[(dy*200+dx)*4:(dy*200+dx+1)*4]=c
        return canvas

    comparisons=[]; sheets={}
    for action in [0,1,10,11,12,13,185,286,287,290,291,495,496,497,498]:
        start,=struct.unpack_from('<h',aid,action*2)
        count=aid[0x1000+action];tick=0
        frames=[]
        for step in range(count):
            for mirror in [False,True]:
                expected=compose(start+step,mirror)
                subprocess.run([str(binary),'--assets',str(ASSETS),'--action',str(action),
                                '--updates',str(tick),'--dump',str(scratch),'--dump-mirror',str(int(mirror))],check=True)
                raw=scratch.read_bytes()
                assert struct.unpack('<II',raw[:8])==(200,140)
                assert raw[8:]==expected,(action,step,mirror,'native composite mismatch')
                comparisons.append(dict(action=action,step=step,mirror=mirror,first_update=tick,sha256=hashlib.sha256(expected).hexdigest()))
                if not mirror: frames.append(expected)
            tick+=struct.unpack_from('<h',act,(start+step)*60+0x34)[0]
        sheets[action]=frames
    scene_count=0
    def at_tick(action,tick):
        start=struct.unpack_from('<h',aid,action*2)[0];count=aid[0x1000+action]
        durations=[struct.unpack_from('<h',act,(start+i)*60+0x34)[0] for i in range(count)]
        # Idle loops; attack and guard-pose fixtures hold their last record.
        tick=tick%sum(durations) if action==0 else min(tick,sum(durations)-1)
        for i,duration in enumerate(durations):
            if tick<duration: return start+i
            tick-=duration
        raise AssertionError('Unreachable phase')
    for tick in [0,1,2,3,4,8,9,18,19,55,100]:
      for defense,defender_action in [('neutral',0),('stand',286),('crouch',290)]:
        for distance in [-160,-64,0,48,64,96,160]:
            canvas=bytearray(288*140*4)
            for action,x,mirror in [(185,0,False),(defender_action,distance,True)]:
                pixels=compose(at_tick(action,tick),mirror)
                ox=int(144+x-distance/2)-(110 if mirror else 90)
                for y in range(140):
                    for px in range(200):
                        dx=ox+px
                        c=pixels[(y*200+px)*4:(y*200+px+1)*4]
                        if 0<=dx<288 and c[3]: canvas[(y*288+dx)*4:(y*288+dx+1)*4]=c
            subprocess.run([str(binary),'--assets',str(ASSETS),'--mode','contacts','--action','185',
                            '--updates',str(tick),'--target-x',str(distance),'--defense',defense,'--dump',str(scratch)],check=True)
            raw=scratch.read_bytes()
            assert struct.unpack('<II',raw[:8])==(288,140) and raw[8:]==canvas,(tick,distance,defense,'scene mismatch')
            scene_count+=1
    # A deterministic contact sheet makes phase/weapon alignment reviewable.
    frames=sheets[185];width,height=4*200,2*140
    sheet=bytearray(bytes([22,28,37,255])*(width*height))
    for i,frame in enumerate(frames):
        ox,oy=i%4*200,i//4*140
        for y in range(140):
            for x in range(200):
                c=frame[(y*200+x)*4:(y*200+x+1)*4]
                if c[3]: sheet[((oy+y)*width+ox+x)*4:((oy+y)*width+ox+x+1)*4]=c
    png(OUT/'attack-185-contact-sheet.png',width,height,sheet)
    report=dict(all_passed=True,composite_count=len(comparisons),contact_scene_count=scene_count,actions=list(sheets),comparisons=comparisons,
                viewer_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                scope='Independent native/Python decoders agree for both actor facings, PIL local flips and two-actor inspection scenes; this is not a GS/PS2 rendered image comparison.')
    (OUT/'action_image_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='comparisons'},indent=2))


if __name__=='__main__': main()
