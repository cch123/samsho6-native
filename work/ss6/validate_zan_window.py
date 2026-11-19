#!/usr/bin/env python3
"""Play Zan's four system controls through SDL and compare arena layers with original draw calls."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile

from validate_shin_scene import (
    ASSETS, BUILD, CAPTURE_DRIVER, LIB, OUT, PACKAGE, ROOT, SOURCE_HASH, STAGE_DRIVER,
    compare_battle_sequence, compile_driver, sha,
)
from mips_probe import Probe
from validate_shin_window import encode, keyboard
from validate_versus_heavy import DUMMY, HERE, pixels, run


def scenarios(side):
    forward=(128,64)[side]
    def pair(n,own=0,other=0):
        return (n,other,own) if side else (n,own,other)
    def actor(action):
        return dict(slot=side,action=action,steps=[])
    def aura():
        return dict(kind='effect',bank=3,actions=[6],steps=[])
    return [
        ('evade',[pair(500),pair(1,4096),pair(40)],{509:('evade',actor(72))}),
        ('cross',[pair(500),pair(80,forward),pair(4),pair(1,forward|4096),pair(55)],{599:('cross',actor(74))}),
        ('charge',[pair(500),pair(220,768)],{512:('charge-aura',aura()),676:('charge-full',actor(158))}),
        ('disarm',[pair(500),pair(176,768),pair(100),pair(75,forward),pair(5),pair(1,32),
                   pair(1,32|forward),pair(1,forward|768),pair(360)],
         {870:('weapon-startup',dict(kind='effect',bank=4,actions=list(range(4)),steps=[])),
          959:('weapon-flying',dict(slot=1-side,action=466,steps=[])),
          1122:('weapon-landed',dict(slot=1-side,action=467,steps=[]))}),
        ('air-guard',[pair(500),pair(40,forward,forward^192),pair(8),pair(1,16,16),pair(11),
                      pair(1,0,1024),pair(3),pair(1,4096),pair(90)],{575:('air-guard',actor(308))}),
    ]


def verify_keys(folder,side,seq,tick,spirit='zan',assets=PACKAGE/'assets'):
    flags=['--p2-spirit' if side else '--p1-spirit',spirit]
    cutoff=tick
    segments=[]
    for n,a,b in seq:
        segments.append((min(n,cutoff),a,b))
        cutoff-=segments[-1][0]
        if not cutoff:break
    assert cutoff==0 and segments[0]==(500,0,0)
    initial=folder/'start';initial.write_text(encode(segments[:1]))
    replay=folder/'case';replay.write_text(encode(segments))
    reference=folder/'snapshot.bmp';actual=folder/'keyboard.bmp'
    output=run([folder/'keys',assets,initial,actual,'--versus',*flags,*keyboard(segments[1:])],
               env=DUMMY,text=True).stdout
    run([folder/'viewer','--assets',assets,'--mode','versus',*flags,
         '--match-replay',replay,'--snapshot',reference],env=DUMMY)
    observed=next(line.split()[1:] for line in output.splitlines() if line.startswith('observed '))
    assert int(observed[0])==tick and pixels(actual)==pixels(reference),(side,tick,observed)
    return [list(map(int,observed[1+9*i:8+9*i])) for i in (0,1)]


def verify_rematch(folder,side,spirit='zan',assets=PACKAGE/'assets'):
    flags=['--p2-spirit' if side else '--p1-spirit',spirit]
    def pair(n,held=0):
        return (n,0,held) if side else (n,held,0)
    initial=folder/'start';screenshot=folder/'menu.bmp'
    # R clears the selected spirit’s move. CONTINUE has to inherit the
    # selected spirit across two timed-out rounds and a fresh NativeMatch.
    for restart in (True,False):
        setup=[pair(500),pair(100,768 if spirit=='zan' else 1792)] if restart else [pair(12200)]
        initial.write_text(encode(setup))
        start=[] if restart else [pair(1,32),pair(1),pair(1,1024)]
        post=[*start,pair(500),pair(12,768)]
        keys=(['R'] if restart else [])+keyboard(post)
        shown=run([folder/'keys',assets,initial,screenshot,'--versus',*flags,*keys],
                  env=DUMMY,text=True).stdout
        actual=next(line.split()[1:] for line in shown.splitlines() if line.startswith('observed '))
        assert list(map(int,actual[1+9*side:4+9*side]))==({'zan':[0,46,158],'ten':[1,39,242],'zero':[0,62,144],'ken':[1,0,186]}[spirit]),(side,restart,actual)
        reference=post if restart else setup+post
        row=run([BUILD/'ss6-match-replay',assets,'--mode','versus',*flags,'--spirit-fields'],
                text=True,input=encode(reference)).stdout.splitlines()[-1].split()
        assert int(actual[0])==int(row[0]) and int(row[31])==(1 if restart else 2)
        assert (int(row[23+side*4]),int(row[23+(1-side)*4]))==({'zan':2,'ten':3,'zero':4,'ken':5}[spirit],0)


def verify_charge_clock(side):
    flag='--p2-spirit' if side else '--p1-spirit'
    charge='1 0 768\n' if side else '1 768 0\n'
    def trace(field):
        result=run([BUILD/'ss6-match-replay',PACKAGE/'assets','--mode','versus',flag,'zan',field],
                   input='500 0 0\n'+charge*215,text=True)
        return {int(words[0]):words for row in result.stdout.splitlines() if (words:=row.split())}
    sound,shake,rage=(trace(field) for field in ('--sound-fields','--shake-fields','--rage-fields'))
    events=[]
    for tick,words in sound.items():
        requests=[tuple(map(int,words[j:j+3])) for j in range(26,len(words),3)]
        if (0,0,61) in requests:events.append(tick)
    assert events==[676],(side,events)
    i=23+side*11
    assert rage[675][i]=='0' and list(map(int,rage[676][i:i+3]))==[1,0xb800,98]
    # 11ec5c requests 30 vertical ticks in the gauge task. Fighter-camera
    # publication consumes the first tick, the stage still uses the previous camera.
    for tick in range(674,710):
        assert list(map(int,shake[tick][23:25]))==[0,(705-tick)*256 if 676<=tick<705 else 0],(side,tick)
        assert shake[tick][30:32]==shake[tick-1][28:30],(side,tick,'stage camera delay')
    return dict(side=side+1,full_update=676,sample=61,vertical_shake_ticks=30)


def verify_set_result(side):
    forward=(128,64)[side]
    def pair(n,held=0):
        return (n,0,held) if side else (n,held,0)
    def trace(mode,fields,seq):
        return [row.split() for row in run([BUILD/'ss6-match-replay',PACKAGE/'assets','--mode',mode,
                    '--p2-spirit' if side else '--p1-spirit','zan',fields],input=encode(seq),text=True).stdout.splitlines()]
    # Five heavies put the opponent in range for a lethal disarm. Wait past
    # the next round's opening before repeating the same inputs on a fresh bar.
    hit=([pair(65,forward),pair(5),pair(1,1024),pair(88)]*5+
         [pair(400,768),pair(15),pair(75,forward),pair(5),pair(1,32),pair(1,32|forward),pair(1,forward|768)])
    first=[pair(500),*hit]
    clocks=trace('fixed-versus','--rage-fields',first+[pair(1)]*1100)
    combat=next(row for row in clocks if int(row[45])==1 and int(row[1])==4 and int(row[2])==0)
    assert int(combat[23+side*11])==0 and int(combat[9+10*(1-side)])==200
    between=int(combat[0])-sum(n for n,_,_ in first)+60
    both=[*first,pair(between),*hit,pair(1250)]
    row=trace('fixed-versus','--result-fields',both)[-1]
    assert int(row[12+side*10])==2 and int(row[25])==side
    finish=trace('fixed-versus','--finish-fields',both)[-1]
    stat=(-8 if side==0 else -4)
    category,detail=int(finish[stat+2]),int(finish[stat+3])
    assert (category,detail)==(1,0)
    # Use the winning fighter's observed HP, spirit and finishing category
    # as arguments to the Japanese victory-dialogue selection routine.
    ee=Probe((ASSETS.parent/'SLPS_255.59').read_bytes());battle,actors=0x1b00000,0x1c00000
    for addr,val in ((0x4d3d00,battle),(0x4d3d08,actors),(0x4c3810,side)):
        ee.write(addr,val,4)
    for i in range(2):
        actor=actors+0xf2c*i;ee.write(battle+0x24c+4*i,actor,4)
        for off,val in ((0xa24,i),(0x10c,2 if side==i else 0),(0xa30,int(row[9+10*i]))):
            ee.write(actor+off,val,4)
    stats=battle+0x254+0x108*side
    ee.write(stats+0x1c,category,4);ee.write(stats+0x20,detail,4)
    original,instructions=ee.run(0x1453a8,[battle])
    assert int(row[26])==original==11
    menu=trace('versus','--vs-menu-fields',both)[-1]
    assert int(menu[12+side*10])==2 and int(menu[23])==1
    return dict(winner=side+1,score=[int(row[12]),int(row[22])],outcome=category,
                quote=original,original_instructions=instructions)


def main():
    assert sha(ASSETS.parent/'SLPS_255.59')==SOURCE_HASH
    results=[];clocks=[];sets=[]
    with tempfile.TemporaryDirectory(prefix='ss6-zan-play-') as temp:
        folder=Path(temp);lib=folder/'runtime.a';shutil.copy2(LIB,lib)
        shutil.copy2(PACKAGE/'ss6-viewer',folder/'viewer')
        assert sha(folder/'viewer')==sha(BUILD/'ss6-viewer')
        compile_driver(folder,'queue',CAPTURE_DRIVER,lib);compile_driver(folder,'stage',STAGE_DRIVER,lib)
        sdl=shlex.split(run(['pkg-config','--cflags','--libs','sdl3'],text=True).stdout)
        subprocess.run([*shlex.split(os.environ.get('CXX','c++')),'-std=c++20','-O2','-I',ROOT/'src',
                        HERE/'sdl_slash_input_test.cpp',lib,*sdl,'-o',folder/'keys'],check=True)
        for side in (0,1):
            clocks.append(verify_charge_clock(side))
            sets.append(verify_set_result(side))
            verify_rematch(folder,side)
            for name,seq,wanted in scenarios(side):
                captures,_=compare_battle_sequence(folder,side,name,'zan',seq,wanted,
                                                   range(859,924) if name=='disarm' else (),
                                                   [n for n,_ in wanted.values()])
                for capture in captures:
                    capture['keyboard_actors']=verify_keys(folder,side,seq,capture['update'])
                    if name=='disarm' and capture['update']>945:
                        assert capture['keyboard_actors'][1-side][4]==148
                    if name=='air-guard':
                        defender,attacker=capture['keyboard_actors'][side],capture['keyboard_actors'][1-side]
                        assert defender[:3]==[2,6,308] and defender[4]==200 and attacker[5:7]==[0,1]
                results.extend(captures)
        for result in results:
            target=OUT/result['screenshot'];target.parent.mkdir(exist_ok=True)
            shutil.copy2(folder/target.name,target)
        report=dict(status='passed',original_sha256=SOURCE_HASH,viewer_sha256=sha(folder/'viewer'),
                    frames=results,charge=clocks,sets=sets,restart_and_continue_seats=[1,2],
                    scope='Both human ports via SDL key events and normal versus match input. Source-stage projection, object order, character and effect draw calls, including charge aura; 640x448 RGBA against original commands. Physical keys compared with the full 640x480 packaged window except the test pause label.')
        (OUT/'zan-window-validation.json').write_text(json.dumps(report,indent=2)+'\n')
        print(len(results),'Zan keyboard and source-rendered battle frames passed')

if __name__=='__main__':
    main()
