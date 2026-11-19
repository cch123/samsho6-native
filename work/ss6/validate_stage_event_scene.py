#!/usr/bin/env python3
"""Count visible referee pixels in the published versus scene using the Japanese raster inputs."""
from collections import Counter
import json
from pathlib import Path
import struct
import tempfile
from validate_combat_stage import jump_draw_records
from validate_dash_motion import ELF, PIN, ROOT, digest
from validate_jump_light_presentation import verify_queue
from validate_native_scene import compare,capture_combat_layers

OUT=ROOT/'outputs/ss6-feasibility'
VIEWER=OUT/'native-viewer/ss6-viewer'


def main():
    assert digest(ELF)==PIN
    # Actual starts, greeting, ordinary stance and a heavy-hit flag signal.
    segments=[(500,0,0),(36,128,64),(8,0,0),(1,1024,0),(65,0,0)]
    samples=[120,500,566,581]
    results=[];stats=Counter()
    with tempfile.TemporaryDirectory() as tmp:
        folder=Path(tmp);p,stream=jump_draw_records(folder,segments,samples)
        for tick in samples:
            (n,)=struct.unpack('<I',stream.read(4));published=[stream.read(328) for _ in range(n)]
            verify_queue(p,published,stream.getbuffer()[stream.tell():])
            refs=[struct.unpack('<82I',r) for r in published if struct.unpack_from('<I',r,12)[0]==2 and 25<=struct.unpack_from('<I',r,36)[0]<=44]
            assert len(refs)==1,(tick,len(refs))
            remaining=tick;prefix=[]
            for length,a,b in segments:
                if not remaining:break
                count=min(remaining,length);prefix.append(f'{count} {a} {b}');remaining-=count
            pad=folder/'snapshot.pad';pad.write_text('\n'.join(prefix)+'\n')
            scene,background=capture_combat_layers(VIEWER,pad,folder)
            stage_ref=dict(slot=2,action=refs[0][9],steps=[])
            outcome=compare(p,stream,stats,tick,scene,stage_ref,background)
            assert stage_ref['quads'] and stage_ref['visible_pixels']>0,(tick,stage_ref)
            assert stage_ref['steps']==[refs[0][10]]
            results.append(dict(tick=tick,rgba_sha256=outcome['viewer_sha256'],**stage_ref))
        assert not stream.read(1)
    report=dict(status='passed',elf_sha256=PIN,viewer_sha256=digest(VIEWER),validator_sha256=digest(Path(__file__)),
                scope='Four published 640×448 console-versus combat images. Copy and sort the actual world-queue records with 1207e8/122bc0, project and fetch slot2 resource51 referee sprites through Japanese 1208b0/121b80, reconstruct primitive colors/geometry/texture coordinates and compare the final image byte for byte. Count referee pixels by repeating the composite with its batch removed. The arena is supplied by the viewer and is covered by its separate stage oracle.',frames=results,renderer=stats)
    (OUT/'stage_event_scene_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print([(s['tick'],s['action'],s['visible_pixels']) for s in results])


if __name__=='__main__':main()
