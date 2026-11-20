#!/usr/bin/env python3
"""Compare each seat's lethal 一閃 in a nondeciding and deciding console VS round."""
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import subprocess
import tempfile
from validate_dash_motion import ASSETS, ELF, PIN, ROOT, digest
from validate_finishing_blow import Comparison, BATTLE, QUEUE, OBJECTS, actor, stats, put
from validate_shin_specials import initialize_pools
from validate_ten_explosion import ABC, REPLAY, play, scenario
from validate_weapon_handling import setup
from validate_input_lifecycle import Boundary

OUT=ROOT/'outputs/ss6-feasibility/ten_issen_finish_validation.json'
BUILD=ROOT/'work/ss6/build-native'
# The console opens its VS menu. Its recorded quote is available in the
# match result structure before that branch, separately from any drawn quote.
DRIVER=r'''
#include "local_versus.hpp"
#include <iostream>
int main(int argc,char** argv) {
    unsigned slot=std::stoul(argv[2]);std::array<unsigned,2> spirits{};
    spirits.at(slot)=3;
    ss6::LocalVersus session(argv[1],-1,ss6::VersusMode::Console,spirits);
    unsigned ticks;std::array<uint32_t,2> previous{},held{};
    while(ss6::readVersusReplaySegment(std::cin,ticks,held)) {
        for(unsigned i=0;i<ticks;++i) {
            std::array<ss6::NormalizedPadSample,2> pads;
            for(unsigned j=0;j<2;++j)pads[j]={held[j],held[j]&~previous[j]};
            session.tick(pads);previous=held;
        }
        const auto& b=session.match().battle();
        std::cout<<b.matchEnd.winner08<<' '<<b.matchEnd.result8c<<' '<<b.endingParameter2c<<' '
                 <<b.match.result.ui<<' '<<b.match.result.result<<' '<<b.match.result.winner<<' '
                 <<b.consoleMenu.active<<' '<<int(b.resultScreen.scene)<<'\n';
    }
}
'''

def inputs(slot,decisive):
    front=(128,64)[slot]
    def pair(n,a=0,b=0):return (n,b,a) if slot else (n,a,b)
    pre,pads=scenario(slot,'lethal')
    if decisive:
        # Earn round one without spending the explosion, then start the lethal
        # case from the first playable state of the second round.
        first=[pair(500)]
        for _ in range(6):first.extend([pair(75,front),pair(5),pair(1,1024),pair(170)])
        wait=play(slot,first,[pair(1)]*1100,'--rage-fields')
        ready=next(int(r[0]) for r in wait if r[45]=='1' and r[1]=='4' and r[9]==r[19]=='200')
        pre=first+[pair(ready-int(wait[0][0])+15)]+pre[1:]
    pads=pads+[pair(1)]*1000
    if not decisive:pads.extend([pair(1,ABC)]+[pair(1)]*90)
    return pre,pads


def original_finish(slot,previous,now,old_wins):
    c=Comparison();p=c.p;initialize_pools(p)
    victim=1-slot
    for i in range(2):
        c.original.install_player(previous,i);p.write(BATTLE+0x24c+i*4,actor(i),4)
        put(p,actor(i),[(0x10c,3 if i==slot else 0),(0xa14,0),(0xa34,200)])
        put(p,stats(i),list(zip((12,24,28,32),map(int,previous[75+4*i:79+4*i]))))
        put(p,stats(i),[(0x28,old_wins if i==slot else 0),(0x2c,2)])
    stdout=p.read(p.read(0x5d1bf8,4)+8,4)
    put(p,stdout,[(0,0x19e0000),(16,0x19e0000)])
    p.write(BATTLE,4,4);p.write(0x12d2698,0,4)
    for order in (OBJECTS,OBJECTS[::-1]):c.run(0x1536e8,list(order))
    c.run(0x1544a0)
    evt=next(QUEUE+108*j for j in range(p.read(0x12d2698,4))
             if p.read(QUEUE+108*j,4)==7 and p.read(QUEUE+108*j+0x40,4)==OBJECTS[slot])
    assert p.read(evt+0x20,4)==31 and c.run(0x155850,[evt])==0
    c.run(0x155a88,[evt,1]);damage=p.read(actor(victim)+0xa38,4)
    assert damage>=int(previous[9+10*victim]) and not int(now[9+10*victim])
    assert p.read(actor(victim)+0x192,2)==int(now[4+10*victim])==58
    assert c.metadata(slot)[2:]==list(map(int,now[77+4*slot:79+4*slot]))==[3,1]
    # Original score computation starts with committed HP; no special case
    # for a captured corpse is supplied to the two-win threshold.
    for i in range(2):
        p.write(0x1fff000+i*4,actor(i),4);p.write(0x1fff020+i*4,stats(i),4)
        p.write(actor(i)+0xa30,int(now[9+10*i]),4)
    p.put(18,BATTLE);c.run(0x143ce0,stop_before=(0x143d54,0x143d58))
    assert p.read(BATTLE+0x24,4)==slot
    assert [p.read(stats(i)+0x28,4) for i in (slot,victim)]==[old_wins+1,0]
    assert c.run(0x145358,[BATTLE])==int(old_wins==1)
    result=dict(raw=31,damage=damage,requested_reaction=58,outcomes=c.metadata(slot)[2:],
                winner=slot,wins_before=old_wins,wins_after=old_wins+1)
    if old_wins:
        p.write(0x4d3d04,0x1d00000,4);c.run(0x145118,[BATTLE],stop_before=(0x139f20,))
        choice=p.read(0x4c3894,4);ptr=c.run(0x1a3070,[0,2,choice]);lines=[]
        for k in range(3):
            addr=p.read(ptr+8+4*k,4)
            if addr:lines.append(bytes(p.memory[addr:p.memory.index(0,addr)]).decode('cp932'))
        assert p.read(0x4c3810,4)==slot and choice==13
        result.update(quote_index=choice,quote_japanese=lines,parameter=p.read(BATTLE+0x2c,4))
    # Reuse this exact hit descriptor and damage accumulator at the original
    # inclusive lethal threshold. Reset only the classifier's one-shot latch.
    source_flags=int(previous[30+26*slot])
    outcomes=[]
    for hp in (damage-1,damage,damage+1):
        p.write(actor(slot)+0x244,source_flags,4);put(p,stats(slot),[(0x1c,-1),(0x20,-1)])
        p.write(actor(victim)+0xa30,hp,4);p.write(actor(victim)+0xa38,damage,4)
        c.run(0x1575d0,[evt,1,0,0])
        outcome=c.metadata(slot)[2:]
        assert outcome==([3,1] if hp<=damage else [-1,-1])
        outcomes.append([hp,outcome])
    result['threshold_hp_and_finish_codes']=outcomes
    result['original_instructions']=c.instructions
    return result


def original_release(slot,decisive):
    # 172a90 keeps ACT430 until it ends even after KO. On release it asks
    # whether the attacker has won the match before restarting the arena music.
    src,_=setup(1-slot);p,a,other,o=src.p,src.a,src.other,src.o
    ctx=0x1981000;p.write(ctx,a,4);p.write(ctx+4,other,4)
    p.write(other+0x194,0x260001,4);p.write(a+0x194,0x3a0002,4)
    p.write(a+0x23c,0x1080,4);p.write(a+0xa30,0,4)
    for i in (0,1):
        at,_=p.run(0x1400d8,[i]);put(p,at,[(0x2c,2),(0x28,(1+int(decisive)) if i==slot else 0)])
    calls=[];instructions=0
    for ended in (0,1):
        p.write(a+0xa3c,-1,4);p.write(o+0xc0,ended,4);p.write(o+0x104,0,4)
        p.write(a+0x190,-1,4);p.write(a+0x18c,0,4)
        # The nondeciding round's next operation hands playback to the IOP.
        # The actor request is already committed at that call boundary.
        music=Boundary(0x13aaf8)
        _,count=p.run(0x172a90,[ctx],limit=500000,stop_before=music)
        if music.stopped==0x13aaf8:calls.append(p.registers[4])
        instructions+=count
        if ended:assert [p.read(a+0x190,2),p.read(a+0x192,2),p.read(a+0x18c,4)]==[2,16,1]
        else:assert p.read(a+0x190,4)==0xffffffff
    assert calls==([] if decisive else [1])
    return instructions


def verify(args):
    exe,slot,decisive=args
    pre,pads=inputs(slot,decisive);v=1-slot
    r=play(slot,pre,pads,'--finish-fields');m=play(slot,pre,pads,'--vs-menu-fields');g=play(slot,pre,pads,'--rage-fields')
    md=subprocess.run([exe,ASSETS,str(slot)],input=''.join('%d %d %d\n'%x for x in pre+pads),
        capture_output=True,text=True,check=True).stdout.splitlines()[len(pre)-1:]
    meta=[list(map(int,line.split())) for line in md]
    hit=next(i for i,x in enumerate(r) if int(x[9+10*v])==0)
    source=original_finish(slot,r[hit-1],r[hit],int(decisive))
    assert r[hit-1][3+10*slot:6+10*slot]==['1','38','227']
    score=next(i for i in range(hit,len(r)) if int(r[i][12+10*slot])==1+int(decisive))
    assert score==hit+2 and r[score][1]=='5' and meta[score][5]==slot
    release=next(i for i in range(hit,len(r)) if r[i][3+10*v:5+10*v]==['2','16'])
    assert all(x[3+10*v:6+10*v]==['2','58','430'] for x in r[hit:release])
    assert all(int(x[28+26*v])&0x80 for x in r[hit:release+1])
    corpse=next(i for i in range(release,len(r)) if r[i][3+10*v:5+10*v]==['2','15'])
    assert not any(x[4+10*v] in ('30','31') for x in r[hit:corpse+1])
    at=lambda i:int(r[i][0])
    result=dict(player=slot+1,deciding_round=decisive,contact=at(hit),opponent_hp_before=int(r[hit-1][9+10*v]),
                attacker_hp=int(r[hit-1][9+10*slot]),score_frame=at(score),release=at(release),corpse=at(corpse),
                ko_ui=meta[score][3],original=source,release_instructions=original_release(slot,decisive))
    if decisive:
        assert meta[score][:3]==[slot,source['quote_index'],source['parameter']]
        assert meta[-1][6:] == [1,0] and int(m[-1][33+slot*2])==1 and int(m[-1][34+v*2])==1
        result.update(menu_winner=int(m[-1][37]),session_wins=int(m[-1][33+slot*2]),session_losses=int(m[-1][34+v*2]),
                      console_next='VS post-match menu',quote_screen_displayed=False)
    else:
        next_round=next(i for i in range(corpse,len(g)) if g[i][45]=='1' and g[i][1]=='4')
        assert all(int(x[23+slot*11])==3 for x in g[next_round:])
        assert not any(x[3+slot*10]=='1' and x[4+slot*10] in ('36','38') for x in r[next_round:])
        src,_=setup(slot);p,a=src.p,src.a
        p.write(a+0x10c,3,4);p.write(a+0x120,3,4)
        src.run(0x14ec80,a+0x10c);src.run(0x179258,a+0x2c4,a+0x10c)
        assert p.read(a+0x120,4)==3
        out=src.frame(ABC)
        result.update(next_round=at(next_round),next_round_hp=int(g[next_round][9+10*slot]),spent_phase=3,
                      original_ABC_state=out[0],native_ABC_state=int(r[-91][3+10*slot])|(int(r[-91][4+10*slot])<<16))
        assert result['native_ABC_state']==result['original_ABC_state'] and out[0] not in (0x240001,0x260001)
    return result


def main():
    assert digest(ELF)==PIN
    with tempfile.TemporaryDirectory(prefix='ss6-issen-finish-') as temp:
        cpp=Path(temp)/'view.cpp';exe=Path(temp)/'view';cpp.write_text(DRIVER)
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',cpp,BUILD/'libss6-runtime.a','-o',exe],check=True)
        with ProcessPoolExecutor(4) as pool:cases=list(pool.map(verify,[(exe,s,k) for s in range(2) for k in (False,True)]))
    OUT.write_text(json.dumps(dict(status='passed',original_sha256=PIN,replay_sha256=digest(REPLAY),
        validator_sha256=digest(Path(__file__)),cases=cases),indent=2,ensure_ascii=False)+'\n')
    print('4 lethal Issen rounds matched the Japanese finish, score, quote and capture release')
if __name__=='__main__':main()
