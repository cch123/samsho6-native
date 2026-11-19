#!/usr/bin/env python3
"""Compare system 0 rage offense in live versus with the Japanese damage paths."""
from concurrent.futures import ProcessPoolExecutor
from itertools import product
from pathlib import Path
import json
import shutil
import struct
import tempfile

from mips_probe import signed
from validate_collisions import ACTORS, OBJECTS, QUEUE
from validate_combined_slash import initialize_pools
from validate_dash_motion import ASSETS, ELF, PIN, ROOT, digest
from validate_directional_slash import setup_actor
from validate_haohmaru_special import ContactOracle
from validate_pursuit_attack import REPLAY, read

REPORT = ROOT/'outputs/ss6-feasibility/rage_attack_match_validation.json'


def setup(slot, target_armed, raging):
    front=(128,64)[slot]
    def pair(ticks,ours,other):
        return (ticks,other,ours) if slot else (ticks,ours,other)
    pads=[(500,0,0)]
    for _ in range(3):
        pads += [pair(65,0,front^192),(5,0,0),pair(1,0,1024)]+[(1,0,0)]*35+[(53,0,0)]
    # The defender was the one delivering the three priming hits. Optionally
    # discard their own weapon, without changing the geometry or health of
    # the defender. The rage-controlled player's sword is full in both arms.
    pads += [pair(1,0,0 if target_armed else (front^192)|8),(140 if raging else 620,0,0),
             pair(36,front,0),(5,0,0)]
    return pads,pair


def play(exe, seq):
    return read(exe,['--contact-fields'],['%d %d %d'%r for r in seq])


def compare_match(args):
    exe,slot,target_armed,raging,button=args
    target=1-slot
    pads,pair=setup(slot,target_armed,raging)
    rows=play(exe,pads+[pair(1,button,0)]+[(1,0,0)]*86)
    oracle=ContactOracle();p=oracle.probe;initialize_pools(p)
    stdout=p.read(p.read(0x5d1bf8,4)+8,4)
    for off in (0,16):p.write(stdout+off,0x19e0000,4)
    battle=p.read(0x4d3d00,4)
    for i in range(2):p.write(battle+0x24c+4*i,ACTORS+0xf2c*i,4)
    p.write(battle,4,4)
    ins=0
    def call(pc,*argv,observer=None):
        nonlocal ins
        val,n=p.run(pc,argv,observe=observer,limit=1200000)
        ins+=n
        return val
    events=[];decay=[0,0]
    for old,now in zip(rows,rows[1:]):
        for i in (0,1):
            j=1-i;src=ACTORS+0xf2c*i;dest=ACTORS+0xf2c*j;f=23+26*i;g=23+26*j
            if int(now[10+i*10])==int(old[10+i*10]):continue
            assert int(now[0])==int(old[0])+1
            for side in (0,1):
                oracle.install_player(old,side)
                p.write(ACTORS+0xf2c*side+0x128,decay[side],4)
                call(0x11e760,side)
            p.write(0x12d2698,0,4)
            for order in (OBJECTS,OBJECTS[::-1]):call(0x1536e8,*order)
            call(0x1544a0)
            candidates=[]
            for n in range(p.read(0x12d2698,4)):
                event=QUEUE+108*n
                if p.read(event,4)==7 and p.read(event+0x40,4)==OBJECTS[i]:candidates.append(event)
            assert candidates,(slot,i,now[:23])
            e=candidates[0];aux=p.read(e+0x10,4);raw=p.read(e+0x20,4)
            assert call(0x155850,e)==0
            visits=[]
            def watch(pc):
                if pc in (0x1a3e38,0x1a3f54):visits.append(pc)
            # Trace the actual load, so accidentally using the armed column for
            # BOTH branches cannot pass merely because Haohmaru's values agree.
            call(0x1a3c18,aux,src,dest,0,observer=watch)
            intermediate=p.floats[0]
            p.floats[12]=intermediate
            amount=call(0x1a3f90,src,dest)
            resolver_visits=[]
            call(0x155a88,e,1,0,observer=lambda pc:resolver_visits.append(pc) if pc in (0x1a3e38,0x1a3f54) else None)
            assert resolver_visits==visits
            actual=int(old[9+10*j])-int(now[9+10*j])
            assert amount==p.read(dest+0xa38,4)==actual,(slot,target_armed,raging,button,now[0],amount,actual)
            assert int(now[4+10*j])==p.read(dest+0x192,2)
            assert [int(n) for n in now[g+16:g+20]]==[p.read(dest+off,4) for off in (0x120,0x124,0x134,0x138)]
            decay[j]=p.read(dest+0x128,4)
            active=int(old[f+16])==1
            armed=bool(int(old[g+5])&0x1000)
            assert visits==([0x1a3e38 if armed else 0x1a3f54] if active else [])
            events.append(dict(player=i+1,tick=int(now[0]),action=int(old[5+i*10]),step=int(old[6+i*10]),raw=raw,
                               auxiliary=aux,damage=actual,source_amount_bits=intermediate,source_raging=active,
                               sword=int(old[f+18]),sword_max=int(old[f+19]),target_armed=armed,
                               target_health=int(old[9+j*10]),rage_multiplier_loads=[hex(v) for v in visits],
                               x_bits=[int(old[23+side*26]) for side in (i,j)]))
    assert len(events)==4 and [e['player'] for e in events]==[target+1]*3+[slot+1]
    assert [e['damage'] for e in events[:3]]==[38,35,35]
    result=events[-1]
    assert result['source_raging']==raging and result['target_armed']==target_armed and result['target_health']==200
    assert result['sword']==result['sword_max']==(46080 if raging else 25600)
    expected={256:(185,2,8,11),512:(187,4,12,18),1024:(189,5,38,57)}[button]
    assert (result['action'],result['step'],result['damage'])==(expected[0],expected[1],expected[2+int(raging)])
    return dict(player=slot+1,target_armed=target_armed,raging=raging,button=button,result=result,original_instructions=ins)


def verify_commands(args):
    exe,slot=args;front=(128,64)[slot]
    setup_pads,pair=setup(slot,True,True)
    inputs=(('A+B',(768,),21,264),('A+B+C',(1792,),26,230),('236+A+B',(32,32|front,front|768),65,530))
    records=[]
    for name,buttons,state,action in inputs:
        rows=play(exe,setup_pads+[pair(1,b,0) for b in buttons])[len(setup_pads)-1:]
        src=setup_actor(slot);p=src.p
        owner=src.a+0x2c4
        # 179258 initialized the actual stock system-0 table in this actor.
        # Record the executable definitions as well as running the pad inputs.
        enabled=[i+64 for i in range(p.read(owner+0x5bc,4)) if signed(p.read(owner+0x644+2*i,2),16)>=0]
        assert enabled==list(range(64,78))+[80]
        normal=[signed(p.read(owner+0x4c4+2*i,2),16) for i in (14,20,21)]
        assert normal==[15,-1,-1]
        for old,now,pad in zip(rows,rows[1:],buttons):
            ours=23+26*slot;other=23+26*(1-slot)
            for obj,owner_f in ((src.o,ours),(src.o+0x1000,other)):
                p.write(obj+0x40,int(old[owner_f]),4)
            for off,val in zip((0x120,0x124,0x134,0x138),old[ours+16:ours+20]):p.write(src.a+off,int(val),4)
            assert int(old[ours+16])==1
            p.write(src.a+0xa30,int(old[9+slot*10]),4)
            p.write(src.other+0x23c,int(old[other+5]),4)
            orig=src.frame(pad)
            native=int(now[3+10*slot])|(int(now[4+10*slot])<<16)
            assert (orig[0],orig[54])==(native,int(now[5+10*slot])),(slot,name,pad,orig[:7],now[:23])
        assert (orig[0],orig[54])==((state<<16)|1,action)
        records.append(dict(command=name,state=state,action=action,original_instructions=src.instructions))
    return dict(player=slot+1,enabled_character_special_states=enabled,system_command_14_20_21=normal,inputs=records)


def main():
    assert digest(ELF)==PIN;raw=ELF.read_bytes()
    menu={}
    for off,phrase in ((0x4e3540,'怒スピリッツ'),(0x4e35e8,'怒りＭＡＸ'),(0x4e3640,'超斬り'),
                       (0x4e36f8,'真スピリッツ'),(0x4e38e0,'武器破壊技'),(0x4e3ad8,'天スピリッツ'),(0x4e3c98,'怒り爆発')):
        assert raw[off:off+len(phrase.encode('cp932'))]==phrase.encode('cp932')
        menu[hex(off)]=phrase
    mask_data=(ASSETS/'input_special.bin').read_bytes()
    masks=[struct.unpack_from('<H',mask_data,slot*12+8)[0] for slot in (14,15)]
    assert masks==[0x1fe,0x22]
    character=struct.unpack_from('<7i',(ASSETS/'damage_00.bin').read_bytes(),0xec)
    assert character[3:5]==(100,100)
    with tempfile.TemporaryDirectory() as tmp:
        exe=Path(tmp)/'replay';shutil.copy2(REPLAY,exe)
        with ProcessPoolExecutor(max_workers=4) as pool:
            cases=list(pool.map(compare_match,[(exe,*c) for c in product(range(2),(False,True),(False,True),(256,512,1024))]))
            commands=list(pool.map(verify_commands,[(exe,i) for i in range(2)]))
        exe_hash=digest(exe)
    for slot,button in product(range(2),(256,512,1024)):
        group=[c['result'] for c in cases if c['player']==slot+1 and c['button']==button]
        assert len(set(tuple(c['x_bits']) for c in group))==1
        assert len(set(c['auxiliary'] for c in group))==1
    report=dict(status='passed',elf_sha256=PIN,replay_sha256=exe_hash,validator_sha256=digest(Path(__file__)),
                menu_file_offsets=menu,system_masks_row_78_79=masks,rage_percent_versus_armed_unarmed=character[3:5],
                commands=commands,matches=cases,original_contacts=len(cases)*4,
                original_instructions=sum(c['original_instructions'] for c in cases)+sum(r['original_instructions'] for c in commands for r in c['inputs']),
                scope='Both pad slots, resource00/system0 local versus with stage items disabled. Three real heavy strikes charge rage, opponent optionally discards, wait controls expiry; matched final geometry, defender HP and source weapon energy capacity. Original full collision, damage and reaction on match snapshots, both original multiplier loads traced. Full, unmodified 179258/input paths for system exclusivity and three actual pad commands. No changes to production runtime.')
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(len(cases),'versus replays,',report['original_contacts'],'original hits,',sum(len(c['inputs']) for c in commands),'full-rage command comparisons PASS')


if __name__=='__main__':main()
