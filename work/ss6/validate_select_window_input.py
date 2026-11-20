#!/usr/bin/env python3
"""Drive the production select window using P1 keyboard events and a hotplugged P2 virtual controller."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import tempfile
from PIL import Image
from validate_versus_gamepads import BUILD, DUMMY, HERE, ROOT, run
from validate_selected_combat import prefix
from validate_select_session import encode, trace

OUT=ROOT/'outputs/ss6-feasibility'
KEY={16:'W',32:'S',64:'A',128:'D',256:'J',512:'U',1024:'L',8:'T'}
PAD={16:12,32:14,64:15,128:13,256:7,512:4,1024:5,8:11}

def fixture():
    pads=prefix((0,1))
    # Each user moves off the factory spirit: P1 Ken→Rage, P2 Ken→Zero→Ten.
    pads[211][1]=64;pads[225][1]=64;pads[217][0]=128
    pads += [[128,64]]*42+[[0,0]]*35+[[1024,0]]+[[0,0]]*110
    return list(map(tuple,pads))

def convert(pads,checkpoints):
    lines=[];captures={};previous=(0,0);begin=0
    while begin<len(pads):
        now=pads[begin];end=begin+1
        while end<len(pads) and pads[end]==now and end not in checkpoints:end+=1
        events=['+1'] if not begin else []
        for k,name in KEY.items():
            if (previous[0]^now[0])&k:events.append(f'K{name}{"+" if now[0]&k else "-"}')
        for k,bit in PAD.items():
            if (previous[1]^now[1])&k:events.append(f'1.{bit}={int(bool(now[1]&k))}')
        # N advances through the shipping loop; resume on the same fixed host
        # timestamp so the picture exactly matches an unpaused replay snapshot.
        lines.append(' '.join(events+[f'N{end-begin}','KSpace+','KSpace-']))
        if end in checkpoints:captures[end]=len(lines)
        previous=now;begin=end
    return lines,captures

def rimururu_duel(assets):
    # Use J on the keyboard for the jumping slash, then the virtual pad's
    # left-facing 623+A. Both players stay in the same live window and match.
    pads=prefix((2,2))+[(128,0)]*45+[(0,32)]*10+[(16,32)]+[(0,32)]*27
    pads += [(256,32)]+[(0,32)]*95+[(0,0)]*12+[(0,64)]*35+[(0,0)]*12
    pads += [(0,64),(0,32),(0,96|256)]+[(0,0)]*265
    pads=list(map(tuple,pads));rows=trace(assets,'select',pads)
    assert rows[-1][25:28]==['2','5','262144'] and rows[-1][35:38]==['2','5','262145']
    first=next(i for i,r in enumerate(rows) if i>1250 and r[19]=='191')
    assert rows[first-1][19]=='200' and rows[first][13:17]==['2','38','350','0']
    steps={}
    for i in range(first,len(rows)):
        if rows[i][15]!='350':break
        steps.setdefault(int(rows[i][16]),i+1)
    assert list(steps)==[0,1,2]
    ice=next(i for i,r in enumerate(rows) if i>first and int(r[9])<200)
    assert rows[ice][13:16]==['1','76','545'] and rows[ice][3]=='2'
    assert rows[-1][3]==rows[-1][13]=='0' and (rows[-1][9],rows[-1][19])==('168','191')
    shots={first:'before_hit',**{t:f'crouch_hurt_{k}' for k,t in steps.items()},ice+1:'ice_impact',len(pads):'recovered'}
    details=dict(seats=['P1 keyboard: Rimururu/Ken','P2 virtual SDL gamepad: Rimururu/Ken'],
                 jump_hit_tick=first+1,ice_hit_tick=ice+1,final_life=[168,191])
    return pads,rows,shots,details

def hanzo_duel(assets):
    pads=prefix((3,3))
    pads[229]=[128,128]
    pads += [(128,64)]*43+[(0,0)]*10
    # P1's 623+C captures P2. Wait for both to recover before bringing
    # them together again for the opposing controller's left-facing 214+A.
    pads += [(128,0),(32,0),(160|1024,0)]+[(0,0)]*342
    pads += [(128,64)]*52+[(0,0)]*10+[(0,32),(0,160),(0,128|256)]+[(0,0)]*200
    pads=list(map(tuple,pads))
    rows=trace(assets,'select',pads)
    assert rows[-1][25:28]==['3','0','262144'] and rows[-1][35:38]==['3','0','262145']
    tick=lambda cond:next(i+1 for i,r in enumerate(rows) if i>1250 and cond(r))
    grab=tick(lambda r:r[5]=='627' and r[15]=='1313')
    lift=tick(lambda r:r[5:7]==['627','5'] and r[15]=='1317')
    throw_damage=tick(lambda r:int(r[19])<200)
    cast=tick(lambda r:r[13:16]==['1','64','529'])
    flame_hit=tick(lambda r:int(r[9])<200)
    assert grab<lift<throw_damage<cast<flame_hit
    assert rows[throw_damage-1][19]=='147' and rows[flame_hit-1][3:6]==['2','63','382']
    assert rows[-1][3:6]==rows[-1][13:16]==['0','0','0'] and rows[-1][9]=='179'
    shots={87:'selection',grab:'grab',lift:'airborne_pair',throw_damage:'slam',
           cast+23:'flame',flame_hit:'flame_hit',len(pads):'recovered'}
    return pads,rows,shots,dict(seats=['P1 keyboard: Hanzo/Rage','P2 virtual SDL gamepad: Hanzo/Rage'],
        grab_tick=grab,slam_damage_tick=throw_damage,flame_start_tick=cast,flame_damage_tick=flame_hit,
        final_life=[179,147])

def default_duel(assets):
    pads=fixture();oracle=trace(assets,'select',pads);start=next(i+1 for i,r in enumerate(oracle) if r[24]=='0')
    assert oracle[start-1][25:28]==['0','0','262144'] and oracle[start-1][35:38]==['1','3','262145']
    assert oracle[start-1][50:54]==['17','0','0','0']
    without=list(pads[:start]);without[464]=(0,0);assert trace(assets,'select',without)[-1][24]=='1'
    hit=next(i+1 for i,r in enumerate(oracle) if i>1250 and int(r[19])<200);assert int(oracle[hit-1][10])>0
    shots={87:'characters',240:'spirits',345:'stage',464:'faceoff',start:'curtain',1175:'fight',hit:'heavy'}
    details=dict(seats=['P1 keyboard: Haohmaru/Rage','P2 virtual SDL gamepad: Nakoruru/Ten'],
                 stage=0,start_key_tick=465,combat_entry=start,heavy_tick=hit,defender_hp=int(oracle[hit-1][19]))
    return pads,oracle,shots,details

def main():
    cli=argparse.ArgumentParser()
    cli.add_argument('--package',action='store_true')
    choice=cli.add_mutually_exclusive_group()
    choice.add_argument('--rimururu',action='store_true')
    choice.add_argument('--hanzo',action='store_true')
    args=cli.parse_args()
    base=OUT/'native-viewer' if args.package else BUILD
    assets=base/'assets' if args.package else HERE/'extracted/resources';viewer=base/'ss6-viewer'
    pads,oracle,shots,details=(hanzo_duel if args.hanzo else rimururu_duel if args.rimururu else default_duel)(assets)
    lines,captures=convert(pads,shots)
    with tempfile.TemporaryDirectory() as td:
        work=Path(td);harness=work/'select-window';setup=work/'empty.pad';setup.write_text('0 0 0\n')
        seq=work/'events';seq.write_text('\n'.join(lines)+'\n');script=work/'reference.pad';snap=work/'reference.bmp'
        sdl=shlex.split(run(['pkg-config','--cflags','--libs','sdl3']))
        run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',HERE/'sdl_gamepad_input_test.cpp',BUILD/'libss6-runtime.a',*sdl,'-o',harness])
        cap=[arg for tick,frame in captures.items() for arg in ('--capture',str(frame),work/f'{tick}.bmp')]
        out=run([harness,assets,setup,seq,'--mode','select','--fixed-host-time',*cap],env=DUMMY)
        events=list(map(int,next(line for line in out.splitlines() if line.startswith('events ')).split()[1:]))
        assert events[0]==2 and events[2]>=9 and events[3]>=9,events
        hashes={};photos=[]
        for t,name in shots.items():
            script.write_text(encode(pads[:t]));run([viewer,'--assets',assets,'--mode','select','--match-replay',script,'--snapshot',snap],env=DUMMY)
            actual=Image.open(work/f'{t}.bmp').convert('RGBA');expected=Image.open(snap).convert('RGBA')
            assert actual.size==expected.size==(640,480)
            assert actual.tobytes()==expected.tobytes(),(t,name,sum(x!=y for x,y in zip(actual.tobytes(),expected.tobytes())))
            hashes[name]=hashlib.sha256(actual.tobytes()).hexdigest();photos.append(actual.convert('RGB'))
            if name=='heavy':actual.save(OUT/'selected-heavy-window.png')
        if args.hanzo:
            sheet=Image.new('RGB',(960,480))
            for i,img in enumerate(photos[1:]):sheet.paste(img.resize((320,240),Image.Resampling.NEAREST),(320*(i%3),240*(i//3)))
            sheet.save(OUT/'hanzo-window-input.png')
        elif not args.rimururu:
            sheet=Image.new('RGB',(960,480))
            for i,img in enumerate(photos[:4]+photos[-2:]):sheet.paste(img.resize((320,240),Image.Resampling.NEAREST),(i%3*320,i//3*240))
            sheet.save(OUT/'select-window-input.png')
        last=next(r for r in reversed(out.splitlines()) if r.startswith('render ')).split()[1:]
        assert [int(last[i]) for i in (5,14)]==[int(oracle[-1][i]) for i in (9,19)]
        result=dict(status='passed',package=args.package,viewer_sha256=hashlib.sha256(viewer.read_bytes()).hexdigest(),runtime_sha256=hashlib.sha256((BUILD/'libss6-runtime.a').read_bytes()).hexdigest(),sdl_events=events,**details,capture_ticks=shots,rgba_sha256=hashes,fully_compared_pixels=640*480*len(shots),scope='Production viewer poll/update/render with SDL3 keyboard events and mapped virtual controller buttons. Fixed host time and manual stepping with a software SDL window renderer. Complete raw framebuffer captures versus the normalized replay; no masked rectangles.')
        name=('hanzo-window-input-validation.json' if args.hanzo else 'rimururu-window-input-validation.json' if args.rimururu else 'select-window-input-validation.json')
        (OUT/name).write_text(json.dumps(result,indent=2)+'\n');print(result)
if __name__=='__main__':main()
