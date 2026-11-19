#!/usr/bin/env python3
"""First resource00 introductions: original helpers and native integration."""
import hashlib,json,struct
from round_entry_oracle import fixture,ROOT
from validate_contact_trial import run,PROBE

def main():
 p,a,o,b=fixture();a1=a+0xf2c;o1=o+0x1000
 p.memory[a1:a1+0xf2c]=p.memory[a:a+0xf2c]
 p.memory[o1:o1+0x140]=p.memory[o:o+0x140]
 p.write(a1,o1,4);p.write(a1+0xa24,1,4);p.write(o1+0xcc,1,4);p.write(b+0x250,a1,4)
 p.write(b+0x18,0,4);p.write(0x345188,0,4);p.write(0x4c3820,1,4)
 instructions=0;dispatches=0;actor_visits=0
 def original(address,args=()):
  nonlocal instructions
  instructions+=p.run(address,args,limit=200000)[1]
 for actor,obj in [(a,o),(a1,o1)]:
  p.write(actor+0x194,0,4);original(0x120390,[obj,0])
 original(0x13fd80)
 #143708 also performs PS2 console/audio work. State1 is a declared entry
 #boundary here; this is not a whole143430 or original full-frame trace.
 p.write(b,1,4);p.write(b+4,1,4)
 rows=run(['match']+['tick 1']*500);ready=[None,None];compared=[]
 scalar=lambda v:struct.unpack('<f',struct.pack('<I',v))[0]
 for tick in range(1,237):
  if tick>1:original(0x1435d8,[b]);dispatches+=1
  for actor,obj in [(a,o),(a1,o1)]:
   for address,arg in [(0x11d730,obj),(0x11d6c8,obj),(0x149d08,actor),(0x149918,actor),(0x11d8e0,obj)]:
    original(address,[arg])
   actor_visits+=1
  row=rows[tick]
  want=[p.read(b+4,4),p.read(b,4),p.read(b+0x118,4),p.read(b+0x11c,4)]
  got=[int(row[j]) for j in [57,58,98,99]]
  for i,(actor,obj) in enumerate([(a,o),(a1,o1)]):
   state=p.read(actor+0x194,4);gate=p.read(actor+0x244,4)&0x40000000
   want += [state&0xffff,state>>16]+[p.read(obj+off,4) for off in [0x24,0x28,0xc0,0x2c,0x104]]
   want += [scalar(p.read(obj+off,4)) for off in [0x40,0x44]]+[gate]
   got += [int(row[j+i*11]) for j in [3,4,5,6]]
   got += [int(row[j+i*6]) for j in [48,49,50]]+[row[7+i*11],row[45+i*6],int(row[60+i])&0x40000000]
   if gate and ready[i] is None:ready[i]=tick
  assert got==want,(tick,[(j,x,y) for j,(x,y) in enumerate(zip(got,want)) if x!=y])
  compared.append(got)
 assert all(v is not None for v in ready)
 release=max(ready)+1;ui=release+31
 assert rows[release][57:59]==[1,3] and rows[ui][57:59]==[3,3]
 fight=next(int(row[0]) for row in rows if row[57:59]==[4,4])
 for i in range(2):
  assert {int(r[6+i*11]) for r in rows if r[5+i*11]==492}==set(range(21))
  assert all(int(r[41+i*2])&1 for r in rows[:fight])
 # Repeated direct attack requests must not interrupt the introduction or
 #leak into the first unlocked update. The real pad parser is still absent.
 spam=['match']
 for tick in range(fight-1):spam+=['command 0 5','command 1 5','tick 1']
 spam+=['tick 1'] # No fresh request on the first unlocked update.
 attacked=run(spam);assert attacked[-1][5]==attacked[-1][16]==0
 for r in attacked:assert r[2]==r[13]==200 and r[7]==240 and r[18]==400
 resumed=run(spam+['command 0 1','tick 50','command 0 0','command 0 5','tick 40'])[-1]
 assert resumed[13]<200 and resumed[57:59]==[4,4]
 log=bytes(p.memory[0x1a00000:0x1a10000]).split(b'\0')[0];assert b'ASSERT' not in log
 report=dict(status='passed_for_projected_fields',native_sha256=hashlib.sha256(PROBE.read_bytes()).hexdigest(),
  whole13fd80_cases=1,whole1435d8_visits=dispatches,whole149d08_visits=actor_visits,
  compared_updates=len(compared),original_instructions=instructions,ready_updates=ready,
  idle_request_update=release,opening_update=ui,fight_update=fight,next_contact_life=int(resumed[13]),
  scope='Same-character resource00 first round. Whole13fd80 then explicit state1 boundary;235 whole1435d8 visits,472 whole149d08 actor dispatches and associated animation/motion/action-commit wrappers. Projected battle clocks,state,normal state,body492 stages/fraction/end/flags,position and readiness match native integration through update236. Includes both type0 entry-prefix passes and zero-duration record12. Native UI/input-lock integration through opening and first actual hit; UI helpers separately verified. No whole143430, full original frame scheduler,input parser,audio,other-character voice separation or GS claim.')
 (ROOT/'outputs/ss6-feasibility/character_intro_validation.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
