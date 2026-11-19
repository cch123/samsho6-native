"""Exercise the CPU option through the public viewer, select screen and post-match rematch."""
import argparse
import json
import shlex
import subprocess
import tempfile
from hashlib import sha256
from pathlib import Path
from PIL import Image
from validate_versus_heavy import ROOT,HERE,BUILD,PKG,DUMMY
from validate_select_session import encode
from validate_selected_combat import prefix
from validate_select_window_input import convert,run

def trace(assets,entry,cpu,field,segments):
    proc=subprocess.run([BUILD/'ss6-match-replay',assets,'--mode',entry,'--cpu',cpu,field],
                        input=segments,text=True,capture_output=True,check=True)
    return [row.split() for row in proc.stdout.splitlines()]

def screenshot(command,assets,path,tick):
    subprocess.run([*command,'--assets',assets,'--updates',str(tick),'--snapshot',path],
                   env=DUMMY,check=True,capture_output=True)
    with Image.open(path) as img:
        assert img.size==(640,480)
        return sha256(img.convert('RGBA').tobytes()).hexdigest()

def play_window(assets,viewer,work,harness,seat):
    cpu=('p2','p1')[seat]
    def held(mask):return (0,mask) if seat else (mask,0)
    # One human heavy comes from the keyboard on P1 or the hotplugged gamepad
    # on P2. Release it and let the CPU advance the fight on its own.
    pads=[(0,0)]*460+[held((128,64)[seat])]*28+[held(1024)]+[(0,0)]*900
    rows=trace(assets,'versus',cpu,'--vs-menu-fields',''.join(f'1 {a} {b}\n' for a,b in pads))
    first=[next(i+1 for i,row in enumerate(rows) if int(row[col])) for col in (10,20)]
    assert first[seat]<first[1-seat]
    checkpoints={first[seat],first[1-seat],first[1-seat]+20}
    pads=pads[:max(checkpoints)]
    record,captures=convert(pads,checkpoints)
    keys=work/'keys';keys.write_text('\n'.join(record)+'\n')
    empty=work/'empty.pad';empty.write_text('0 0 0\n')
    shots=[arg for tick,frame in captures.items() for arg in ('--capture',str(frame),work/f'{tick}.bmp')]
    run([harness,assets,empty,keys,'--mode','versus','--cpu',cpu,'--fixed-host-time',*shots],env=DUMMY)
    for tick in checkpoints:
        replay=work/'normalized.pad';replay.write_text(encode(pads[:tick]))
        ref=work/'reference.bmp'
        run([viewer,'--assets',assets,'--mode','versus','--cpu',cpu,'--match-replay',replay,'--snapshot',ref],env=DUMMY)
        with Image.open(ref) as expected,Image.open(work/f'{tick}.bmp') as actual:
            assert actual.size==expected.size==(640,480) and actual.convert('RGBA').tobytes()==expected.convert('RGBA').tobytes()
    return dict(cpu=cpu,first_human_hit=first[seat],first_cpu_hit=first[1-seat],matched_window_frames=len(checkpoints))

def validate(assets,viewer,package):
    routes=[]
    for cpu in ('p1','p2','both'):
        # Both ports can operate the menu, including the one assigned to CPU in the fight.
        end,menu,*_,again,second=trace(assets,'versus',cpu,'--vs-menu-fields',
                '22000 0 0\n1 32 0\n10 0 0\n1 1024 0\n1600 0 0\n22000 0 0\n')
        assert end[2]=='1' and end[23:26]==['1','1','1'] and max(int(end[12]),int(end[22]))>=2
        assert menu[27]=='1' and again[23]=='2' and again[2]=='0' and second[23]=='2' and second[2]=='1'
        seats=[int(end[10]),int(end[20])]
        if cpu=='both':assert min(seats)>0
        else:
            side=int(cpu=='p2')
            assert seats[side]>0 and seats[1-side]==0
            assert int(again[(10,20)[side]])>0 and int(again[(10,20)[1-side]])==0
        routes.append(dict(cpu=cpu,first_round_wins=[int(end[12]),int(end[22])],first_contacts=seats,
                           second_round_wins=[int(second[12]),int(second[22])]))
    pads=prefix((3,2))
    selected=trace(assets,'select','p2','--select-fields',encode(pads)+'2000 0 0\n')[-1]
    assert selected[24]=='0' and selected[25]=='3' and selected[35]=='2'
    assert int(selected[20])>0 and int(selected[10])==0
    with tempfile.TemporaryDirectory() as folder:
        work=Path(folder);out=work/'cpu.bmp'
        harness=work/'window';libs=shlex.split(run(['pkg-config','--cflags','--libs','sdl3']))
        run(['c++','-std=c++20','-O2','-I',ROOT/'src',HERE/'sdl_gamepad_input_test.cpp',BUILD/'libss6-runtime.a',*libs,'-o',harness])
        window_routes=[play_window(assets,viewer,work,harness,seat) for seat in (0,1)]
        def snap(command,tick):return screenshot(command,assets,out,tick)
        cpu_command=[ROOT/'cpu.command'] if package else [viewer,'--mode','versus','--cpu','p2']
        actual=snap(cpu_command,900)
        same=snap([viewer,'--mode','versus','--cpu','p2'],900)
        human=snap([viewer,'--mode','versus'],900)
        opposite=snap([viewer,'--mode','versus','--cpu','p1'],900)
        assert actual==same and len({actual,human,opposite})==3
    return dict(status='passed',package=package,viewer_sha256=sha256(viewer.read_bytes()).hexdigest(),
                routes=routes,windows=window_routes,selected_fighters=[3,2],selected_cpu_p2_contacts=int(selected[20]),
                p2_window_sha256=actual,p1_window_sha256=opposite,human_window_sha256=human)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--package',action='store_true');args=parser.parse_args()
    base=PKG if args.package else BUILD;assets=base/'assets' if args.package else HERE/'extracted/resources'
    result=validate(assets,base/'ss6-viewer',args.package)
    (ROOT/'outputs/ss6-feasibility/cpu-session-validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result)

