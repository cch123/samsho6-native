#!/usr/bin/env python3
"""Verify mixed-fighter descending jump A against the Japanese contact and render paths."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from hashlib import sha256
from itertools import groupby, takewhile
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

from validate_nakoruru_combat import MixedContactOracle, ACTORS
from validate_native_scene import LIB, SOURCE_HASH, fixture
from validate_selected_combat import BUILD, CAPTURE, OUT, ROOT, SOURCE, capture, prefix, trace


# Keep camera, palette, hit tint and world position fixed. This diagnostic
# distinguishes visibly different character drawings from a damage flash on
# an otherwise unchanged standing sprite. The full-scene test still measures
# how many target pixels survive the other fighter, eagle and contact spark.
POSE_DRIVER=CAPTURE.replace('    fill({17,31,43,255});scene.paint',r'''    if(argc>=7||argc==5) {
        unsigned seat=unsigned(std::stoi(argv[4]));ObjectDrawQueue body;
        for(const auto& row:q.active())if(row[81]==0 && row[3]==seat && row[51]==seat)body.slots[body.count++]=row;
        if(body.count!=1)return 5;
        body.sort();std::vector<uint8_t> before;
        if(argc==5){
            body.slots[0][0x38/4]|=0x200000u; // Omit only the original shadow in the isolated figure.
            fill({235,232,223,255});scene.paint(body,
                {b.camera,{b.gauges.words910[2],b.gauges.words910[3]},b.gauges.focus46a948,0},
                b.paletteState,b.gauges.paletteTones,rgba,[](const EffectDraw&){});
            std::cout.write(reinterpret_cast<char*>(rgba.data()),rgba.size());return 0;
        }
        auto paint=[&](){fill({17,31,43,255});scene.paint(body,
            {b.camera,{b.gauges.words910[2],b.gauges.words910[3]},b.gauges.focus46a948,0},
            b.paletteState,b.gauges.paletteTones,rgba,[](const EffectDraw&){});};
        paint();before=rgba;body.slots[0][9]=std::stoi(argv[5]);
        unsigned minimum=640*448;
        for(int record=6;record<argc;++record) {
            body.slots[0][10]=std::stoi(argv[record]);paint();
            unsigned differences=0;for(size_t i=0;i<rgba.size();i+=4)
                differences+=!std::equal(before.begin()+i,before.begin()+i+4,rgba.begin()+i);
            minimum=std::min(minimum,differences);
        }
        std::cout<<minimum;return 0;
    }
    fill({17,31,43,255});scene.paint''')

class KenContact(MixedContactOracle):
    def install_player(self,row,slot):
        super().install_player(row,slot)
        self.probe.write(ACTORS+0xf2c*slot+0x10c,5,4)


def controls(lineup,attacker,posture):
    def pair(us,them):return (them,us) if attacker else (us,them)
    transition=posture=='entering_crouch'
    held=32 if posture=='settled_crouch' else 0
    pads=prefix(lineup)+[pair((128,64)[attacker],0)]*45+[pair(0,held)]*(8 if transition else 6 if held else 2)
    start=len(pads)
    # Rimururu's strike is the sixth ACT record. Her jumping light reaches
    # the croucher with an earlier button edge than the other two fighters.
    delay=(30,33+int(bool(held and lineup[1-attacker])),28)[lineup[attacker]]
    for t in range(100):
        pads.append(pair(16 if t==0 else 256 if t==delay else 0,32 if transition and t>=38 else held))
    return pads,start


def boxes(resource,action,record):
    aid,act,jdg=[(SOURCE/f'{s}_{resource:02}.bin').read_bytes() for s in ('aid','act','jdg')]
    first=struct.unpack_from('<h',aid,2*action)[0];at=60*(first+record)
    count=struct.unpack_from('<H',act,at+30)[0]&7
    return [struct.unpack_from('<I5h',jdg,r*16) for r in struct.unpack_from(f'<{count}h',act,at+14)]



def original_parts(resource,action,step):
    aid,act,pil=[(SOURCE/f'{s}_{resource:02}.bin').read_bytes() for s in ('aid','act','pil')]
    first=struct.unpack_from('<h',aid,action*2)[0]
    refs=struct.unpack_from('<5h',act,(first+step)*60+4)
    return [pil[(ref-1)*16:ref*16] for ref in refs if ref]

def check(job):
    driver,viewer,replay,assets,lineup,attacker,posture=job;defender=1-attacker
    pads,start=controls(lineup,attacker,posture)
    flow=trace(replay,assets,pads)
    raw=subprocess.run([replay,assets,'--mode','select','--contact-fields'],text=True,capture_output=True,check=True,
                       input=''.join('1 %d %d\n'%tuple(v) for v in pads))
    rows=[s.split() for s in raw.stdout.splitlines()];a=3+10*attacker;b=3+10*defender
    assert any(r[24]=='1' and r[45]=='0' and r[47]=='1' for r in flow[:start])
    assert (int(flow[start][25]),int(flow[start][35]))==lineup and flow[start][26]==flow[start][36]=='5'
    assert all(r[:23]==s[:23] for r,s in zip(flow,rows,strict=True))
    assert any(r[a:a+3]==['1','2','209'] for r in rows[start:])
    def select_hurt(item,probe,event,actor):
        # The original hit handler requests a state. 1707b0 selects its
        # armed or disarmed drawing from the actual receiver on the next visit.
        context=0x1e02000;state=item['target_state']
        probe.write(context,actor,4);probe.write(context+4,ACTORS+attacker*0xf2c,4)
        probe.run(0x1707b0,[context,(state-32)//3,(state-32)%3])
        item['original_hurt_action']=probe.read(actor+0xa3c,4)
    contacts=KenContact(lineup).contacts(rows[start-5:],attacker,select_hurt)
    target_hp=int(rows[-1][b+6]);case=dict(lineup=lineup,attacker=attacker+1,defender=defender+1,posture=posture,
        target_hp=target_hp,original_contacts=contacts,captures=[])
    if not lineup[attacker] and posture=='settled_crouch':
        # Even on the last airborne pose the saber starts above the settled
        # croucher's upper hurtbox. The lowering animation can still be hit.
        active=[r for r in rows[start:] if r[a+2:a+4]==['209','4']]
        assert active and not contacts and target_hp==200 and all(r[b+2:b+4]==['4','0'] for r in active)
        weapon=[x for x in boxes(0,209,4) if x[0]>>28==2];hurt=[x for x in boxes(lineup[defender],4,0) if x[0]>>26==2]
        vulnerable_top=max(x[5] for x in hurt);strike_bottom=min(x[3] for x in weapon)
        assert vulnerable_top<strike_bottom and all(float(r[a+5])>=0 for r in active)
        case.update(minimum_strike_height=strike_bottom,maximum_vulnerable_height=vulnerable_top)
        return case
    assert len(contacts)==1 and contacts[0]['raw']==10 and contacts[0]['defense']==0 and 200-target_hp==contacts[0]['damage']
    hit=next(i for i in range(start,len(rows)) if int(rows[i][b+6])<200)
    assert rows[hit-1][a+2:a+4]==['209',str(5 if lineup[attacker]==2 else 4)] and int(rows[hit][0])==contacts[0]['frame']
    assert rows[-1][a+7:a+9]==['1','0'] and rows[-1][a]==rows[-1][b]=='0'
    expected=356 if posture=='standing' else 350
    run=list(takewhile(lambda r:r[b]=='2',rows[hit:]));assert run and {int(r[b+2]) for r in run}=={expected}
    assert contacts[0]['target_state']==(41 if posture=='standing' else 38) and contacts[0]['original_hurt_action']==expected
    entering=rows[hit-1][b+2:b+4]
    if posture=='entering_crouch':assert entering[0]=='6' and int(entering[1])<2
    if posture=='settled_crouch':assert entering==['4','0']
    ordered=[(s,len(list(g))) for s,g in groupby(int(r[b+3]) for r in run)]
    first,limit=struct.unpack_from('<2h',(SOURCE/f'aid_{lineup[defender]:02}.bin').read_bytes(),expected*2)
    assert [s for s,n in ordered]==list(range(limit-first)),(lineup,posture,ordered)
    case.update(contact_pad_update=hit+1,hurt_action=expected,hurt_duration=len(run),pre_impact_action=list(map(int,entering)),records=ordered)
    original=fixture((*lineup,51));stats=Counter()
    for bank,name in enumerate(('01HitFlash.bin','02Guard.bin','03etc.bin')):
        data=(SOURCE/name).read_bytes();at=0x4a4810+bank*0x3da0;original.memory[at:at+len(data)]=data
    with tempfile.TemporaryDirectory() as td:
        elapsed=0
        for step,count in ordered:
            result=capture(driver,viewer,assets,Path(td),original,lineup,pads,hit+elapsed,{'slot':defender,'action':expected,'steps':[]},stats)
            visible=result['visible'][0]
            assert visible['steps']==[step] and visible['visible_pixels']>100 and visible['quads']>0,(lineup,attacker,posture,step,visible)
            change=subprocess.run([driver,assets,*map(str,lineup),str(defender),*entering],check=True,capture_output=True,
                input=''.join('%d %d\n'%tuple(v) for v in pads[:hit+elapsed+1]).encode())
            changed=int(change.stdout)
            parts=original_parts(lineup[defender],expected,step)
            previous_parts=original_parts(lineup[defender],*map(int,entering))
            # Resource 01's final crouching hurt record uses exactly the two
            # PIL entries from settled crouch. The body remains in hitstun
            # until the action exits, even though its silhouette has recovered.
            same=parts==previous_parts
            assert changed==0 if same else changed>100,(lineup,defender,posture,step,changed,same)
            if same:assert lineup[defender]==1 and posture=='settled_crouch' and step==2
            case['captures'].append(dict(pose_change_pixels=changed,source_reuses_preimpact_pose=same,source_picture_ids=[int.from_bytes(v[:2],'little') for v in parts],pad_update=result['pad_tick'],record=step,source_act_record=first+step,native_sha256=result['rgba_sha256'],
                visible_victim_pixels=visible['visible_pixels'],victim_quads=visible['quads'],queue_records=result['ordered_objects']))
            if lineup[defender]==2 and step==ordered[-1][0]:
                # Compare the last hurt pose with every on-disc idle drawing.
                # A pre-impact record alone would miss a reused later cel.
                idle=4 if posture!='standing' else 0
                idle_first,idle_end=struct.unpack_from('<2h',(SOURCE/f'aid_{lineup[defender]:02}.bin').read_bytes(),2*idle)
                reference=sorted({tuple(original_parts(2,idle,n)):n for n in range(idle_end-idle_first)}.values())
                rendered=subprocess.run([driver,assets,*map(str,lineup),str(defender),str(idle),*map(str,reference)],
                    input=''.join('%d %d\n'%tuple(v) for v in pads[:hit+elapsed+1]).encode(),check=True,capture_output=True)
                minimum=int(rendered.stdout)
                assert minimum>100,(lineup,defender,posture,step,'idle comparison',minimum)
                case['final_pose_vs_idle']=dict(action=idle,distinct_records=len(reference),minimum_changed_pixels=minimum)
            elapsed+=count
    return case


def digest(path):return sha256(path.read_bytes()).hexdigest()


def figure(viewer,assets,replay,report):
    """One public match, four actual window crops with a matching unobstructed target below."""
    from PIL import Image,ImageDraw,ImageFont
    background=(235,232,223);ink=(34,40,38);muted=(79,84,79);teal=(0,95,97)
    regular='/System/Library/Fonts/STHeiti Light.ttc';medium='/System/Library/Fonts/STHeiti Medium.ttc'
    def font(n,strong=False):return ImageFont.truetype(medium if strong else regular,n)
    c=next(c for c in report['cases'] if c['lineup']==[1,1] and c['attacker']==1 and c['posture']=='settled_crouch')
    assert report['viewer_sha256']==digest(viewer) and report['replay_sha256']==digest(replay)
    pads,_=controls((1,1),0,'settled_crouch')
    caps=c['captures'];ticks=[c['contact_pad_update']-1,*[f['pad_update'] for f in caps]]
    assert c['records']==[[0,9],[1,3],[2,3]] and caps[-1]['source_reuses_preimpact_pose'] and caps[-1]['pose_change_pixels']==0
    sheet=Image.new('RGB',(1328,680),background);draw=ImageDraw.Draw(sheet)
    draw.text((28,19),'娜可露露蹲姿受到跳轻斩',font=font(38,True),fill=ink)
    draw.text((1300,32),'蓝色 P2 受击　｜　红色 P1 进攻',font=font(23),fill=teal,anchor='ra')
    draw.line((28,85,1300,85),fill=(170,173,162));width=304;gap=18
    headings=['命中前','第一种受击姿势','第二种受击姿势','蹲姿恢复，仍有硬直']
    times=['上一帧','受击第 1—9 帧','受击第 10—12 帧','受击第 13—15 帧']
    with tempfile.TemporaryDirectory() as td:
        tmp=Path(td);cpp=tmp/'queue.cpp';exe=tmp/'queue';cpp.write_text(POSE_DRIVER)
        subprocess.run(['c++','-std=c++20','-O2','-ffp-contract=off','-I',ROOT/'src',cpp,LIB,'-o',exe],check=True)
        for i,tick in enumerate(ticks):
            inputs=pads[:tick];seq=tmp/'inputs.pad';seq.write_text(''.join('1 %d %d\n'%tuple(v) for v in inputs))
            snapshot=tmp/'window.bmp';dump=tmp/'scene.rgba'
            subprocess.run([viewer,'--assets',assets,'--mode','select','--match-replay',seq,'--snapshot',snapshot,'--dump',dump],check=True,stdout=subprocess.DEVNULL)
            pixels=dump.read_bytes()[8:]
            if i:assert sha256(pixels).hexdigest()==caps[i-1]['native_sha256']
            crop=(163,188,467,424);scene=Image.frombytes('RGBA',(640,448),pixels).convert('RGB');actual=Image.open(snapshot).convert('RGB')
            # These crops are below the HUD. Preserve the exact screen pixels
            # and positions from the public window in the entire upper row.
            assert actual.size[0]==640 and actual.crop(crop).tobytes()==scene.crop(crop).tobytes()
            body=subprocess.run([exe,assets,'1','1','1'],input=''.join('%d %d\n'%tuple(v) for v in inputs).encode(),check=True,capture_output=True)
            isolated=Image.frombytes('RGBA',(640,448),body.stdout).convert('RGB')
            left=28+(width+gap)*i;center=left+width//2
            draw.text((center,105),headings[i],font=font(24,True),fill=ink,anchor='ma')
            sheet.paste(actual.crop(crop),(left,145))
            # Anchor the isolated target horizontally by its own center so
            # pushback does not obscure the equivalence of first/last poses.
            from PIL import ImageChops
            bb=ImageChops.difference(isolated,Image.new('RGB',isolated.size,background)).getbbox();assert bb
            px=(bb[0]+bb[2])//2;fragment=isolated.crop((px-152,278,px+152,437))
            sheet.paste(fragment,(left,406));draw.text((center,582),times[i],font=font(22),fill=teal,anchor='ma')
    draw.line((28,621,1300,621),fill=(170,173,162));draw.text((28,638),'上排为实战截图局部，下排单独显示 P2。命中后生命从 200 降至 191；第 13 帧已画回蹲姿，第 16 帧才结束受击。',font=font(19),fill=muted)
    dest=OUT/'nakoruru-jump-light-crouch.png';sheet.save(dest,optimize=True)
    return dict(file=dest.name,sha256=digest(dest),pad_updates=ticks,width=sheet.width,height=sheet.height)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--viewer',type=Path,default=OUT/'native-viewer/ss6-viewer');ap.add_argument('--assets',type=Path,default=OUT/'native-viewer/assets');ap.add_argument('--replay',type=Path,default=BUILD/'ss6-match-replay');ap.add_argument('--figure',action='store_true');args=ap.parse_args()
    assert digest(SOURCE.parent/'SLPS_255.59')==SOURCE_HASH
    if args.figure:
        target=OUT/'selected-jump-light-validation.json';report=json.loads(target.read_text())
        report['figure']=figure(args.viewer,args.assets,args.replay,report);target.write_text(json.dumps(report,indent=2)+'\n');return
    with tempfile.TemporaryDirectory() as td:
        tmp=Path(td);cpp=tmp/'queue.cpp';exe=tmp/'queue';cpp.write_text(POSE_DRIVER)
        viewer=tmp/'viewer';replay=tmp/'replay';library=tmp/'runtime.a'
        for src,dest in ((args.viewer,viewer),(args.replay,replay),(LIB,library)):shutil.copy2(src,dest)
        subprocess.run(['c++','-std=c++20','-O2','-ffp-contract=off','-I',ROOT/'src',cpp,library,'-o',exe],check=True)
        jobs=[(exe,viewer,replay,args.assets,line,side,posture) for line in ((0,1),(1,0),(1,1),(2,2),(1,2),(2,1),(0,2),(2,0)) for side in (0,1)
              for posture in (('standing','entering_crouch','settled_crouch') if line[side]==0 else ('standing','settled_crouch'))]
        with ProcessPoolExecutor(max_workers=4) as pool:
            cases=[]
            for c in pool.map(check,jobs):cases.append(c);print(c['lineup'],c['attacker'],c['posture'],c['target_hp'],[f['visible_victim_pixels'] for f in c['captures']],flush=True)
        frames=[f for c in cases for f in c['captures']]
        report=dict(status='passed',cases=cases,pixel_frames=len(frames),minimum_visible_victim_pixels=min(f['visible_victim_pixels'] for f in frames),minimum_pose_change_pixels_during_first_record=min(f['pose_change_pixels'] for f in frames if f['record']==0),reused_recovery_frames=sum(f['source_reuses_preimpact_pose'] for f in frames),source_sha256=SOURCE_HASH,runtime_sha256=digest(library),viewer_sha256=digest(viewer),replay_sha256=digest(replay),scope='Both human pads select fighters and Ken spirits. Original contact collection, defense, hit and damage on the published native actors and boxes. Compare every on-disc standing or crouching hurt record with original 1207e8/122bc0/1208b0/123840, then compare the 640x448 original character/effect composition on the actual stage dump with the viewer. Visible victim pixels come from recomposition without the hurt body. Isolated pose-change pixels compare that target at the same position, camera, color and damage tint against its pre-impact ACT and record. The final Rimururu hurt record is also compared to every distinct settled idle or crouch drawing. Original hardware video output and stage production are outside this oracle.')
    target=OUT/'selected-jump-light-validation.json'
    if target.is_file():
        previous=json.loads(target.read_text());art=previous.get('figure')
        # Keep the existing contact sheet when its files and exact source
        # build still match. --figure can regenerate it for a new release.
        if art and all(previous.get(k)==report[k] for k in ('viewer_sha256','replay_sha256')):
            path=OUT/art['file']
            if path.is_file() and digest(path)==art['sha256']:report['figure']=art
    target.write_text(json.dumps(report,indent=2)+'\n');print(len(cases),'fights,',len(frames),'verified frames')

if __name__=='__main__':main()
