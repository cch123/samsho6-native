#!/usr/bin/env python3
"""Real heavy follow-up contacts plus whole149d08 downed-entry projections."""
import hashlib,itertools,json,struct
from validate_contact_trial import run,ROOT,ASSETS,PROBE,VIEWER
from knockdown_oracle import fixture,OTHER_OBJECT
from mips_probe import signed

def main():
 cases=[];instructions=visits=states=0
 for player,distance in itertools.product([0,1],[64,100]):
  defender=1-player;commands=[f'place 280 {280+distance}',f'heavy-hurt {defender}',f'command {player} 6']
  rows=run(commands+['tick 1']*350);base=2+defender*11;extra=108+defender*16
  hit=next(i for i,r in enumerate(rows) if r[base+3]==384)
  recovered=next(i for i in range(hit,len(rows)) if rows[i][base+1:base+4]==[0,0,0])
  assert rows[-1][base]==(162 if distance==64 else 157)
  assert rows[-1][47+defender*6]==1 and rows[-1][extra+7]==0
  for action,count in [(384,12),(48,2),(52,5)]:
   assert {int(r[base+4]) for r in rows if r[base+3]==action}==set(range(count))
  #First contact is an explicit boundary: import its world anchor, life,
  #freeze/delta schedule and counterpart position. Run the entire original
  #actor dispatcher thereafter, including173108/14a348 and real landing dust.
  #This does not claim the surrounding contact/stage scheduler is original.
  p,a,o,b=fixture();first=rows[hit]
  def original(fn,args=()):
   nonlocal instructions,visits
   _,n=p.run(fn,[signed(v&0xffffffff,32) for v in args],limit=2000000);instructions+=n
   if fn==0x149d08:visits+=1
  def fword(v):return struct.unpack('<I',struct.pack('<f',v))[0]
  p.write(o+0x38,0x10000000|(defender<<19),4);p.write(o+0x40,fword(first[base+5]),4)
  p.write(OTHER_OBJECT+0x40,fword(first[2+player*11+5]),4)
  p.write(a+0xa30,int(first[base]),4);p.write(a+0xa34,200,4)
  p.write(a+0x194,2|(34<<16),4);p.write(a+0x258,1,4)
  original(0x14ff80,[a+0x18c,2,64]);original(0x149d08,[a]);original(0x149918,[a]);original(0x11d8e0,[o])
  for n,r in enumerate(rows[hit:recovered+1]):
   if n:
    prev=rows[hit+n-1];p.write(o+0x30,int(prev[base+8]),4);p.write(a+0x1ac,int(r[base+8]),4)
    p.write(o+0x104,(p.read(o+0x104,4)&~0x30)|(0x30 if prev[base+6]>0 else 0),4)
    p.write(o+0xfe,6 if prev[base+6]>0 else 0,2)
    p.write(OTHER_OBJECT+0x40,fword(r[2+player*11+5]),4)
    original(0x11d730,[o]);original(0x11d6c8,[o]);original(0x149d08,[a]);original(0x149918,[a]);original(0x11d8e0,[o])
   expected=[p.read(a+0x194,2),p.read(a+0x196,2),p.read(o+0x24,4),p.read(o+0x28,4),p.read(o+0x2c,4),p.read(o+0xc0,4),
    p.read(a+0x1b8,4),p.read(a+0x1c8,4),p.read(a+0x160,4),p.read(a+0x19a,1),
    *[signed(p.read(o+off,4),32) for off in range(0x4c,0x64,4)],p.read(o+0x44,4),p.read(a+0x253,1)]
   actual=[r[base+1],r[base+2],r[base+3],r[base+4],r[49+defender*6],r[48+defender*6],
    r[extra+7],r[extra+8],r[extra+5],r[extra+6],*r[extra+10:extra+16],fword(r[45+defender*6]),r[extra+9]]
   assert actual==expected,(player,distance,n,r[0],[(j,x,y) for j,(x,y) in enumerate(zip(actual,expected)) if x!=y])
   states+=1
  #Only ordinary command input after recovery; no life/position edits.
  follow=run(commands+['tick 350',f'command {defender} 6','tick 1'])[-1]
  assert follow[base+1:base+3]==[1,8]
  name=f'heavy-knockdown-{player}-{distance}'
  (ROOT/'work/ss6/scenarios'/f'{name}.txt').write_text('\n'.join(commands)+'\n')
  cases.append(dict(name=name,contact_update=first[0],recovered_update=rows[recovered][0],life=rows[-1][base],dust=1))
  #Fatal follow-up must hand over to KO/round flow, never revive with52.
  fatal=run(['rounds',*commands[:2],f'life {defender} 1',commands[2]]+['tick 1']*800)
  assert any(r[1]==player for r in fatal) and fatal[-1][105]==1 and fatal[-1][57]==4
  assert fatal[-1][2]==fatal[-1][13]==200
  assert all(r[base+3]!=52 for r in fatal if r[base]==0)
 report=dict(status='passed_for_integration_fixture',scenarios=cases,whole149d08_visits=visits,projected_states=states,
  original_instructions=instructions,probe_sha256=hashlib.sha256(PROBE.read_bytes()).hexdigest(),viewer_sha256=hashlib.sha256(VIEWER.read_bytes()).hexdigest(),
  scope='Initial heavy-hurt34 fixture then actual raw12 contact,damage64/384,two landings,dust29,damage16/48,damage7/52,normal0 and subsequent heavy input;both players,near/far,4fatal follow-ups into next round. Whole149d08 downed dispatcher/entry projections import first-contact anchor/life and subsequent freeze/delta/counterpart position. Compare state,metadata,conditions,ACT clock,all6motion words,Y,timer2/6;finite FP model,not full battle or GS proof. No new roll/special recovery input,other systems,contactFX/audio claim.')
 (ROOT/'outputs/ss6-feasibility/knockdown_trial_validation.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
