#!/usr/bin/env python3
"""Compare the local versus finishing classification with the original EE handlers."""
import collections
import hashlib
import json
import random
import struct
import subprocess
from validate_haohmaru_special import ACTORS, BUILD, ELF, OBJECTS, QUEUE, RES, ROOT, SOURCE_HASH, ContactOracle, initialize_effects, run_native
from mips_probe import signed

BATTLE = 0x1b80000
EVENT = 0x1e05000
CHILD = 0x1e03000

def state(table, index):
    return index << 16 | table

def stats(slot):
    return BATTLE+0x254+0x108*slot

def actor(slot):
    return ACTORS+0xf2c*slot

def put(p, base, pairs):
    for offset, value in pairs:
        p.write(base+offset, value, 4)

class Comparison:
    def __init__(self):
        self.original = ContactOracle()
        self.p = self.original.probe
        self.commands = []
        self.results = []
        self.coverage = collections.Counter()
        self.instructions = 0

    def run(self, pc, args=(), **kwargs):
        value, instructions = self.p.run(pc,args,limit=500000,**kwargs)
        self.instructions += instructions
        self.coverage[f'{pc:x}'] += 1
        return value

    def metadata(self, slot):
        p=self.p
        return [p.read(actor(slot)+off,4) for off in (0x244,0x248)]+[signed(p.read(stats(slot)+off,4),32) for off in (0x1c,0x20)]

    def native_case(self, mode, src, ev, projectile):
        p=self.p
        a,b=actor(src),actor(1-src)
        strength=p.read(a+0x19a,1) | (p.read(a+0x1aa,1)<<8)
        count=p.read(stats(src)+12,4)
        return [mode,p.read(a+0x194,4),p.read(a+0x1a4,4),strength,p.read(a+0x23c,4),*self.metadata(src)[:2],
                p.read(b+0x194,4),p.read(b+0x1a4,4),p.read(b+0x23c,4),p.read(b+0x240,4),
                p.read(ev+0x60,4),p.read(ev+0x24,4),int(projectile),
                p.read(b+0xa38,4),p.read(b+0xa30,4),count,*self.metadata(src)[2:],p.read(a+0xa10,4)]

    def record(self, cmd, counter, slot):
        self.commands.append(cmd)
        self.results.append([counter,*self.metadata(slot)])

    def matrix(self):
        p=self.p
        rng=random.Random(0x1576e8)
        for n in range(3840):
            slot=n%2;victim=1-slot
            a,b=actor(slot),actor(victim)
            for i in range(2):
                put(p,actor(i),[(0,OBJECTS[i]),(0xa24,i),(0x134,25600),(0x138,25600),(0xa30,200),(0xa34,200)])
                put(p,OBJECTS[i],[(0xc,i),(0x10,i),(0xcc,i)])
            character=(n//96+slot)%2
            put(p,a,[(0xa10,character)]);put(p,b,[(0xa10,1-character)])
            mode=rng.randrange(4)
            # Include both ends of the original normal/special tables and all
            # six result categories, even when a command isn't playable yet.
            index=n%96
            main=state(1,index)
            flags=rng.choice([0,0x1000,0x1800]) | rng.choice([0,0x200000])
            alias=main
            other=state(rng.choice([0,1,2]),rng.randrange(20))
            if flags&0x200000:main=other
            else:alias=other
            if n%9==0:main,alias=other,other
            put(p,a,[(0x194,main),(0x1a4,alias),(0x23c,flags),(0x244,0x8000000 if n%17==0 else 0x100),
                     (0x248,0x40000000 if n%3==0 else 8)])
            p.write(a+0x19a,rng.randrange(8),1);p.write(a+0x1aa,rng.randrange(8),1)
            put(p,b,[(0x194,state(rng.randrange(3),0)),(0x1a4,state(rng.randrange(3),1)),(0x240,rng.randrange(2)),
                     (0x23c,0x1000 | rng.choice([0,0x200000]) | (0x80 if n%13==0 else 0)),
                     (0xa30,20),(0xa38,rng.choice([0,7,18,19,20,22]))])
            put(p,stats(slot),[(12,rng.choice([0,0,1,4])),(0x1c,-1),(0x20,-1)])
            projectile=bool(n%7==0)
            put(p,CHILD,[(0xc,slot),(0x10,slot),(0xcc,2),(0xd0,(n//7)%2)])
            srcobj=CHILD if projectile else OBJECTS[slot]
            put(p,EVENT,[(0x20,36 if projectile else 12),(0x24,rng.randrange(6)),(0x40,srcobj),
                         (0x48,rng.randrange(1,4)),(0x60,rng.randrange(4)),(0x68,OBJECTS[victim])])
            counter=self.run(0x157fa8,[b,EVENT+0x48])
            cmd=self.native_case(mode,slot,EVENT,projectile)
            if mode<2:
                self.run(0x1575d0,[EVENT,int(not projectile),mode,counter if mode==0 else 0])
            else:
                self.run(0x1413d8,[victim,8,srcobj,int(mode==3)])
                cmd[14]=p.read(b+0xa38,4)
            self.record(cmd,counter,slot)

    def compare(self):
        result=subprocess.run([BUILD/'ss6-finishing-blow-probe',RES],input='\n'.join(' '.join(map(str,r)) for r in self.commands)+'\n',
                              text=True,capture_output=True,check=True)
        got=[list(map(int,line.split())) for line in result.stdout.splitlines()]
        assert len(got)==len(self.results)
        for n,(row,want) in enumerate(zip(got,self.results)):
            assert row==want,(n,self.commands[n],row,want)

def mirror(mask):
    return (mask&~192)|((mask&64)<<1)|((mask&128)>>1)

def world_case(kind,slot):
    heavy=[(70,128,0),(3,0,0),(1,1024,0),(220,0,0)]
    throw=[(80,128,0),(1,1664,0),(220,0,0)]
    wind=[(45,128,0),(30,0,0),(1,32,0),(1,160,0),(1,1152,0),(290,0,0)]
    chip=[(80,128,0),(30,0,0),(1,32,0),(1,160,0),(1,1152,0),(55,0,128),(190,0,0)]
    rising=[(65,128,0),(30,0,0),(1,128,0),(1,32,0),(1,1184,0),(230,0,0)]
    pre,final={
        'heavy':(heavy*5,heavy),'counter':(heavy*5,heavy[:3]+[(5,0,0),(1,0,512),(214,0,0)]),'throw':(throw*14,throw),'slam':(wind*6,wind),
        'chip':(wind*6+chip*10,chip),'projectile':(wind*6+chip*5,wind),
        'two_hits':(wind*5+chip*14,rising)
    }[kind]
    commands=[(500,0,0)]+pre+[(1,a,b) for n,a,b in final for _ in range(n)]
    if slot:commands=[(n,mirror(b),mirror(a)) for n,a,b in commands]
    commands=[' '.join(map(str,v)) for v in commands]
    rows=run_native('ss6-match-replay',commands,'--finish-fields')
    winds=run_native('ss6-match-replay',commands,'--whirlwind-fields')
    victim=1-slot
    base=23+26*slot
    stat=75+4*slot
    win=next(i for i,r in enumerate(rows) if int(r[base+7])&0x08000000)
    assert win>len(pre) and int(rows[win-1][0])+1==int(rows[win][0])
    assert len(rows)==len(winds) and int(rows[-1][12+10*slot])==1
    frames=[win]
    if kind=='two_hits':
        first=next(i for i,r in enumerate(rows) if i>len(pre) and int(r[stat])==1)
        assert first<win and int(rows[win-1][stat])==1 and int(rows[win][stat])==2
        frames.insert(0,first)
    c=Comparison();p=c.p
    initialize_effects(p)
    for pc in (0x1123a8,0x112570,0x11e290):c.run(pc)
    for bank,name in enumerate(('01HitFlash.bin','02Guard.bin','03etc.bin')):
        at=0x4a4810+bank*0x3da0;p.memory[at:at+0x3da0]=(RES/name).read_bytes()
    for i in range(32):p.write(0x4c3510+i*4,i+1,4)
    # Original newlib's string output must be distinct from both JDG arrays.
    stdout=p.read(p.read(0x5d1bf8,4)+8,4)
    put(p,stdout,[(0,0x19e0000),(16,0x19e0000)])
    contacts=[]
    for idx in frames:
        prev,now=rows[idx-1:idx+1]
        for i in (0,1):
            c.original.install_player(prev,i)
            put(p,stats(i),list(zip((12,24,28,32),map(int,prev[75+4*i:79+4*i]))))
        traced=collections.defaultdict(list)
        def observe(pc):
            if pc in (0x1576e8,0x1413d8,0x156fb8,0x1575d0):
                traced[pc].append(tuple(p.registers[4:11]))
        projectile=kind in ('projectile','chip')
        source=CHILD if projectile else OBJECTS[slot]
        raw=None
        if kind=='throw':
            act,step=map(int,prev[5+10*slot:7+10*slot])
            start=struct.unpack_from('<h',c.original.aid,2*act)[0]
            damage=c.original.act[60*(start+step)+2]
            assert damage==10,(kind,slot,prev[:23],damage)
            p.write(source+0xd8,damage,4)
            c.run(0x154120,[source],observe=observe)
        elif kind=='slam':
            # 165f94/166324 mark this damage as capture damage. The victim
            # releases the child in phase 3, before phase 4 requests damage.
            vbase=75+27*victim
            assert int(winds[idx-1][vbase+20])==0 and int(winds[idx-1][vbase+10])==0
            assert int(winds[idx-1][vbase])==3 and int(winds[idx][vbase])==4
            c.run(0x1413d8,[victim,18,source,1],observe=observe)
        # A throw can deliver its ACT d8 damage and its falling hit on the same
        # update. Run both; the first request must retain the winning metadata.
        if kind not in ('throw','slam') or now[10+10*slot]!=prev[10+10*slot]:
            if projectile:
                words=list(map(int,winds[idx-1][131:211]))
                assert len(words)==80 and words[0xcc//4]==2 and words[0x10//4]==slot
                struct.pack_into('<80I',p.memory,CHILD,*words)
                bank=0x17c0000
                p.memory[bank:bank+len(c.original.jdg)]=c.original.jdg
                p.write(0x4751e0+slot*4,bank,4)
                for who,act,step in ((OBJECTS[slot],*map(int,prev[5+10*slot:7+10*slot])),(CHILD,words[9],words[10])):
                    first=struct.unpack_from('<h',c.original.aid,act*2)[0]
                    refs=0x17a0000+0x100*int(who==CHILD)
                    p.memory[refs:refs+16]=c.original.act[60*(first+step)+14:60*(first+step)+30]
                    p.write(who+0xbc,refs,4)
            p.write(0x12d2698,0,4)
            for pair in ((source,OBJECTS[victim]),(OBJECTS[victim],source)):c.run(0x1536e8,pair)
            c.run(0x1544a0)
            candidates=(QUEUE+108*j for j in range(p.read(0x12d2698,4)))
            e=next(e for e in candidates if p.read(e,4)==7 and p.read(e+0x40,4)==source)
            raw=p.read(e+0x20,4)
            defense=c.run(0x155850,[e])
            assert bool(defense)==(kind=='chip')
            c.run(0x155d50 if defense else 0x155a88,[e,int(not projectile),defense],observe=observe)
            assert len(traced[0x1575d0])==1
            if not defense:
                assert len(traced[0x156fb8])==1
                assert traced[0x156fb8][0][1]==traced[0x1575d0][0][3]
        calls=traced[0x1576e8]
        assert len(calls)==(2 if kind=='throw' else int(idx==win)),(kind,slot,int(now[0]),traced)
        if idx==win:
            call=traced[0x1576e8][0]
            assert call[0]==actor(slot) and call[1]==source and call[3]==int(not projectile)
            assert call[4]==int(kind=='chip') and call[5]==int(kind=='counter') and call[6]==int(kind=='slam')
        original=c.metadata(slot)
        got=[int(now[base+7]),int(now[base+8]),int(now[stat+2]),int(now[stat+3])]
        masks=[0x18000000,0x00fe0000,0xffffffff,0xffffffff]
        assert [v&m for v,m in zip(original,masks)]==[v&m for v,m in zip(got,masks)],(kind,slot,now[0],original,got)
        for i in (0,1):
            for off,column in ((12,75+4*i),(24,76+4*i)):
                assert p.read(stats(i)+off,4)==int(now[column]),(kind,i,now[0],off,p.read(stats(i)+off,4),now[column])
        contacts.append(dict(frame=int(now[0]),life=int(now[9+10*victim]),raw=raw,combo=int(now[stat]),
                             outcome=got[2:],finish_flags=[hex(got[k]&masks[k]) for k in range(2)]))
    life_column=9+10*victim
    zero=next(row for row in rows[win:] if int(row[life_column])==0)
    assert int(zero[0])==int(rows[win][0])+int(kind=='slam')
    return dict(kind=kind,player=slot+1,contacts=contacts,life_zero_frame=int(zero[0]),round_win=int(rows[-1][12+slot*10]),original_calls=c.coverage,
                original_instructions=c.instructions)

def main():
    assert hashlib.sha256(ELF.read_bytes()).hexdigest()==SOURCE_HASH
    check=Comparison()
    check.matrix()
    check.compare()
    worlds=[]
    for kind in ('heavy','counter','throw','slam','projectile','chip','two_hits'):
        for slot in range(2):
            world=world_case(kind,slot);worlds.append(world)
            print(kind,slot+1,world['contacts'],flush=True)
    outcomes=sorted(set(row[-2] for row in check.results))
    assert outcomes==[-1,0,1,2,3,4,5]
    report=dict(status='passed',elf_sha256=SOURCE_HASH,classification_cases=len(check.results),
                comparisons=check.coverage,original_classification_instructions=check.instructions,observed_outcomes=outcomes,
                world_replays=worlds,
                scope='Resources 00 and 01, local versus. Full original 1575d0 and 1413d8 run across live/KO thresholds, both players, source body or descriptor-0/1 child, aliases, combo counts and pre-latched flags. All seven Haohmaru KO routes start both players at 200 HP and use normalized inputs. Collision oracle replays original full 155a88/155d50 on previous native geometry including original effects allocation, counter and combo bookkeeping. Throw uses ACT d8 and 154120. Released-child slam starts at the 1413d8 damage call. Round progression is native; the full original game loop is outside this comparison.')
    (ROOT/'outputs/ss6-feasibility/finishing_blow_validation.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()
