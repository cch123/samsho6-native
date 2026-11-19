"""Compare Ken Haohmaru's two super moves with original Japanese player callbacks."""
from concurrent.futures import ProcessPoolExecutor
from itertools import product
import json
import struct
import sys

from validate_shin_specials import (
    ELF, PIN, REPLAY, ROOT, compare_contacts, configure, digest, objects,
    pad_actor, read, setup_actor, verify_weapon,
)

REPORT = ROOT/'outputs/ss6-feasibility/ken_specials_validation.json'


def sequence(slot, move, case):
    forward = (128, 64)[slot]
    back = forward ^ 192

    def p(n, own=0, other=0):
        return (n, other, own) if slot else (n, own, other)

    pre = [p(500)]
    if case == 'mikiri':
        # Four heavy hits and one light leave 46 HP, above the factory cap.
        # Retreat from the corner together, then let the next heavy strike
        # the real afterimage. The fighter takes no damage on that contact.
        pre += [p(65,0,back),p(5),p(1,0,1024),p(100)]*4
        pre += [p(65,0,back),p(5),p(1,0,256),p(75),p(120,forward,forward),p(8)]
        pre += [p(1,0,1024),p(11),p(1,4096),p(1),p(1),p(88)]
    elif move == 79:
        pre += [p(65, 0, back), p(5), p(1, 0, 1024), p(100)] * 5
    else:
        # Each completed flask command earns three rage points even when it
        # misses. The second player can thus keep all 200 HP for the test.
        pre += [p(1, 32), p(1, 32|back), p(1, back|2048), p(43)] * 62
    if case == 'bare':
        pre += [p(1, 0, back|8), p(150)]
    if case == 'unarmed-source':
        pre += [p(1, forward|8), p(150)]
    if case == 'lethal':
        pre += [p(65, forward), p(5), p(1, 1024), p(105)] * 5
    pre += [p(230, back, forward), p(5)] if case in ('miss', 'repeat') else [p(75, forward), p(5)]
    launch = [p(1, 32), p(1, 32|forward), p(1, (1536 if move==79 else 768)|forward)]
    if case == 'repeat':
        # After 1/79 returns to idle, retry once inside the cooldown, then
        # after the reserve has risen above HP again, all in the same round.
        post = launch + [p(175)] + launch + [p(250)] + launch + [p(275)]
    else:
        post = launch + [p(320, 0, forward if case=='guard' else 0)]
    return pre, [(1,a,b) for n,a,b in post for _ in range(n)]


def play(slot, flags, pads):
    return read(REPLAY, ['--mode','versus', f'--p{slot+1}-spirit','ken', *flags],
                ['%d %d %d'%r for r in pads])


def pickup(slot, pads, last):
    target = 1-slot
    blade = objects(last)[target][1]
    assert len(blade)==1 and blade[0][0]==467
    x = struct.unpack('<f', struct.pack('<I',blade[0][2]))[0]
    forward = 128 if float(last[7+10*target]) < x else 64

    def p(n, button=0):
        return (n, 0, button) if target else (n, button, 0)

    approach = play(slot, ['--shin-fields'], pads+[p(1, forward)]*260)[len(pads)-1:]
    n = next(i for i,r in enumerate(approach) if abs(float(r[7+10*target])-x) < 12)
    after = ([p(n,forward)] if n else [])+[p(4),p(1,256)]+[p(1)]*55+[p(1,1024)]
    rows = play(slot,['--shin-fields'],pads+after)[len(pads):]
    picked = next(r for r in rows if int(r[4+10*target])==51)
    assert objects(picked)[target][1]==[] and int(picked[28+26*target])&0x1000
    assert int(rows[-1][5+10*target]) in (189,190)
    return dict(landing_act=467, picked_up=int(picked[0]), next_heavy=int(rows[-1][5+10*target]))


def source_select(slot, row, meter, move):
    src=setup_actor(slot); configure(src,5)
    p,a=src.p,src.a
    forward=(128,64)[slot]
    own,other=23+26*slot,23+26*(1-slot)
    for off,col in ((0x23c,5),(0x244,7),(0x248,8),(0x120,16),(0x124,17),(0x134,18),(0x138,19)):
        p.write(a+off,int(row[own+col]),4)
    p.write(a+0xa30,int(row[9+10*slot]),4); p.write(a+0x158,meter,4)
    p.write(src.o+0x38,int(row[own+2]),4)
    p.write(src.o+0x40,int(row[own]),4); p.write(src.o+0x1040,int(row[other]),4)
    p.write(src.b+0x144,abs(int(float(row[7])-float(row[17]))),4)
    for key in (32,32|forward,forward|(1536 if move==79 else 768)):
        snap=src.frame(key)
    return (snap[0]&0xffff, snap[0]>>16, snap[54]), src.instructions


def validate(spec):
    slot,move,case=spec
    target=1-slot; own=3+10*slot; j=23+8*slot
    pre,pads=sequence(*spec); start=len(pre)-1

    def trace(*flags):
        return play(slot,flags,pre+pads)[start:]

    rows=trace('--shin-fields'); meters=trace('--ken-fields')
    assert int(meters[0][j+3])==(16640 if case=='mikiri' else 8192)
    assert int(meters[0][j+4])==int(move==78)
    assert int(meters[0][j+7])==(46 if case=='mikiri' else 19 if move==79 else 200)
    evasion=None
    if case=='mikiri':
        history=play(slot,['--ken-fields'],pre)
        before,after=next((u,v) for u,v in zip(history,history[1:]) if int(v[j+3])>int(u[j+3]))
        assert (int(before[j+3]),int(after[j+3]))==(8192,16640)
        assert int(before[j+7])==int(after[j+7])==46
        assert int(after[0])==1473
        evasion=dict(frame=int(after[0]),remaining_life=46,previous_reserve=8192,earned_reserve=16640)
    openings=[];ins=0
    # The direction sequence is submitted in three one-tick segments.
    # Independently execute all three on the original actor, including the
    # two held-button fallbacks while the secret reserve is unavailable.
    for i,(count,a,b) in enumerate(pads,1):
        if (b if slot else a)&(768 if move==78 else 1536) != (768 if move==78 else 1536):
            continue
        want,n=source_select(slot, rows[i-3], int(meters[i-3][j+3]), move)
        got=tuple(map(int, rows[i][own:own+3]))
        assert want==got,(spec,i,got,want)
        openings.append(dict(tick=int(rows[i][0]), state=list(got), reserve=int(meters[i-3][j+3])))
        ins+=n
    if case=='unarmed-source':
        assert openings[0]['state'][1]!=move
        return dict(player=slot+1,move=move,case=case,commands=openings,original_instructions=ins)
    if case=='repeat':
        assert [v['state'][1] for v in openings]==[79,66,79],(spec,openings)
        assert [v['reserve'] for v in openings]==[8192,0,8192]
    else:
        assert [v['state'][1] for v in openings]==[move],(spec,openings)
    clocks={int(r[0]):int(r[24]) for r in trace('--round-time','60')}
    body=pad_actor(slot,move,'miss' if case=='miss' else 'hit',rows,pads,5,int(meters[0][j+3]),clocks)
    spirits=[0,0]; spirits[slot]=5
    sounds={int(r[0]):r for r in trace('--sound-fields')}
    contacts,n=compare_contacts(slot,move,rows,spirits,sounds)
    if case!='repeat':
        assert len(contacts)==({78:{'hit':1,'guard':4,'miss':0,'bare':1,'lethal':1},
                                79:{'hit':10,'guard':8,'miss':0,'bare':10,'lethal':10,'mikiri':10}}[move][case]),(spec,contacts)
    assert all(bool(e['defense'])==(case=='guard') for e in contacts)
    if case=='lethal':
        assert int(rows[-1][9+10*target])==0
    seen={}
    for row in rows:
        _,children=objects(row)[target]
        for child in children:seen.setdefault(child[0],int(row[0]))
    flight=recovered=None
    if move==78 and case in ('hit','lethal'):
        assert all(e['raw']==39 for e in contacts) and seen[466]==contacts[0]['frame']
        assert not any(a in seen for a in (468,469,470,471))
        flight=verify_weapon(slot,rows,5,0,contacts[0]['post_contact_library_seed'],first_only=case=='lethal',battle_clocks=clocks)
        if case=='hit':recovered=pickup(slot,pre+pads,rows[-1])
    elif case!='bare':
        assert not any(466<=a<=471 for a in seen)
    else:
        assert all(len(objects(r)[target][1])==1 for r in rows)
    # The consumption belongs to the transition out of this attack, after
    # the active/capture phase. A missed attack spends the same gauge.
    if case not in ('lethal','repeat'):
        release=next(i for i in range(4,len(rows)) if rows[i-1][own+1]==str(move) and rows[i][own+1]!=str(move))
        before,after=meters[release-1],meters[release]
        if move==79:assert int(before[j+3])>=8192 and list(map(int,after[j:j+4]))==[1,150,256,0]
        else:assert int(before[j+4])==1 and list(map(int,after[j+4:j+6]))==[0,0]
    return dict(player=slot+1,move=move,case=case,commands=openings,contacts=contacts,
                actor=body,weapon=flight,pickup=recovered,evasion=evasion,
                original_instructions=ins+n+body['original_instructions'])


def boundaries(slot):
    source=setup_actor(slot); configure(source,5); p=source.p
    commands=struct.unpack_from('<3h',p.memory,source.a+0x2c4+0x644+2*14)
    assert commands==(173,174,177)
    out=[]
    for hp,amount in [(32,8192),(33,8192),(32,8191),(1,256),(1,255)]:
        src=setup_actor(slot); configure(src,5); p,a=src.p,src.a; f=(128,64)[slot]
        p.write(a+0xa30,hp,4);p.write(a+0x158,amount,4)
        for key in (32,32|f,f|1536):r=src.frame(key)
        want=79 if hp*256<=amount else 66
        assert (r[0],r[54])==((want<<16)|1,612 if want==79 else 531)
        out.append(dict(life=hp,reserve=amount,selected=want))
    return dict(slot=slot+1,bindings=commands,thresholds=out)


if __name__=='__main__':
    assert digest(ELF)==PIN
    if len(sys.argv)==4:
        print(validate((int(sys.argv[1]),int(sys.argv[2]),sys.argv[3])));sys.exit()
    p=setup_actor(0).p
    for addr,label in ((0x5e2f20,'剣スピリッツ'),(0x5e3078,'秘奥義ゲージ点滅時'),
                       (0x5e3090,'I2I3I6PLIBIC同時押し'),(0x5e3660,'秘奥義　天覇封神斬'),
                       (0x5e36b8,'天覇凄煌斬')):
        assert p.memory[addr:addr+len(label.encode('cp932'))]==label.encode('cp932')
    cases=list(product(range(2),(78,79),('hit','guard','miss','bare','lethal','unarmed-source')))
    cases += [(s,79,c) for s,c in product(range(2),('repeat','mikiri'))]
    native_sha=digest(REPLAY)
    with ProcessPoolExecutor(max_workers=3) as pool:results=list(pool.map(validate,cases))
    assert digest(REPLAY)==native_sha, 'Rebuild completed during original comparison'
    report=dict(status='passed',original_sha256=PIN,native_sha256=native_sha,
                cases=results,control_boundaries=[boundaries(s) for s in range(2)])
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(len(results),'actual Ken pad matches,',sum(len(r.get('contacts',())) for r in results),'original contacts')
