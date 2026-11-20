#!/usr/bin/env python3
"""Compare Hanzō's callbacks in real, publicly selected fights with SLPS_255.59."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from hashlib import sha256
from itertools import groupby
import io
import json
import struct
from pathlib import Path
import subprocess
import tempfile

from validate_dash_motion import ELF, PIN
from validate_selected_combat import BUILD, ROOT, prefix
from validate_weapon_handling import setup

RES=ROOT/'work/ss6/extracted/resources'
OUT=ROOT/'outputs/ss6-feasibility/hanzo-special-validation.json'

def pads(side,state,variant):
    pair=lambda x,y=0:(y,x) if side else (x,y)
    f,b=(128,64)[side],(64,128)[side]
    seq=prefix((0,3) if side else (3,0))
    if state==90:
        for tick in (211,222,233):seq[tick-1][side]=128

    elif state==91:
        for tick in (211,228):seq[tick-1][side]=128
    else:seq[229]=[128,128]
    if variant=='unarmed':seq += [pair(f|8)]+[pair(0)]*125
    walk=-70 if variant=='distance' else 43
    if 69<=state<=71 and variant!='distance':walk=0
    if 75<=state<=77 and variant!='distance':walk=17
    if state==88 and variant!='distance':walk=26
    seq+= [(64,128) if walk<0 else (128,64)]*abs(walk)+[pair(0)]*10
    if state in (86,87,89):seq += [pair(0)]*25
    if state==90:seq += [pair(768)]*420+[pair(0)]*22
    if 69<=state<=71:seq += [pair(16)]+[pair(0)]*7
    if 75<=state<=77:seq += [pair(f),pair(0)]+[pair(f)]*16
    if state==78:seq += [pair(16,16)]+[pair(0)]*11
    start=len(seq)
    buttons=(256,512,1024,2048)
    if state<=66:keys=[32,b|32,b|buttons[state-64]]
    elif state<=68:keys=[f,f|32,32,b|32|(2304 if state==67 else 5120)]
    elif state<=71:keys=[32,f|32,f|buttons[state-69]]
    elif state<=77:keys=[f,32,f|32|buttons[(state-72)%3]]
    elif state==78:keys=[f|2048]
    elif state<=81:keys=[0,32,0,32|buttons[state-79]]
    elif state<=85:keys=[b,32,b|32|buttons[state-82]]
    elif state in (86,87,89):keys=[f,0,b,0,f,0,b,0,f,0,b,32|{86:2304,87:5120,89:3584}[state]]
    elif state==88:keys=[0,32,0,32,0,32|4352]
    elif state==90:keys=[32,f|32,f|768]
    else:keys=[32|b,f,32|f,32,32|b,b,32|f|1536]
    defender=(f|32 if state in (68,87) else f) if variant=='guard' else 0
    seq += [pair(key,defender) for key in keys+[0]*(710 if state in (89,90,91) else 290)]
    if state in (86,87):seq[start-5]=pair(0,1024)
    if state==88 and variant!='distance':
        for t in range(start,start+9):seq[t]=pair(keys[t-start] if t<start+len(keys) else 0)
        for t in range(start+9,start+34):seq[t]=pair(0,b)
    return seq,start

class Original:
    def __init__(self,side):
        self.src,_=setup(side,3);o=self.src;self.p=p=o.p
        stage=p.run(0x140040)[0];self.ctx=0x1dc0000
        p.write(self.ctx,o.a,4);p.write(self.ctx+4,o.other,4)
        p.write(0x169810,0x03e00008,4);p.write(0x169814,0,4)
        a,b=o.a,o.o
        self.fields=[(a+i,1 if i==0x19a else 4) for i in (0x194,0x23c,0x248,0x19a,0x18c,0xa3c,*range(0x260,0x27c,4),*range(0x28c,0x2c0,4))]
        self.fields += [(b+i,4) for i in (0x24,0x104,0x108,0x38,0xc0,0x3c,0x134,0x40,0x44,0x1040,*range(0x4c,0x64,4))]
        self.fields += [(a+0x2c4+i,4) for i in (0xe0,0xfc,0x160,0x168)]
        self.fields += [(o.other+0x23c,4),(o.b+0x108,4),(0x46a948,4),(0x3ebf30+2*512,2),(a+0x190,2),(a+0x192,2),
                        (b+0x128,4),(a+0x1b0+17*4,4),(a+0x1b0+18*4,4),(o.b+0x138,4)]
        self.fields += [(stage+off,4) for off in (0x10,0x14,0x1c)]
        target=p.read(o.other,4);self.fields += [(target+0x40,4),(target+0x44,4),(a+0x24c,1)]
        self.calls=Counter();self.instructions=0
    def color(self,values):
        a,b=self.src.a,self.src.o;p=self.p
        offsets=[(a+0xa28,4),(a+0x10c,4),(a+0x120,4),(a+0x194,4),(b+0x24,4),
                 (a+0xa2c,4),(a+0x1ac,4),(b+0x38,4),(b+0x8c,4),(b+0x20,4)]
        timers=[(a+0x1b0+4*i,4) for i in range(35)];before=offsets+timers
        for (addr,size),value in zip(before,values):p.write(addr,value,size)
        _,count=p.run(0x14b190,[a],limit=10000);self.instructions+=count;self.calls['0x14b190']+=1
        assert [p.read(addr,size) for addr,size in offsets[-3:]+timers]==values[len(before):]
    def compare(self,tick,values):
        p=self.p;n=len(self.fields);start,end=values[:n],values[n+1:]
        assert len(start)==len(end)==n
        for (addr,size),v in zip(self.fields,start):p.write(addr,v,size)
        pc=start[6];p.write(self.ctx+8,start[8],4);recover=[]
        _,ins=p.run(pc,[self.ctx],limit=500000,observe=lambda ad:recover.append(1) if ad==0x169810 else None)
        self.instructions+=ins;self.calls[hex(pc)]+=1
        assert bool(recover)==bool(values[n]),(tick,hex(pc),'recovery',recover,values[n])
        wrong=[(i,hex(ad),hex(p.read(ad,size)),hex(v)) for i,((ad,size),v) in enumerate(zip(self.fields,end)) if p.read(ad,size)!=v&((1<<(size*8))-1)]
        assert not wrong,(tick,hex(pc),wrong)

def check(job):
    exe,assets,side,state,variant=job;seq,start=pads(side,state,variant)
    args=[exe,assets,str(start)];r=subprocess.run(args,input=''.join(f'{a} {b}\n' for a,b in seq),text=True,capture_output=True)
    src=Original(side);colors=[];states=[];opponent=[];health=[];hit=[];guard=[];actions=[];armed_during=[];public=[];target_weapon=[]
    for line in r.stdout.splitlines():
        if not line or not line[0] in 'FCV':continue
        tag,*ls=line.split();v=list(map(int,ls));tick=v[0]
        if tag=='C' and v[1]==side and tick>=start and len(v)>100:src.compare(tick,v[2:])
        if tag=='V' and tick>=start:
            src.color(v[1:])
        if tag=='F' and tick>=start:
            a=v[1+10*side:11+10*side];t=v[1+10*(1-side):11+10*(1-side)]
            colors.append((tick,v[21+2*side]>>24,v[22+2*side]));states.append(a[2:4]);opponent.append(t[2:4]);health.append(t[6]);target_weapon.append(bool(t[9]&4096));hit.append(a[7]);guard.append(a[8])
            public.append((tick,a[2:9],t[2:9]))
            if a[2:4]==[1,state]:actions.append(a[4]);armed_during.append(a[9])
    assert r.returncode==0,(side,state,variant,r.stderr,[k for k,_ in groupby(states)])
    # A far air throw becomes a kick; a reversal cannot activate if the
    # other player's heavy slash never reached the fighter in the first place.
    rejected=(variant=='distance' and state in (78,86,87)) or (variant=='unarmed' and state==90)
    assert ([1,state] in states)!=rejected,(side,state,variant,[k for k,_ in groupby(states)])
    if variant=='unarmed':assert not any(r&4096 for r in armed_during),(side,state,variant)
    if rejected:assert health[-1]==200 and not src.calls
    elif state!=78:assert src.calls['0x1ee4a0']==1,(side,state,variant)
    assert [0,0] in states[-20:] or [0,1] in states[-20:],(side,state,variant,states[-1])

    replay=subprocess.run([BUILD/'ss6-match-replay',assets,'--mode','select'],
                          input=''.join(f'1 {x} {y}\n' for x,y in seq),text=True,capture_output=True,check=True)
    for (tick,own,target),line in zip(public,replay.stdout.splitlines()[start-1:],strict=True):
        vals=line.split()
        for seat,want in ((side,own),(1-side,target)):
            assert want==[int(vals[3+seat*10+i]) for i in (0,1,2,3,6,7,8)],(tick,side,state,variant)
    if variant=='near':
        expected=(180,180,180,177,174,196,188,180,178,169,151,187,183,172,186,200,200,200,200,200,200,200,177,174,197,200,160,136)
        assert health[-1]==expected[state-64],(side,state,health[-1])
    if variant=='guard' and (64<=state<=71 or state in (86,87,88,90)):
        assert guard[-1]>0 and hit[-1]==0,(side,state,variant,guard[-1],hit[-1])
    if state==90:
        assert all(target_weapon) if variant!='near' else not target_weapon[-1] and [2,62] in opponent
    dropped_tick=start+target_weapon.index(False) if False in target_weapon else None
    conceal=None
    if state==89:
        nonzero=[t for t,alpha,timer in colors if timer]
        hidden=[t for t,alpha,timer in colors if alpha==0]
        assert nonzero and hidden and colors[-1][1:]==(255,0),(side,variant,colors[-1])
        conceal=dict(timer_first=nonzero[0],timer_last=nonzero[-1],transparent_first=hidden[0],transparent_last=hidden[-1],
                     fully_visible=next(t for t,alpha,_ in colors if t>hidden[-1] and alpha==255))
    return dict(seat=side+1,state=state,variant=variant,concealment=conceal,target_lost_weapon=dropped_tick,entry=None if rejected else start+states.index([1,state]),actions=[a for a,_ in groupby(actions)],
                target_states=[a for a,_ in groupby(opponent)],target_hp=health[-1],hits=hit[-1],guards=guard[-1],
                callbacks=src.calls,original_instructions=src.instructions)

def build(directory):
    exe=directory/'fight';obj=directory/'cast.o';cxx=['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src']
    subprocess.run([*cxx,'-DupdateHanzoSpecial=tracedCast','-c',ROOT/'src/hanzo_special.cpp','-o',obj],check=True)
    color=directory/'color.o'
    subprocess.run([*cxx,'-DupdateActorColor=tracedColor','-c',ROOT/'src/actor_color.cpp','-o',color],check=True)
    subprocess.run([*cxx,ROOT/'work/ss6/hanzo_special_trace.cpp',obj,color,BUILD/'libss6-runtime.a','-o',exe],check=True)
    return exe

def original_notices(exe,assets,directory,inputs,samples):
    # The dropped sword has its own priority-20 player marker. Replay the
    # original notice task from before the discard, retaining its animation
    # clock independently of the body renderer and its hitstop.
    from validate_stage_item_notices import original
    p=original();p.run(0x1b5b08,limit=100000);p.write(0x4c3808,3,4)
    battle=0x1c30000;p.write(0x4d3d00,battle,4);p.memory[battle:battle+0x500]=bytes(0x500)
    data=''.join(f'{a} {b} {int(t>=1250)}\n' for t,(a,b) in enumerate(inputs[:max(samples)],1))
    run=subprocess.run([exe,assets,directory],text=True,input=data,capture_output=True,check=True)
    pictures={}
    for line in run.stdout.splitlines():
        row=list(map(float,line.split()));tick,delta,x0,x1=map(int,row[:4])
        for addr,value in zip((0x4a2a58,0x4a2a5c,0x4a2a60,0x4a2a6c,0x4a2a68),row[4:9]):struct.pack_into('<f',p.memory,addr,value)
        struct.pack_into('<f',p.memory,0x4a2a64,-160)
        for i,x in enumerate((x0,x1)):
            task=0x1ba0000+i*0x1000;body=task+0x100
            p.write(battle+0x29c+i*0x108,task if x>=0 else 0,4);p.write(task+28,body,4)
            p.write(body+0xcc,4,4);struct.pack_into('<2f',p.memory,body+0x40,x,0)
        p.write(0x46a908,delta,4);p.write(0x3db8f4,100,4)
        for addr in (0x345178,0x378e08,0x3db8f8):p.write(addr,0,4)
        vertices=[]
        def observe(pc):
            if pc==0x108464:
                ptr=p.read(p.registers[19]+24,4)
                vertices.append([struct.unpack_from('<5fI',p.memory,ptr+24*i) for i in range(4)])
        p.run(0x1b5e30,limit=500000,observe=observe)
        if tick in samples:
            assert len(vertices)==int(row[18])==1
            q=vertices[0];raw=[*q[0][:2],*q[3][:2],q[0][3],q[0][4],q[0][5]>>24]
            assert all(abs(a-b)<1e-5 for a,b in zip(raw,row[-7:],strict=True)),(tick,raw,row[-7:])
            pictures[tick]=vertices
    return pictures

def verify_pixels(directory,assets,viewer,results):
    from validate_native_scene import compare, fixture
    from validate_jump_light_presentation import verify_queue
    from validate_selected_jump_light import POSE_DRIVER
    from validate_stage_item_notice_scene import DRIVER as NOTICE_INPUTS
    from validate_stage_item_notices import atlas, raster
    import numpy as np
    # The flat diagnostic image is the fighter/effect pass. The separately
    # verified notice is added to the real stage only, where it is visible.
    reference=POSE_DRIVER.replace('scene.paint(m,rgba,[&](const auto&){fill({67,29,71,255});});',
        'scene.paint(q,{b.camera,{b.gauges.words910[2],b.gauges.words910[3]},b.gauges.focus46a948,0},'
        'b.paletteState,b.gauges.paletteTones,rgba,[&](const auto&){fill({67,29,71,255});});')
    source=directory/'draw.cpp';source.write_text(reference)
    exe=directory/'draw'
    subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',source,BUILD/'libss6-runtime.a','-o',exe],check=True)
    ns=directory/'notice-input.cpp';ns.write_text(NOTICE_INPUTS.replace('session(argv[1],99,','session(argv[1],-1,'))
    notice=directory/'notice-input';subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',ns,BUILD/'libss6-runtime.a','-o',notice],check=True)
    texture=atlas()[10];report=[]
    for side,state in ((0,89),(1,89),(0,86),(1,86)):
        variant='near' if state==89 else 'unarmed'
        seq,_=pads(side,state,variant);lineup=(0,3) if side else (3,0)
        original=fixture((*lineup,51));stats=Counter()
        for bank,name in enumerate(('01HitFlash.bin','02Guard.bin','03etc.bin')):
            chunk=(assets/name).read_bytes();at=0x4a4810+bank*0x3da0;original.memory[at:at+len(chunk)]=chunk
        case=next(r for r in results if r['state']==state and r['variant']==variant and r['seat']==side+1)
        if state==89:
            events=case['concealment']
            sample_ticks=(events['timer_first']-2,events['timer_first']+30,events['transparent_last']+7,events['fully_visible']+1)
        else:
            rows=subprocess.run([BUILD/'ss6-match-replay',assets,'--mode','select'],capture_output=True,check=True,text=True,
                                input=''.join(f'1 {x} {y}\n' for x,y in seq)).stdout.splitlines()
            sparse=[tick for tick,row in enumerate(rows,1) if int(row.split()[5+10*side])==693]
            assert len(sparse)>=13
            sample_ticks=(sparse[0],sparse[-1],sparse[-1]+1)
        markers=original_notices(notice,assets,directory,seq,sample_ticks) if state==86 else {}
        for tick in sample_ticks:
            inputs=seq[:tick];packet=subprocess.run([exe,assets,*map(str,lineup)],capture_output=True,check=True,
                    input=''.join(f'{x} {y}\n' for x,y in inputs).encode()).stdout
            data=io.BytesIO(packet);n,=struct.unpack('<I',data.read(4));rows=[data.read(328) for _ in range(n)]
            verify_queue(original,rows,data.getbuffer()[data.tell():])
            body=next(r for raw in rows if (r:=struct.unpack('<82I',raw))[81]==0 and r[3]==side and r[51]==side)
            replay=directory/'hide.pad';replay.write_text(''.join(f'1 {x} {y}\n' for x,y in inputs))
            frame=directory/'frame.rgba';stage=directory/'stage.rgba'
            subprocess.run([viewer,'--assets',assets,'--mode','select','--match-replay',replay,'--dump',frame,'--dump-stage',stage],
                           stdout=subprocess.DEVNULL,check=True)
            visible={'slot':side,'action':body[9],'steps':[]}
            def paint_notice(pixels):
                return raster(markers[tick],texture,np.frombuffer(pixels,dtype=np.uint8).reshape(448,640,4)).tobytes()
            notice_depth=min(v[2] for quad in markers[tick] for v in quad) if tick in markers else None
            compare(original,data,stats,f'hanzo-{state}-{side}-{tick}',frame.read_bytes()[8:],visible,stage.read_bytes()[8:],
                    final_overlay=(notice_depth,paint_notice) if notice_depth is not None else None)
            pose=subprocess.run([exe,assets,*map(str,lineup),str(side)],capture_output=True,check=True,
                                input=''.join(f'{x} {y}\n' for x,y in inputs).encode()).stdout
            background=int.from_bytes(bytes((235,232,223,255)),'little')
            sprite_pixels=sum(pixel!=background for pixel in memoryview(pose).cast('I'))
            alpha=body[0x8c//4]>>24
            if state==89:assert (alpha==0)==(sprite_pixels==0)
            else:assert body[9]==(685 if tick==sample_ticks[-1] else 693) and sprite_pixels>0
            report.append(dict(seat=side+1,state=state,tick=tick,action=body[9],record=body[10],alpha=alpha,
                               pixels_with_shadow=visible['visible_pixels'],sprite_pixels=sprite_pixels,notice_depth=notice_depth))
    return report

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--case',nargs=3);ap.add_argument('--assets',type=Path,default=RES);ap.add_argument('--viewer',type=Path,default=BUILD/'ss6-viewer');args=ap.parse_args()
    release=(args.viewer,BUILD/'ss6-match-replay',BUILD/'libss6-runtime.a')
    hashes=[sha256(p.read_bytes()).hexdigest() for p in release]
    with tempfile.TemporaryDirectory() as tmp:
        exe=build(Path(tmp))
        scenarios=[(p,s,v) for p in (0,1) for s in range(64,92) for v in ('near','guard','distance')]
        scenarios += [(side,state,'unarmed') for side in (0,1) for state in range(64,92)]
        if args.case:scenarios=[(int(args.case[0]),int(args.case[1]),args.case[2])]
        with ProcessPoolExecutor(4) as pool:results=list(pool.map(check,[(exe,args.assets,*c) for c in scenarios]))
        pixels=[] if args.case else verify_pixels(Path(tmp),args.assets,args.viewer,results)
    if args.case:print(results);return
    assert sha256(ELF.read_bytes()).hexdigest()==PIN and hashes==[sha256(p.read_bytes()).hexdigest() for p in release]
    report=dict(status='passed',elf_sha256=PIN,viewer_sha256=hashes[0],replay_sha256=hashes[1],runtime_sha256=hashes[2],
                scenarios=len(results),distinct_slots=sorted({r['state'] for r in results if r['entry'] is not None}),
                original_callback_visits=sum(sum(r['callbacks'].values()) for r in results),
                original_instructions=sum(r['original_instructions'] for r in results),source_gs_frames=pixels,cases=results)
    OUT.write_text(json.dumps(report,indent=2)+'\n');print(len(results),'fights')
if __name__=='__main__':main()
