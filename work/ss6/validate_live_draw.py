#!/usr/bin/env python3
"""Compare complete packaged Game Over frames after an actual tied 60-second match."""
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import numpy as np
from PIL import Image
from extract_versus_draw_stage import capture
from validate_combat_stage_state import Oracle,DELTA,PROJECTION,bits
import validate_versus_draw_stage as stage
import validate_versus_draw_art as art
from validate_versus_result import Original
from validate_dash_motion import ROOT,ELF,PIN,digest

def replay(exe,pkg,field,updates):
    # One line per tick makes every post-owner stage/gauge state visible.
    args=[exe,pkg/'assets','--mode','fixed-versus',field,'--round-time','60']
    rows=subprocess.run(args,input='1 0 0\n'*updates,text=True,capture_output=True,check=True).stdout
    return [list(map(int,line.split())) for line in rows.splitlines()]


def battle_history(exe,pkg):
    stage_rows=replay(exe,pkg,'--stage-fields',14000)
    end=next(i+1 for i,r in enumerate(stage_rows) if r[2])
    assert stage_rows[end-1][12:23:10]==[2,2]
    gauges=replay(exe,pkg,'--rage-fields',end)
    o=Oracle()
    prev=0
    deltas=Counter()
    for clock,(stage_row,gauge) in enumerate(zip(stage_rows[:end],gauges,strict=True),1):
        # Priority 5 is active during the round. The battle owner later
        # publishes pause/speed changes; the stage sees those next visit.
        if prev==4:o.call(0x11e708)
        deltas[o.p.read(DELTA,4)]+=1
        o.sample(False)
        assert o.snapshot()[6:]==stage_row[29:50], ('battle stage clocks',clock)
        if gauge[49]:o.call(0x11f588,1)
        else:
            o.call(0x11f5a0,0)
            o.p.write(0x1239d88,stage_row[51],4)
            if prev!=5 and stage_row[1]==5:o.call(0x11e600)
        assert o.p.read(DELTA,4)==stage_row[50], ('battle owner delta',clock)
        prev=stage_row[1]
    # The incoming and fixed projections happen to coincide in this idle
    # timeout. The scenery frames demonstrably do not start from zero.
    assert any(o.snapshot()[6:])
    return o,end,deltas


def validate():
    assert digest(ELF)==PIN
    output=ROOT/'outputs/ss6-feasibility'
    pkg=output/'native-viewer'
    initial=digest(pkg/'ss6-viewer')
    match=ROOT/'work/ss6/build-native/ss6-match-replay'
    terminal,end,deltas=battle_history(match,pkg)
    cases=[];samples=(27,30,50,79,80,81,86,135,136,196,203,280,281,282,294)
    with tempfile.TemporaryDirectory() as path:
        tmp=Path(path)
        for skip in (False,True):
            original=Original();original.final(-1,0)
            o=copy.deepcopy(terminal)
            textures=stage.palette(o.p);p=art.setup()
            blob=np.frombuffer(p.memory,np.uint8,512*256,0x1fc0000).reshape(512,256)
            atlas=np.empty((512,512),np.uint8);atlas[:,::2]=blob&15;atlas[:,1::2]=blob>>4
            inputs=f'{end} 0 0\n';posed={};old_stage_visits=0
            for offset in range(345):
                frame=original.snapshot()[7]
                edge=skip and original.ready and frame==51
                inputs+=f'1 {2048 if edge else 0} 0\n'
                was_draw=original.ready and original.scene==0x138340
                was_old=not original.ready and original.scene==0x138340
                original.tick([4 if edge else 0,0]);state=original.snapshot()
                clock,object_tick=state[13:15]
                selected=was_draw and clock in samples and state[18]==0
                if was_old:
                    o.sample(False)
                    old_stage_visits+=1
                    if original.ready:
                        carried=o.snapshot()[6:]
                        # Old priority 10 has already run this tick. The
                        # midpoint destroys its task, resets the delta, and
                        # reinstalls the same stage without clearing its RAM.
                        o.call(0x11e600)
                        o.call(0x11f5a0,0)
                        o.install(True)
                        assert o.snapshot()[6:]==carried and o.p.read(DELTA,4)==256
                        o.call(0x13847c,stop=(0x1384cc,))
                        assert [o.p.read(a,4) for a in PROJECTION]==list(map(bits,(320,120,-400,0,-120)))
                elif was_draw:
                    if selected:backdrop=capture(o.p)
                    else:o.sample(False)
                if not selected:continue
                # Many movie ticks re-use the same surface. Key on actual
                # emitted strips to keep the original character blend intact.
                key=tuple((slot,color,tuple(vertices)) for _,slot,color,vertices in backdrop)
                if key not in posed:
                    body_base=stage.render(backdrop,textures)
                    posed[key]=art.bodies(art.setup(),0,body_base)[0]
                expected=art.render(p,art.packets(p,clock),posed[key][min(object_tick,31)],atlas)
                if state[20]:expected=np.full_like(expected,255)
                pad=tmp/'tie.pad';pad.write_text(inputs);snap=tmp/'tie.bmp'
                subprocess.run([ROOT/'battle.command','--mode','fixed-versus','--round-time','60','--match-replay',pad,'--snapshot',snap],check=True)
                shown=Image.open(snap).convert('RGBA')
                np.testing.assert_array_equal(np.asarray(shown),expected,err_msg=f'Game Over {clock}/{object_tick}, skip={skip}')
                if clock==203 and not skip:shown.save(output/'versus-draw.png')
                cases.append(dict(skip=skip,clock=clock,actor_update=object_tick,white_flash=bool(state[20]),
                                  match_update=end+offset+1,stage_pictures=o.snapshot()[7::3],sha256=hashlib.sha256(expected.tobytes()).hexdigest()))
            assert old_stage_visits==14
    assert digest(pkg/'ss6-viewer')==initial
    report=dict(status='passed',viewer_sha256=initial,elf_sha256=PIN,tied_at=end,cases=cases,
                combat_visits_by_delta=deltas,terminal_stage_layers=terminal.snapshot()[6:],
                terminal_to_transfer_stage_visits=old_stage_visits,
                scope='Packaged 640x480 SDL frames for a two-timeout tie, natural and accelerated. Original seven stage clocks continuously advanced through combat and old-stage transition; the fixed camera, retained clocks, Game Over body, UI and flash compose the expected pixels. Partial global fades excluded. Independent software raster, no hardware capture.')
    (output/'live_draw_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(len(cases),'complete packaged Game Over frames')
if __name__=='__main__':validate()
