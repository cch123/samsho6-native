#!/usr/bin/env python3
"""Replay jumping A against both players, compare the original draw queue and visible native framebuffer."""
import collections
import hashlib
import io
import itertools
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import zlib
import validate_jump_light_stun as stun
from validate_native_scene import ASSETS, DRIVER, HEIGHT, LIB, ROOT, SOURCE_HASH, WIDTH, compare, fixture, capture_combat_layers

OUT=ROOT/'outputs/ss6-feasibility'
BUILD=ROOT/'work/ss6/build-native'
CAPTURE_DRIVER=DRIVER.replace('out(match->fighter(0).hits);','out(current->count);for(const auto& row:current->active())out(row);out(match->fighter(0).hits);')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write_png(path,pixels):
    def chunk(name,payload):
        data=name+payload
        return struct.pack('>I',len(payload))+data+struct.pack('>I',zlib.crc32(data))
    rows=b''.join(b'\x00'+pixels[y*WIDTH*4:(y+1)*WIDTH*4] for y in range(HEIGHT))
    path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>2I5B',WIDTH,HEIGHT,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(rows,9))+chunk(b'IEND',b''))

def verify_queue(p,submission,frame,referee_clocks=None):
    n=len(submission);assert struct.unpack_from('<I',frame,12)[0]==n
    clocks=struct.unpack_from('<2I',frame,16+5*4)
    sorted_rows=[frame[2196+i*328:2196+(i+1)*328] for i in range(n)]
    p.run(0x1207d8)
    for row in submission:
        # The referee submits before the fighter callbacks. Concentration can
        # switch clocks between that submission and the later fighter draws.
        slot=struct.unpack_from('<I',row,12)[0]
        kind=struct.unpack_from('<I',row,324)[0]
        sampled=referee_clocks if referee_clocks is not None and slot==2 and kind==0 else clocks
        for i,v in enumerate(sampled):p.write(0x46a918+4*i,v,4)
        p.memory[0x1e00000:0x1e00148]=row
        p.run(0x1207e8,(0x1e00000,struct.unpack_from('<I',row,324)[0]))
    assert p.read(0x4a2250,4)==n
    for i,row in enumerate(submission):
        original=struct.unpack_from('<82I',p.memory,0x479250+328*i)
        native=struct.unpack('<82I',row)
        assert original==native,(i,n,clocks,[(j,x,y) for j,(x,y) in enumerate(zip(original,native)) if x!=y],native[3:5],native[9],native[81])
    # Multi-hit ice can submit dozens of fragments in the same draw pass.
    p.run(0x122bc0,limit=1500000)
    pointers=struct.unpack_from(f'<{n}I',p.memory,0x4a2258)
    assert [bytes(p.memory[at:at+328]) for at in pointers]==sorted_rows

def counter_inputs(match):
    tests=[]
    for attacker in range(2):
        forward=(128,64)[attacker]
        for mask,duration,delay in [(256,1,i) for i in range(12)]+[(16,24,0),(32,24,0),(forward^192,24,0)]:
            inputs=['500 0 0']
            for tick in range(80):
                a=(16|forward) if tick==0 else 256 if tick==30 else 0
                b=mask if 40+delay<=tick<40+delay+duration else 0
                if attacker:a,b=b,a
                inputs.append(f'1 {a} {b}')
            raw=subprocess.run([match,ASSETS,"--mode","versus"],input='\n'.join(inputs)+'\n',text=True,capture_output=True,check=True).stdout
            rows=[r.split() for r in raw.splitlines()][1:];side=3+10*(1-attacker)
            acts=[int(row[side+2]) for row in rows]
            assert acts[40:50]==[356]*10 and rows[-1][side+6]=='191'
            if mask==256:
                assert (185 in acts)==(delay==11)
                if delay==11:assert acts[51]==185
            else:assert acts[50]=={16:14,32:6,forward^192:10}[mask]
            tests.append(dict(attacker=attacker,defender_mask=mask,held_updates=duration,start=541+delay,
                              first_updates_after_hurt=acts[50:52]))
    return tests

def main():
    assert sha(ASSETS.parent/'SLPS_255.59')==SOURCE_HASH
    p=fixture();stats=collections.Counter()
    for bank,name in enumerate(('01HitFlash.bin','02Guard.bin','03etc.bin'),1):
        addr=0x4a4810+(bank-1)*0x3da0;p.memory[addr:addr+0x3da0]=(ASSETS/name).read_bytes()
    results=[]
    with tempfile.TemporaryDirectory() as temp:
        tmp=Path(temp);source=tmp/'probe.cpp';source.write_text(CAPTURE_DRIVER)
        driver=tmp/'queue';lib=tmp/'runtime.a';shutil.copyfile(LIB,lib)
        viewer=tmp/'viewer';shutil.copy2(BUILD/'ss6-viewer',viewer)
        match=tmp/'match';shutil.copy2(BUILD/'ss6-match-replay',match)
        subprocess.run(['c++','-std=c++20','-O2','-ffp-contract=off','-I',str(ROOT/'src'),source,lib,'-o',driver],check=True)
        for slot,walk,direction,attack,other,contact,reaction,steps in [
                (0,0,144,30,'idle',41,356,(0,5,7,9)),
                (1,35,16,28,'idle',41,356,(0,5,7)),
                (0,0,144,33,'crouch',44,350,None),
                (1,43,16,31,'crouch',44,350,None),
                (0,0,144,32,'block',43,288,(0,8)),
                (1,35,16,12,'jump',25,378,(0,15))]:
            name=f'P{slot+1}-'+('forward' if direction&0xc0 else 'vertical')+'-'+other
            forward=128 if slot==0 else 64
            def pair(attacker,defender):return (defender,attacker) if slot else (attacker,defender)
            pads=[(0,0)]*500+[pair(forward,0)]*walk
            for tick in range(80):
                a=direction if tick==0 else 256 if tick==attack else 0
                b=forward if other=='block' and tick>=25 else 16 if other=='jump' and tick==0 else 0
                if other=='crouch':b=32 if tick<contact-1 else 0
                pads.append(pair(a,b))
            def lines(seq):return '\n'.join(f'1 {a} {b}' for a,b in seq)+'\n'
            rows=subprocess.run([match,ASSETS,"--mode","versus"],input=lines(pads),text=True,capture_output=True,check=True).stdout.splitlines()
            rows=[row.split() for row in rows];a=3+10*slot;b=3+10*(1-slot)
            onset=next(index for index,row in enumerate(rows) if int(row[a+7]) or int(row[a+8]))
            assert onset+1==500+walk+contact
            duration=len(list(itertools.takewhile(lambda r:int(r[b+2])==reaction,rows[onset:])))
            assert duration and int(rows[-1][b+6])==(200 if other=='block' else 191)
            assert (209 if direction==16 else 212) in {int(r[a+2]) for r in rows}
            original=None
            if other=='crouch':
                jump='vertical' if direction==16 else 'forward'
                args=(slot,'crouch','idle',jump)
                reference,held,hit=stun.native(*args)
                start=500+walk
                # The combat oracle drives the PS2 defender from the first
                # crouch input. Bind its pads and snapshots to this pixel replay
                # so a different spacing or hit height cannot pass by accident.
                assert hit==contact and sha(stun.EXE)==sha(match)
                assert [p[1-slot] for p in pads[start:]]==held[1:81]
                assert rows[start:]==[r[:23] for r in reference[1:81]]
                original=stun.run_case(args)
                assert original['reaction']==int(rows[onset][b+1])
                records=struct.unpack_from('<2h',(ASSETS/'aid_00.bin').read_bytes(),reaction*2)
                seen={}
                for i,r in enumerate(rows[onset:onset+duration]):
                    seen.setdefault(int(r[b+3]),i)
                assert sorted(seen)==list(range(records[1]-records[0]))
                steps=tuple(seen.values())
            selected={onset+step for step in steps}
            commands='\n'.join(f'tick {a} {b} {int(i in selected)}' for i,(a,b) in enumerate(pads))+'\n'
            data=io.BytesIO(subprocess.run([driver,ASSETS],input=commands.encode(),capture_output=True,check=True).stdout)
            case=dict(name=name,contact_update=onset+1,air_action=209 if direction==16 else 212,reaction_action=reaction,
                      reaction_updates=duration,steps=[(key,len(list(frames))) for key,frames in itertools.groupby(int(r[b+3]) for r in rows[onset:onset+duration])],
                      attacker_hits=int(rows[-1][a+7]),attacker_guards=int(rows[-1][a+8]),defender_life=int(rows[-1][b+6]),captures=[])
            if original is not None:case['original_hurt_trace']=original
            for tick in sorted(selected):
                n,=struct.unpack('<I',data.read(4));raw=[data.read(328) for _ in range(n)]
                # A mirror match uses two selected on-disc costumes. Check
                # the submitted bodies after hitstop and actor-color updates.
                costumes={struct.unpack_from('<I',v,0xcc)[0]:struct.unpack_from('<I',v,0x20)[0]
                          for v in raw if struct.unpack_from('<I',v,0x144)[0]==0 and struct.unpack_from('<I',v,0xcc)[0]<2}
                assert costumes=={0:0,1:1},costumes
                replay=tmp/'replay';replay.write_text(lines(pads[:tick+1]))
                dumped,background=capture_combat_layers(viewer,replay,tmp)
                pos=data.tell();verify_queue(p,raw,data.getbuffer()[pos:]);visibility=dict(slot=1-slot,action=reaction,steps=[])
                r=compare(p,data,stats,f'{name}-{tick+1}',dumped,visibility,background)
                assert len(visibility['steps'])==1 and visibility['steps'][0]==int(rows[tick][b+3]),visibility
                assert visibility['visible_pixels']>100 and visibility['quads']>0,visibility
                if name=='P1-forward-idle' and tick==onset+5:write_png(OUT/'jump-light-reaction.png',dumped)
                case['captures'].append(dict(update=tick+1,ordered_draw_records=n,costumes=costumes,**visibility,rgba_sha256=r['viewer_sha256']))
            assert not data.read(1);results.append(case);print(name,case['steps'],[(f['update'],f['visible_pixels']) for f in case['captures']],flush=True)
        report=dict(status='passed',cases=results,counter_input_replays=counter_inputs(match),counts=stats,source_sha256=SOURCE_HASH,viewer_sha256=sha(viewer),
                    native_match_sha256=sha(match),runtime_sha256=sha(lib),validator_sha256=sha(Path(__file__)),comparison_sha256=sha(ROOT/'work/ss6/validate_native_scene.py'),
                    scope='Real versus replay inputs. Feed native unsorted object snapshots through original 1207e8/122bc0 and compare every raw record and sorted pointer. Render resulting character and effect records through original 1208b0/123840, original atlas and CLUT, and compare all 640x448 RGBA bytes to the viewer stage image. Count surviving target pixels by independently compositing without the target body. For both crouch cases, bind the recorded pads and match snapshots to the original defender input/actor/impact comparison, and render every on-disc hurt ACT record. Original console display, controller entry timing and original full-loop queue production are outside this raster comparison.')
    (OUT/'jump_light_presentation_validation.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
