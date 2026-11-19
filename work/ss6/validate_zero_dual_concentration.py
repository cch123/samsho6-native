#!/usr/bin/env python3
"""Compare two simultaneous or staggered Zero activations with the Japanese world and gauge callbacks."""
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from knockdown_oracle import initialize_effects
from round_entry_oracle import buffered_stdout
from validate_object_pools import TASKS
from validate_shin_meters import ASSETS, PLAYER, OBJECT, BATTLE, Probe
from validate_dash_motion import ELF, PIN, ROOT, digest
from validate_shin_evasion import EXE

GROUP=[(50,128,64),(5,0,0),(1,1024,1024),(105,0,0),(130,768,768),(1,0,0)]
REPORT=ROOT/'outputs/ss6-feasibility/zero-dual-concentration-validation.json'
EFFECT_OFFSETS=(0x14,0x24,0x28,0x2c,0x30,0xc0)
PACKAGED=ROOT/'outputs/ss6-feasibility/native-viewer'


def unpack(row):
    effects=[]
    index=21
    for side in (0,1):
        n=row[index];index+=1
        effects.append([tuple(row[i:i+6]) for i in range(index,index+6*n,6)])
        index+=6*n
    assert index==len(row)
    return effects


class Original:
    def __init__(self):
        self.p=p=Probe(ELF.read_bytes(),finite_model=True)
        initialize_effects(p);buffered_stdout(p)
        self.instructions=0;self.callbacks=[];self.tick=7468
        for bank,name in enumerate(('01HitFlash.bin','02Guard.bin','03etc.bin','04tenso.bin'),1):
            base=0x4a4810+(bank-1)*0x3da0
            data=(ASSETS/name).read_bytes();p.memory[base:base+len(data)]=data
        for fn in (0x1123a8,0x112570,0x11e290):self.run(fn)
        for addr,value in ((0x4d3d08,PLAYER),(0x4d3d00,BATTLE),(BATTLE,4),(BATTLE+4,4),
                           (0x1239d84,256),(0x1239d88,256),(0x46a908,256),(0x443150,3)):
            p.write(addr,value,4)
        for side in (0,1):
            a=PLAYER+side*0xf2c
            for off,value in ((0,OBJECT+side*0x1000),(0xa24,side),(0x110,side),(0x10c,4),
                              (0x23c,0x1000),(0xa30,18),(0x13c,2),(0x140,16976),(0x134,25600),(0x138,25600)):
                p.write(a+off,value,4)
            p.write(BATTLE+0x24c+side*4,a,4)
            p.write(BATTLE+0x27c+side*0x108,1,4)
            p.write(BATTLE+0x280+side*0x108,2,4)

    def watch(self,pc):
        if pc==0x11ef90:
            self.callbacks.append((self.tick,pc))

    def run(self,pc,*args,watch=False):
        result,count=self.p.run(pc,args,limit=300000,observe=self.watch if watch else None)
        self.instructions+=count
        return result

    def beam_fields(self):
        p=self.p
        by_seat=[[],[]]
        for i in range(256):
            t=TASKS+52*i
            if p.read(t+4,4)!=0x10 or p.read(t,4)!=0x124898:continue
            assert p.read(t+32,4)==0x4a2b30+108
            seat=(p.read(t+20,4)>>16)-4
            obj=p.read(t+28,4)
            while obj:
                by_seat[seat].append(tuple(p.read(obj+off,4) for off in EFFECT_OFFSETS))
                obj=p.read(obj,4)
        return by_seat

    def frame(self,old,row,pressed):
        p=self.p;self.tick=row[0]
        for side in (0,1):
            # The previous fighter state is the external input to priority 5;
            # 11e760 excludes the gesture itself from countdown on that seat.
            p.write(PLAYER+side*0xf2c+0x194,old[1+8*side],4)
        self.run(0x11e708)
        p.write(0x4a2250,0,4)
        self.run(0x112838,watch=True)
        published=p.read(0x1239d84,4)*p.read(0x1239d88,4)>>8
        for side in (0,1):
            if pressed[side]:
                assert row[1+8*side]==0x250001
                self.run(0x11ef30,side)
                # ACT148 emits descriptor 1 on its first record. Its six
                # effects are born after the current scheduler pass.
                p.floats[12:16]=[0x43a00000,0,0xc1200000,0x3f800000]
                self.run(0x124430,1,side<<19,side)
        for side in (0,1):
            a=PLAYER+side*0xf2c
            want=[p.read(a+i,4) for i in (0x13c,0x140,0x144,0x148)]+[p.read(0x46a910+side*4,4)]
            assert row[2+8*side:7+8*side]==want,(self.tick,side,want,row[:21])
        want=[p.read(0x1239d84,4),published,p.read(0x3ebf30+1024,2),p.read(0x46a924,4)]
        assert row[17:21]==want,(self.tick,want,row[17:21])
        beams=self.beam_fields()
        assert unpack(row)==beams,(self.tick,beams,unpack(row))
        return beams


def case(args):
    exe,lag=args
    trigger=[7469+max(0,-lag),7469+max(0,lag)]
    controls=[(6300,0,0)]+GROUP*4+[(1,6144*int(i==trigger[0]),6144*int(i==trigger[1])) for i in range(7469,7701)]
    script=''.join('%d %d %d\n'%r for r in controls)
    result=subprocess.run([exe,ASSETS],input=script,text=True,check=True,capture_output=True)
    rows=[list(map(int,r.split())) for r in result.stdout.splitlines()]
    # Verify the official replay with the same real VS inputs in addition to
    # the narrower observer built to expose world objects at the priority boundary.
    replay=subprocess.run([EXE,ASSETS,'--mode','versus','--p1-spirit','zero','--p2-spirit','zero','--zero-fields'],
                          input=script,text=True,check=True,capture_output=True)
    public=[l.split() for l in replay.stdout.splitlines() if int(l.split()[0])>=7468]
    assert len(public)==len(rows)==233
    src=Original()
    transitions=[];previous=None;visits=[0,0];pending=0
    for i,(row,raw) in enumerate(zip(rows,public)):
        tick=row[0]
        assert tick==int(raw[0])==7468+i and row[7]==row[15]==18
        for s in (0,1):
            c=23+8*s
            assert row[2+8*s:7+8*s]==[int(raw[j]) for j in (c,c+1,c+2,c+3,c+7)]
        if i:
            beams=src.frame(rows[i-1],row,[t==tick for t in trigger])
            for s in (0,1):visits[s]+=len(beams[s])
            if row[17]==0 and (row[2]==3 or row[10]==3):pending+=1
        current=(row[2],row[10],row[6],row[14],row[17],row[19])
        if current!=previous:
            transitions.append(dict(tick=tick,phase=[row[2],row[10]],effect_phase=[row[6],row[14]],
                                    remaining=[row[4],row[12]],scale=row[17],palette=row[19]))
            previous=current
    assert [t for t,_ in src.callbacks]==[7496,7496+abs(lag)]
    assert pending==abs(lag) and visits[0]==visits[1]==27*6
    assert (rows[-1][2],rows[-1][10],rows[-1][17],rows[-1][19])==(4,4,256,0)
    return dict(lag=lag,controls=trigger,first_round_elapsed=6300,original_instructions=src.instructions,
                real_input_updates=7700,compared_updates=len(rows)-1,ray_object_snapshots=visits,
                pending_world_updates=pending,original_release_callbacks=src.callbacks,transitions=transitions)


def main():
    assert digest(ELF)==PIN
    lib=EXE.parent/'libss6-runtime.a';replay_hash=digest(EXE);lib_hash=digest(lib)
    with tempfile.TemporaryDirectory() as folder:
        exe=Path(folder)/'dual'
        subprocess.run(['c++','-O2','-std=c++20','-I',ROOT/'src',Path(__file__).with_name('zero_dual_probe.cpp'),
                        lib,'-o',exe],check=True)
        with ProcessPoolExecutor(3) as pool:cases=list(pool.map(case,[(exe,lag) for lag in (0,8,-8)]))
    assert replay_hash==digest(EXE) and lib_hash==digest(lib)
    report=dict(status='passed',japanese_elf=PIN,replay_sha256=replay_hash,runtime_sha256=lib_hash,
                viewer_sha256=digest(PACKAGED/'ss6-viewer'),cases=cases)
    REPORT.write_text(json.dumps(report,indent=2)+'\n')
    print([(x['lag'],x['transitions'][-1]['tick']) for x in cases])


if __name__=='__main__':main()
