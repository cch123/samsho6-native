"""Run Japanese collection, paired throw, scripted record and strike logic on real match geometry."""
import struct
import subprocess
from validate_nakoruru_combat import MixedContactOracle
from validate_finishing_blow import ACTORS, OBJECTS, QUEUE, CHILD, stats
from validate_input_lifecycle import Boundary


def contact_trace(replay, assets, pads, start, side, eagles, outcome, spirit):
    live=subprocess.run([replay,assets,'--mode','select','--finish-fields'],
                        input=''.join(f'1 {x} {y}\n' for x,y in pads),text=True,capture_output=True,check=True)
    rows=[r.split() for r in live.stdout.splitlines()]
    oracle=MixedContactOracle((1-side,side));p=oracle.probe
    aid,act,jdg=oracle.banks[side];victim=side^1
    # The original logging used by 1551c0 has its own scratch area,
    # distinct from compact JDG fixtures created for the two bodies.
    stdout=p.read(p.read(0x5d1bf8,4)+8,4)
    p.write(stdout,0x19e0000,4);p.write(stdout+16,0x19e0000,4)
    p.memory[0x17c0000:0x17c0000+len(jdg)]=jdg
    f=3+10*side;d=3+10*victim;result=[]
    for i in range(start,len(rows)):
        prev,now=rows[i-1:i+1];before,after=map(int,(prev[d+6],now[d+6]))
        if before<=0 or after>before:continue
        captured=prev[d+1]!='80' and now[d+1]=='80'
        changes=[int(now[k])-int(prev[k]) for k in (f+7,f+8)]
        if not captured and before==after and changes==[0,0]:continue
        for who in range(2):
            oracle.install_player(prev,who)
            a=ACTORS+0xf2c*who;c=stats(who)
            # Characters and sword spirits are selected through their public menus.
            system=spirit if who==side else 5
            p.write(a+0x10c,system,4)
            for n,x in enumerate((12,24,28,32)):p.write(c+x,int(prev[75+4*who+n]),4)
        words=eagles[i];struct.pack_into('<80I',p.memory,CHILD,*words)
        src=OBJECTS[side];dst=OBJECTS[victim];target=ACTORS+0xf2c*victim
        p.write(ACTORS+0xf2c*side+4,CHILD,4)
        # Both owner and eagle use the same original JDG bank, with separate
        # ACT reference lists. install_player's compact references only apply
        # to the opposing fighter after replacing the owner's judgment bank.
        p.write(0x4751e0+side*4,0x17c0000,4)
        for who,action,step,refs in ((src,*map(int,prev[f+2:f+4]),0x17a0000),(CHILD,words[9],words[10],0x17a0100)):
            first=struct.unpack_from('<h',aid,action*2)[0];off=60*(first+step)
            p.memory[refs:refs+16]=act[off+14:off+30];p.write(who+0xbc,refs,4)
        if before>after and changes==[0,0]:
            action,step=map(int,prev[f+2:f+4]);first=struct.unpack_from('<h',aid,action*2)[0]
            base=act[60*(first+step)+2];assert base,(i,side,action,step)
            p.write(src+0xd8,base,4);p.run(0x154120,[src],limit=300000)
            damage=p.read(target+0xa38,4)
            assert after==max(before-damage,0),(i,side,base,damage,before,after)
            result.append(dict(tick=i+1,body=action,record=step,script_base=base,damage=damage,remaining=after))
            continue
        p.write(0x12d2698,0,4)
        for one,two in ((src,dst),(dst,src),(CHILD,dst),(dst,CHILD)):
            p.run(0x1536e8,[one,two],limit=50000)
        p.run(0x1544a0,limit=50000)
        found=False
        for n in range(p.read(0x12d2698,4)):
            event=QUEUE+108*n;route=p.read(event,4);obj=p.read(event+0x40,4)
            if obj not in (src,CHILD) or p.read(event+0x68,4)!=dst or route!=(4 if captured else 7):continue
            raw=p.read(event+0x20,4);item=dict(tick=i+1,route=route,raw=raw,source='eagle' if obj==CHILD else 'body',
                                               action=p.read(obj+0x24,4),record=p.read(obj+0x28,4),remaining=after)
            if captured:
                p.run(0x1551c0,[event],limit=300000)
                assert p.read(target+0x192,2)==int(now[d+1])==80,(item,now[d:d+3])
            else:
                guard=bool(changes[1]);defense=p.run(0x155850,[event])[0]
                assert bool(defense)==guard,(i,side,changes,defense,raw)
                stop=Boundary(0x155e90 if guard else 0x155bb8)
                p.run(0x155d50 if guard else 0x155a88,[event,0,defense],limit=250000,stop_before=stop);assert stop.stopped
                if guard:p.run(0x14d5a0,[target,obj,defense,p.read(event+12,4)])
                elif raw>=36:p.run(0x156538,[event])
                expected=p.read(target+0x192,2);damage=p.read(target+0xa38,4)
                final=int(now[d+1])
                if raw==15:assert expected==65535 and now[d:d+3]==prev[d:d+3],(item,expected,now[d:d+3])
                elif raw==40:assert expected==84 and final==71,(item,expected,final)
                else:assert expected==final,(item,expected,final)
                assert after==max(0,before-damage),(i,side,raw,p.read(event+16,4),before,damage,after)
                item.update(defense=defense,damage=damage,requested=None if expected==65535 else expected)
            result.append(item);found=True;break
        assert found,(side,i+1,outcome,captured,changes,prev[f:f+10],prev[d:d+10],words[9:11])
    assert bool(result)==(outcome!='miss'),(side,outcome,result)
    return result
