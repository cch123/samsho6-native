#!/usr/bin/env python3
"""Compare both slots' physical Shin keyboard moves in the real SDL loop with the packaged viewer."""
import argparse
import hashlib
from itertools import groupby
import json
import os
from pathlib import Path
import shlex
import shutil
import tempfile

from PIL import Image
from validate_versus_heavy import ASSETS, BUILD, DUMMY, HERE, OUTPUT, PKG, ROOT, digest, pixels, run

PADS = ({16:'W',32:'S',64:'A',128:'D',256:'J',512:'U',1024:'L',2048:'M',4096:'F'},
        {16:'Up',32:'Down',64:'Left',128:'Right',256:'O',512:'[',1024:'I',2048:']',4096:'\\'})
ARCHIVE = OUTPUT/'shin-window'


def encode(segments):
    return ''.join(f'{n} {p1} {p2}\n' for n,p1,p2 in segments)


def keyboard(segments):
    held=[0,0]
    result=[]
    for masks,pieces in groupby(segments,key=lambda x:x[1:]):
        for player,mask in enumerate(masks):
            for bit,key in PADS[player].items():
                if (held[player]^mask)&bit:
                    result.append(key+('+' if mask&bit else '-'))
            held[player]=mask
        result.append('N'+str(sum(n for n,_a,_b in pieces)))
    return result


def validate(work,viewer,assets):
    candidate=work/'viewer'
    shutil.copy2(viewer,candidate)
    match=work/'replay'
    shutil.copy2(BUILD/'ss6-match-replay',match)
    harness=work/'keyboard'
    sdl=shlex.split(run(['pkg-config','--cflags','--libs','sdl3'],text=True).stdout)
    run([*shlex.split(os.environ.get('CXX','c++')),'-std=c++20','-O2','-I',ROOT/'src',
         HERE/'sdl_slash_input_test.cpp',BUILD/'libss6-runtime.a',*sdl,'-o',harness])
    results=[]
    for side in (0,1):
        opponent=1-side
        spirits=['rage','rage'];spirits[side]='shin'
        flags=['--p1-spirit',spirits[0],'--p2-spirit',spirits[1]]
        f=(128,64)[side];b=f^192
        def pair(n,own,other=0):
            return (n,other,own) if side else (n,own,other)
        def press(keys):
            return [pair(1,key) for key in keys]
        def case(name,setup,segments,expected,*,player=side,ref_setup=None,host_keys=(),save=False):
            initial=work/'initial.pad';initial.write_text(encode(setup))
            reference=work/'complete.pad'
            reference.write_text(encode((setup if ref_setup is None else ref_setup)+segments))
            actual,exported=work/'keyboard.bmp',work/'packaged.bmp'
            shown=run([harness,assets,initial,actual,'--versus',*flags,*host_keys,*keyboard(segments)],
                      env=DUMMY,text=True)
            run([candidate,'--assets',assets,'--mode','versus',*flags,'--match-replay',reference,'--snapshot',exported],
                env=DUMMY)
            observed=next(line.split()[1:] for line in shown.stdout.splitlines() if line.startswith('observed '))
            output=run([match,assets,'--mode','versus',*flags,'--spirit-fields'],
                       input=reference.read_text(),text=True).stdout.splitlines()
            row=output[-1].split()
            assert [int(row[23+4*i]) for i in (0,1)]==[int(s=='shin') for s in spirits]
            assert observed[0]==row[0],(name,'local update',observed,row)
            for i in (0,1):
                block=row[3+10*i:13+10*i]
                assert observed[1+9*i:8+9*i]==block[:4]+block[6:9],(name,'actor',i,observed,row)
            table,state,act=(int(n) for n in row[3+10*player:6+10*player])
            assert (table,state,act)==expected,(side,name,expected,row)
            key_pixels=pixels(actual)
            assert key_pixels==pixels(exported),(side,name,'keyboard screen differs from packaged normalized input')
            rec=dict(name=name,shin_player=side+1,acting_player=player+1,local_update=int(row[0]),
                     match_number=int(row[31]),round_index=int(row[32]),state=[table,state],action=act,
                     records=[int(row[6]),int(row[16])],life=[int(row[9]),int(row[19])],
                     hits=[int(row[10]),int(row[20])],dolls=[int(row[24]),int(row[28])],
                     flags244=[int(row[25]),int(row[29])],sword_max=[int(row[26]),int(row[30])],
                     smoke_objects=[list(map(int,row[j:j+8])) for j in range(33,len(row),8)],
                     compared_pixels_sha256=hashlib.sha256(key_pixels).hexdigest())
            if save:
                # The production snapshot omits only the pause label used by the
                # keyboard harness. The 640x480 mouse-free artwork is preserved.
                filename=f'p{side+1}-{name}.png'
                with Image.open(exported) as image:image.convert('RGB').save(work/filename)
                rec['screenshot']=filename
            results.append(rec)
            return rec
        stand=[(500,0,0)]
        doll=press((f,32|f,32,32|b,b,f,b|4096))+[(20,0,0)]
        doll_pose=(0,48,164)
        item=case('doll-smoke',stand,doll,doll_pose,save=True)
        assert item['dolls'][side]==1 and item['smoke_objects'][0][:3]==[side+1,54,6]
        clear=case('doll',stand,doll+[(20,0,0)],doll_pose,save=True)
        assert clear['dolls'][side]==1 and not clear['smoke_objects'] and clear['records'][side]==2
        # The other seat makes the mirrored, identical command without Shin.
        rage_doll=[(n,p2,p1) for n,p1,p2 in
                   press((b,32|b,32,32|f,f,b,f|4096))]+[(20,0,0)]
        none=case('rage-doll-input',stand,rage_doll,(0,0,0),player=opponent)
        assert none['dolls']==[0,0] and not none['smoke_objects']
        item=case('restart',stand+doll,stand+doll,doll_pose,ref_setup=[],host_keys=['R'])
        assert item['match_number']==1 and item['local_update']==527 and item['dolls'][side]==1
        # Both rounds run to timeout. The true draw enters the VS menu.
        # All commands to select CONTINUE and transform in match two use keys.
        menu=[(12200,0,0)]
        resume=press((32,0,1024))+stand+doll
        item=case('continue',menu,resume,doll_pose)
        assert item['match_number']==2 and item['round_index']==0 and item['dolls'][side]==1
        # Build rage with four real incoming heavy slashes, then perform 236+A+B.
        prime=( [pair(65,0,b),pair(5,0),pair(1,0,1024),pair(88,0)]*4
                +[pair(100,0),pair(75,f),pair(5,0)])
        weapon=press((32,32|f,f|768))
        item=case('weapon-destruction',stand,prime+weapon+[(86,0,0)],(1,78,625),save=True)
        assert item['hits'][side]==1 and item['life'][opponent]==146 and item['sword_max'][side]==130*256
        fall=case('weapon-destruction-aftermath',stand,prime+weapon+[(150,0,0)],(1,78,625),save=True)
        assert fall['life'][opponent]==146 and fall['hits'][side]==1
        case('weapon-input-with-empty-rage',stand,weapon+[(20,0,0)],(1,65,530))
        # The independently gated secret move is usable from an empty rage bar.
        secret=press((32|f,b,32|b,32,32|f,f,b,32,(32|b)|1536))
        approach=[pair(75,f),pair(5,0)]
        item=case('secret',stand,approach+secret+[(129,0,0)],(1,79,612),save=True)
        assert item['hits'][side]==10 and item['life'][opponent]==152 and item['flags244'][side]&64
    return dict(status='passed',viewer_sha256=digest(candidate),normal_entry='--mode versus',
                cases=results,scope='SDL3 dummy video/software renderer. Real KEY_DOWN/KEY_UP events step the shipping event loop. Compares both fighter states, ACT records, health, hit/guard counts and all 640x480 pixels except the 48x8 PAUSED label against the packaged viewer running the same pads. R restarts from an already transformed fighter. CONTINUE starts at the post-match menu after a genuine timeout.')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--staging',action='store_true',help='Check the current build with its extracted assets without publishing a report.')
    args=parser.parse_args()
    viewer,assets=(BUILD/'ss6-viewer',HERE/'extracted/resources') if args.staging else (PKG/'ss6-viewer',ASSETS)
    if not args.staging:assert digest(viewer)==digest(BUILD/'ss6-viewer'),'Package the current viewer before verifying.'
    with tempfile.TemporaryDirectory(prefix='shin-keyboard-') as tmp:
        work=Path(tmp)
        result=validate(work,viewer,assets)
        if not args.staging:
            ARCHIVE.mkdir(exist_ok=True)
            for item in result['cases']:
                if 'screenshot' in item:shutil.copy2(work/item['screenshot'],ARCHIVE/item['screenshot'])
            (OUTPUT/'shin-window-validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(len(result['cases']),'SDL keyboard cases passed',result['viewer_sha256'])

if __name__=='__main__':
    main()
