#!/usr/bin/env python3
"""Verify visible discarded sword and taunt poses using the Japanese PS2 draw and tile routines."""
import collections
import io
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from validate_jump_light_presentation import ASSETS, BUILD, CAPTURE_DRIVER, HEIGHT, LIB, OUT, ROOT, WIDTH, compare, fixture, sha, verify_queue, write_png


from validate_native_scene import capture_combat_layers

def main():
    oracle=fixture()
    for i,bank in enumerate(('01HitFlash.bin','02Guard.bin','03etc.bin')):
        at=0x4a4810+0x3da0*i
        oracle.memory[at:at+0x3da0]=(ASSETS/bank).read_bytes()
    stats=collections.Counter()
    cases=[]
    with tempfile.TemporaryDirectory() as temp:
        tmp=Path(temp);source=tmp/'driver.cpp';source.write_text(CAPTURE_DRIVER)
        exe=tmp/'driver'
        subprocess.run(['c++','-std=c++20','-I',ROOT/'src',source,LIB,'-o',exe],check=True)
        for slot in range(2):
            forward=(128,64)[slot]
            # Separate button edges by a full natural recovery so state 49
            # observes the armed costume and then its unarmed counterpart.
            steps=[(500,0),(1,(forward^192)|8),(230,0),(1,forward|8),(114,0),(1,(forward^192)|8),(193,0)]
            pads=[(mask,0) if slot==0 else (0,mask) for n,mask in steps for _ in range(n)]
            selected=[(547,150),(780,135),(792,467),(845,467),(885,151)]
            indices={i for i,_ in selected}
            replay=tmp/'replay'
            text=''.join(f'tick {a} {b} {int(i in indices)}\n' for i,(a,b) in enumerate(pads[:max(indices)],1))
            raw=subprocess.run([exe,ASSETS],input=text.encode(),capture_output=True,check=True)
            data=io.BytesIO(raw.stdout)
            for frame,action in selected:
                n,=struct.unpack('<I',data.read(4))
                submissions=[data.read(328) for _ in range(n)]
                verify_queue(oracle,submissions,data.getbuffer()[data.tell():])
                replay.write_text(''.join(f'1 {a} {b}\n' for a,b in pads[:frame]))
                rgba,background=capture_combat_layers(BUILD/'ss6-viewer',replay,tmp)
                visible=dict(slot=slot,action=action,steps=[])
                checked=compare(oracle,data,stats,(slot,frame,action),rgba,visible,background)
                assert visible['steps'] and visible['visible_pixels']>0,(slot,frame,visible)
                if slot==0 and frame==845:
                    write_png(OUT/'weapon-discard.png',rgba)
                cases.append(dict(player=slot+1,frame=frame,**visible,rgba_sha256=checked['viewer_sha256']))
            assert not data.read(1)
            if slot==0:
                (OUT/'weapon-discard.replay').write_text(''.join(f'{n} {mask} 0\n' for n,mask in steps))
    report=dict(status='passed',cases=cases,counts=stats,viewer_sha256=sha(BUILD/'ss6-viewer'),runtime_sha256=sha(LIB),
                scope='Native viewer dimensions and all pixels compared with original PS2 queue submission, sorting, tiles, CLUT and independent raster on published native geometry. The visible-pixel count recomposes each frame without its selected body or dropped weapon.')
    (OUT/'weapon_handling_scene_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(len(cases),'complete viewer images;',stats['quads'],'character and weapon quads')


if __name__=='__main__':main()
