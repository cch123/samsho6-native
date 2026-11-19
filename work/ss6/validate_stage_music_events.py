#!/usr/bin/env python3
"""Stage and victory stream requests through both rounds and the CONTINUE midpoint."""
import hashlib
import json

from validate_battle_sound import frame_events
from validate_console_versus_session import ACTORS, BATTLE, PARAMS, fixture
from validate_haohmaru_special import BUILD, ROOT, SOURCE_HASH, run_native
from validate_shake_inputs import inputs

STOP = (7, 0, 0)
PRELOAD = (5, 0, 5)
START = (6, 0, 0x3200)
VICTORY = (8, 0x3200, 24)
GROUP1, GROUP2 = (3, 0, 1), (3, 0, 2)


def source():
    p=fixture()
    instructions=0
    def run(start, args=(), stop=()):
        nonlocal instructions
        calls=[]
        def observe(pc):
            if pc in (0x1e7a78,0x1e7b40,0x1e7ad0,0x1e7af8,0x2140b8,0x13abb0,
                      0x13aaf8,0x213ff0,0x1e7ce8,0x145118,0x145358,0x1453a8):
                calls.append((pc,*p.registers[4:6]))
        _,n=p.run(start,args,stop_before=stop,observe=observe,limit=150000)
        instructions+=n
        return calls
    def addresses(*args):
        return [c[0] for c in run(*args)]

    # 1b8bc0 copies these seven factory option bytes to 43d050..56.
    # Byte six controls the soundtrack lookup and byte four the BGM gain.
    p.memory[0x57974c:0x579753]=bytes([255])*7
    run(0x1183f8,[0x57974c])
    assert p.read(0x579750,1)==100 and p.read(0x579752,1)==0

    # Capture call order before enabling the hardware wrappers. The same
    # wrappers are exercised below with output enabled up to their actual RPC.
    p.write(0x345188,0,4)
    assert addresses(0x139678,(),(0x139690,))==[0x1e7ad0,0x1e7b40,0x1e7af8]
    assert addresses(0x145d98)==[0x1e7a78,0x1e7b40,0x1e7af8]
    assert addresses(0x1e7df0)==[0x1e7af8,0x1e7ad0]
    p.write(0x345188,1,4)
    for gate in (0,1):
        p.write(0x5850e0,gate,4)
        p.put(4,99);p.put(5,99)
        run(0x1e7af8,(),(0x213878,))
        assert p.registers[4:6]==([0x280000,0] if gate else [99,99])
    for address,group in ((0x1e7a78,1),(0x1e7b40,2)):
        run(address,(),(0x213be8,))
        assert p.registers[4]==group
    run(0x1e7ad0,(),(0x213878,))
    assert p.registers[4:6]==[0x280000,0]

    # The scheduler enters with these first-visit latches cleared by 139e50.
    # Development-console and kernel output are explicit fixture boundaries.
    p.put(12,0x1240000);p.put(16,0x1240000)
    run(0x139088,(),(0x13abb0,))
    assert p.registers[31]==0x1390d0
    p.write(0x123a178,0,4)
    run(0x13abb0,(),(0x323050,))
    assert p.registers[31]==0x13abd8
    for variant in (0,1):
        for stage in range(10):
            p.put(16,0x1240000)
            p.write(0x43d056,variant,1)
            p.write(PARAMS+4,stage,4)
            assert run(0x13abd8,(),(0x13abf8,))==[(0x2140b8,stage+5,1)]
            assert [p.read(a,4) for a in (0x1553b40,0x1553b54,0x1553b58,0x5a9e80,
                                          0x1553b5c,0x5a9e84,0x123a178)]==[stage+6,variant,1,1,0,0,1]
            assert addresses(0x13abb0)==[0x13abb0]
    p.write(0x43d056,0,1)
    for index in (0,1,2):
        p.write(BATTLE+0x18,index,4)
        p.put(16,BATTLE)
        if index:
            assert addresses(0x13aaf8,[0])==[0x13aaf8]
        else:
            run(0x13aaf8,[0],(0x323050,))
            assert p.registers[31]==0x13ab20
            run(0x13ab20,(),(0x214118,))
            assert p.registers[31]==0x13ab48
            for volume in (0,0x200,0x3200):
                p.write(0x5a9e78,volume,4)
                run(0x214118,(),(0x213878,))
                assert p.registers[4:6]==[0x170000,volume] and p.read(0x1553b5c,4)==1

    for i in (0,1):
        a=ACTORS+0xf2c*i
        p.write(a+0xa24,i,4)
        p.write(BATTLE+0x24c+4*i,a,4)
        p.write(BATTLE+0x254+0x108*i+0x2c,2,4)
    for wins in ((0,0),(1,0),(0,1),(1,1),(2,0),(0,2),(2,2)):
        final=max(wins)==2
        for i,value in enumerate(wins):p.write(BATTLE+0x254+i*0x108+0x28,value,4)
        p.put(18,BATTLE);p.put(23,0x4c0000)
        route=addresses(0x143e20,(),(0x139f20,0x143e74))
        assert route==([0x145358,0x145118,0x1453a8] if final else [0x145358])
        if final:
            # Disabled profile returns zero after logging; 143e38 consumes
            # that result and reaches the actual 0x28 RPC.
            p.put(2,0);p.put(23,0x4c0000)
            run(0x143e38,(),(0x213878,))
            assert p.registers[4:6]==[0x280000,0]
        p.put(16,BATTLE);p.write(0x5850e0,0,4);p.write(0x1553b40,0,4)
        result=run(0x1444b4,(),(0x1444ec,))
        if final:
            assert result[-2:]==[(0x1e7ce8,24,0),(0x213ff0,24,0)]
        assert [p.read(a,4) for a in (0x5850e0,0x1553b40)]==([1,25] if final else [0,0])
        if final:assert p.read(0x1553b58,4)==p.read(0x5a9e80,4)==0
    return instructions


def session(seat):
    if seat is None:
        controls=[(0,0)]*12200
    else:
        # Stop attacks after the second KO. Continuing heavy-button edges
        # in the menu could confirm character select instead of CONTINUE.
        controls=[(0,0)]*500+inputs('heavy-KO',seat,'hit')*2
        controls+= [(0,0)]*700
    own=lambda mask:(0,mask) if seat==1 else (mask,0)
    controls += [own(32),(0,0),own(1024)]+[(0,0)]*500
    rows=run_native('ss6-match-replay',[f'1 {a} {b}' for a,b in controls],'--mode','versus','--sound-fields')
    events=[]
    rounds=[]
    first=0
    for tick,row in enumerate(rows,1):
        state=int(row[1]);local=int(row[0]);before=rows[tick-2] if tick>1 else None
        audio=frame_events(row)
        music=[e for e in audio if e[0]>=5]
        expected=[]
        if local==1 and (before is None or before[0]=='0'):
            if first==0:
                assert audio[:2]==[STOP,GROUP2]
                expected.append(STOP)
            expected.append(PRELOAD)
        if local==0:
            assert audio==[STOP,STOP,STOP,GROUP2,STOP],(seat,tick,audio)
            expected=[STOP]*4
            first=tick
        entering=before is None or state!=int(before[1])
        wins=[int(row[12]),int(row[22])]
        if entering and state in (4,5,8):
            rounds.append([tick,state,*wins])
            if state==4 and max(wins)==0:expected=[START]
            if state==5 and max(wins)==2:expected=[STOP]
            if state==8 and max(wins)==2:expected=[VICTORY]
        if before and before[2]=='0' and row[2]=='1':
            assert audio[:3]==[GROUP1,GROUP2,STOP]
            expected=[STOP]
        assert music==expected,(seat,tick,state,local,wins,music,expected)
        if music:events.append([tick,*music])
    assert first>0 and rows[-1][1]=='4'
    first_match=[r for r in rounds if r[0]<first]
    assert [r[1] for r in first_match]==[4,5,8,4,5,8]
    assert first_match[-1][2:]==([2,2] if seat is None else [0,2] if seat else [2,0])
    return dict(winner=seat,ticks=len(rows),transitions=rounds,music=events)


if __name__=='__main__':
    count=source()
    cases=[session(seat) for seat in (0,1,None)]
    report=dict(status='passed',elf_sha256=SOURCE_HASH,
                match_sha256=hashlib.sha256((BUILD/'ss6-match-replay').read_bytes()).hexdigest(),
                source_instructions=count,combat_ticks=sum(c['ticks'] for c in cases),sessions=cases,
                scope='Real two-round controller KOs on each port and a two-round timeout draw, including the menu, '
                      'fade midpoint and following fight. Source slices start after console logging or stop at EE/IOP '
                      'request boundaries. Disc sectors, stereo mixing and resident opening jingle have separate tests.')
    (ROOT/'outputs/ss6-feasibility/stage_music_events_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f"{len(cases)} CONTINUE sessions, {report['combat_ticks']} ticks, {count} original instructions")
