#!/usr/bin/env python3
"""Replay mixed spirits through character select and compare the visible combo to the Japanese HUD."""
import argparse
from pathlib import Path
import struct
import subprocess
import tempfile

import numpy as np
from PIL import Image
from validate_rimururu_ice_scene import play
from validate_select_session import encode
from validate_versus_heavy import ASSETS, BUILD, DUMMY, PKG, digest
from validate_zero_hud import atlas, draw, original, seed

# Spirit selection starts on Ken. A direction must be released between cursor steps.
OFFSETS=(1,2,3,-2,-1,0)
FILL=(255,255,32)

def run_case(viewer,replay,assets,d,attacker,systems,atlases,save):
    _,pads=play(attacker,76,0)
    pads[229]=[0,0]
    for side,system in enumerate(systems):
        offset=OFFSETS[system]
        for tick in (211,222,233)[:abs(offset)]:pads[tick-1][side]=128 if offset>0 else 64
    def trace(flag):
        result=subprocess.run([replay,assets,'--mode','select',flag],capture_output=True,check=True,
                              text=True,input=''.join(f'1 {l} {r}\n' for l,r in pads))
        rows=[line.split() for line in result.stdout.splitlines()]
        assert len(rows)==len(pads)
        return rows
    picks=trace('--select-fields')[-1]
    assert [int(picks[k]) for k in (26,36)]==list(systems)
    rows=trace('--finish-fields')
    idx=-8+attacker*4
    hits=[int(row[idx]) for row in rows]
    first={n:hits.index(n) for n in range(1,6)}
    assert max(hits)==5
    samples={first[1]-1,first[1]+1,first[2]+1,first[3]+3,first[4]+1,first[5]+12,first[5]+55,first[5]+88,first[5]+125}
    assert samples and max(samples)<len(pads)
    probe=original()
    seed(probe,systems)
    probe.run(0x1be1a8,limit=200000)
    victim=attacker^1
    actor=probe.read(0x132f598+4*victim,4)
    first_tick=min(samples)
    snapshots=0
    for i in range(first_tick,max(samples)+1):
        prev=rows[i-1]
        table,state=map(int,prev[3+10*victim:5+10*victim])
        probe.write(actor+0x194,(state<<16)|table,4)
        if hits[i-1]>=2 and hits[i-1]!=hits[i-2]:
            probe.run(0x1be008,[attacker,hits[i-1]])
        for a in (0x345178,0x378e08,0x3db8f8):probe.write(a,0,4)
        if i not in samples:
            probe.run(0x1bc580,limit=200000)
            continue
        pad=d/'input.pad';pad.write_text(encode(pads[:i+1]))
        scene=d/'scene.rgba';shot=d/'screen.bmp'
        subprocess.run([viewer,'--assets',assets,'--mode','select','--match-replay',pad,
                        '--dump',scene,'--snapshot',shot],env=DUMMY,stdout=subprocess.DEVNULL,check=True)
        raw=scene.read_bytes()
        assert struct.unpack_from('<II',raw)==(640,448)
        expected=np.frombuffer(raw,np.uint8,offset=8).reshape(448,640,4).copy()
        packets=draw(probe,expected,atlases,(0x1bc580,))
        window=np.asarray(Image.open(shot).convert('RGB'))
        # The top HUD, including its round-win rings, ends above this band.
        # Compare the whole width so that a second label on the wrong side also fails.
        y0,y1=100,208
        diff=np.any(expected[y0:y1,:,:3]!=window[y0:y1],axis=2)
        if diff.any():
            y,x=np.argwhere(diff)[0]
            raise AssertionError((systems,attacker,i+1,hits[i],int(diff.sum()),int(x),int(y+y0),packets))
        if i in (first[1]-1,first[1]+1,first[5]+125):
            assert packets==0,(systems,i,packets)
        else:
            assert packets>0,(systems,i,packets)
        # At full and after damage both gauges use the 200px strip. Its inner
        # edge may contain the spirit's colored reserve; sample the outer end here.
        for side,left in enumerate((73,366)):
            hp=int(prev[9+side*10])
            bar=window[50,left:left+200]
            if side==0:bar=bar[::-1]
            assert hp>=100 and np.array_equal(bar[hp-2],FILL),(systems,i,side,hp,bar[hp-2])
            if hp<200:
                assert not np.array_equal(bar[hp],FILL),(systems,i,side,hp,bar[hp])
        if save and i==first[5]+12:
            Image.fromarray(window).save(save/f'hud-mixed-combo-p{attacker+1}.png')
        snapshots+=1
    print(f'P{attacker+1}, spirits {systems}, 1..5 hits, {snapshots} verified windows',flush=True)

def main():
    cli=argparse.ArgumentParser()
    cli.add_argument('--viewer',type=Path,default=PKG/'ss6-viewer')
    cli.add_argument('--replay',type=Path,default=BUILD/'ss6-match-replay')
    cli.add_argument('--assets',type=Path,default=ASSETS)
    cli.add_argument('--save',type=Path,help='save a 5-hit screenshot for each seat')
    opts=cli.parse_args()
    paths=(opts.viewer,opts.replay);versions=[digest(p) for p in paths]
    textures=atlas()
    with tempfile.TemporaryDirectory() as tmp:
        for seat,systems in ((0,(0,4)),(1,(4,0))):
            run_case(*paths,opts.assets,Path(tmp),seat,systems,textures,opts.save)
    assert versions==[digest(p) for p in paths]
if __name__=='__main__':main()
