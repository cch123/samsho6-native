#!/usr/bin/env python3
"""Resource 00 special inputs, full actor callbacks and local two-player replays."""
import hashlib
import itertools
import json
import struct
import subprocess

from extract_collision_tables import SOURCE_HASH
from knockdown_oracle import initialize_effects
from mips_probe import Probe, signed
from round_entry_oracle import ROOT, buffered_stdout, fixture
from validate_collisions import ACTORS, OBJECTS, QUEUE, install, player
from validate_input_features import PADS
from validate_input_lifecycle import Boundary

RES = ROOT / 'work/ss6/extracted/resources'
BUILD = ROOT / 'work/ss6/build-native'
ELF = ROOT / 'work/ss6/extracted/SLPS_255.59'


def run_native(program, commands, *args):
    result = subprocess.run([BUILD / program, RES, *args], text=True, capture_output=True,
                            input='\n'.join(commands) + '\n')
    assert result.returncode == 0, (program, len(result.stdout.splitlines()), result.stderr)
    return [line.split() for line in result.stdout.splitlines()]


def pads_for(state, slot):
    forward, back = (128, 64) if slot == 0 else (64, 128)
    if state in (23, 24):
        return (32, 32 | forward, forward | 4096)
    if state == 80:
        return (forward,32|forward,32,32|back,back,forward|256|512)
    if 64 <= state <= 66:
        return (32, 32 | forward, forward | (256 << (state-64)))
    if 71 <= state <= 73:
        # The 623 command overlaps the opening forward taps. The run must
        # already be beyond timer8 before the final attack edge.
        return (0, forward, 0, *([forward]*16), 32, 32|forward|(256 << (state-71)))
    if state == 77:
        return (32,32|back,back|2048)
    if state == 67:
        return (32, 32 | forward, forward | 2048)
    horizontal = forward if state < 74 else back
    strength = state - (68 if state < 74 else 74)
    return (horizontal, 32, horizontal | 32 | (256 << strength))


def actor_trace(state, slot, fall=False, armed=True):
    p, a, o, battle = fixture(slot)
    p.finite_model = True
    other = 0x1c00000 + (1-slot)*0xf2c
    other_body = o + 0x1000
    x, other_x = (280, 380) if slot == 0 else (380, 280)
    commands = [f'reset {slot} {slot} {x} {other_x}', 'phases', 'special-fields']
    count = 0

    def call(pc, *args, stops=()):
        nonlocal count
        _, n = p.run(pc, args, limit=500000, stop_before=stops)
        count += n

    for addr, value in [(other, other_body), (other+4, o+0x2000), (other+0x23c, 0x1000),
                        (other+0xa24, 1-slot), (battle+0x24c+4*(1-slot), other), (other_body+0xcc, 1-slot),
                        (a+4, o+0x3000), (o+0x30c4, -1)]:
        p.write(addr, value, 4)
    for pc, args in [(0x149008, [a, 0]), (0x149918, [a]), (0x11d8e0, [o]), (0x179258, [a+0x2c4, a+0x10c])]:
        call(pc, *args)
    initialize_effects(p)
    for addr, value in [(0x4c38a8, 0), (battle, 4), (battle+0x144, 100),
                        (o+0x38, 0x10000000 | slot<<19), (a+0xa08, slot)]:
        p.write(addr, value, 4)
    struct.pack_into('<f', p.memory, o+0x40, x)
    struct.pack_into('<f', p.memory, other_body+0x40, other_x)
    for mapping in (0x4eaac0, 0x12d32d8):
        struct.pack_into('<8I', p.memory, mapping+slot*32, *(1<<n for n in range(8, 16)))
    if not armed:
        p.write(a+0x23c,0,4)
        p.write(a+0x244,0,4)
        commands.append('posture 0 0')
    if fall:
        p.write(a+0x18c, 1, 4)
        call(0x14ff80, a+0x18c, 2, state)
        commands.append(f'damage {state}')
    if fall and state==67:
        # Keep the camera boundary fixed in both isolated callback runs. The
        # world replay additionally exercises the actual moving camera.
        commands.append('wall-camera 160 480')
        p.write(battle+0x44,160,4);p.write(battle+0x48,480,4)
        for bank,name in enumerate(('01HitFlash.bin','02Guard.bin','03etc.bin')):
            addr=0x4a4810+bank*0x3da0;p.memory[addr:addr+0x3da0]=(RES/name).read_bytes()
    setup = len(commands)
    sampled = () if fall else (*pads_for(state, slot), 0)
    previous = 0
    seen = set()
    expected = []
    # State/timers/clocks/motion come from actual 149d08 + body passes.
    # After the neutral pad edge, no further input changes during recovery.
    for tick in range(170):
        call(0x11d730, o)
        call(0x11d6c8, o)
        p.put(11, o)
        p.put(14, other_body)
        p.put(18, battle)
        call(0x1428f4, stops=Boundary(0x142918))
        call(0x151b00, a)
        call(0x151eb0, a)
        if tick < len(sampled):
            held = sampled[tick]
            p.write(PADS+12*slot, held, 4)
            p.write(PADS+12*slot+4, held & ~previous, 4)
            p.put(16, 1)
            p.put(17, a)
            p.put(18, other)
            end = Boundary(0x149770, 0x1498b0)
            call(0x1495e8, stops=end)
            assert end.stopped == 0x149770
            commands.append(f'pad {held} {held & ~previous}')
            previous = held
        else:
            commands.append('tick')
        call(0x149d08, a)
        if tick < len(sampled):
            p.put(17, a)
            p.write(0x1fff038, 0x1ffff00, 8)
            call(0x149790)
        call(0x149918, a)
        call(0x11d8e0, o)
        cols = [p.read(a+off, 4) for off in (0x194, 0x18c)]
        cols += [signed(p.read(a+off, 2), 16) for off in (0x190, 0x192)]
        cols += [p.read(a+0x19a, 1)]
        cols += [p.read(a+off, 4) for off in (0x23c, 0x244, 0x248, 0xc0, *range(0x15c,0x168,4), *range(0x260,0x27c,4))]
        cols += [signed(p.read(a+off, 4), 32) for off in range(0x1b0,0x23c,4)]
        cols += [p.read(o+off, 4) for off in (0x24,0x28,0x2c,0xc0,0x38,0x104,0x108)]
        cols += [p.read(o+0xfe,2)]
        cols += [signed(p.read(o+off,4),32) for off in range(0x4c,0x64,4)]
        cols += [p.read(o+off,4) for off in (0x40,0x44)]
        cols += [p.read(a+off,4) for off in range(0x28c,0x2c0,4)]
        cols += [p.read(o+0x134,4)]
        seen.add((cols[0], cols[54]))
        expected.append(cols)
        if tick > 4 and p.read(a+0x194,4) == 0 and p.read(o+0x24,4) == int(not armed):
            break
    assert tick < 169 and any(s == (state<<16)|(2 if fall else 1) for s,_ in seen), (state,slot,seen)
    rows = run_native('ss6-ground-state-probe', commands)[setup:]
    for tick, (row, want) in enumerate(zip(rows,expected,strict=True)):
        got = list(map(int, row[:70] + row[-14:]))
        assert got == want, (state, slot, tick, [(i,x,y) for i,(x,y) in enumerate(zip(got,want)) if x!=y])
    return len(rows), count, sorted({act for _,act in seen})


class ContactOracle:
    """Replay original collection and hit/guard handlers on published match snapshots."""
    def __init__(self):
        self.probe=Probe(ELF.read_bytes(),finite_model=True)
        self.aid,self.act,self.jdg=[(RES/f'{key}_00.bin').read_bytes() for key in ('aid','act','jdg')]
        p=self.probe
        buffered_stdout(p)
        for addr,value in [(0x4d3d08,ACTORS),(0x4d89b8,QUEUE),(0x4d3d00,0x1b80000),(0x1b8013c,3),(0x4c3808,3)]:
            p.write(addr,value,4)
        p.write(0x43d061,100,1)  # Default 100 percent handicap.

    def install_player(self,row,slot):
        p=self.probe
        table,state,action,step=map(int,row[3+10*slot:7+10*slot])
        life=int(row[9+10*slot])
        base=23+26*slot
        (x,y,flags38,flags104,flags108,flags23c,flags240,flags244,flags248,flags24c,state_flags,
         timer6,c8,down,back,low_back,rage,amount,sword,maximum,previous,heavy,adjust,*history)=map(int,row[base:base+26])
        first=struct.unpack_from('<h',self.aid,2*action)[0]
        rec=60*(first+step)
        jf=struct.unpack_from('<H',self.act,rec+0x1e)[0]
        refs=struct.unpack_from('<8h',self.act,rec+0xe)[:jf&7]
        data=[[r,*struct.unpack_from('<I5h',self.jdg,16*r)] for r in refs]
        src=player(slot,data)
        f32=lambda bits:struct.unpack('<f',struct.pack('<I',bits))[0]
        src.update(x=f32(x),y=f32(y),mx=bool(flags38&0x80000),my=bool(flags38&0x40000),
                   flags104=flags104,flags108=flags108,actorFlags=flags23c,table=table,state=state,
                   stateFlags=state_flags,field1c8=timer6,judgmentFlags=jf)
        install(p,slot,src)
        actor,obj=ACTORS+slot*0xf2c,OBJECTS[slot]
        for off,val in [(0xa24,slot),(0x240,flags240),(0x244,flags244),(0x248,flags248),(0xc8,c8),
                        (0x3c0,down),(0x39c,back),(0x398,low_back),(0x120,rage),(0x124,amount),
                        (0x134,sword),(0x138,maximum),(0xa30,life),(0xa50,adjust),(0x258,heavy),(0x190,-1)]:
            p.write(actor+off,val,4)
        for off,val in [(0x24c,flags24c),(0x255,previous),*zip((0x250,0x251,0x252),history)]:
            p.write(actor+off,val,1)
        p.write(obj+0xcc,slot,4)
        p.write(obj+0x24,action,4)
        p.write(obj+0x28,step,4)

    def contacts(self,rows,attacker,observe=None):
        p=self.probe
        accepted=[]
        for j in range(5,len(rows)-1):
            prev,next_row=rows[j:j+2]
            self.install_player(prev,0)
            self.install_player(prev,1)
            p.write(0x12d2698,0,4)
            for a,b in (OBJECTS,OBJECTS[::-1]):
                p.run(0x1536e8,[a,b],limit=50000)
            p.run(0x1544a0,limit=50000)
            b=1-attacker
            change=False
            for n in range(p.read(0x12d2698,4)):
                event=QUEUE+108*n
                if p.read(event,4)!=7 or p.read(event+0x40,4)!=OBJECTS[attacker]:
                    continue
                if p.read(OBJECTS[attacker]+0x104,4)&0x06000000:
                    continue
                defense,_=p.run(0x155850,[event])
                actor=ACTORS+b*0xf2c
                if defense:
                    end=Boundary(0x155e90)
                    p.run(0x155d50,[event,0,defense],limit=200000,stop_before=end)
                    assert end.stopped==0x155e90
                    p.run(0x14d5a0,[actor,OBJECTS[attacker],defense,p.read(event+12,4)])
                else:
                    # Stop just after the original writes hit flags and source
                    # character: subsequent instructions start visual effects.
                    end=Boundary(0x155bb8)
                    p.run(0x155a88,[event,0],limit=200000,stop_before=end)
                    assert end.stopped==0x155bb8
                frame=int(next_row[0])
                pending=signed(p.read(actor+0xa38,4),32)
                reaction=p.read(actor+0x192,2)
                projected=23+26*b
                actual_rage=int(next_row[projected+17])
                assert actual_rage==p.read(actor+0x124,4),(frame,actual_rage,p.read(actor+0x124,4))
                actual_life=int(next_row[9+10*b])
                assert actual_life==int(prev[9+10*b])-pending,(frame,actual_life,pending)
                assert int(next_row[4+10*b])==reaction,(frame,next_row[4+10*b],reaction)
                col=10+10*attacker+bool(defense)
                assert int(next_row[col])==int(prev[col])+1,(frame,attacker,defense)
                change=True
                accepted.append(dict(frame=frame,raw=p.read(event+0x20,4),defense=defense,damage=pending,
                            target_state=reaction,metadata=[p.read(actor+off,1) for off in (0x250,0x251,0x252,0x254)]))
                if observe:observe(accepted[-1],p,event,actor)
                break  # Route 7 consumes this source until its next ACT record.
            assert change==(prev[10+10*attacker:12+10*attacker]!=next_row[10+10*attacker:12+10*attacker])
        return accepted


def world(state, slot, guard, oracle, air_target=False):
    forward, back = (128, 64) if slot == 0 else (64, 128)
    approach = [(500,0,0),(21 if air_target else 32,forward,back),(5 if air_target else 4,0,0)]
    sequence = approach + [(1,k,forward if guard else 0) for k in pads_for(state,slot)]
    sequence += [(1,0,forward if guard else 0)]*170
    if air_target:
        sequence[3+12]=(1,0,16)  # Real up edge during the heavy 421 windup.
    if slot:
        sequence = [(n,b,a) for n,a,b in sequence]
    rows = run_native('ss6-match-replay', [' '.join(map(str,v)) for v in sequence], '--contact-fields')
    own, target = 3+10*slot, 3+10*(1-slot)
    assert rows[5][own:own+2] == ['1',str(state)]
    assert rows[-1][own:own+3] == ['0','0','0']
    last_counts = (0,0)
    contacts = []
    for row in rows:
        counts = tuple(map(int,row[own+7:own+9]))
        if counts != last_counts:
            contacts.append([int(row[0]),int(row[own+2]),int(row[own+3]),int(row[target+1]),int(row[target+6])])
            last_counts = counts
    if state == 67:
        assert not contacts and int(rows[-1][target+6]) == 200
    elif guard:
        assert last_counts[0] == 0 and last_counts[1] > 0
        assert int(rows[-1][target+6]) == 200 - last_counts[1], (state,slot,last_counts,contacts)
    else:
        assert last_counts[0] > 0 and last_counts[1] == 0 and int(rows[-1][target+6]) < 200
    original=oracle.contacts(rows,slot)
    assert [x["frame"] for x in original]==[x[0] for x in contacts]
    if air_target:assert any(e["raw"]==20 and e["target_state"]==70 for e in original)
    return dict(state=state,player=slot+1,guard=guard,air_target=air_target,contacts=contacts,original_contacts=original)


def special_contact_matrix():
    p=Probe(ELF.read_bytes(),finite_model=True)
    buffered_stdout(p)
    source,target=ACTORS,ACTORS+0xf2c
    ctx=0x1e02000
    p.write(0x4d3d08,ACTORS,4)
    def clear():
        p.memory[source:target+0xf2c]=bytes(2*0xf2c)
        for a,obj,slot in ((source,OBJECTS[0],0),(target,OBJECTS[1],1)):
            p.write(a,obj,4)
            p.write(a+0xa24,slot,4)
            p.write(a+0x190,-1,4)
            p.write(a+0xa3c,-1,4)
            p.write(obj+0xcc,slot,4)
        p.write(ctx,target,4)
        p.write(ctx+4,source,4)
    commands,expected=[],[]
    for raw,strength,part,posture,armed,previous in itertools.product(
            (10,11,17,20),range(3),range(3),(0,8,16),range(2),(0,34)):
        clear()
        flags=posture|(0x1000 if armed else 0)
        p.write(source+0x194,1|((68+strength)<<16),4)
        p.write(source+0x19a,8|(1<<strength),1)
        p.write(source+0x23c,0x1000,4)
        p.write(source+0x248,0x1234,4)
        p.write(target+0x23c,flags,4)
        p.write(target+0x258,1,4)
        p.write(target+0x255,previous,1)
        p.run(0x14d198,[target,OBJECTS[0],0,raw,part,0])
        state=p.read(target+0x255,1)
        if state==74:
            p.run(0x1708d8,[ctx,0,0])
        elif state>=62:
            p.run(0x171418,[ctx,state-62])
        else:
            p.run(0x1707b0,[ctx,(state-32)//3,(state-32)%3])
        expected.append([p.read(target+0x23c,4),signed(p.read(target+0x190,2),16),
                         signed(p.read(target+0x192,2),16),p.read(target+0x18c,4),state,p.read(target+0x256,1),
                         p.read(source+0x1b0,4),p.read(source+0x1b4,4),p.read(target+0x1b0,4),p.read(target+0x1b4,4),
                         p.read(target+0xa3c,4),p.read(target+0x258,4),p.read(source+0x248,4)])
        commands.append(f'{flags} 0 {previous} 0 {part} 0 0 {raw} {strength} 1 4660')
    for cmd,row,want in zip(commands,run_native('ss6-reaction-probe',commands,'--special'),expected,strict=True):
        assert list(map(int,row))==want,(cmd,row,want)
    reactions=len(commands)
    commands,expected=[],[]
    for strength,guard,current,amount,target_rage in itertools.product(range(3),range(2),(0,25600),(0,0xb700),range(3)):
        clear()
        for off,val in ((0x194,1|((68+strength)<<16)),(0x134,current),(0x138,25600),(0x23c,0x1000)):
            p.write(source+off,val,4)
        p.write(source+0x19a,8|(1<<strength),1)
        for off,val in ((0x120,target_rage),(0x124,amount),(0x134,17000),(0x138,25600),(0x23c,4096),(0xa30,150),(0x248,8)):
            p.write(target+off,val,4)
        damage,_=p.run(0x1a41b8,[40,source,target,0x10 if guard else 0])
        expected.append([signed(damage,32),p.read(source+0x134,4),p.read(source+0x23c,4),
                         *[p.read(target+off,4) for off in (0x120,0x124,0x128,0x134,0x138,0x248)]])
        commands.append(f'special-contact 40 {guard} {current} 25600 0 4096 {strength} 150 {target_rage} {amount} 0 17000 25600 8')
    for cmd,row,want in zip(commands,run_native('ss6-damage-probe',commands),expected,strict=True):
        assert list(map(int,row))==want,(cmd,row,want)
    return reactions,len(commands)


def main():
    assert hashlib.sha256(ELF.read_bytes()).hexdigest() == SOURCE_HASH
    states = (67,68,69,70,74,75,76)
    traces = []
    for state,slot in itertools.product(states,range(2)):
        ticks, instructions, actions = actor_trace(state,slot)
        traces.append(dict(state=state,player=slot+1,ticks=ticks,instructions=instructions,actions=actions))
    for state,slot in itertools.product((63,69,70),range(2)):
        ticks,instructions,actions = actor_trace(state,slot,fall=True)
        traces.append(dict(fall=state,player=slot+1,ticks=ticks,instructions=instructions,actions=actions))
    oracle=ContactOracle()
    matches = [world(s,p,g,oracle) for s,p,g in itertools.product(states,range(2),(False,True))]
    matches.extend(world(76,slot,False,oracle,air_target=True) for slot in range(2))
    reactions,meters=special_contact_matrix()
    report = dict(special_reaction_cases=reactions,special_gauge_cases=meters,status='passed', elf_sha256=SOURCE_HASH, actor_traces=traces, world_replays=matches,
                  scope='Human/system0, armed resource00 vs resource00. Original 149d08, 149918, 11d8e0 and input slices; '
                        'body actions, frame clocks, motion, flags, timers, special registry and recovery. World replays '
                        'exercise natural collision, HP, guard chip and both facings through the native match. '
                        'For each world contact the original 1536e8, 1544a0, 155850 and hit or guard handler '
                        'prefix executes against the previous published native actor and geometry snapshot. '
                        'World positions between contacts are supplied.')
    (ROOT/'outputs/ss6-feasibility/haohmaru_special_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f'{len(traces)} original/native actor traces, {sum(t["ticks"] for t in traces)} ticks, {len(matches)} native match replays')


if __name__ == '__main__':
    main()
