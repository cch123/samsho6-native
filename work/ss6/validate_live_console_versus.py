#!/usr/bin/env python3
"""Play consecutive sets through the shipping SDL loop and compare the packaged menu to PS2 draw packets."""
import json
from hashlib import sha256
import shlex
import subprocess
import tempfile
from itertools import groupby
from pathlib import Path
import numpy as np
from PIL import Image
from extract_console_versus_art import prepare, capture, ORIGINAL
from validate_console_versus_art import reference
from validate_versus_heavy import ASSETS, BUILD, DUMMY, HERE, OUTPUT, ROOT, digest

NEUTRAL=(0,0)
REMATCH=0x139760

# Sample the shipping composition just before the menu painter. The priority-20
# HUD keeps ticking while the fighter clocks are paused (for example the red
# damage trail can still drain). A backdrop captured on menu entry goes stale.
BACKDROP_DRIVER=r'''
#include "console_versus_art.hpp"
namespace ss6 {
class MenuBackdrop {
public:
    explicit MenuBackdrop(const std::filesystem::path&) {}
    void paint(const ConsoleVersusMenuDraw&,std::span<uint8_t>) const {}
};
}
#define ConsoleVersusArt MenuBackdrop
#include "viewer.cpp"
'''
def encode(pads):
    return ''.join(f'{sum(1 for _ in group)} {a} {b}\n' for (a,b),group in groupby(pads))

def trace(commands,*args):
    raw=subprocess.check_output([BUILD/'ss6-match-replay',ASSETS,'--vs-menu-fields',*args],input=commands,text=True)
    return [row.split() for row in raw.splitlines()]

def winning_inputs(side):
    walk=(128,0) if side==0 else (0,64)
    heavy=(1024,0) if side==0 else (0,1024)
    return [NEUTRAL]*440+( [walk]*45+[heavy]+[NEUTRAL]*84 )*30

def first_menu(prefix,pads):
    # Output one row per tick so gameplay-driven round lengths need no fixture constant.
    rows=trace(encode(prefix)+''.join(f'1 {a} {b}\n' for a,b in pads))[-len(pads):]
    stop=next(i+1 for i,r in enumerate(rows) if r[24]=='1')
    return pads[:stop],rows[stop-1]

def pixels(tmp,pads,viewer):
    script=tmp/'snapshot.pad';script.write_text(encode(pads))
    bmp=tmp/'window.bmp'
    subprocess.run([viewer,'--mode','versus','--assets',ASSETS,'--match-replay',script,'--snapshot',bmp],
                   env=DUMMY,check=True,stdout=subprocess.DEVNULL)
    return np.array(Image.open(bmp).convert('RGBA'))

def compare_menu_art(tmp,won,viewer,backdrop):
    p=prepare();p.run(0x1daf50);p.run(0x1cebb0,[52])
    records=[];samples={0,16,30,40,45,60,61,63,65,67,69}
    inputs=[NEUTRAL]*61+[(0,32),NEUTRAL,(0,16),NEUTRAL,(512,0),NEUTRAL,(0,128),NEUTRAL,(0,2048)]
    rows=trace(encode(won)+''.join(f'1 {a} {b}\n' for a,b in inputs))[-len(inputs):]
    for i,row in enumerate(rows):
        sel,dialog,choice=map(int,row[27:30])
        for offset,value in [(0,sel),(4,dialog),(8,0),(12,choice)]:
            p.write(0x582fb8+offset,value,4)
        packets=capture(p,0x1dafa0,[])
        if i not in samples:continue
        assert row[32]=='0'  # These menu snapshots precede the global screen fade.
        pads=won+inputs[:i+1]
        screen=pixels(tmp,pads,viewer)
        base=pixels(tmp,pads,backdrop)[:448]
        expected=reference(p,packets,base)
        assert np.array_equal(expected,screen[:448]),(i,sel,dialog,choice,int(np.count_nonzero(expected!=screen[:448])))
        changed=int(np.count_nonzero(np.any(base!=expected,axis=2)))
        records.append(dict(menu_frame=i,item=sel,dialog=dialog,answer=choice,packets=len(packets),
                            backdrop_sha256=sha256(base.tobytes()).hexdigest(),changed_menu_pixels=changed))
        if i==61:
            Image.fromarray(screen).save(OUTPUT/'console-versus-rematch.png')
            (OUTPUT/'console-versus-rematch.replay').write_text(encode(won+inputs[:i+1]))
    assert len({r['backdrop_sha256'] for r in records})>1
    assert records[0]['changed_menu_pixels']==0 and all(r['changed_menu_pixels']>0 for r in records[1:])
    return records

def validate():
    with tempfile.TemporaryDirectory() as name:
        tmp=Path(name)
        viewer=OUTPUT/'native-viewer/ss6-viewer'
        identity=digest(viewer)
        sdl=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','sdl3'],text=True))
        source=tmp/'backdrop.cpp';source.write_text(BACKDROP_DRIVER);backdrop=tmp/'backdrop'
        subprocess.run(['c++','-std=c++20','-O2','-I',ROOT/'src',source,BUILD/'libss6-runtime.a',*sdl,'-o',backdrop],check=True)
        first,r=first_menu([],winning_inputs(0))
        assert r[33:37]==['1','0','0','1'] and r[12]=='2' and r[22]=='0'
        pictures=compare_menu_art(tmp,first,viewer,backdrop)
        start=first+[NEUTRAL]*65
        setup=tmp/'first-set.pad';setup.write_text(encode(start))
        samples=[];steps=[];buttons=[0,0]
        def emit(count,a=0,b=0,keyboard=False,connect=False):
            tokens=['+1'] if connect else []
            # Alternate keyboard and physical input on the same menu. No two
            # controls share a held level across input sources in these steps.
            for side,held in enumerate((a,b)):
                for mask,physical,keys in [(32,14,('S','Down')),(64,15,('A','Left')),
                        (128,13,('D','Right')),(1024,5,('L','I')),(2048,6,('M',']'))]:
                    if (buttons[side]^held)&mask:
                        down=bool(held&mask)
                        tokens.append('K'+keys[side]+('+' if down else '-') if keyboard else
                                      f'{side}.{physical}={int(down)}')
                buttons[side]=held
            steps.append(' '.join(tokens+[f'N{count}']))
            samples.append((count,a,b))
        emit(1,0,1024,connect=True) # P2 opens Character Select, then cancels.
        emit(1);emit(1,0,2048);emit(1)
        emit(1,0,32);emit(1);emit(1,1024,0,keyboard=True)
        emit(1,keyboard=True);emit(14)
        warm=start[:]
        for n,a,b in samples:warm.extend([(a,b)]*n)
        state=trace(encode(warm))[-1]
        assert state[23:26]==['2','0','0'] and state[0]=='0' and state[9]==state[19]=='200'
        assert state[12]==state[22]=='0' and state[33:37]==r[33:37] and state[43]!=r[43]
        second,r2=first_menu(warm,winning_inputs(1))
        for (a,b),run in groupby(second):emit(sum(1 for _ in run),a,b)
        emit(65)
        assert r2[12]=='0' and r2[22]=='2' and r2[33:37]==['1','1','1','1']
        replay=encode(start)+''.join(f'{n} {a} {b}\n' for n,a,b in samples)
        rows=trace(replay)[-(len(samples)+1):]
        assert rows[0][24]=='1'  # first rendered update is already at the menu
        seq=tmp/'controls';seq.write_text('\n'.join(steps+['KR+ KR- N1'])+'\n')
        harness=tmp/'pads'
        subprocess.run(['c++','-std=c++20','-O2','-I',ROOT/'src',HERE/'sdl_gamepad_input_test.cpp',
                        BUILD/'libss6-runtime.a',*sdl,'-o',harness],check=True)
        log=subprocess.check_output([harness,ASSETS,setup,seq],text=True,env=DUMMY,timeout=90)
        lines=[line.split()[1:] for line in log.splitlines() if line.startswith('menu ')]
        fields=[0,24,25,27,28,29,30,31,32,33,34,35,36,40,12,22]
        assert len(lines)==len(rows)+1
        for i,(observed,row) in enumerate(zip(lines[:-1],rows,strict=True)):
            assert observed==[str(i)]+[row[f] for f in fields],(i,observed,row)
        assert lines[-1][1]=='1' and all(v=='0' for v in lines[-1][10:14])
        # The terminal routes are separate main tasks; choosing No preserves
        # this fight while selecting Yes follows its actual PS2 entry address.
        endings=[]
        for item,entry in [(0,0x128008),(2,0x127940)]:
            route=start+([(0,16),NEUTRAL] if item==2 else [])
            route += [(1024,0),NEUTRAL,(0,1024),NEUTRAL]
            assert trace(encode(route))[-1][28:32]==['0','1','0','0']
            route += [(0,1024),NEUTRAL,(0,128),NEUTRAL,(1024,0)]+[NEUTRAL]*15
            dest=trace(encode(route))[-1]
            assert int(dest[31])==entry and dest[33:37]==(['0']*4 if item==2 else ['1','0','0','1'])
            endings.append(hex(entry))
        draw=trace('14000 0 0\n')[-1]
        assert draw[24]=='1' and draw[33:37]==['0','1','0','1'] and draw[37]=='-1'
        assert trace('500 0 0\n')[-1][40]=='60'
        events=next(line for line in log.splitlines() if line.startswith('events ')).split()[1:]
        assert digest(viewer)==identity,'Packaged viewer changed during capture'
        report=dict(status='passed',original_sha256=ORIGINAL,viewer_sha256=identity,
                    first_set_ticks=len(first),second_set_ticks=len(second),sdl_samples=len(rows),sdl_events=list(map(int,events)),
                    second_set_score=r2[33:37],default_counts=60,tie_losses=[1,1],destination_entries=endings,
                    original_menu_window_frames=pictures,compared_menu_pixels=640*448*len(pictures),
                    scope='Two complete sets in the shipping SDL event loop. For each menu sample, replay the same inputs with only the final menu painter omitted, composite the Japanese menu packets over that update’s arena and HUD, and compare the 640x448 game area with the release snapshot.')
        (OUTPUT/'live_console_versus_validation.json').write_text(json.dumps(report,indent=2)+'\n')
        print('Two played sets, both physical ports, keyboard confirm, manual reset, tied set, two destinations,',len(pictures),'window frames passed')
if __name__=='__main__':validate()
