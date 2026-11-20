#!/usr/bin/env python3
"""Play both sides, win full sets, reselect the fighters, and compare the live companions to Japanese draws."""
from collections import Counter
from hashlib import sha256
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
from PIL import Image
from validate_selected_combat import BUILD, CAPTURE, LIB, OUT, ROOT, SOURCE, capture, fixture, prefix
from validate_select_session import encode
from validate_stage01_session import trace, again
from validate_versus_heavy import DUMMY


def choose(lineup,arena):
    pads=prefix(lineup)
    if arena==1:
        pads[340][1]=128;pads[354][1]=0;pads[379][1]=1024
    return pads


def win(assets,moves,seat):
    pair=lambda a:(0,a) if seat else (a,0)
    attacks=[pair((128,64)[seat])]*45+[pair(1024)]+[(0,0)]*84
    played=moves+attacks*45
    rows=trace(assets,played,'--vs-menu-fields')
    end=next(i for i in range(len(moves),len(rows)) if rows[i][25]=='1')
    assert (rows[end][12],rows[end][22])==(('0','2') if seat else ('2','0'))
    return played[:end+1]+[(0,0)]*71


def check_spirits(assets):
    results=[]
    for spirit,offset in enumerate((1,2,3,-2,-1,0)):
        pads=prefix((2,2))
        # Both cursors start at Ken and wrap independently on the spirit wheel.
        for tick in (211,222,233)[:abs(offset)]:
            pads[tick-1]=[128 if offset>0 else 64]*2
        pads.extend([(128,64)]*42+[(0,0)]*5+[(1024,0)]+[(0,0)]*100)
        row=trace(assets,pads,'--select-fields')[-1]
        assert row[26]==row[36]==str(spirit) and row[49]=='0'
        assert row[3]=='0' and int(row[19])==(171,168,170,169,165,170)[spirit]
        results.append(dict(spirit=spirit,defender_life=int(row[19])))
    return results


def main():
    cli=argparse.ArgumentParser();cli.add_argument('--package',action='store_true');args=cli.parse_args()
    viewer=(OUT/'native-viewer' if args.package else BUILD)/'ss6-viewer'
    assets=OUT/'native-viewer/assets' if args.package else SOURCE
    hashes=[sha256(x.read_bytes()).hexdigest() for x in (viewer,BUILD/'ss6-match-replay')]
    stats=Counter();images=[];sets=[]
    with tempfile.TemporaryDirectory() as directory:
        tmp=Path(directory);source=tmp/'capture.cpp';source.write_text(CAPTURE);probe=tmp/'capture'
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',source,LIB,'-o',probe],check=True)
        for lineup,seat in (((2,0),0),((0,2),1),((1,2),1),((2,2),0)):
            arena=int(lineup[0]!=0)
            first=choose(lineup,arena)
            rows=trace(assets,first,'--select-fields')
            assert (rows[-1][25],rows[-1][35])==tuple(map(str,lineup)) and rows[-1][49]=='0'
            p=fixture((*lineup,51))
            for bank,name in enumerate(('01HitFlash.bin','02Guard.bin','03etc.bin'),1):
                at=0x4a4810+(bank-1)*0x3da0;p.memory[at:at+0x3da0]=(SOURCE/name).read_bytes()
            images.append(capture(probe,viewer,assets,tmp,p,lineup,first,len(first)-1,
                {'slot':seat,'action':0,'steps':[]},stats))
            before=win(assets,first,seat)
            rematch=trace(assets,again(before),'--select-fields')
            assert rematch[-1][23:25]==['2','0'] and rematch[-1][52]==str(arena)
            assert (rematch[-1][25],rematch[-1][35])==tuple(map(str,lineup))
            sets.append(dict(lineup=lineup,winner=seat+1,arena=arena))
            if lineup==(2,0):
                # The losing second seat controls the arena on the next selection.
                change=before+[(1024,0),(0,0),(128,0),(0,0),(1024,0)]+[(0,0)]*15+choose((1,2),0)
                new=trace(assets,change,'--select-fields')[-1]
                assert (new[23:25],new[25],new[35],new[52])==(['2','0'],'1','2','0')
            if lineup==(1,2):
                inputs=tmp/'mirror.pad';inputs.write_text(encode(first))
                shot=tmp/'duel.bmp'
                subprocess.run([viewer,'--assets',assets,'--mode','select','--match-replay',inputs,'--snapshot',shot],env=DUMMY,check=True)
                im=Image.open(shot).convert('RGB');assert im.size==(640,480);im.save(OUT/'rimururu-selected-duel.png')
    assert hashes==[sha256(x.read_bytes()).hexdigest() for x in (viewer,BUILD/'ss6-match-replay')]
    result=dict(status='passed',packaged=args.package,viewer_sha256=hashes[0],replay_sha256=hashes[1],
                sets=sets,spirits=check_spirits(assets),changed_lineup=[1,2],scenes=images,counts=dict(stats))
    (OUT/'rimururu-session-validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(sets)

if __name__=='__main__':main()

