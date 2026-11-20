#!/usr/bin/env python3
"""Independent original sprite/CLUT composition for native throw and mutual throw-break frames."""
import collections
import io
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
from validate_ground_throw import ASSETS, ELF, MATCH, PIN, ROOT, digest, pad_case
from validate_jump_light_presentation import BUILD,CAPTURE_DRIVER,HEIGHT,OUT,WIDTH,compare,fixture,verify_queue,write_png

from validate_native_scene import capture_combat_layers

def main():
    assert digest(ELF)==PIN
    p=fixture();stats=collections.Counter();cases=[]
    for bank,name in enumerate(('01HitFlash.bin','02Guard.bin','03etc.bin'),1):
        addr=0x4a4810+(bank-1)*0x3da0;p.memory[addr:addr+0x3da0]=(ASSETS/name).read_bytes()
    with tempfile.TemporaryDirectory() as folder:
        tmp=Path(folder);lib=tmp/'lib.a';shutil.copyfile(BUILD/'libss6-runtime.a',lib)
        view=tmp/'view';shutil.copy2(BUILD/'ss6-viewer',view)
        program=tmp/'probe.cpp';program.write_text(CAPTURE_DRIVER);exe=tmp/'probe'
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',program,lib,'-o',exe],check=True)
        for slot,kind,selected in [(0,'forward',{4:404,32:404,39:408,56:400}),
                                   (1,'back',{4:406,54:410,78:400}),
                                   (0,'break',{3:236,16:236})]:
            walk,inputs=pad_case(slot,kind)
            def pair(a,b):return (b,a) if slot else (a,b)
            pads=[(0,0)]*500+[pair((128,64)[slot],0)]*walk+[(0,0)]*6;prefix=len(pads)
            pads+=[pair(a,b) for a,b in inputs[:max(selected)]]
            commands=''.join(f'tick {a} {b} {int(i+1-prefix in selected)}\n' for i,(a,b) in enumerate(pads))
            probe=subprocess.run([exe,ASSETS],input=commands.encode(),capture_output=True)
            assert probe.returncode==0,(kind,probe.returncode,probe.stderr.decode())
            data=io.BytesIO(probe.stdout)
            for tick,pose in selected.items():
                replay=tmp/'pad';replay.write_text(''.join(f'1 {a} {b}\n' for a,b in pads[:prefix+tick]))
                image,background=capture_combat_layers(view,replay,tmp)
                n,=struct.unpack('<I',data.read(4));raw=[data.read(328) for _ in range(n)]
                verify_queue(p,raw,data.getbuffer()[data.tell():]);visible=dict(slot=1-slot,action=pose,steps=[])
                details=compare(p,data,stats,(kind,tick),image,visible,background)
                assert visible['steps'] and visible['visible_pixels']>0,visible
                cases.append(dict(kind=kind,attacker=slot,update=tick,ordered_records=n,
                                  effects=[(struct.unpack_from('<I',r,20)[0],struct.unpack_from('<I',r,36)[0]) for r in raw if struct.unpack_from('<I',r,324)[0]],
                                  **visible,sha256=details['viewer_sha256']))
                if kind=='forward' and tick==39:write_png(OUT/'ground-throw.png',image)
            assert not data.read(1)
        assert stats['textured_effect_quads']>0 and stats['painted_effect_texels']>0
        assert all(any(c['effects'] for c in cases if c['kind']==k) for k in ('forward','back','break'))
        result=dict(status='passed',cases=cases,counters=stats,native_viewer_sha256=digest(view),runtime_sha256=digest(lib),elf_sha256=PIN,
                    validator_sha256=digest(Path(__file__)),scope='Actual two-player viewer stage framebuffer versus complete ELF 1207e8 and 122bc0 queue copy/order, 1208b0 character tiles and 123840 effects plus independent nearest-sample raster. Original positions enter from native snapshot; full motion and captures have separate actor/geometry probes. Hardware GS pixels are outside this check.')
    (OUT/'throw_scene_validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(len(cases),'frames;',stats['quads'],'character quads;',stats['textured_effect_quads'],'effect quads')
if __name__=='__main__':main()
