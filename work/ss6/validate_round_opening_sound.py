#!/usr/bin/env python3
"""Compare opening audio in the caption scheduler to the Japanese EE callbacks."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from extract_combat_sound_bank import ISO, ELF_SHA, ROOT
from inspect_iso import Iso
from mips_probe import Probe
from round_entry_oracle import buffered_stdout
from validate_scheduled_opening import ASSETS, B, A, O, OWNERS, OBJECTS, bits

REPORT = ROOT/'outputs/ss6-feasibility/round-opening-sound-validation.json'
DRIVER = r"""
#include "round_control.hpp"
#include "sound_selection.hpp"
#include <iostream>
int main(int argc,char** argv) {
    ss6::SoundSelection sound(argv[1]);ss6::ScheduledOpening opening(argv[1],&sound);
    ss6::ActionBank bank(argv[1],true);ss6::StageEventRules events(argv[1]);
    ss6::PlayerObject p0(bank,189),p1(bank,189);
    std::array<ss6::StateEntryActor,2> a;std::array<ss6::ActorCommandInput,2> i;
    std::array<ss6::InputSystemConfig,2> cfg;std::array<ss6::RoundActorStorage,2> storage;
    std::array<ss6::CallbackContext,2> ctx;
    const std::array<ss6::RoundPlayerRef,2> players{{
       {p0,a[0],i[0],cfg[0],storage[0],ctx[0]}, {p1,a[1],i[1],cfg[1],storage[1],ctx[1]}}};
    int index,wins,volume,pause,frames;
    while(std::cin>>index>>wins>>volume>>pause>>frames) {
        ss6::BattleRoundState b;auto& pools=b.entry.tasks;
        pools.initializeOwners();pools.initializeTasks();pools.initializeObjects();
        for(unsigned n=0;n<32;++n)b.effectResidency.slots[n]=n+1;
        b.match.roundIndex=index;b.audio.streamParameter5a9e78=volume;b.stageEvent.x=320;
        for(auto& player:b.match.players){player.wins=wins;player.requiredWins=2;}
        for(int tick=0;tick<=frames;++tick){
            sound.beginFrame();
            if(!tick) {
                if(index>=0)ss6::RoundControl::enterOpening(b,players,events,opening,&sound);
                else {
                    b.match.result.result=(-index==19)?3:(-index==18)?1:0;
                    for(auto& actor:a)actor.flags23c=0x90;
                    b.openingOwner30=opening.startEnding(unsigned(-index),pools,b.effectResidency);
                }
            }
            else {
                if(index<0)ss6::RoundControl::ending(b,players,opening);
                std::vector<ss6::EffectDraw> draws;ss6::TaskDispatch handlers;
                handlers.call=[&](uint32_t,uint32_t h){opening.task(h,pools,b.effectResidency,b.paletteState,draws,pause&&tick>30&&tick<=45);};
                pools.dispatchTasks(handlers);
            }
            for(const auto& e:sound.events())std::cout<<tick<<' '<<int(e.kind)<<' '<<e.bank<<' '<<e.tone<<'\n';
        }
        std::cout<<"end\n";
    }
}
"""


def expected(raw, iso, case):
    index,wins,volume,pause,frames = case
    p = Probe(raw, finite_model=True)
    def w(a,v): p.write(a,v,4)
    buffered_stdout(p)
    for adr, name in [(0x5a0a98,'BVOICE2'),(0x59d028,'BVOICE1'),(0x5a89c8,'NAL')]:
        h=iso.read('/VOICE/'+name+'.MSH');p.memory[adr:adr+len(h)]=h
    for bank,name in [(5,'Display.bin'),(6,'Display2.bin'),(7,'Display3.bin')]:
        raw_bank=(ASSETS/name).read_bytes();adr=0x4a4810+(bank-1)*0x3da0
        p.memory[adr:adr+len(raw_bank)]=raw_bank
    for ad,length in [(OWNERS,512*4),(OBJECTS,256*320),(0x1232440,258*4),(0x3d3698,257*4)]:
        p.memory[ad:ad+length]=bytes(length)
    insns=0
    captured=[]
    tick=0
    def trace(pc):
        if pc==0x1e7d60:captured.append([tick,1,p.registers[4],p.registers[5]])
    def run(pc, args=(), stop=()):
        nonlocal insns
        _,n=p.run(pc,args,stop_before=stop,observe=trace,limit=200000)
        insns+=n
    for pc in (0x1123a8,0x112570,0x11e290):run(pc)
    for i in range(32):w(0x4c3510+i*4,i+1)
    w(0x345188,1);w(0x4d3d00,B);w(0x4d3d08,A);w(B+0x18,index)
    for i in range(2):
        w(B+0x24c+i*4,A+i*0xf2c);w(A+i*0xf2c,O+i*0x1000)
        w(O+i*0x1000+0x40,bits(280+i*80))
        w(B+0x254+i*0x108+0x28,wins);w(B+0x254+i*0x108+0x2c,2)
    w(0x132c0e8,bits(320));w(0x5a9e78,volume)
    sp=0x1fff000;p.registers[16]=B;p.registers[17]=1
    w(sp+0x20,B+0x254);w(sp+0x24,B+0x35c);p.write(sp+0x40,0x1ffff00,8)
    # The ordinary 143930 business tail bypasses only the opening console log.
    # If a live resident sound reaches its RPC, stop at the hardware boundary.
    if index>=0:
        run(0x14398c,stop=(0x213b98,))
    else:
        # 143c60's descriptor has already been selected. Exercise the real
        # spawn call through 143ee4 and, subsequently, the full 144020 loop.
        p.put(18,B);p.put(22,-index);p.write(sp+0x78,0x1ffff00,8)
        w(B+0x28,3 if index==-19 else 1 if index==-18 else 0)
        for actor in (A,A+0xf2c):w(actor+0x23c,0x90)
        run(0x143ea8)
    if not index and volume:
        addr,pitch,vol=p.registers[4:7]
        header=iso.read('/VOICE/BVOICE1.MSH')
        off=struct.unpack_from('<I',header,49*272+20+8*12)[0]
        assert addr==0x146010+off and pitch==0x761
        captured.append([tick,4,vol,12])
    for tick in range(1,frames+1):
        w(0x46a924,int(pause and 30<tick<=45));w(0x4a2250,0)
        if index<0:run(0x144020,[B])
        run(0x112838)
    return captured,insns


def stream_paths(raw,iso):
    p=Probe(raw,finite_model=True)
    buffered_stdout(p);p.write(0x345188,1,4);p.write(0x43d056,0,1)
    output={}
    for label,pc,track,loop in [('victory',0x1e7ce8,24,0),('stage',0x2140b8,5,1)]:
        p.run(pc,[track,loop,0x144548],stop_before=(0x213d80,),limit=20000)
        pending=p.read(0x1553b40,4)
        # Phase 3 consumes the pending ID and formats BOTH paths via sprintf.
        p.run(0x214380,stop_before=(0x2139d8,),limit=100000)
        paths=[bytes(p.memory[a:a+40]).split(bytes(1))[0].decode() for a in p.registers[4:6]]
        names=[name.removesuffix(';1').replace(chr(92),'/') for name in paths]
        assert all(name in iso.by_path for name in names)
        output[label]=dict(pending=pending,paths=names)
    assert output['victory']['paths']==['/BGM2/BGM24_L.VB','/BGM2/BGM24_R.VB']
    assert output['stage']['paths']==['/BGM1/BGM05_L.VB','/BGM1/BGM05_R.VB']
    return output


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--iso',type=Path,default=ISO)
    ap.add_argument('--report',type=Path,default=REPORT)
    args=ap.parse_args()
    iso=Iso(args.iso);raw=iso.read('/SLPS_255.59')
    assert sha256(raw).hexdigest()==ELF_SHA
    defaults=Probe(raw,finite_model=True)
    defaults.run(0x1183f8,[0x57974c])
    # 1b8bc0..1b8bf4 copy seven option bytes with unaligned MIPS transfers.
    # Supply those exact bytes before executing the original gain arithmetic.
    defaults.memory[0x43d050:0x43d057]=defaults.memory[0x57974c:0x579753]
    defaults.put(15,0x440000);defaults.run(0x1b8bf8)
    volume=defaults.read(0x5a9e78,4)
    assert volume==12800 and defaults.read(0x43d055,1)==0
    # Test the first, second, and tied deciding round through owner release.
    # Include alternate labels and the exact zero-volume gate on the first round.
    cases=[(0,0,volume,0,200),(1,0,volume,0,140),(2,1,volume,1,160),
           (0,0,0,0,0),(0,0,511,0,0),(0,0,512,0,0)]
    cases.extend((i,0,volume,0,0) for i in range(2,11))
    cases.extend((-i,0,volume,0,0) for i in range(15,20))
    cases.extend([(-19,0,volume,0,180),(-19,2,volume,1,230),(-18,2,volume,0,180)])
    with tempfile.TemporaryDirectory() as temp:
        temp=Path(temp);src=temp/'probe.cpp';src.write_text(DRIVER);exe=temp/'probe'
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',str(ROOT/'src'),str(src),
                        *[str(ROOT/'src'/f) for f in ('round_control.cpp','scheduled_opening.cpp','sound_selection.cpp')],
                        str(ROOT/'work/ss6/build-native/libss6-runtime.a'),'-o',str(exe)],check=True)
        text=subprocess.check_output([str(exe),str(ASSETS)],input=''.join(' '.join(map(str,c))+'\n' for c in cases),text=True)
    native=text.split('end\n');assert native.pop()==''
    result=[];instructions=0
    for c,got in zip(cases,native,strict=True):
        actual=[list(map(int,line.split())) for line in got.splitlines()]
        original,n=expected(raw,iso,c)
        assert actual==original,(c,actual,original)
        instructions+=n;result.append(dict(round_index=c[0],wins=c[1],volume=c[2],pause=bool(c[3]),ticks=c[4],events=actual))
    report=dict(status='passed',source_sha256=ELF_SHA,original_instructions=instructions,
                scope='EE round-entry tail with active sound driver, actual numbered caption/NAL callbacks and whole 112838 task dispatches. Resident jingle observed before SIF/RPC. Tick 0 is caption creation. Each event is tick / kind / character or volume code / tone.',cases=result,stream_file_service=stream_paths(raw,iso),ending_fixtures='Negative indices are ending caption descriptor numbers, all five original 124548 table entries. Three persistent ending chains use whole original 144020 before each task dispatch, with both actors marked airborne and defeated.')
    data=json.dumps(report,indent=2);args.report.write_text(data+'\n');print(data)


if __name__=='__main__':
    main()
