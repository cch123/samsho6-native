#!/usr/bin/env python3
"""Whole weapon-lock controller/callbacks with real shared common objects.

Actor phase flags/timers are explicit boundary inputs. This does not claim
normal31 animations, common-object frame playback, or a full playable frame.
"""
import collections
import hashlib
import itertools
import json
import random
import struct
import subprocess
from pathlib import Path
from mips_probe import Probe, signed
from extract_collision_tables import SOURCE_HASH
from round_entry_oracle import buffered_stdout
from validate_object_pools import pointer, handle, digest, TASKS, OBJECTS

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT/'work/ss6/extracted/resources'
BINARY = ROOT/'work/ss6/build-native/ss6-weapon-lock-probe'
B, A, O = 0x1b00000, 0x1c00000, 0x1e00000
ACT = [0x1400000, 0x1500000, 0x1600000]
tp = lambda h: pointer(h, TASKS, 52)
op = lambda h: pointer(h, OBJECTS, 320)
th = lambda a: handle(a, TASKS, 52)
oh = lambda a: handle(a, OBJECTS, 320)
bits = lambda v: struct.unpack('<I', struct.pack('<f', v))[0]

def main():
    raw = (ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SOURCE_HASH
    p = Probe(raw, finite_model=True)
    rng = random.Random(0x1449c0)
    commands, expected, labels = [], [], []
    counts = collections.Counter()
    instructions = total = traces = 0

    def words(at, values):
        values = list(values)
        p.memory[at:at+len(values)*4] = struct.pack(f'<{len(values)}I', *[v&0xffffffff for v in values])

    def readwords(at, count):return list(struct.unpack_from(f'<{count}I', p.memory, at))
    def read(at, width=4, signed_value=False):
        value = p.read(at, width)
        return signed(value, width*8) if signed_value else value

    def run(pc, args=()):
        nonlocal instructions
        value, n = p.run(pc, args, limit=250000)
        instructions += n;counts[f'whole{pc:06x}'] += 1
        return value&0xffffffff

    for slot, resource in enumerate([0, 0, 51]):
        aid = (ASSETS/f'aid_{resource:02}.bin').read_bytes()
        act = (ASSETS/f'act_{resource:02}.bin').read_bytes()
        p.memory[0x46a9b0+slot*0x1800:0x46a9b0+(slot+1)*0x1800] = aid
        p.memory[ACT[slot]:ACT[slot]+len(act)] = act
        p.write(0x4751b0+slot*4, ACT[slot], 4);p.write(0x46a9a0+slot*4, resource, 4)

    def features(player, mask):
        words(A+player*0xf2c+0x2c4+24, [0x80000001 if mask&(1<<j) else 0 for j in range(3)])

    def fixture(*, phases=(0,0), results=(-1,-1), presses=(0,0), timers=(0,0), masks=(0,0),
                ai=(0,0), ai_fields=(0,0), mode=3, current_interaction=1, old_interaction=0,
                positions=(280,360)):
        seed = rng.getrandbits(32);game = rng.getrandbits(32);library = rng.getrandbits(64);flags = rng.getrandbits(32)
        buffered_stdout(p);p.memory[0x1a00000:0x1a10000] = bytes(65536)
        p.memory[B:B+0x1000] = bytes(0x1000);p.memory[A:A+2*0xf2c] = bytes(2*0xf2c)
        p.memory[O:O+0x2000] = bytes(0x2000);p.memory[OBJECTS:OBJECTS+256*320] = bytes(256*320)
        words(0x1232440, [0]*258);words(0x3d3698, [0]*257);words(0x3d2e88, [0]*512)
        run(0x1123a8);run(0x112570);run(0x11e290)
        words(B, [4,4,current_interaction,old_interaction]);words(B+0x104, [0,0,256,256,0,0,256,0,0,0,0])
        p.write(B+0x138, flags, 4);p.write(B+0x13c,3,4)
        p.write(0x4d3d00,B,4);p.write(0x4d3d08,A,4);p.write(0x345188,0,4);p.write(0x123a0c0,0,1)
        p.write(0x443150,mode,4);p.write(0x3d2e80,game,4);p.write(read(0x5d1bf8)+0xa8,library,8)
        data = [seed,mode,game,library,current_interaction,old_interaction,flags]
        for i in range(2):
            a,o,stats = A+i*0xf2c,O+i*0x1000,B+0x254+i*0x108
            p.write(B+0x24c+i*4,a,4);p.write(a,o,4);p.write(a+0xa24,i,4)
            words(a+0x1b0,(seed+i*31+j*17 for j in range(35)))
            f38,f104,f108 = (rng.getrandbits(32) for _ in range(3))
            life,old_life,posture = 123+i,190-i,i
            request = rng.getrandbits(32);table,index = rng.choice([-1,0,1,2]),rng.randrange(-1,65)
            state,flags23c,flags244 = 39<<16,0x1000|(i<<3),rng.getrandbits(32)
            vals = [phases[i],results[i],presses[i],timers[i],ai[i],ai_fields[i],masks[i],
                    bits(positions[i]),bits(9-i*2),f38,f104,f108,life,old_life,posture,request,table,index,state,flags23c,flags244]
            for off,value in [(0xa54,phases[i]),(0xa58,results[i]),(0x1e4,timers[i]),(0xa20,ai[i]),(0xf4,ai_fields[i]),
                              (0xa30,life),(0x18c,request),(0x194,state),(0x23c,flags23c),(0x244,flags244)]:p.write(a+off,value,4)
            p.write(a+0x190,table,2);p.write(a+0x192,index,2)
            words(stats+0x10,[old_life,posture]);p.write(stats+0x30,presses[i],4)
            for off,value in [(0x38,f38),(0x104,f104),(0x108,f108),(0x40,bits(positions[i])),(0x44,bits(9-i*2))]:p.write(o+off,value,4)
            owner=a+0x2c4;words(owner,(seed+i*37+j*19 for j in range(171)));features(i,masks[i])
            for special,count in [(False,31),(True,32)]:
                for j in range(count):
                    p.write(owner+(0x644 if special else 0x4c4)+j*2,j+17,2)
                    p.write(owner+(0x5c4 if special else 0x448)+j*4,j%2,4)
                    p.write(owner+(0x328 if special else 0x2ac)+j*4,seed+j*13,4)
                    if special:p.write(owner+0x3a8+j*4,seed+j*7,4)
                    at=owner+(0x684 if special else 0x502)+j*6
                    p.memory[at:at+5]=struct.pack('<BBHB',j%14,(seed+j)&255,(seed+j*3)&65535,(seed+j*5)&255)
            data += vals
        commands.append('fixture '+' '.join(str(v if i==3 else v&0xffffffff) for i,v in enumerate(data)))

    def snapshot(result=0):
        row=[result,*[read(B+off,signed_value=True) for off in [0,4,8,12]],read(B+0x138)]
        row += [signed(v,32) for v in readwords(B+0x114,7)]
        row += [read(0x443150,signed_value=True),read(0x3d2e80),read(read(0x5d1bf8)+0xa8,8)]
        for i in range(2):
            a,o,stats=A+i*0xf2c,O+i*0x1000,B+0x254+i*0x108;owner=a+0x2c4
            row += [read(a+0xa54,signed_value=True),read(a+0xa58,signed_value=True),read(stats+0x30,signed_value=True)]
            row += [read(a+0xa20),read(a+0xf4,signed_value=True),read(a+0xa30,signed_value=True),
                    read(stats+0x10,signed_value=True),read(stats+0x14,signed_value=True),read(a+0x18c),
                    read(a+0x190,2,True),read(a+0x192,2,True),read(a+0x194),read(a+0x23c),read(a+0x244)]
            row += [signed(v,32) for v in readwords(a+0x1b0,35)]
            row += [read(o+off) for off in [0x38,0x104,0x108,0x40,0x44]]
            row.append(digest(readwords(owner,171)))
            slots=[]
            for special,count in [(False,31),(True,32)]:
                for j in range(count):
                    slots += [read(owner+(0x644 if special else 0x4c4)+j*2,2),read(owner+(0x5c4 if special else 0x448)+j*4),
                              read(owner+(0x328 if special else 0x2ac)+j*4),read(owner+0x3a8+j*4) if special else 0,
                              *struct.unpack_from('<BBHB',p.memory,owner+(0x684 if special else 0x502)+j*6)]
            row.append(digest(slots))
        tasks=readwords(TASKS,256*13);objects=readwords(OBJECTS,256*80)
        for i in range(256):
            tasks[i*13+3]=th(tasks[i*13+3]);tasks[i*13+7]=oh(tasks[i*13+7])
            objects[i*80+1]=th(objects[i*80+1]);objects[i*80+78]=oh(objects[i*80+78])
            ref=objects[i*80+0xbc//4]
            if ref:
                for base in ACT:
                    if base<=ref<base+0x100000:objects[i*80+0xbc//4]=ref-base+1;break
                else:raise AssertionError(hex(ref))
        registry=list(map(th,readwords(B+0x14c,64)))
        row += [th(read(0x1232844)),oh(read(0x46a900)),read(0x46a904),digest(tasks),digest(objects),digest(registry)]
        for h in registry:
            if h:
                obj=tasks[(h-1)*13+7]
                row += [h,*objects[(obj-1)*80:obj*80]]
        return row+[0]

    def execute(command,label):
        code,*values=command.split();values=list(map(int,values));result=0
        if code=='phase':p.write(A+values[0]*0xf2c+0xa54,values[1],4)
        elif code=='timer':p.write(A+values[0]*0xf2c+0x1e4,values[1],4)
        elif code=='features':features(*values)
        elif code=='move':words(O+values[0]*0x1000+0x40,values[1:])
        elif code=='populate':
            for i in range(values[0]):
                task=run(0x1471a8,[B+0x14c,64,0x777,0]);o=read(task+0x1c)
                for off,value in [(4,task),(0xcc,7 if i%3 else 6),(0xc4,135 if i%4 else 134),(0x104,0x100)]:p.write(o+off,value,4)
        elif code=='alias':p.write(B+0x14c+values[0]*4,read(B+0x14c+values[1]*4),4)
        elif code=='callbacks':
            for task in readwords(B+0x14c,64):
                if task:
                    handler=read(task);assert handler in [0x145e30,0x147540]
                    run(handler,[task])
        elif code=='commit':
            for task in readwords(B+0x14c,64):
                if task:
                    o=read(task+0x1c)
                    if read(o+0xcc)==7:run(0x11d958,[o])
        elif code=='ai':result=run(0x158ac8,[A+values[0]*0xf2c+8])
        elif code!='snapshot':run(dict(enter=0x1449c0,update=0x144b28,interaction=0x144950,step=0x143320)[code],[B])
        commands.append(command)
        if code not in ['phase','timer','features','move','populate','alias']:
            expected.append(snapshot(result));labels.append(label)

    def flush():
        nonlocal total
        if not expected:return
        result=subprocess.run([str(BINARY),str(ASSETS)],input='\n'.join(commands)+'\n',text=True,capture_output=True)
        assert result.returncode==0,(len(result.stdout.splitlines()),labels[min(len(result.stdout.splitlines()),len(labels)-1)],result.stderr)
        actual=[list(map(int,line.split())) for line in result.stdout.splitlines()]
        assert len(actual)==len(expected),(len(actual),len(expected))
        for i,(got,want) in enumerate(zip(actual,expected)):
            assert got==want,(total+i,labels[i],len(got),len(want),[(j,hex(x),hex(y)) for j,(x,y) in enumerate(zip(got,want)) if x!=y][:16])
        total+=len(expected);print('weapon lock',total,'passed',flush=True)
        commands.clear();expected.clear();labels.clear()

    #Entry, real common object allocation, deferred action commit and both
    #callbacks. Other object kinds/pending actions/aliases must survive.
    for invocation, occupied, phases in itertools.product(['enter','interaction','step'],[0,6,31,63],[(0,0),(3,-1)]):
        fixture(phases=phases,results=(2,3),presses=(99,-7),timers=(1234,5678),masks=(7,7))
        execute(f'populate {occupied}',('populate',occupied))
        if occupied>=6:execute('alias 4 1','duplicate registry reference')
        execute(invocation,('entry',invocation,occupied,phases))
        execute('commit','commit common action135')
        execute(f'move 0 {bits(-41.5)} {bits(73)}','move parent')
        execute(f'move 1 {bits(700.25)} {bits(-3)}','move opponent')
        execute('callbacks','follow player center')
        execute('timer 0 46080','explicit actor timer boundary')
        execute('update','zero press timeout release')
        execute('callbacks','released callback clears hold')
        execute('interaction','publish cleared interaction')
        if len(expected)>=128:flush()

    for phases,timer,presses,masks in itertools.product(
            [(0,0),(1,1),(0,1),(1,2),(2,1),(-1,1),(2,3)],
            [-1,0,0x4fff,0x5000,0xb3ff,0xb400,0x7fffffff],
            [(0,0),(9,0),(9,9),(10,11),(11,10),(0x7fffffff,-1)],
            [(0,0),(1,0),(7,0),(3,7)]):
        fixture(phases=phases,timers=(timer,17),presses=presses,masks=masks,old_interaction=1)
        execute('update',('update',phases,timer,presses,masks))
        #Flush only at fixture boundaries; subsequent commands otherwise
        #need the same native state when a batch crosses128 snapshots.
        flush()

    for results,phases in itertools.product([(-1,-1),(-1,2),(2,-1),(2,3),(17,19)],[(0,0),(1,1)]):
        fixture(phases=phases,results=results,presses=(10,11),timers=(0x5000,0),old_interaction=1)
        execute('interaction',('preserve_results',results,phases));execute('interaction','next visit publication');flush()

    for mode,ai_fields in itertools.product([0,-2,3],[(0,0),(1,7),(-1,-10),(0x7fffffff,-0x80000000)]):
        fixture(ai=(1,2),ai_fields=ai_fields,mode=mode,old_interaction=1,timers=(0x5000,0))
        for visit in range(32):execute('update',('ai',mode,ai_fields,visit))
        execute('ai 0','standalone158ac8 player0');execute('ai 1','standalone158ac8 player1');flush()

    for final_masks,phase_ready in itertools.product([(1,0),(0,7),(7,7),(0,0)],[False,True]):
        fixture(masks=(0,0));execute('interaction','continuous entry');execute('commit','continuous commit')
        for visit in range(200):
            execute(f'timer 0 {visit*256}','actor timer boundary')
            if visit==40:
                for i in range(2):execute(f'features {i} {final_masks[i]}','sampled input boundary')
            if visit==90 and phase_ready:
                for i in range(2):execute(f'phase {i} 1','normal31 callback boundary')
            execute('interaction',('continuous',final_masks,phase_ready,visit))
            execute('callbacks','continuous object callback')
        traces+=1;flush()

    flush()
    report=dict(status='passed_for_projected_fields',snapshots=total,persistent_traces=traces,
                original_functions=dict(counts),original_instructions=instructions,
                elf_sha256=SOURCE_HASH,native_sha256=hashlib.sha256(BINARY.read_bytes()).hexdigest(),
                scope='Whole1449c0/144b28/144950 and delayed143320 with real140a78/1471a8/11d570 common-kind7/resource51 initialization; '
                      'whole11d958 commits queued135,145e30 follows both positions,147540 releases hold,158ac8 consumes original shared RNG. '
                      'Full256-slot task/object hashes and64-slot registry, actor requests/35timers/lock phase/results, input171features/all63command slots, '
                      'battle state/timers/history snapshots, both RNGs and body flags/positions compared. '
                      'Muted audio option, original ELF/callees unchanged, real buffered libc, finite scalar model. '
                      'Phase/timer/input updates are explicit actor/sampler boundary fixtures; no normal31 animations, common-object frame playback, full frame, rendering or live playable weapon lock claim.')
    (ROOT/'outputs/ss6-feasibility/weapon_lock_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
