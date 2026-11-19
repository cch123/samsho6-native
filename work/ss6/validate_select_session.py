#!/usr/bin/env python3
"""Play character select from the launcher and from a won set. Check the public SDL and replay entry points."""
from itertools import groupby
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import tempfile
import wave
from PIL import Image
from validate_selected_combat import prefix
from validate_versus_heavy import BUILD,OUTPUT,ROOT,DUMMY

def encode(pads):
    return ''.join(f'{sum(1 for _ in group)} {a} {b}\n' for (a,b),group in groupby(map(tuple,pads)))

def trace(assets,mode,pads,prelude=''):
    body=prelude+''.join(f'1 {a} {b}\n' for a,b in pads)
    proc=subprocess.run([BUILD/'ss6-match-replay',assets,'--mode',mode,'--select-fields'],input=body,text=True,capture_output=True,check=True)
    return [line.split() for line in proc.stdout.splitlines()[-len(pads):]]

def ready(pads,rows,ordinal):
    onset=next(i for i,r in enumerate(rows) if r[24]=='0')
    assert all(row[23]==str(ordinal) for row in rows[onset:])
    row=rows[onset]
    assert row[25:28]==['0','5','262144'] and row[35:38]==['1','5','262145']
    assert row[50:54]==['17','0','0','0'] and row[9]==row[19]=='200'
    assert [int(r[50]) for r in rows[onset-17:onset+17]]==list(range(33))+[-1]
    first=next(i for i,r in enumerate(rows) if r[47]=='1')
    white=[int(r[51]) for r in rows[first:first+72]]
    assert white[0:33]==list(range(0,257,8)) and white[33:37]==[256]*4 and white[37:69]==list(range(248,-1,-8))
    assert rows[-1][1]=='4'
    return onset,first

def verify_item_rounds(assets,enabled):
    def play(pads,field):
        raw=subprocess.run([BUILD/'ss6-match-replay',assets,'--mode','select',field],
            input=''.join(f'1 {x} {y}\n' for x,y in pads),text=True,capture_output=True,check=True)
        return [line.split() for line in raw.stdout.splitlines()]
    # Play two rounds with an item already on the floor when the first
    # winner is declared. Enter the real post-match menu with both pads released.
    attacks=([[128,0]]*45+[[1024,0]]+[[0,0]]*84)*38
    played=enabled+attacks
    menu=play(played,'--vs-menu-fields')
    end=next(i for i,r in enumerate(menu) if r[25]=='1')
    assert menu[end][12]=='2' and menu[end][22]=='0'
    before=played[:end+1]+[[0,0]]*71
    continuation=before+[[0,32],[0,0],[0,1024]]+[[0,0]]*1500
    matches=play(continuation,'--vs-menu-fields')
    second=next(i for i,r in enumerate(matches) if r[23]=='2')
    items=play(continuation,'--stage-item-fields')
    assert all(r[23]=='1' for r in items[len(enabled):])
    assert any(r[28]!='-1' and r[12]=='1' and r[1]=='5' for r in items[:end])
    reset=next(i for i,r in enumerate(items[:end]) if r[12]=='1' and r[1]=='1')
    assert items[reset][24:29]==['0','0','0','0','-1']
    assert items[second][12]==items[second][22]=='0' and items[second][9]==items[second][19]=='200'
    assert any(r[28]!='-1' or r[36]=='2' for r in items[second:])
    # Re-select from the same finished set. The previous choice initially
    # stays on, but one left press explicitly turns it off for the next fight.
    selection=prefix((0,1))
    selection[265][1]=64
    change=before+[[1024,0],[0,0],[128,0],[0,0],[1024,0]]+[[0,0]]*15+selection+[[0,0]]*1500
    changed=play(change,'--select-fields')
    assert changed[-1][23:25]==['2','0'] and changed[-1][53]=='0'
    off=play(change,'--stage-item-fields')[-1500:]
    assert all(r[23]=='0' and r[26:29]==['0','0','-1'] and r[36]=='0' for r in off)
    return dict(next_round_tick=reset+1,rematch_tick=second+1,rematch_delivered=True,reselected_items_off=True)

def main():
    cli=argparse.ArgumentParser();cli.add_argument('--package',action='store_true');flags=cli.parse_args()
    viewer=(OUTPUT/'native-viewer' if flags.package else BUILD)/'ss6-viewer'
    assets=OUTPUT/'native-viewer/assets' if flags.package else ROOT/'work/ss6/extracted/resources'
    pads=prefix((0,1));rows=trace(assets,'select',pads)
    start,first=ready(pads,rows,1)
    # A played first-to-two match. Its post-match option starts the same
    # selector, with the losing seat making the item and stage choices.
    base=(OUTPUT/'console-versus-rematch.replay').read_text().splitlines()
    assert base[-1]=='1 0 32'
    pre='\n'.join(base[:-1]+['1 1024 0','1 0 0','1 128 0','1 0 0','1 1024 0','15 0 0'])+'\n'
    second=trace(assets,'versus',pads,pre)
    restart,_=ready(pads,second,2)
    assert all(r[54:56]==['1','0'] for r in second)
    assert second[restart][12]==second[restart][22]=='0'
    blocked=[]
    for kind in ('character','stage'):
        q=[v[:] for v in pads[:505]]
        if kind=='character':q[65][0]=0
        if kind=='stage':q[309][1]=64
        q.append([256,0]);q.append([0,0])
        rr=trace(assets,'select',q)
        assert rr[-3][49]=='1' and rr[-2][49]=='0' and rr[-1][24]=='1' and rr[-1][30]=='-1',kind
        blocked.append(kind)
    enabled=[v[:] for v in pads]
    enabled[265][1]=128
    item_rows=trace(assets,'select',enabled)
    assert item_rows[-1][24]=='0' and item_rows[-1][49]=='0' and item_rows[-1][53]=='1'
    item_rounds=verify_item_rounds(assets,enabled)
    # The same selected P2 can execute the on-disc 236+A, finish its
    # airborne recovery and return to neutral without leaving the fight.
    technique=pads+[[0,32],[0,96],[0,64|256]]+[[0,0]]*150
    completed=trace(assets,'select',technique)[len(pads):]
    assert all(row[49]=='0' and row[24]=='0' for row in completed)
    assert any(row[13:16]==['1','67','540'] for row in completed)
    assert completed[-1][13:15]==['0','0']
    with tempfile.TemporaryDirectory() as tmp:
        d=Path(tmp);file=d/'input.pad';output=d/'screen.bmp';pictures={}
        for name,t in [('characters',87),('spirits',240),('stage',345),('face',464),('door',start+1),('battle',1175)]:
            file.write_text(encode(pads[:t]))
            subprocess.run([viewer,'--mode','select','--assets',assets,'--match-replay',file,'--snapshot',output],check=True,env=DUMMY)
            img=Image.open(output).convert('RGB');assert img.size==(640,480) and len(img.getcolors(640*480))>80
            pictures[name]=hashlib.sha256(img.tobytes()).hexdigest()
            if name=='battle':img.save(OUTPUT/'selected-duel-native.png')
        assert len(set(pictures.values()))==len(pictures)
        # Render the actual selected sound groups, the BGM and both speakers
        # through the same mixer callback used by a live SDL audio device.
        file.write_text(encode(pads[:465]));song=d/'select.wav'
        subprocess.run([viewer,'--mode','select','--assets',assets,'--match-replay',file,'--audio-out',song],check=True,env=DUMMY)
        with wave.open(str(song)) as f:
            assert (f.getnchannels(),f.getframerate(),f.getnframes())==(2,48000,465*800)
            f.setpos(100*800);stereo=f.readframes(2000)
            assert max(stereo)>100 and stereo[0::4]!=stereo[2::4]
    out=dict(status='passed',packaged=flags.package,viewer_sha256=hashlib.sha256(viewer.read_bytes()).hexdigest(),
             direct_first_combat_tick=start+1,reselect_first_combat_tick=restart+1,
             select_fade_start=first+1,item_rounds=item_rounds,preserved_set_wins=[1,0],first_match_number=1,reselected_match_number=2,
             unavailable_choices_return_to_live_grid=blocked,framebuffer_rgb_sha256=pictures,
             audio_frames=465*800,scope='Public pad replay and complete 640x480 SDL snapshot. Original controller and pixel comparisons are in the character, spirit, faceoff and curtain reports.')
    (OUTPUT/'select-session-validation.json').write_text(json.dumps(out,indent=2)+'\n')
    print(out)
if __name__=='__main__':main()

