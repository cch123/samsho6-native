#!/usr/bin/env python3
"""Render the original HUD over real native match frames, then compare the packaged window."""
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import sys
import numpy as np
from PIL import Image
from validate_rage_gauge import original, draw, ASSETS, OUT, W, H

ROOT=Path(__file__).resolve().parents[2]
MATCH=ROOT/'work/ss6/build-native/ss6-match-replay'
PKG=OUT/'native-viewer'
# Immediately before/on/after the filling blow, both ends of the pulse,
# the next round's HUD reset, and the strict-below-zero expiry.
SAMPLES={500,560,570,874,875,876,877,890,900,944,1744,1745,2016,2017,2018}

def run(path,args,**kw):
    return subprocess.run([path,*args],capture_output=True,check=True,**kw)

def atlas(slot):
    data=np.frombuffer((ASSETS/f'obj{slot}_16.tex').read_bytes(),np.uint8)
    clut=data[-1024:].reshape(8,4,8,4)[:,[0,2,1,3],:,:].reshape(256,4)
    return data[:-1024].reshape(512,512),clut

def check(arguments):
    side,spirits,work,viewer,match,charge,assets=arguments
    ten=3 in spirits
    zan=(2 in spirits and not ten)
    work.mkdir()
    names=("rage","shin","zan","ten")
    args=["--p1-spirit",names[spirits[0]],"--p2-spirit",names[spirits[1]]]
    samples=SAMPLES if not spirits[side] else {500,570,1033,1034,1035,1040,1049,1088,1744,1745,2267,2268,2269}
    path=OUT/f'rage-round-carry-p{side+1}.replay'
    pads=[]
    for line in path.read_text().splitlines():
        n,a,b=map(int,line.split());pads.extend([f'1 {a} {b}\n']*n)
    if zan:
        # Both attacker orders use genuine incoming standing heavies. A
        # separate match reaches full using just the simultaneous A+B hold.
        samples=({500,506,507,590,674,675,676,677,692,710} if charge else
                 {500,558,620,874,875,876,892,1192,1193,1194,1243,1351,1352,1353,1743,1744,1745})
        if charge:
            hold='1 0 768\n' if side else '1 768 0\n'
            pads=['1 0 0\n']*500+[hold]*200+['1 0 0\n']*30
    if ten:
        forward=(128,64)[side];back=forward^192
        def pair(n,a=0,b=0):return (n,b,a) if side else (n,a,b)
        seq=[pair(500)]
        # HP-dependent duration and full-health 0/0 differ. The secondary
        # press after exhaustion must not reopen the gauge, including round two.
        if not charge:
            seq.extend([pair(65,0,back),pair(5),pair(1,0,1024),pair(88)]*3)
            seq.extend([pair(75,back,forward),pair(8)])
        seq.extend([pair(1,1792),pair(130)])
        if not charge and spirits[1-side]==1:
            seq.extend([pair(130,forward,back),pair(10),pair(1,1792)])
        seq.extend([pair(555),pair(1,1792),pair(90)])
        seq.extend([pair(65,0,back),pair(5),pair(1,0,1024),pair(88)]*8)
        seq.extend([pair(500),pair(1,1792),pair(5500)])
        pads=[f'1 {a} {b}\n' for n,a,b in seq for _ in range(n)]
        samples={500,len(pads)}
    rows=run(match,[assets,'--mode','versus','--rage-hud-fields',*args],input=''.join(pads[:max(samples)]),text=True).stdout.splitlines()
    if ten:
        next_round=next((i for i,line in enumerate(rows,1) if int(line.split()[45])==1 and line.split()[1]=='4'),None)
        assert next_round is not None,(spirits,charge,rows[-1])
        retry=next_round+20
        pads[next_round:next_round+60]=['1 0 0\n']*60
        pads[retry-1]='1 0 1792\n' if side else '1 1792 0\n'
        rows=run(match,[assets,'--mode','versus','--rage-hud-fields',*args],
                 input=''.join(pads[:next_round+60]),text=True).stdout.splitlines()
        samples={500,retry,retry+1,len(rows)}
        assert all(int(row.split()[23+11*side])==3 and row.split()[3+10*side:5+10*side]!=['1','36']
                   for row in rows[retry-1:]),(side,spirits,'second-round explosion')

        states=[int(line.split()[23+11*side]) for line in rows]
        assert states.count(2)>0 and states[-1]==3
        changes=[i+1 for i,(a,b) in enumerate(zip(states,states[1:]),1) if a!=b]
        assert len(changes)==2 and int(rows[-1].split()[45])>=1,(spirits,charge,changes,rows[-1])
        samples.update(t for event in changes for t in (event-1,event,event+1))
        samples.update((changes[0]-53,changes[1]+25))
        if not charge:samples.update((changes[0]-75,changes[0]+23))
        previous_round=0
        for i,line in enumerate(rows,1):
            r=line.split()
            if int(r[45])!=previous_round:
                samples.update((i-1,i,i+1));previous_round=int(r[45])
    p=original()
    for who,spirit in enumerate(spirits):
        p.write(0x45689c+who*0x30,spirit,4)
        p.write(p.read(0x132f598+4*who,4)+0x10c,spirit,4)
    atlases={2:atlas(1),10:atlas(2)}
    old=None;captures=[];fingerprint=hashlib.sha256();held=[False,False]
    battle=0x1d08000
    if zan or ten:
        p.write(0x4d3d00,battle,4)
        for who in (0,1):
            actor=p.read(0x132f598+4*who,4)
            p.write(actor,0x1d00000+who*0x1000,4)
            for off in (0x110,0xa24):p.write(actor+off,who,4)
    for tick,line in enumerate(rows,1):
        row=line.split()
        # The game awards new rage on contact after priority 20 has sampled.
        # A running priority-5 decay is visible to priority 20 in the same tick.
        for who in (0,1):
            base=23+11*who
            amount_state=row[base:base+2]
            if old and old[base]=='0' and old[10+(1-who)*10]!=row[10+(1-who)*10]:
                amount_state=old[base:base+2]
            actor=p.read(0x132f598+who*4,4)
            if not (zan or ten):
                for i,value in enumerate(amount_state):p.write(actor+0x120+4*i,int(value),4)
            elif old:
                # The preceding end-of-tick state includes hits, actor callbacks
                # and KO. Execute the actual priority-five gauge before the HUD
                # samples it, ahead of this tick's contact/critical-HP writes.
                for i,offset in enumerate((0x120,0x124,0x128,0x130,0x134,0x138,0x23c)):
                    p.write(actor+offset,int(old[base+i]),4)
                p.write(actor+0x194,int(old[3+10*who])|(int(old[4+10*who])<<16),4)
                active=bool(int(old[base+6])&0x10000)
                if active and not held[who]:p.write(actor+0x12c,40,4) # 14f1b0 on holding entry
                held[who]=active
                if int(old[50]) and int(old[46])==4 and int(old[48])<=0 and not int(old[49]):
                    p.write(battle,4,4);p.write(battle+8,int(old[47]),4)
                    p.run(0x11e760,[who],limit=200000)
                if ten and int(old[base])<2 and int(row[base])==2:
                    # World-4 completes after the gauge update, before the HUD.
                    # Derive its amount from the prior real actor HP via 11f248.
                    p.write(actor+0xa30,int(old[9+who*10]),4);p.run(0x11f248,[who])

        if old is None or old[-1]=='1':p.run(0x1be1a8,limit=100000)
        for at in (0x345178,0x378e08,0x3db8f8):p.write(at,0,4)
        if tick in samples:
            replay=work/'snapshot.pad';replay.write_text(''.join(pads[:tick]))
            scene=work/'scene.rgba';window=work/'window.bmp'
            run(viewer,['--assets',assets,'--mode','versus',*args,'--match-replay',replay,'--dump',scene,'--snapshot',window])
            raw=scene.read_bytes();assert struct.unpack_from('<II',raw)==(W,H)
            stage=np.frombuffer(raw[8:],np.uint8).reshape(H,W,4).copy()
            packets=draw(p,stage,atlases)
            full=Image.open(window).convert('RGBA');actual=np.asarray(full)[314:H]
            np.testing.assert_array_equal(stage[314:],actual,err_msg=f'P{side+1} update {tick}')
            fingerprint.update(actual.tobytes())
            if zan and not side and spirits[1]==0:
                filename=({620:'zan-gauge.png',1243:'zan-critical.png'} if not charge else {676:'zan-charge.png'}).get(tick)
                if filename:full.convert('RGB').save(work/filename)
            if ten and side==0 and spirits[1]==0 and not charge:
                filename={changes[0]-75:'ten-gauge.png',changes[0]+23:'ten-explosion.png',changes[1]+25:'ten-spent.png'}.get(tick)
                if filename:full.convert('RGB').save(work/filename)
            captures.append(dict(update=tick,packets=packets,actor_rage=int(row[24+11*side]),
                                 displayed_pixels=int(row[52+6*side]),pulse=int(row[53+6*side]),life=int(row[9+10*side]),decay=int(row[25+11*side])))
        else:
            for addr in (0x1c0d08,0x1c02f8,0x1c0920):p.run(addr,limit=200000)
        for who in (0,1):
            offset=51+6*who
            expected_width=p.read(0x132f3e0+who*0x98,4)
            assert int(row[offset+1])==expected_width,(charge,spirits,tick,who,row[offset:offset+6],expected_width)
            assert int(row[offset+2])==p.read(0x132f538+4*who,4),(tick,who)
        old=row
    if zan:
        index={c['update']:c for c in captures}
        if charge:
            assert index[675]['actor_rage']<47104 and index[676]['actor_rage']==47104 and index[676]['life']==200
        else:
            assert 0<index[1193]['life']<=20 and index[1193]['decay']==0 and index[1243]['actor_rage']==47104
            assert index[1352]['life']==0 and index[1352]['decay']==98
            assert index[1744]['actor_rage']==index[1745]['displayed_pixels']==0
    if ten:
        assert all(int(rows[t-1].split()[23+11*side])==3 for t in samples if t>=changes[1])
        # Round index and HP both change after the KO, while state 3 persists.
        assert any(int(row.split()[45])==1 and int(row.split()[9+10*side])==200 for row in rows)
    return dict(raging_player=side+1,spirits=spirits,manual_charge=charge,rage_updates=len(rows),captures=captures,final_pixel_digest=fingerprint.hexdigest())

if __name__=='__main__':
    with tempfile.TemporaryDirectory() as tmp:
        work=Path(tmp);viewer=work/'ss6-viewer';match=work/'ss6-match-replay'
        staging='--staging' in sys.argv;zan='--zan' in sys.argv;ten='--ten' in sys.argv
        shutil.copy2((MATCH.parent if staging else PKG)/'ss6-viewer',viewer);shutil.copy2(MATCH,match)
        digest=hashlib.sha256(viewer.read_bytes()).hexdigest()
        cases=[(0,(0,0)),(1,(0,0)),(0,(1,0)),(1,(0,1)),(1,(1,1))]
        cases=([(0,(2,0)),(1,(0,2)),(0,(2,1)),(1,(1,2)),(1,(2,2))] if zan else cases)
        cases=[(*c,False) for c in cases]+([(0,(2,0),True),(1,(1,2),True)] if zan else [])
        if ten:
            cases=[(side,spirits,False) for side in (0,1) for other in range(4)
                   for spirits in [((other,3) if side else (3,other))]]
            cases.extend([(0,(3,0),True),(1,(1,3),True)])
        with ProcessPoolExecutor(max_workers=4) as pool:
            reports=list(pool.map(check,[(side,spirits,work/f'case-{n}',viewer,match,charge,ASSETS if staging else PKG/'assets')
                                         for n,(side,spirits,charge) in enumerate(cases)]))
        if not staging and (ten or zan):
            for shot in work.glob('case-*/ten-*.png' if ten else 'case-*/zan-*.png'):shutil.copyfile(shot,OUT/shot.name)
    result=dict(status='passed',source_sha256=hashlib.sha256((ASSETS.parent/'SLPS_255.59').read_bytes()).hexdigest(),
                viewer_sha256=digest,
                updates=sum(r["rage_updates"] for r in reports),window_frames=sum(len(r['captures']) for r in reports),sides=reports,
                scope='Real versus inputs through round two. Original Japanese HUD state and textured drawing over the identical native stage scene compared with packaged SDL framebuffer rows 314..447. Software reference, no console capture.')
    if not staging:(OUT/('ten-live-hud-validation.json' if ten else 'zan-live-hud-validation.json' if zan else 'live_rage_hud_validation.json')).write_text(json.dumps(result,indent=2)+'\n')
    print(result['updates'],'HUD updates;',result['window_frames'],'packaged window frames')
