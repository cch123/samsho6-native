#!/usr/bin/env python3
"""Timed local versus, including the original count boundary, slow motion and tie handling."""
import hashlib
import json
import subprocess

from extract_collision_tables import SOURCE_HASH
from round_entry_oracle import ROOT, fixture
from mips_probe import signed

WORK = ROOT / 'work/ss6'
MATCH = WORK / 'build-native/ss6-match-replay'
OUT = ROOT / 'outputs/ss6-feasibility'
TIME, RAW, NEXT, ROUND, CAPTION, WINNER, SPEED, BASE, DELTA, LOCK, SLOW, SLOWER, PAUSED, RAGE0, RAGE1 = range(23,38)


def replay(limit, steps):
    cmds = ''.join(f'1 {a} {b}\n' for a,b in steps)
    result = subprocess.run([MATCH,WORK/'extracted/resources','--round-time',str(limit)],
                            input=cmds,capture_output=True,text=True,check=True)
    rows = []
    for line in result.stdout.splitlines():
        row = [int(float(x)) for x in line.split()]
        rows.append(row)
        if row[2]:
            break
    return rows


def original_clock(probe, battle, actors, option, old):
    # Use the real battle-owner and actor pointers. Seed the prior published
    # clocks so both the old-delta expiry and the new-delta count are tested.
    p = probe
    for off,value in [(0,old[NEXT]),(4,old[1]),(8,old[LOCK]),(0x13c,option),
                      (0x110,old[DELTA]),(0x114,old[RAW]),(0x128,old[SLOW]),(0x12c,old[SLOWER])]:
        p.write(battle+off,value,4)
    for i,actor in enumerate(actors):
        p.write(actor+0x194,(old[4+10*i]<<16)|old[3+10*i],4)
        p.write(actor+0x120,old[RAGE0+i],4)
        p.write(p.read(actor,4)+0x24,old[5+10*i],4)
    n = p.run(0x1421b0,[battle],limit=20000)[1]
    n += p.run(0x142cd8,[battle])[1]
    result = [signed(p.read(battle+x,4),32) for x in (0x134,0x114,0x140,0x10c,0x110,0x128,0x12c)]
    return result,n


def main():
    assert hashlib.sha256((WORK/'extracted/SLPS_255.59').read_bytes()).hexdigest()==SOURCE_HASH
    p,a,o,b=fixture()
    actors=[a,a+0xf2c]
    for i,actor in enumerate(actors):
        p.write(b+0x24c+4*i,actor,4)
        p.write(actor,o+i*0x1000,4)
        p.write(actor+0xa24,i,4)
        p.write(actor+0x23c,0x1000,4)
    p.write(0x46a908,256,4)
    steps = [(0,0)]*20500
    summaries=[]
    compared=0
    instructions=0
    modes=set()
    def check(rows,limit,option):
        nonlocal compared,instructions
        p.write(b+0x13c,option,4)
        p.run(0x1406e0)
        assert rows[0][RAW]==p.read(b+0x114,4)
        assert rows[0][TIME]==signed(p.run(0x1407d0)[0],64)
        for old,new in zip(rows,rows[1:]):
            # Round entry reinitializes all timers after the clock pass.
            # Ending entry schedules its own timer5/6 after the clock pass.
            if new[2] or new[PAUSED] or (new[1]!=old[1] and new[1] in (1,5,6)):
                continue
            raw=old[RAW]
            if old[1]==4 and old[LOCK]!=1 and 2 not in old[RAGE0:RAGE1+1]:
                raw=max(0,raw-new[DELTA])
            assert new[RAW]==raw,(limit,old[0],raw,new)
            assert new[TIME]==((raw+23039)//23040 if limit else -1)
            modes.add(new[SPEED])
            if old[0]%127!=0 and old[SPEED]==new[SPEED] and not (
                old[TIME]!=new[TIME] and new[TIME] in (60,30,10,1,0)):
                continue
            expected,n=original_clock(p,b,actors,option,old)
            actual=[new[i] for i in (TIME,RAW,SPEED,BASE,DELTA,SLOW,SLOWER)]
            assert actual==expected,(limit,old[0],actual,expected)
            compared+=1;instructions+=n
    for option,limit in enumerate([60,90,99,0]):
        rows=replay(limit,steps if limit else steps[:9600])
        check(rows,limit,option)
        if limit:
            endings=[new for old,new in zip(rows,rows[1:]) if old[1]!=5 and new[1]==5]
            assert len(endings)==2 and all(r[CAPTION]==19 and r[WINNER]==-1 for r in endings)
            assert rows[-1][2]==1 and rows[-1][12]==rows[-1][22]==2
            assert any(r[5]==r[15]==503 for r in rows)
        else:
            assert rows[-1][1]==4 and rows[-1][12]==rows[-1][22]==0
        summaries.append(dict(limit=limit,updates=len(rows),score=[rows[-1][12],rows[-1][22]]))
    for i in (0,1):
        attack=[(128,0)]*45+[(256,0)] if i==0 else [(0,64)]*45+[(0,256)]
        rows=replay(60,steps[:500]+attack+steps[:6200])
        end=next(r for r in rows if r[1]==5)
        assert end[WINNER]==i and end[CAPTION]==19 and end[12+10*i]==1
        assert any(r[15-10*i]==505 for r in rows)
        check(rows,60,0)
        summaries.append(dict(winner=i,timeout_update=end[0],life=[end[9],end[19]]))
    heavy=[(0,0)]*440+([(128,0)]*45+[(1024,0)]+[(0,0)]*84)*50
    rows=replay(99,heavy)
    assert rows[-1][2] and rows[-1][12]==2 and rows[-1][22]==0
    check(rows,99,2)
    assert {0,1,2}<=modes
    report=dict(status='passed',timed_matches=summaries,ko_match_updates=len(rows),speed_modes=sorted(modes),
                original_clock_comparisons=compared,original_instructions=instructions,
                match_sha256=hashlib.sha256(MATCH.read_bytes()).hexdigest(),source_sha256=SOURCE_HASH,
                scope='Resource00 local versus. Complete native round flows with real input. Original 1406e0/1407d0 initialization and 1421b0/142cd8 on sampled prior states, including each change of slow-motion rate.')
    (OUT/'versus_clock_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f'{len(summaries)} clock cases and one full KO match; {compared} original update comparisons')


if __name__=='__main__':
    main()
