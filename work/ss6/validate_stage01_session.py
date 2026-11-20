#!/usr/bin/env python3
"""Use both selection pads, keep one renderer across arena changes, and fight over the snow stage's own item."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

from PIL import Image
from validate_selected_combat import prefix
from validate_select_session import encode
from validate_versus_heavy import BUILD, DUMMY, HERE, OUTPUT, ROOT


def select(arena, items):
    pads=prefix((0,1))
    pads[265][1]=128 if items else 0
    if arena==10:pads[309][1]=0
    if arena==1:pads[340][1]=128
    pads[354][1]=0
    pads[379][1]=1024
    return pads


def trace(assets,pads,fields):
    result=subprocess.run([BUILD/'ss6-match-replay',assets,'--mode','select',fields],
        input=''.join(f'1 {a} {b}\n' for a,b in pads),text=True,capture_output=True,check=True)
    return [r.split() for r in result.stdout.splitlines()]


def win(assets,inputs):
    attacks=([[128,0]]*45+[[1024,0]]+[[0,0]]*84)*38
    played=inputs+attacks
    menu=trace(assets,played,'--vs-menu-fields')
    end=next(i for i in range(len(inputs),len(menu)) if menu[i][25]=='1')
    assert menu[end][12]=='2' and menu[end][22]=='0'
    return played[:end+1]+[[0,0]]*71


def reselect(before,arena):
    return before+[[1024,0],[0,0],[128,0],[0,0],[1024,0]]+[[0,0]]*15+select(arena,False)


def again(before):
    return before+[[0,32],[0,0],[0,1024]]+[[0,0]]*1250


def check_item(assets,side,guard):
    fight=select(1,True)+[[0,0] for _ in range(700)]
    # Leave the two fighters on opposite sides of the courier's first parcel.
    for i in range(1250,1282):fight[i]=[128,64]
    fight[1287]=[0,1024]
    for i in range(22 if side==0 else 20):fight[1824+i][side]=(128,64)[side]
    fight[1855][side]=2304
    if guard:
        for i in range(1870,1888):fight[i][1-side]=(128,64)[side]
    rows=trace(assets,fight,'--stage-item-fields')
    slot=39+3*side
    first=next(i for i,r in enumerate(rows) if r[slot+1]=='92')
    assert any(r[28]=='11' for r in rows[:first])
    assert rows[first][28]=='-1' and rows[first+1][slot+1]=='93'
    victim=3+10*(1-side)
    before,after=[int(row[victim+6]) for row in rows[first:first+2]]
    assert before-after==(0 if guard else (23,21)[side])
    assert rows[first+1][victim:victim+2]==(['2','0'] if guard else ['2','64'])
    assert rows[first+30][slot]=='0'
    return dict(thrower=side+1,guard=guard,item=11,flight_tick=first+1,contact_tick=first+2,hp=[before,after])


def main():
    cli=argparse.ArgumentParser();cli.add_argument('--package',action='store_true');args=cli.parse_args()
    viewer=(OUTPUT/'native-viewer' if args.package else BUILD)/'ss6-viewer'
    assets=OUTPUT/'native-viewer/assets' if args.package else HERE/'extracted/resources'
    first=select(1,True)
    rows=trace(assets,first,'--select-fields')
    assert any(r[45:48]==['1','1','1'] for r in rows)
    assert rows[-1][24]=='0' and rows[-1][52:54]==['1','1']
    continuation=again(win(assets,first))
    zero=reselect(win(assets,continuation),0)
    one=reselect(win(assets,zero),1)
    # The shared RNG state at the end of the previous game decides RANDOM.
    # A five-tick delay before advancing the first fighter produces arena 1.
    random=reselect(win(assets,first+[[0,0]]*5),10)
    rolled=trace(assets,random,'--select-fields')
    assert any(r[45:48]==['10','1','1'] for r in rolled)
    assert rolled[-1][23:25]==['2','0'] and rolled[-1][52:54]==['1','0']
    reroll=trace(assets,again(win(assets,random)),'--select-fields')
    assert reroll[-1][23:25]==['2','1'] and reroll[-1][49]=='1'
    items=[check_item(assets,s,guard) for s in (0,1) for guard in (False,True)]
    with tempfile.TemporaryDirectory() as directory:
        tmp=Path(directory);padfile=tmp/'input.pad';screen=tmp/'screen.bmp'
        padfile.write_text(encode(one))
        flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','sdl3'],text=True))
        probe=tmp/'stage-switch'
        subprocess.run([*shlex.split(os.environ.get('CXX','c++')),'-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',
            HERE/'stage_switch_screen_test.cpp',BUILD/'libss6-runtime.a',*flags,'-o',probe],check=True)
        visited=subprocess.check_output([probe,assets,padfile,tmp/'stage.rgba'],text=True).splitlines()
        assert visited==['1 1','2 1','3 0','4 1'],visited
        fight=first+[[128,0]]*45+[[0,0]]*2+[[16,0]]+[[0,0]]*29+[[256,0]]+[[0,0]]*70
        battle=trace(assets,fight,'--select-fields')
        hit=next(i for i,r in enumerate(battle) if int(r[19])<200)
        poses=[int(r[16]) for r in battle[hit:hit+10]]
        assert all(r[15]=='356' and r[19]=='189' for r in battle[hit:hit+10])
        assert sorted(set(poses))==[0,1,2] and battle[hit+10][15]=='0'
        for tick,name in [(len(first),'duel'),(hit+8,'jump-light')]:
            padfile.write_text(encode(fight[:tick]))
            subprocess.run([viewer,'--mode','select','--assets',assets,'--match-replay',padfile,
                '--snapshot',screen],check=True,env=DUMMY)
            image=Image.open(screen).convert('RGB');assert image.size==(640,480)
            image.save(OUTPUT/f'combat-stage01-{name}.png')
    report=dict(status='passed',viewer_sha256=sha256(viewer.read_bytes()).hexdigest(),packaged=args.package,
        match_and_stage=visited,random_stage=1,unavailable_random_rematch_returned_to_select=True,
        item_combat=items,standing_jump_light=dict(hit_tick=hit+1,damage=11,hurt_action=356,display_steps=poses))
    (OUTPUT/'combat-stage01-session-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(report)


if __name__=='__main__':main()

