#!/usr/bin/env python3
"""Use the shipping SDL event loop to enter VS from either seat and play a first-round strike."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shlex
import subprocess
import tempfile

from PIL import Image
from validate_select_window_input import BUILD, DUMMY, HERE, OUT, ROOT, convert, encode, prefix, run


def trace(assets, controls, field):
    proc = subprocess.run([BUILD/'ss6-match-replay',assets,'--mode','title',field],
                          input=''.join(f'1 {l} {r}\n' for l,r in controls),
                          text=True,check=True,capture_output=True)
    return [r.split() for r in proc.stdout.splitlines()]


def controls(confirming):
    owner = 1-confirming
    title = [[0,0] for _ in range(97)]
    for tick,button in ((40,8),(59,32),(82,1024)):
        title[tick][confirming] = button

    picks = prefix((0,1))
    # The title confirm determines ownership independently of the character
    # picks. Try to confirm items and move/confirm the arena with the wrong
    # device while each is already actionable; then do it with the owner.
    for tick in (279,309,354,464):
        picks[tick] = [0,0]
    for tick,button in ((262,1024),(303,64),(340,1024)):
        picks[tick][confirming] = button
    for tick,button in ((279,1024),(309,128),(354,1024),(464,8)):
        picks[tick][owner] = button
    if confirming:
        # P1 picks snow rather than P2's first arena. Waiting for the
        # second carousel animation also delays the face-off Start edge.
        picks[346][owner]=128; picks[354][owner]=0; picks[384][owner]=1024
        picks[464][owner]=0; picks[494][owner]=8
    heavy = (1024,0) if confirming==0 else (0,1024)
    fight = [(128,64)]*42+[(0,0)]*35+[heavy]+[(0,0)]*135
    return list(map(tuple,title+picks+fight)),len(title)


def validate(viewer,assets,harness,work,confirming):
    owner = 1-confirming
    pads,offset = controls(confirming)
    titles = trace(assets,pads[:offset+1],'--title-fields')
    rows = trace(assets,pads,'--select-fields')
    assert titles[39][23:26]==['1','0','5']
    assert titles[41][23:26]==['1','1','5']
    assert titles[59][23:27]==['1','1','0','2']
    assert titles[74][23:27]==['1','1','0','0']
    assert titles[95][30:32]==['256','0']
    assert titles[96][30:34]==['256','1',str(owner),str(owner)]

    at = lambda i: rows[offset+i]
    phase=33+10*owner
    assert all(int(row[46])==owner for row in rows[offset:] if row[24]=='1')
    for t,p in ((262,13),(279,17),(303,20),(309,23),(340,20)):
        assert int(at(t)[phase])==p,(confirming,t,at(t)[phase])
    # All three wrong-port edges leave the phase and completion flags intact.
    assert all(at(t)[45:48]==at(t-1)[45:48] and at(t)[phase]==at(t-1)[phase] for t in (262,303,340))
    completed = next(i for i in range(offset,len(rows)) if rows[i][47]=='1')
    assert rows[completed][45:48]==[str(confirming),str(owner),'1']
    playable = next(i for i,row in enumerate(rows) if row[1]=='4')
    assert rows[playable][25:28]==['0','5','262144'] and rows[playable][35:38]==['1','5','262145']
    assert int(rows[playable][52])==confirming and rows[playable][9]==rows[playable][19]=='200'
    victim_life=9+10*owner
    strike = next(i for i in range(playable,len(rows)) if int(rows[i][victim_life])<200)
    assert rows[strike][10+10*confirming]=='1' and rows[strike][3+10*owner]=='2'
    contacts=[i for i in range(strike,len(pads)) if rows[i-1][victim_life]!=rows[i][victim_life]]
    # Nakoruru's close heavy strikes twice. Check the second reaction before recovery.
    assert [int(rows[i][victim_life]) for i in contacts]==([187,173] if confirming else [156])
    assert rows[-1][3]==rows[-1][13]=='0' and rows[-1][victim_life]==rows[contacts[-1]][victim_life]
    faceoff = next(i for i in range(completed,len(rows)) if int(rows[i][48])>=45)
    shots = {40:'title',53:'mode_menu',75:'vs_selected',89:'fade',offset+87:'character_selection',
             offset+240:'spirit_selection',offset+264:'items_wrong_port',offset+305:'arena_wrong_port',
             offset+344:'arena_after_wrong_confirm',completed+1:'owner_locked_arena',faceoff+1:'faceoff',
             playable+1:'first_round',strike+1:'heavy_hit',len(pads):'recovery'}

    if len(contacts)>1:
        shots[contacts[1]+1]='second_heavy_hit'

    # SDL3 creates the gamepad button events from a mapped virtual joystick.
    # The harness injects keyboard events at SDL_RenderPresent and samples
    # the real framebuffer after the shipping window processes those events.
    records,captures = convert(pads,shots)
    seq=work/'events';seq.write_text('\n'.join(records)+'\n')
    empty=work/'empty.pad';empty.write_text('0 0 0\n')
    images=[arg for tick,present in captures.items() for arg in ('--capture',str(present),work/f'{tick}.bmp')]
    out=run([harness,assets,empty,seq,'--mode','title','--fixed-host-time',*images],env=DUMMY)
    counts=list(map(int,next(r for r in out.splitlines() if r.startswith('events ')).split()[1:]))
    assert counts[0]==2 and counts[2]>=9 and counts[2]==counts[3],counts
    rendered=next(r for r in reversed(out.splitlines()) if r.startswith('render ')).split()[1:]
    assert [int(rendered[i]) for i in (5,14)]==[int(rows[-1][i]) for i in (9,19)]
    ref=work/'reference.bmp';replay=work/'reference.pad';frames={}
    for tick,name in shots.items():
        replay.write_text(encode(pads[:tick]))
        run([viewer,'--assets',assets,'--mode','title','--match-replay',replay,'--snapshot',ref],env=DUMMY)
        with Image.open(ref) as master,Image.open(work/f'{tick}.bmp') as observed:
            assert observed.size==master.size==(640,480)
            pixels=observed.convert('RGBA').tobytes()
            assert pixels==master.convert('RGBA').tobytes(),(confirming,tick,name)
            frames[name]=dict(tick=tick,rgba_sha256=sha256(pixels).hexdigest())
    return dict(vs_confirmed_by=confirming+1,stage_picked_by=owner+1,stage=confirming,
                devices=['P1 SDL keyboard','P2 hotplugged virtual SDL gamepad'],sdl_gamepad_events=counts,
                compared_window_pixels=len(shots)*640*480,selected_fighters=[0,1],strike_seat=confirming+1,contact_ticks=[i+1 for i in contacts],
                first_round_tick=playable+1,heavy_contact_tick=strike+1,ending_life=[int(rows[-1][i]) for i in (9,19)],
                screenshots=frames)


def main():
    cli=argparse.ArgumentParser()
    cli.add_argument('--package',action='store_true')
    args=cli.parse_args()
    base=OUT/'native-viewer' if args.package else BUILD
    assets=base/'assets' if args.package else HERE/'extracted/resources'
    viewer=base/'ss6-viewer'
    with tempfile.TemporaryDirectory() as td:
        work=Path(td);harness=work/'window'
        libs=shlex.split(run(['pkg-config','--cflags','--libs','sdl3']))
        runtime=BUILD/'libss6-runtime.a'
        run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',HERE/'sdl_gamepad_input_test.cpp',runtime,*libs,'-o',harness])
        paths=[validate(viewer,assets,harness,work,seat) for seat in (0,1)]
    report=dict(status='passed',package=args.package,viewer_sha256=sha256(viewer.read_bytes()).hexdigest(),
                runtime_sha256=sha256(runtime.read_bytes()).hexdigest(),paths=paths,
                scope='Shipping SDL event/update/draw loop using a software window, P1 keyboard and P2 virtual joystick attached through SDL. Compare full window pixels to the stock viewer at title, menu, selection, fight and recovery.')
    (OUT/'title-window-input-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Both SDL window routes passed;',sum(p['compared_window_pixels'] for p in paths),'compared pixels',
          [(p['vs_confirmed_by'],p['stage_picked_by'],p['stage'],p['ending_life']) for p in paths])


if __name__=='__main__':
    main()
