#!/usr/bin/env python3
"""Compare drink, reflected whirlwind and wall-strike frames with the original draw and sort."""
import collections
import io
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from validate_haohmaru_flask import matches
from validate_haohmaru_wall_slash import commands as wall
from validate_jump_light_presentation import (
    ASSETS, BUILD, CAPTURE_DRIVER, HEIGHT, LIB, OUT, ROOT, SOURCE_HASH, WIDTH, compare, fixture, sha, verify_queue,
)


from validate_native_scene import capture_combat_layers

def main():
    assert sha(ASSETS.parent/'SLPS_255.59')==SOURCE_HASH
    p=fixture()
    for bank,name in enumerate(('01HitFlash.bin','02Guard.bin','03etc.bin')):
        at=0x4a4810+bank*0x3da0
        p.memory[at:at+0x3da0]=(ASSETS/name).read_bytes()
    stats=collections.Counter()
    results=[]
    viewer=BUILD/'ss6-viewer'
    with tempfile.TemporaryDirectory() as folder:
        tmp=Path(folder)
        probe=tmp/'probe'
        source=tmp/'probe.cpp'
        source.write_text(CAPTURE_DRIVER)
        subprocess.run(['c++','-std=c++20','-O2','-I',ROOT/'src',source,LIB,'-o',probe],check=True)
        for player in (0,1):
            other=1-player
            for move,inputs,targets in [
                ('flask',matches(player,'hit')[0],[(577,player,600),(581,other,396)]),
                # The bank and draw depth follow the original caster during
                # reflection, even after ownership of the hit changes.
                ('reflect',matches(player,'reflect',2)[0],[(560,other,534),(569,other,535)]),
                ('wall',wall(player,'hit'),[(599,player,592),(603,other,390),(631,other,392)])]:
                pads=[(a,b) for line in inputs for n,a,b in [map(int,line.split())] for _ in range(n)]
                chosen={tick for tick,_,_ in targets}
                capture=''.join(f'tick {a} {b} {int(i in chosen)}\n' for i,(a,b) in enumerate(pads[:max(chosen)],1))
                raw=subprocess.run([probe,ASSETS],input=capture.encode(),capture_output=True,check=True)
                data=io.BytesIO(raw.stdout)
                for frame,slot,act in targets:
                    n,=struct.unpack('<I',data.read(4))
                    submitted=[data.read(328) for _ in range(n)]
                    verify_queue(p,submitted,data.getbuffer()[data.tell():])
                    depths=[]
                    for body in submitted:
                        if struct.unpack_from('<I',body,0x144)[0]:
                            continue
                        resource,team=struct.unpack_from('<2I',body,0xc)
                        kind,=struct.unpack_from('<I',body,0xcc)
                        depth,=struct.unpack_from('<f',body,0xb0)
                        if kind==2:
                            assert depth==(13,7)[resource],(move,frame,resource,team,depth)
                        depths.append([kind,resource,team,depth])
                    replay=tmp/'replay'
                    replay.write_text(''.join(f'1 {a} {b}\n' for a,b in pads[:frame]))
                    rgba,background=capture_combat_layers(viewer,replay,tmp)
                    visible=dict(slot=slot,action=act,steps=[])
                    result=compare(p,data,stats,(player,move,frame),rgba,visible,background)
                    assert visible['steps'] and visible['visible_pixels']>0,(player,move,frame,visible)
                    results.append(dict(player=player+1,move=move,frame=frame,depths=depths,**visible,rgba_sha256=result['viewer_sha256']))
                assert not data.read(1)
                print('P'+str(player+1),move,'passed',flush=True)
    assert stats['textured_effect_quads']>0
    report=dict(status='passed',elf_sha256=SOURCE_HASH,viewer_sha256=sha(viewer),runtime_sha256=sha(LIB),cases=results,counts=stats,
                scope='Published native draw records, unmodified original queue and ordering (1207e8/122bc0), original character and effect commands with an independent raster (1208b0/123840). All viewer stage RGBA bytes compared. Visibility counts measure the pixels contributed by the selected actor or projectile. Full console GS scanout is outside this comparison.')
    (OUT/'haohmaru_special_scene_validation.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':
    main()
