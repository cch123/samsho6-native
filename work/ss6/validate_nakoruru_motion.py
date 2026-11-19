#!/usr/bin/env python3
"""Selected 01/00 human inputs against the original Nakoruru movement and air attack callbacks."""
from concurrent.futures import ProcessPoolExecutor
from hashlib import sha256
import json
import struct
from validate_dash_motion import Original
from validate_haohmaru_special import run_native, ROOT, ELF, BUILD
from validate_selected_combat import prefix
from validate_weapon_handling import setup as weapon_fixture


def measure(test):
    side,name=test
    f,b=((128,64),(64,128))[side]
    lineup=(1-side,side)
    pre=prefix(lineup);pre[229]=[128,128]
    pack=lambda key:(0,key) if side else (key,0)
    if name.startswith('wall'):
        pre+= [pack(b)]*120+[pack(0)]*15
        pads=[16|b]+[0]*10+[f|(16 if name=='wall-high' else 32)]*3+[0]*70
    elif name.startswith('421-'):
        strength={'421-A':256,'421-B':512,'421-C':1024}[name]
        pads=[b,32,32|b|strength]+[0]*102
    elif name=='run':pads=[0,f,0,f]+[f]*14+[0]*28
    elif name=='backstep':pads=[0,b,0,b]+[0]*32
    elif name=='jump-heavy':pads=[16]+[0]*22+[1024]+[0]*48
    else:pads=[16|{'up':0,'forward':f,'back':b}[name]]+[0]*68
    args=['1 %d %d'%tuple(k) for k in pre]+['1 %d %d'%pack(k) for k in pads]
    rows=run_native('ss6-match-replay',args,'--mode','select','--wall-fields')[-(1+len(pads)):]
    original=Original(side,1);p,a,o=original.p,original.a,original.o
    source=23+26*side;target=23+26*(side^1);base=3+side*10
    # The isolated actor uses the same camera and starting anchors as the
    # public battle. Original ACTs integrate all vertical velocity/height.
    p.write(o+0x40,int(rows[0][source]),4);p.write(o+0x1040,int(rows[0][target]),4)
    stage,_=p.run(0x140040);acts=[];states=[]
    for tick,(held,prev,row) in enumerate(zip(pads,rows,rows[1:])):
        p.write(stage+0x10,int(row[129]),4);p.write(stage+0x14,int(row[130]),4)
        p.write(o+0x40,int(prev[source]),4);p.write(o+0x1040,int(prev[target]),4)
        ref=original.frame(held)
        got=(int(row[base+1])<<16|int(row[base]),int(row[base+2]),int(row[base+3]),int(row[source+1]),int(row[source+2])&0x80000)
        want=(ref[0],ref[54],ref[55],ref[69],ref[58]&0x80000)
        if got[1]==0 and want[1]==0:
            # Idle is already running at the end of character selection.
            want=(want[0],want[1],got[2],want[3],want[4])
        assert want==got,(side,name,tick,hex(held),want,got)
        if not acts or got[1]!=acts[-1]:acts.append(got[1])
        if not states or got[0]!=states[-1]:states.append(got[0])
    required={'up':{14,16,26},'forward':{18,20,26},'back':{22,24,26},'run':{28,34},'backstep':{36},'jump-heavy':{211},
              'wall-high':{38,40},'wall-low':{38,42},'421-A':{554},'421-B':{555},'421-C':{556}}[name]
    assert required<=set(acts),(side,name,acts)
    return dict(player=side+1,input=name,frames=len(pads),actions=acts,states=states,original_instructions=original.instructions)


def weapon_case(side):
    lineup=(1-side,side);pre=prefix(lineup);pre[229]=[128,128]
    # Unlike Haohmaru, her 16fe20 discard offsets are (0,0). She can
    # retrieve the grounded weapon without moving after the discard ends.
    pads=[(128,64)[side]|8]+[0]*119+[256]+[0]*70+[1024]+[0]*65
    log=['1 %d %d'%tuple(k) for k in pre]+['1 %d %d'%((0,k) if side else (k,0)) for k in pads]
    rows=run_native('ss6-match-replay',log,'--mode','select','--shin-fields')[-len(pads):]
    oracle,registry=weapon_fixture(side,1);p,a,o=oracle.p,oracle.a,oracle.o
    base=3+10*side;source=23+26*side;fields=129+2*side
    p.write(o+0x40,int(rows[0][source]),4);p.write(o+0x1040,int(rows[0][23+26*(side^1)]),4)
    first=None;acts=[]
    for tick,(word,row) in enumerate(zip(pads,rows)):
        oracle.run(0x147028,registry,48);ref=oracle.frame(word)
        oracle.run(0x146ef8,registry,48);oracle.run(0x1207d8);oracle.run(0x1470a8,registry,48)
        original=[p.read(p.read(task+28,4)+off,4) for task in struct.unpack_from('<48I',p.memory,registry)
                  if task and p.read(p.read(task+28,4)+0xcc,4)==4 for off in (0x24,0x28,0x40,0x44,0x104,0x108)]
        count=int(row[fields+1]);got=list(map(int,row[fields+2:fields+2+6*count]));assert got==original,(side,tick,original,got)
        assert (ref[0],ref[54],ref[55],ref[5]&4096)==(int(row[base+1])<<16|int(row[base]),int(row[base+2]),int(row[base+3]),int(row[source+5])&4096),(side,tick)
        if original and first is None:first=tick
        if not acts or acts[-1]!=ref[54]:acts.append(ref[54])
    assert acts==[135,1,136,0,190,0] and first is not None,(side,acts,first)
    return dict(player=side+1,input='discard-pickup-heavy',frames=len(pads),actions=acts,first_grounded_weapon=first+1,original_instructions=oracle.instructions)

def main():
    tests=[(side,name) for side in (0,1) for name in ('up','forward','back','jump-heavy','run','backstep','wall-high','wall-low','421-A','421-B','421-C')]
    with ProcessPoolExecutor(max_workers=4) as pool:
        rows=[]
        for row in pool.map(measure,tests):rows.append(row);print(row['player'],row['input'],row['actions'],flush=True)
        for row in pool.map(weapon_case,(0,1)):rows.append(row);print(row['player'],row['input'],row['actions'],flush=True)
    result=dict(status='passed',cases=rows,frames=sum(r['frames'] for r in rows),original_instructions=sum(r['original_instructions'] for r in rows),
                elf_sha256=sha256(ELF.read_bytes()).hexdigest(),replay_sha256=sha256((BUILD/'ss6-match-replay').read_bytes()).hexdigest(),
                scope='Actual public selection and two human pads versus Japanese original 1495e8/149d08, ACT and movement passes. Compare every actor state, moving ACT/step, height bits and facing. The source fixture uses the native horizontal anchors and stage bounds to isolate actor movement callbacks. Both resource01 wall-rebound routes and three strengths of the 421 special include both seat assignments.')
    (ROOT/'outputs/ss6-feasibility/nakoruru_motion_validation.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':main()
