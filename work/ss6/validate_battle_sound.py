#!/usr/bin/env python3
"""Check the Japanese ACT dispatcher and the combat code issuing actual sound requests."""
import hashlib
import itertools
import json
import struct
import subprocess
import tempfile
from pathlib import Path

from mips_probe import signed
from validate_finishing_blow import CHILD, actor, put, stats
from validate_haohmaru_special import (
    BUILD, ELF, OBJECTS, QUEUE, RES, ROOT, SOURCE_HASH, ContactOracle, initialize_effects, pads_for, run_native,
)
from validate_shake_inputs import inputs

DRIVER = r'''
#include "sound_selection.hpp"
#include <iostream>
using namespace ss6;
int main(int argc,char** argv) {
    SoundSelection sound(argv[1]); GameRandom rng;
    int op,a,b,c,d,e,f;
    while(std::cin>>op>>a>>b>>c>>d>>e>>f>>rng.mode>>rng.gameSeed>>rng.librarySeed) {
        sound.beginFrame();
        if(op==0)sound.act(a,b,0,c,d,e,rng);
        else sound.contact(a,b,c,d,e,f,rng);
        std::cout<<rng.gameSeed<<' '<<rng.librarySeed;
        for(const auto& v:sound.events())std::cout<<' '<<int(v.kind)<<' '<<v.bank<<' '<<v.tone;
        std::cout<<'\n';
    }
}
'''


def events_at(p, dest):
    def observe(pc):
        a, b = (signed(p.registers[i], 32) for i in (4, 5))
        if pc == 0x1e7b70:
            dest.append((0, a + 1, b))
        elif pc == 0x1e7d60:
            dest.append((1, a, b))
        elif pc == 0x1e7aa8:
            dest.append((2, 0, a))
    return observe


def seed(p, mode, game, library):
    p.write(0x443150, mode, 4)
    p.write(0x3d2e80, game, 4)
    p.write(p.read(0x5d1bf8, 4) + 0xa8, library, 8)


def rng_state(p):
    return [p.read(0x3d2e80, 4), p.read(p.read(0x5d1bf8, 4) + 0xa8, 8)]


def sound_oracle():
    case = ContactOracle()
    p = case.probe
    p.write(0x345188, 0, 4)
    for seat in (0, 1):
        put(p, actor(seat), [(0, OBJECTS[seat]), (0xa10, 0), (0xa24, seat)])
        put(p, OBJECTS[seat], [(0xc, seat), (0x10, seat), (0xcc, seat)])
    return case


def matrix():
    p = sound_oracle().probe
    for seat in (-1, 0, 1):
        p.run(0x1e7968, [seat, 23], stop_before=[0x212fa0])
        assert p.registers[4:6] == [seat + 1, 23]
    commands, expected = [], []
    game, library = 1, 1
    n = 0
    # Feed the same persistent previous-value cells across both players.
    # 1e7b70 is observed BEFORE its hardware-enable switch: selection and
    # both real RNG draws still execute while hardware output is disabled.
    for seat, mode, flags, command in itertools.product((0, 1), (0, 3), (0, 128),
            [1, 31, 99, 100, *range(149, 161), 169, 170, 197, 198, 259, 260, 275, 299, 300, 322, 0x6098, 0xa09b]):
        stage = n % 12
        game_mode = (3, 13, 14)[n % 3]
        commands.append([0, command, seat, flags, game_mode, stage, 0, mode, game, library])
        seed(p, mode, game, library)
        p.write(0x4c3808, game_mode, 4)
        p.write(0x4c380c, stage, 4)
        p.write(actor(seat) + 0x23c, flags, 4)
        out = []
        p.run(0x1e8298, [seat, command, 0], limit=12000, observe=events_at(p, out))
        game, library = rng_state(p)
        expected.append([game, library, *itertools.chain.from_iterable(out)])
        n += 1
    act_count = n
    event = 0x1e05000
    put(p, event, [(0x40, OBJECTS[0]), (0x68, OBJECTS[1])])
    for group, defense, armed, lethal, counter, action in itertools.product(
            range(6), (0, 1, 2, 3, 4), (0, 1), (0, 1), (0, 1), (189, 529)):
        mode = n % 2
        commands.append([1, group, defense, armed, lethal, counter, action, mode, game, library])
        seed(p, mode, game, library)
        put(p, event, [(0x24, group), (0x60, counter)])
        put(p, actor(1), [(0xa30, 35), (0xa38, 36 * lethal), (0x23c, armed << 12), (0x240, 0)])
        put(p, stats(0), [(0x28, 1), (0x2c, 2)])
        put(p, OBJECTS[0], [(0x24, action)])
        out = []
        p.run(0x156d68, [event, defense, 0], limit=20000, observe=events_at(p, out))
        game, library = rng_state(p)
        expected.append([game, library, *itertools.chain.from_iterable(out)])
        n += 1
    with tempfile.TemporaryDirectory() as tmp:
        main = Path(tmp) / 'sound.cpp'
        main.write_text(DRIVER)
        binary = Path(tmp) / 'sound'
        subprocess.run(['c++', '-std=c++20','-ffp-contract=off', '-I', str(ROOT / 'src'), str(main),
                        str(BUILD / 'libss6-runtime.a'), '-o', str(binary)], check=True)
        result = subprocess.run([binary, RES], text=True, capture_output=True, check=True,
                                input=''.join(' '.join(map(str, c))+'\n' for c in commands))
    actual = [list(map(int, r.split())) for r in result.stdout.splitlines()]
    assert len(actual) == len(expected)
    for i, (got, want) in enumerate(zip(actual, expected)):
        assert got == want, (i, commands[i], got, want)
    return act_count, n - act_count


def frame_events(row):
    n = int(row[25])
    values = list(map(int, row[26:]))
    assert len(values) == 3*n
    return [tuple(values[i:i+3]) for i in range(0, len(values), 3)]


def world(move, seat, stance):
    pads = ['500 0 0'] + [f'1 {a} {b}' for a, b in inputs(move, seat, stance)]
    def replay(fields):
        return run_native('ss6-match-replay', pads, '--mode', 'versus', fields)
    sounds = replay('--sound-fields')
    fighters = replay('--finish-fields')
    children = replay('--whirlwind-fields') if isinstance(move, int) and move < 67 else None
    original = sound_oracle()
    p = original.probe
    initialize_effects(p)
    for name in (0x1123a8, 0x112570, 0x11e290):
        p.run(name)
    for index, name in enumerate(('01HitFlash.bin', '02Guard.bin', '03etc.bin')):
        at = 0x4a4810 + index*0x3da0
        p.memory[at:at+0x3da0] = (RES/name).read_bytes()
    for i in range(32):
        p.write(0x4c3510+4*i, i+1, 4)
    stdout = p.read(p.read(0x5d1bf8,4)+8,4)
    put(p, stdout, [(0,0x19e0000), (16,0x19e0000)])
    victim = 1-seat
    contacts, records = [], []
    for idx, (old, now) in enumerate(zip(fighters, fighters[1:]), 1):
        frame = int(now[0])
        heard = frame_events(sounds[idx])
        column = 10+10*seat
        if old[column:column+2] == now[column:column+2]:
            if stance != 'whiff':
                continue
            was, cur = [(int(r[5+10*seat]),int(r[6+10*seat])) for r in (old,now)]
            if was==cur:
                assert not heard, (move, seat, frame, heard)
                continue
            first = struct.unpack_from('<h',original.aid,2*cur[0])[0]
            command = struct.unpack_from('<h',original.act,60*(first+cur[1])+56)[0]
            if command:
                seed(p,0,*map(int,sounds[idx-1][23:25]))
                expected=[]
                p.run(0x1e8298,[seat,command,0],limit=12000,observe=events_at(p,expected))
                assert heard==expected,(move,seat,frame,was,cur,command,heard,expected)
                assert rng_state(p)==list(map(int,sounds[idx][23:25]))
                records.append([frame,*cur,*expected])
            else:
                assert not heard,(move,seat,frame,heard)
            continue
        for i in (0,1):
            original.install_player(old,i)
            put(p, stats(i), [(12,int(old[75+4*i])),(0x28,int(old[12+10*i])),(0x2c,2)])
            put(p, actor(i), [(0xa38,0)])
        source = OBJECTS[seat]
        if children is not None:
            source=CHILD
            words=list(map(int,children[idx-1][131:211]))
            assert len(words)==80 and words[0xcc//4]==2
            struct.pack_into('<80I',p.memory,source,*words)
            bank=0x17c0000
            p.memory[bank:bank+len(original.jdg)]=original.jdg
            p.write(0x4751e0+seat*4,bank,4)
            for obj,act,step,refs in ((OBJECTS[seat],*map(int,old[5+seat*10:7+seat*10]),0x17a0000),
                                      (source,words[9],words[10],0x17a0100)):
                first=struct.unpack_from('<h',original.aid,act*2)[0]
                p.memory[refs:refs+16]=original.act[60*(first+step)+14:60*(first+step)+30]
                p.write(obj+0xbc,refs,4)
        p.write(0x12d2698,0,4)
        for pair in ((source,OBJECTS[victim]),(OBJECTS[victim],source)):
            p.run(0x1536e8,pair,limit=100000)
        p.run(0x1544a0,limit=50000)
        e = next(e for e in (QUEUE+108*j for j in range(p.read(0x12d2698,4)))
                 if p.read(e,4)==7 and p.read(e+0x40,4)==source)
        defense,_=p.run(0x155850,[e])
        assert bool(defense)==(stance=='guard')
        seed(p,0,*map(int,sounds[idx-1][23:25]))
        expected=[]
        p.run(0x155d50 if defense else 0x155a88,[e,int(children is None),defense],
              limit=500000,observe=events_at(p,expected))
        if expected:
            assert heard[:len(expected)]==expected,(move,seat,frame,heard,expected)
        else:
            # 156edc suppresses the primary guard sound for group 5.
            assert defense and p.read(e+0x24,4)==5 and all(sound[1]!=0 for sound in heard)
        contacts.append([frame,defense,*expected])
    if stance=='whiff':
        assert len(records)>=2 and not contacts
    else:
        assert contacts
    return dict(move=move,seat=seat,stance=stance,frames=len(sounds)-1,contacts=contacts,miss_records=records)


def blade_interactions():
    lock = ['500 0 0','20 128 64','15 0 0','1 1024 1024'] + ['1 0 0']*210
    rows = run_native('ss6-match-replay',lock,'--sound-fields')
    tones = [(int(r[0]),tone) for r in rows if r[4]=='31' for k,bank,tone in frame_events(r)
             if (k,bank)==(0,0) and tone in (22,62)]
    assert [t for _,t in tones]==[22,62,62] and tones[2][0]-tones[1][0]==96
    # 144a64 and 144bf8 both reach 1e7b70 with a direct zero-based index.
    p = sound_oracle().probe
    for pc,tone in ((0x144a60,22),(0x144bf4,62)):
        p.run(pc,stop_before=[0x1e7b70])
        assert (signed(p.registers[4],32),p.registers[5])==(-1,tone)
    cases=[]
    for seat,bare in itertools.product((0,1),(False,True)):
        f=(128,64)[seat]
        pair=lambda a,b:(b,a) if seat else (a,b)
        command=pads_for(24 if bare else 23,1-seat)
        pads=[(0,0)]*500+[pair(f,0)]*66+[(0,0)]*4
        if bare:
            pads += [pair(0,(f^192)|8)] + [(0,0)]*125
        pads += [pair(1024 if j==5 else 0,command[j-5] if 5<=j<5+len(command) else 0) for j in range(62)]
        data=[f'1 {a} {b}' for a,b in pads]
        sounds=run_native('ss6-match-replay',data,'--sound-fields')
        fighters=run_native('ss6-match-replay',data,'--contact-fields')
        original=sound_oracle()
        p=original.probe
        from validate_combined_slash import initialize_pools
        initialize_pools(p)
        last=None
        next_channel=14
        seen=False
        for idx,row in enumerate(sounds):
            events=frame_events(row)
            if (0,0,63 if bare else 22) in events and not seen:
                for i in (0,1):
                    original.install_player(fighters[idx-1],i)
                put(p,actor(1-seat),[(0xa48,4 if bare else 3)])
                assert last is not None
                p.write(OBJECTS[seat]+0x34,0xc000|last,4)
                p.write(0x12d2698,0,4)
                for pair_ in (OBJECTS,OBJECTS[::-1]):
                    p.run(0x1536e8,pair_,limit=60000)
                p.run(0x1544a0)
                ev=next(ev for ev in (QUEUE+108*n for n in range(p.read(0x12d2698,4)))
                        if p.read(ev,4)==2 and p.read(ev+0x40,4)==OBJECTS[seat])
                expected=[]
                accepted,_=p.run(0x154e10,[ev],limit=800000,observe=events_at(p,expected))
                assert accepted and expected==[(0,0,63 if bare else 22),(2,0,last)] and events[:2]==expected
                assert p.read(OBJECTS[seat]+0x34,4)==0
                seen=True
                cases.append(dict(seat=seat,bare=bare,tick=int(row[0]),events=expected))
            for k,bank,tone in events:
                if k==0 or k==4 or (k==1 and bank==50):
                    if k==0 and bank==seat+1 and row[5+10*seat]=='189':
                        last=next_channel
                    next_channel=14 if next_channel==21 else next_channel+1
        assert seen
    return dict(lock=tones,parry=cases)


def knockout(seat):
    data=['500 0 0']+[f'1 {a} {b}' for a,b in inputs('heavy-KO',seat,'hit')*3]
    rows=run_native('ss6-match-replay',data,'--mode','versus','--sound-fields')
    cues=[]
    victim=1-seat
    for row in rows:
        if int(row[9+10*victim])!=0:
            continue
        for kind,bank,tone in frame_events(row):
            if kind==0 and bank==victim+1 and tone in (26,27):
                cues.append([int(row[0]),int(row[12+10*seat]),tone])
    assert [r[1:] for r in cues]==[[1,26],[2,27]],cues
    # Replay the actual timer increment, the >=7-tick gate and the winner
    # lookup. A second visit after acceptance must not issue another voice.
    p=sound_oracle().probe
    for _,wins,tone in cues:
        a=actor(victim)
        put(p,a,[(0x23c,0x80),(0x248,0),(0x1ac,256),(0x218,0x600)])
        put(p,stats(seat),[(0x28,wins),(0x2c,2)])
        for expected in ([],[(0,victim+1,tone)],[]):
            heard=[]
            p.registers[17]=a
            p.run(0x149548,stop_before=[0x14959c],observe=events_at(p,heard))
            assert heard==expected,(seat,tone,expected,heard)
    return dict(seat=seat,knockout_voices=cues)


if __name__=='__main__':
    assert hashlib.sha256(ELF.read_bytes()).hexdigest()==SOURCE_HASH
    act,impact=matrix()
    worlds=[world(move,seat,stance) for seat in (0,1)
            for move in ('heavy',64,65,66,69,70,74,80)
            for stance in (('hit','guard','whiff') if move=='heavy' else ('hit','guard'))]
    blades=blade_interactions()
    knockouts=[knockout(seat) for seat in (0,1)]
    report=dict(status='passed',elf_sha256=SOURCE_HASH,match_sha256=hashlib.sha256((BUILD/'ss6-match-replay').read_bytes()).hexdigest(),blade_interactions=blades,knockouts=knockouts,
                original_act_calls=act,original_contact_sound_calls=impact,world_cases=worlds,
                scope='CPU requests for resource 00 and both controller ports. ACT lookup and real collision handlers run from the Japanese executable. '
                      'Contact snapshots seed the shared generators before original visual effects and audio selection. Hardware playback is a separate test.')
    (ROOT/'outputs/ss6-feasibility/battle_sound_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f'{act} ACT dispatches, {impact} collision sound selections, {len(worlds)} real controller cases')
