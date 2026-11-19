#!/usr/bin/env python3
"""Persistent native human input + ordinary entry/callback/body composition."""
import gzip,hashlib,itertools,json,struct,subprocess,sys
from pathlib import Path
from round_entry_oracle import fixture,ROOT
from mips_probe import signed
from validate_input_features import FEATURES,LATCHES,PADS,HELD,PRESSED
from validate_input_lifecycle import Boundary
from knockdown_oracle import initialize_effects
import round_initialization_projection as round_projection

def oracle_pins():
 #Cached expectations are only reusable while every local oracle helper,
 #the original ELF and its body resources remain byte-identical.
 work=ROOT/'work/ss6'
 if '--rolls' in sys.argv:
  # Only imported oracle code affects roll expectations. Independent suites
  # may be added while a full set of manual-recovery inputs is running.
  # The EE runner imports this module on its first floating-point operation.
  import finite_float
  files=sorted({Path(module.__file__).resolve() for module in tuple(sys.modules.values())
                if getattr(module,'__file__',None) and Path(module.__file__).resolve().parent==work})
 else:files=sorted(work.glob('*.py'))
 files.append(work/'extracted/SLPS_255.59')
 active_script=Path(__file__).resolve()
 if active_script not in files:files.append(active_script)
 files += [ROOT/'work/ss6/extracted/resources'/name for name in ['aid_00.bin','act_00.bin','01HitFlash.bin','sound_selection.bin']]
 return {str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in files}

def check_native(commands,expected,labels):
 binary=ROOT/'work/ss6/build-native/ss6-ground-state-probe'
 before=hashlib.sha256(binary.read_bytes()).hexdigest()
 result=subprocess.run([str(binary),str(ROOT/'work/ss6/extracted/resources')],input='\n'.join(commands)+'\n',text=True,capture_output=True)
 assert result.returncode==0,(len(result.stdout.splitlines()),result.stderr,labels[min(len(result.stdout.splitlines()),len(labels)-1)])
 rows=[list(map(int,line.split())) for line in result.stdout.splitlines()];assert len(rows)==len(expected)
 for i,(actual,want) in enumerate(zip(rows,expected)):
  assert actual==want,(i,labels[i],commands[max(0,i-2):i+1],[(j,x,y) for j,(x,y) in enumerate(zip(actual,want)) if x!=y][:20],len(actual),len(want))
 assert before==hashlib.sha256(binary.read_bytes()).hexdigest(),'Native executable changed during comparison'
 return before

def main():
 commands=[];expected=[];labels=[];instructions=visits=raw_visits=0;seen=set()
 quick='--quick' in sys.argv;boundaries='--boundaries' in sys.argv;attacks='--attacks' in sys.argv;damage='--damage' in sys.argv;downed='--downed' in sys.argv;ko='--ko' in sys.argv;ending='--ending' in sys.argv
 rolls='--rolls' in sys.argv
 downed=downed or rolls
 colors='--colors' in sys.argv;rounds='--rounds' in sys.argv
 assert sum([boundaries,attacks,damage,downed,ko,ending,colors,rounds])<=1,'Choose a single validation suite'
 name='ground_round_input' if rounds else 'ground_color_input' if colors else 'ground_ending_input' if ending else 'ground_ko_input' if ko else 'ground_downed_input' if downed else 'ground_damage_input' if damage else 'ground_attack_input' if attacks else 'ground_input_boundaries' if boundaries else 'ground_state'
 if rolls:name='recovery_roll'
 destination=ROOT/'outputs/ss6-feasibility'/f'{name}_validation.json'
 cache=ROOT/'work/ss6'/f'{name}_oracle.json.gz'
 pins=oracle_pins()
 if '--reuse-oracle' in sys.argv:
  assert not quick,'Full cached oracle cannot be used as a quick subset'
  with gzip.open(cache,'rt') as stream:cached=json.load(stream)
  assert cached['pins']==pins,'Original oracle inputs changed; regenerate expectations'
  report=cached['report'];report['native_sha256']=check_native(cached['commands'],cached['expected'],cached['labels'])
  report['status']='passed_for_projected_fields';report['oracle_cache_reused']=True
  destination.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return
 phases=False;object_fixture=False;contact_phases=False;phase_visits=contact_visits=hit_visits=guard_visits=clash_visits=0
 dust_events=total_dust=0;recovery_requests=[]
 ko_phases=False;recovery_diagnostics=watchdog_visits=watchdog_cases=0;ko_traces=[]
 ending_traces=[];ending_chains=[];intro_holds=0;intro_steps=set();release_visits=defer_visits=0
 color_projection=False;color_changes=0;color_values=set()
 round_fields=False;round_images=[0,0,0];round_visits=round_preserved_input=0;round_traces=[]
 def run(fn,args=(),stops=()):
  nonlocal instructions
  _,n=p.run(fn,args,limit=2000000,stop_before=stops);instructions+=n
 def snapshot():
  owner=a+0x2c4
  values=[p.read(a+0x194,4),p.read(a+0x18c,4),signed(p.read(a+0x190,2),16),signed(p.read(a+0x192,2),16),
   p.read(a+0x19a,1),*[p.read(a+off,4) for off in [0x23c,0x244,0x248,0xc0]],
   *[p.read(a+off,4) for off in range(0x15c,0x168,4)],*[p.read(a+off,4) for off in range(0x260,0x27c,4)],
   *[signed(p.read(a+0x1b0+4*i,4),32) for i in range(35)]]
  values += [p.read(o+off,4) for off in [0x24,0x28,0x2c,0xc0,0x38,0x104,0x108]]+[p.read(o+0xfe,2)]
  values += [signed(p.read(o+off,4),32) for off in range(0x4c,0x64,4)]+[p.read(o+0x40,4),p.read(o+0x44,4)]
  values += list(struct.unpack_from('<171I',p.memory,owner))
  for special,count in [(False,31),(True,32)]:
   for i in range(count):
    progress=owner+(0x684 if special else 0x502)+6*i
    values += [p.read(owner+(0x328 if special else 0x2ac)+4*i,4),p.read(owner+0x3a8+4*i,4) if special else 0,
     *struct.unpack_from('<BBHB',p.memory,progress)]
  values+=list(p.memory[LATCHES:LATCHES+12])
  values += [signed(p.read(a+0x198,2),16),signed(p.read(a+0x130,4),32),p.read(other+0xb8,4),p.read(0x12d2300,4),p.read(a+0x24c,1)]
  for h in [1,2]:values += [p.read(0x1d10000+h*320+off,4) if object_fixture else 0 for off in [0xd4,0x108]]
  values += list(p.memory[a+0x250:a+0x258])+[p.read(a+off,4) for off in [0x258,0x25c,*range(0x27c,0x28c,4)]]
  values += [p.read(o+0xe4,4),p.read(o+0xe8,4),signed(p.read(a+0x1ac,4),32),p.read(other+0x248,4)]
  values += [signed(p.read(other+0x1b0+4*i,4),32) for i in range(35)]
  values += [signed(p.read(a+0xa4c,4),32),p.read(a+0xb8,4),dust_events]
  if ko_phases:values += [signed(p.read(a+off,4),32) for off in [0xa30,0xa34,0xa38]]+[recovery_diagnostics]
  if color_projection:values += [p.read(o+0x8c,4),p.read(o+0x20,4),p.read(a+0xa28,4),p.read(a+0xa2c,4),signed(p.read(a+0x120,4),32),signed(p.read(a+0x124,4),32)]
  if round_fields:values += round_projection.snapshot(p,a,o,b,player,round_images)
  return values
 def append(command):commands.append(command);expected.append(snapshot());labels.append(label)
 def reset(player,mirror):
  nonlocal p,a,o,b,other,phases,object_fixture,contact_phases,dust_events,ko_phases,recovery_diagnostics,intro_holds,intro_steps,color_projection,round_fields,round_images
  phases=False;object_fixture=False;contact_phases=False
  dust_events=0
  ko_phases=False;recovery_diagnostics=0
  intro_holds=0;intro_steps=set()
  color_projection=False
  round_fields=False;round_images=[0,0,0]
  p,a,o,b=fixture(player);other=0x1c00000+(1-player)*0xf2c
  if downed or ko or ending or rounds:p.finite_model=True;initialize_effects(p)
  p.write(other,o+0x1000,4);p.write(other+4,o+0x2000,4);p.write(other+0x23c,0x1000,4)
  p.write(other+0xa24,1-player,4);p.write(o+0x10cc,1-player,4)
  p.write(a+4,o+0x3000,4);p.write(o+0x30c4,-1,4)
  run(0x149008,[a,0]);run(0x149918,[a]);run(0x11d8e0,[o]);run(0x179258,[a+0x2c4,a+0x10c])
  p.write(o+0x38,0x10000000|(mirror<<19),4);p.write(a+0xa08,mirror,4)
  for address,value in [(o+0x40,280),(o+0x1040,400)]:p.memory[address:address+4]=struct.pack('<f',value)
  p.write(0x4c38a8,0,4);p.write(b,4,4);p.write(b+0x18,0,4);p.write(b+0x144,120,4)
  for player_map in range(2):
   mapping=[1<<(8+i) for i in range(8)]
   for at in [0x4eaac0,0x12d32d8]:p.memory[at+player_map*32:at+player_map*32+32]=struct.pack('<8I',*mapping)
  if rounds:round_projection.align_initial_fixture(p,a,o)
  append(f'reset {player} {mirror} 280 400')
 def watchdog():
  nonlocal recovery_diagnostics,watchdog_visits
  #Count genuine printf calls without stopping or replacing their execution.
  class Calls:
   count=0
   def __contains__(self,pc):
    if pc==0x316140:self.count+=1
    return False
  calls=Calls();run(0x14b880,[a],stops=calls)
  recovery_diagnostics+=calls.count;watchdog_visits+=1
 def tick(player,held=None,previous=0):
  nonlocal visits,raw_visits,phase_visits,contact_visits,dust_events,total_dust,intro_holds,color_changes
  if contact_phases:
   p.put(16,b+player*4);p.put(17,3);p.put(19,0x140000)
   boundary=Boundary(0x142618,0x14261c);run(0x142580,stops=boundary);assert boundary.stopped==0x142618
   contact_visits+=1
  run(0x11d730,[o]);run(0x11d6c8,[o])
  if ending and p.read(o+0x24,4)==492:
   step=p.read(o+0x28,4);intro_steps.add(step)
   if step==12 and p.read(o+0x104,4)&0x100:intro_holds+=1
  if contact_phases:
   delta=128 if p.read(a+0x1b4,4) else 256;p.write(a+0x1ac,delta,4);p.write(o+0x30,delta,4)
  if phases:
   #1428f4 converts the POSITION DIFFERENCE, not each position separately.
   #At322.5 vs400 those formulas disagree across the inclusive78 boundary.
   #Run that original slice; the remaining stage/camera pass stays external.
   p.put(11,o);p.put(14,o+0x1000);p.put(18,b)
   boundary=Boundary(0x142918);run(0x1428f4,stops=boundary);assert boundary.stopped==0x142918
   #Timers deliberately read LAST visit's features before sampling.
   run(0x151b00,[a]);run(0x151eb0,[a]);phase_visits+=1
  if contact_phases:run(0x151968,[a])
  if held is not None:
   pressed=held&~previous;p.write(PADS+12*player,held,4);p.write(PADS+12*player+4,pressed,4)
   p.put(16,1);p.put(17,a);p.put(18,other)
   boundary=Boundary(0x149770,0x1498b0);run(0x1495e8,stops=boundary);assert boundary.stopped==0x149770
   raw_visits+=1
  free=p.read(0x46a904,4);handler=p.read(a+0x260,4)
  if ko_phases:watchdog()
  old_color=p.read(o+0x8c,4)
  run(0x149d08,[a]);visits+=1
  if color_projection:
   color_values.add(p.read(o+0x8c,4));color_changes+=p.read(o+0x8c,4)!=old_color
  if (downed or ko or ending) and free>p.read(0x46a904,4):
   assert free-p.read(0x46a904,4)==1 and handler in [0x1715b0,0x172be8],'Unexpected effect producer'
   dust_events+=1;total_dust+=1
  #The raw-input tail is executed separately, with its actual saved return
  #address. The earlier slice ends before14b880 and is never called whole1494f0.
  if held is not None:
   p.put(17,a);p.write(0x1fff038,0x1ffff00,8);run(0x149790)
  run(0x149918,[a]);run(0x11d8e0,[o]);seen.add(p.read(o+0x24,4))
  append('tick' if held is None else f'pad {held} {held&~previous}')
 p=a=o=b=other=None;label=''
 states=[0,1,2,3,4,5,6,7,9,10,11,12,13,14]
 for player,mirror,state in itertools.product(range(2),range(2),[] if boundaries or attacks or damage or downed or ko or ending or colors or rounds else states if not quick else [9,10,4]):
  label=f'entry:{player}:{mirror}:{state}';reset(player,mirror)
  run(0x14ff80,[a+0x18c,0,state]);append(f'state {state}')
  for _ in range(100):tick(player)
 #No guessed state IDs in these trajectories: software pad bits feed real
 #bindings, all command slots, permission gates and the request dispatcher.
 sequences=[[(0x20,40),(0,40)],[(0x20,1),(0,40)],[(0x20,2),(0,40)],
  [(0x20,40),(0,1),(0x20,40),(0,40)],[(0x40,40),(0,40),(0x80,40),(0,40)],
  [(0x60,40),(0,40)],[(0xa0,40),(0,40)],[(0x20,40),(0x60,40),(0xa0,40),(0,40)]]
 for player,mirror,case in itertools.product(range(2),range(2),range(0 if boundaries or attacks or damage or downed or ko or ending or colors or rounds else len(sequences) if not quick else 2)):
  label=f'pad:{player}:{mirror}:{case}';reset(player,mirror);previous=0
  for held,count in sequences[case]:
   for _ in range(count):tick(player,held,previous);previous=held
 if boundaries:
  for player,mirror,case in itertools.product(range(2),range(2),range(7)):
   label=f'boundary:{player}:{mirror}:{case}';reset(player,mirror);previous=0
   def held_for(held,count):
    nonlocal previous
    for _ in range(count):tick(player,held,previous);previous=held
   if case<3:
    #An explicit opponent attack snapshot supplies151478's threat input;
    #the defender must select and play its guard transitions from raw back.
    p.write(other+0x194,1,4);p.write(other+0x23c,0x1001,4);p.write(o+0x1024,185,4);append('threat 1')
    #Normalized bits6/7 feed the original producer's held[2]/held[3].
    #Use the verified back predicate(d8), not a guessed keyboard bit order.
    back=0x80 if mirror else 0x40
    held_for(back|(0x20 if case!=0 else 0),40)
    held_for(0x20 if case==2 else 0,40)
    held_for(0,40)
   elif case==3:
    #Keep sampling while requests are locked;unlock with down still held.
    p.write(a+0x24c,1,1);append('lock 1');held_for(0x20,20)
    p.write(a+0x24c,0,1);append('lock 0');held_for(0x20,30);held_for(0,30)
   elif case==4:
    #Original opposite-direction priority is observable on keyboard input.
    held_for(0xc0,30);held_for(0xe0,30);held_for(0,30)
   elif case==5:
    p.write(a+0x24c,2,1);append('lock 2');held_for(0,50);held_for(0x20,30)
    p.memory[o+0x1040:o+0x1044]=struct.pack('<f',160);append('other 160')
    held_for(0x20,50);held_for(0,30)
   else:
    held_for(0x20,1);p.write(a+0x24c,1,1);append('lock 1');held_for(0,40)
    p.write(a+0x24c,0,1);append('lock 0');held_for(0,40)
 if boundaries:assert {278,280,282,284,286,290,44,46}<=seen,('missing exercised guard/turn actions',seen)
 if attacks:
  for player,mirror,distance,case in itertools.product(range(1 if quick else 2),range(1 if quick else 2),[77,78],range(1 if quick else 4)):
   label=f'attack:{player}:{mirror}:{distance}:{case}';reset(player,mirror);previous=0
   other_x=280+(-distance if mirror else distance)
   p.memory[o+0x1040:o+0x1044]=struct.pack('<f',other_x);append(f'other {other_x}')
   phases=True;append('phases')
   #Live identity fixture: holes, duplicates, and two kind3 objects. The
   #first receives index-64; timer4 must release BOTH objects'108 gates.
   table=b+0x29c+player*0x108
   for slot,h in [(2,1),(7,2),(9,1)]:p.write(table+slot*4,0x1d00000+h*52,4)
   for h,d4,flags in [(1,0x12345678,0x200042),(2,0x89abcdef,0x208080)]:
    obj=0x1d10000+h*320;p.write(0x1d00000+h*52+0x1c,obj,4)
    for off,value in [(0xcc,3),(0xd4,d4),(0x108,flags)]:p.write(obj+off,value,4)
   object_fixture=True;append('objects')
   def held_for_attack(held,count):
    nonlocal previous
    for _ in range(count):tick(player,held,previous);previous=held
   if case==0:
    #A held button is not a repeated press. Then press light during heavy
    #recovery and again after it; requests are filtered by real151b00 gates.
    held_for_attack(0x400,12);held_for_attack(0,2);held_for_attack(0x100,2)
    held_for_attack(0,100);held_for_attack(0x100,1);held_for_attack(0,60)
   elif case==1:
    held_for_attack(0x20,30);held_for_attack(0x420,1);held_for_attack(0x20,100)
    held_for_attack(0x120,1);held_for_attack(0x20,65);held_for_attack(0,35)
   elif case==2:
    for _ in range(28):held_for_attack(0x400,1);held_for_attack(0,3)
    held_for_attack(0,100)
   else:
    #Down and attack on the same visit, then a posture change during the
    #attack. No guessed normal1 injection or artificial recovery request.
    held_for_attack(0x420,1);held_for_attack(0,100)
    held_for_attack(0x120,1);held_for_attack(0x20,65);held_for_attack(0,35)
  if not quick:assert {185,186,189,190,191,192,195,196}<=seen,('missing attack body',seen)
 if damage:
  #Direct descriptors exercise all newly admitted callbacks without a
  #guessed input shortcut; the following matrix adds real request producers.
  for player,mirror,state in itertools.product(range(1 if quick else 2),range(1 if quick else 2),[0,34] if quick else [0,1,2,3,4,5,32,34,35,37,38,40,43,44,46,47,49]):
   label=f'damage-entry:{player}:{mirror}:{state}';reset(player,mirror)
   history=[1,2,0,3,4,47,35,5,0x12345678,0x87654321]
   p.memory[a+0x250:a+0x260]=struct.pack('<8B2I',*history);append('history '+' '.join(map(str,history)))
   run(0x14ff80,[a+0x18c,2,state]);p.write(a+0x18c,1,4);append(f'damage {state}')
   for _ in range(110):tick(player)
  for player,mirror,crouch,strength in itertools.product(range(0 if quick else 2),range(2),range(2),[0,2]):
   label=f'clash-entry:{player}:{mirror}:{crouch}:{strength}';reset(player,mirror)
   if crouch:
    run(0x14ff80,[a+0x18c,0,1]);append('state 1');tick(player)
   run(0x14d070,[a,strength,1]);clash_visits+=1;append(f'clash {strength}')
   for _ in range(110):tick(player)
  for player,mirror,case in itertools.product(range(1 if quick else 2),range(1 if quick else 2),range(1 if quick else 7)):
   label=f'damage-input:{player}:{mirror}:{case}';reset(player,mirror);previous=0
   phases=contact_phases=True;append('combat')
   def pads_for(held,count):
    nonlocal previous
    for _ in range(count):tick(player,held,previous);previous=held
   def hit(raw=10,part=0,special=0,air=0):
    nonlocal hit_visits
    for off,value in [(0x194,((8 if raw==12 else 0)<<16)|1),(0x23c,0x1000|(0x20 if air else 0))]:p.write(other+off,value,4)
    p.write(other+0x19a,12 if raw==12 else 8,1);p.write(o+0x1024,189 if raw==12 else 185,4)
    run(0x14d198,[a,o+0x1000,0,raw,part,special]);hit_visits+=1;append(f'hit {raw} {part} {special} {air}')
   def guard(defense,strength):
    nonlocal guard_visits
    p.write(other+0x194,1,4);p.write(other+0x23c,0x1000,4);p.write(o+0x1024,185,4)
    run(0x14d5a0,[a,o+0x1000,defense,strength]);guard_visits+=1;append(f'guard {defense} {strength}')
   if case==0:
    pads_for(0x400,1);pads_for(0,5);hit();pads_for(0x100,1);pads_for(0,100)
    pads_for(0x400,1);pads_for(0,90)
   elif case==1:
    pads_for(0x20,30);pads_for(0x420,1);pads_for(0x20,5);hit(12,1)
    pads_for(0x120,1);pads_for(0x20,120);pads_for(0,35)
   elif case in [2,3]:
    back=0x80 if mirror else 0x40;down=0x20 if case==3 else 0
    pads_for(down,30);guard(2 if down else 1,2 if down else 0)
    pads_for(back|down,100);pads_for(0,40)
   elif case==4:
    hit();pads_for(0,8);hit();pads_for(0,8);hit();pads_for(0,110)
    pads_for(0x400,1);pads_for(0,90)
   elif case==5:
    pads_for(0x400,1);pads_for(0,5)
    run(0x14d070,[a,2,1]);clash_visits+=1;append('clash 2')
    pads_for(0x100,1);pads_for(0,100);pads_for(0x400,1);pads_for(0,90)
   else:
    pads_for(0x20,30);hit(10,1)
    for _ in range(180):
     pads_for(0x20,1)
     if p.read(a+0x194,2)==0 and p.read(a+0x18c,4):break
    else:raise AssertionError('No recovery entry gap')
    hit(12,1);pads_for(0x20,120);pads_for(0,35)
  if not quick:assert {288,292,338,342,344,348,350,354,360,362,366,368,372,141,143}<=seen,('missing reaction body',seen)
 if downed:
  for player,mirror,state in itertools.product(range(0 if rolls else 1 if quick else 2),range(1 if quick else 2),[64] if quick else [64,16,7]):
   label=f'downed-entry:{player}:{mirror}:{state}';reset(player,mirror)
   phases=contact_phases=True;append('combat')
   history=[1,2,0,15,4,34,34,5,1,0x87654321]
   p.memory[a+0x250:a+0x260]=struct.pack('<8B2I',*history);append('history '+' '.join(map(str,history)))
   run(0x14ff80,[a+0x18c,2,state]);p.write(a+0x18c,1,4);append(f'damage {state}')
   for _ in range(400):
    tick(player)
    if p.read(a+0x194,4)==0 and p.read(a+0x18c,4)==0 and p.read(o+0x24,4)==0:break
   else:raise AssertionError(('Downed entry failed to recover',label))
   assert dust_events==(state==64)
  selected=[int(arg.split('=')[1]) for arg in sys.argv if arg.startswith('--downed-case=')]
  cases=selected or (range(6,9) if rolls else range(1) if quick else range(9))
  for player,mirror,case in itertools.product(range(1 if quick else 2),range(1 if quick else 2),cases):
   label=f'downed-input:{player}:{mirror}:{case}';reset(player,mirror);previous=0
   phases=contact_phases=True;append('combat')
   def pads(held,count=1):
    nonlocal previous
    for _ in range(count):tick(player,held,previous);previous=held
   def heavy():
    nonlocal hit_visits
    p.write(other+0x194,(8<<16)|1,4);p.write(other+0x23c,0x1000,4)
    p.write(other+0x19a,12,1);p.write(o+0x1024,189,4)
    run(0x14d198,[a,o+0x1000,0,12,0,0]);hit_visits+=1;append('hit 12 0 0 0')
   if case==1:pads(0x20,30)
   elif case==2:pads(0x400);pads(0,5)
   heavy();pads(0,8);heavy();pads(0)
   assert p.read(a+0x194,4)==(64<<16)|2 and p.read(o+0x24,4)==384
   if case in [3,4]:
    #Interrupt the state/clip gap, once before rise52 and once before
    #idle. A stale playback phase must not restart the cancelled get-up.
    wanted=(7<<16)|2 if case==3 else 0
    for _ in range(400):
     pads(0)
     if p.read(a+0x194,4)==wanted and p.read(a+0x18c,4):break
    else:raise AssertionError(('Missing downed entry gap',label))
    heavy()
   elif case==5:
    pads(0x400);pads(0,2);pads(0x400);pads(0,2)
   elif case in [6,7,8]:
    for _ in range(400):
     y=struct.unpack_from('<f',p.memory,o+0x44)[0]
     if p.read(a+0x260,4)==0x1715b0 and y<=20 and signed(p.read(o+0x5c,4),32)<0:break
     pads(0)
    else:raise AssertionError(('No manual recovery window',label))
    #1720b0 reads BACK100. Neutral and forward both select54; only
    #back selects55. Test the producer instead of naming a raw field forward.
    direction=(0x80 if mirror else 0x40) if case==7 else (0x40 if mirror else 0x80) if case==8 else 0
    pads(0x1000|direction)
    for _ in range(120):
     if p.read(a+0x194,2)==0:break
     pads(0)
    state=p.read(a+0x196,2);assert state==(55 if case==7 else 54),(label,state)
    recovery_requests.append(dict(player=player,mirror=mirror,state=state))
    wanted=76 if state==55 else 70
    for _ in range(120):
     pads(0)
     if p.read(o+0x24,4)==wanted:break
    else:raise AssertionError(('Missing roll ACT',label,wanted))
    assert p.read(a+0x1b0+6*4,4)==(0 if state==55 else 3*256)
    assert p.read(a+0x1b0+25*4,4)==15*256
    origin=struct.unpack_from('<f',p.memory,o+0x40)[0]
    displacement=0
    for _ in range(180):
     pads(0)
     if p.read(o+0x24,4)==wanted:
      displacement=struct.unpack_from('<f',p.memory,o+0x40)[0]-origin
     if (p.read(a+0xb8,4)&0x20) and p.read(o+0x24,4)!=wanted:break
    else:raise AssertionError(('Roll failed to finish',label,wanted))
    assert displacement!=0,(label,displacement)
    recovery_requests[-1].update(action=wanted,displacement=displacement)
    pads(0,25)
    pads(0x400);pads(0,90)
    continue
   for _ in range(500):
    pads(0)
    if p.read(a+0x194,4)==0 and p.read(a+0x18c,4)==0 and p.read(o+0x24,4)==0:break
   else:raise AssertionError(('Continuous downed sequence did not recover',label))
   assert dust_events==1
   pads(0x400);pads(0,90)
  if rolls:
   assert {70,76,384}<=seen,('Missing recovery roll ACT',seen)
  else:
   assert {384,48,52}<=seen,('Missing downed clips',seen)
 if ko:
  def enable_ko():
   nonlocal phases,contact_phases,ko_phases
   phases=contact_phases=ko_phases=True;append('ko-phases')
  def life(current,maximum=200,pending=0):
   for off,value in zip([0xa30,0xa34,0xa38],[current,maximum,pending]):p.write(a+off,value,4)
   append(f'life {current} {maximum} {pending}')
  def ko_pads(held,count=1):
   nonlocal previous
   for _ in range(count):tick(player,held,previous);previous=held
  def finish_ko():
   for count in range(400):
    ko_pads(0x1420 if count%7==0 else 0)
    if p.read(a+0x260,4)==0x169a50 and p.read(a+0x274,4)==7 and p.read(o+0xc0,4):break
   else:raise AssertionError(('KO did not reach terminal hold',label))
   for held in [0x400,0,0x1000,0,0x20,0,0x80,0]:ko_pads(held)
   assert p.read(a+0xa30,4)==0 and p.read(a+0x23c,4)&0x80 and p.read(a+0x194,2)==2
   assert p.read(a+0x260,4)==0x169a50 and p.read(a+0x274,4)==7
   ko_traces.append(dict(label=label,state=p.read(a+0x196,2),action=p.read(o+0x24,4),dust=dust_events,diagnostics=recovery_diagnostics))
  direct=[(30,0,0)] if quick else [(0,0,0),(7,0,0),(16,0,0),(30,0,0),(30,1,0),(30,0,1),(31,0,0),(32,0,0),(34,0,0),(64,0,0)]
  for player,mirror,(state,back,air) in itertools.product(range(1 if quick else 2),range(1 if quick else 2),direct):
   label=f'ko-entry:{player}:{mirror}:{state}:{back}:{air}';reset(player,mirror);previous=0;enable_ko()
   life(0);posture=0x1080|(0x10 if air else 0);gates=0x8000 if back else 0
   p.write(a+0x23c,posture,4);p.write(a+0x244,gates,4);append(f'posture {posture} {gates}')
   if air:
    motion=[0,12345,0,0,-16384,-512,280,64]
    for off,value in zip(range(0x4c,0x64,4),motion[:6]):p.write(o+off,value,4)
    p.memory[o+0x40:o+0x48]=struct.pack('<ff',*motion[6:]);append('body-motion '+' '.join(map(str,motion)))
   run(0x14ff80,[a+0x18c,2,state]);p.write(a+0x18c,1,4);append(f'damage {state}')
   #Enter directly before raw input can replace an explicit ground fixture.
   tick(player);finish_ko()
  selected=[int(arg.split('=')[1]) for arg in sys.argv if arg.startswith('--ko-case=')]
  for player,mirror,case in itertools.product(range(1 if quick else 2),range(1 if quick else 2),selected or (range(1) if quick else range(8))):
   label=f'ko-input:{player}:{mirror}:{case}';reset(player,mirror);previous=0;enable_ko()
   def ko_hit(raw):
    nonlocal hit_visits
    p.write(other+0x194,((8 if raw==12 else 0)<<16)|1,4);p.write(other+0x23c,0x1000,4)
    p.write(other+0x19a,12 if raw==12 else 8,1);p.write(o+0x1024,189 if raw==12 else 185,4)
    run(0x14d198,[a,o+0x1000,0,raw,0,0]);hit_visits+=1;append(f'hit {raw} 0 0 0')
   if case==1:ko_pads(0x400);ko_pads(0,5)
   if case==4:ko_pads(0x20,30)
   if case in [2,3,4]:ko_hit(10 if case==2 else 12)
   if case in [5,6]:
    ko_hit(12);ko_pads(0,8);ko_hit(12);ko_pads(0)
    assert p.read(o+0x24,4)==384
    if case==6:
     for _ in range(350):
      ko_pads(0)
      if p.read(a+0x194,4)==(7<<16)|2 and p.read(a+0x18c,4):break
     else:raise AssertionError(('Missing rise entry gap',label))
   if case==7:p.write(a+0x24c,1,1);append('lock 1')
   life(1,200,1);finish_ko()
  #Full14b880 helper boundaries, including its living-air recovery path.
  #Raw protected states15/61 are examined without executing their callbacks.
  label='ko-watchdog';reset(0,0);enable_ko()
  for index in range(35):p.write(a+0x1b0+4*index,(index+1)*257,4);append(f'timer {index} {(index+1)*257}')
  states=[0,(8<<16)|1,*[(index<<16)|2 for index in [15,16,30,31,61,64]]]
  old_values=[0x257ff,0x25800] if quick else [-1,0,0x257ff,0x25800,0x173400,0x7fffffff]
  for index,(state,flags,old,delta) in enumerate(itertools.product(states,[0,0x10,0x80,0x90],old_values,[256] if quick else [0,128,512])):
   request=index%2;pending=[(-1,-1),(2,31),(0,1)][index%3];y=64 if flags&0x10 else -2
   for off,value,size in [(0x194,state,4),(0x23c,0x1000|flags,4),(0x1ec,old,4),(0x1ac,delta,4),(0x18c,request,4),(0x190,pending[0],2),(0x192,pending[1],2)]:p.write(a+off,value,size)
   p.memory[o+0x44:o+0x48]=struct.pack('<f',y)
   append('watchdog-fixture '+' '.join(map(str,[state,0x1000|flags,old,delta,request,*pending,y])))
   watchdog();append('watchdog');watchdog_cases+=1
  if not quick:assert {382,384,400,402,48,52}<=seen,('Missing KO/downed bodies',seen)
 if ending:
  def ending_context(state,wins=0,required=2):
   p.write(b,state,4)
   for off,value in [(0x28,wins),(0x2c,required)]:p.write(b+0x254+player*0x108+off,value,4)
   append(f'round-context {state} {wins} {required}')
  def ending_life(current):
   for off,value in [(0xa30,current),(0xa34,200),(0xa38,0)]:p.write(a+off,value,4)
   append(f'life {current} 200 0')
  def ending_setup():
   nonlocal phases,contact_phases,ko_phases,previous
   reset(player,mirror);phases=contact_phases=ko_phases=True;previous=0;append('ko-phases')
   p.write(a+0x24c,1,1);append('lock 1')
  def ending_pads(held,count=1):
   nonlocal previous
   for _ in range(count):tick(player,held,previous);previous=held
  def ending_request(table,state):
   run(0x14ff80,[a+0x18c,table,state])
   if table==2:p.write(a+0x18c,1,4)
   append(f'{"damage" if table==2 else "state"} {state}')
  def ending_ready(state):
   for count in range(600):
    ending_pads(0x1420 if count%7==0 else 0)
    if p.read(a+0x260,4)==0x169a50 and p.read(a+0x274,4)==4 and p.read(o+0xc0,4):break
   else:raise AssertionError(('Ending did not complete',label))
   assert p.read(a+0x196,2)==state
   if state!=52:assert p.read(a+0x244,4)&0x40000000
   before=p.read(o+0x24,4)
   #Force the old-value timeout boundary while holding. Corpse15 is a
   #protected raw state and mode4 must never restart its KO action.
   p.write(a+0x1ec,0x257ff,4);append(f'timer 15 {0x257ff}')
   for held in [0x400,0,0x1000,0,0x20,0,0x80,0]:ending_pads(held)
   assert p.read(a+0x196,2)==state and p.read(o+0x24,4)==before
   ending_traces.append(dict(label=label,state=state,action=before,ready=bool(p.read(a+0x244,4)&0x40000000),intro_steps=sorted(intro_steps),intro_zero_holds=intro_holds))
  direct=[(0,52,200,0,0),(2,15,0,0,0),(0,41,99,2,0)] if quick else [(0,52,200,0,0),*[(2,15,0,0,back) for back in [0,1]],*[(0,41,life,wins,0) for life,wins in itertools.product([99,100],[1,2])]]
  for player,mirror,(table,state,health,wins,back) in itertools.product(range(1 if quick else 2),range(1 if quick else 2),direct):
   label=f'ending-entry:{player}:{mirror}:{table}:{state}:{health}:{wins}:{back}';ending_setup();ending_context(8,wins);ending_life(health)
   if table==2:
    p.write(a+0x23c,0x1080,4);p.write(a+0x244,0x8000 if back else 0,4);append(f'posture 4224 {0x8000 if back else 0}')
   ending_request(table,state);ending_pads(0)
   first_action=p.read(o+0x24,4)
   if state==41:
    assert first_action==(495 if health>=100 else 497)+(4 if wins>=2 else 0)
    ending_context(8,0 if wins>=2 else 2);ending_life(200 if health<100 else 50)
   ending_ready(state);assert p.read(o+0x24,4)==first_action
  for player,mirror,delay in itertools.product(range(1 if quick else 2),range(1 if quick else 2),[3] if quick else [0,3,17]):
   label=f'intro-input:{player}:{mirror}:{delay}';ending_setup();ending_context(1);ending_request(0,39);ending_pads(0)
   run(0x14be28,[a,delay]);defer_visits+=1;append(f'intro-defer {delay}')
   ending_ready(39);assert intro_steps==set(range(21)) and intro_holds==1
   run(0x14bea0,[a]);release_visits+=1;append('intro-release');ending_request(0,0)
   ending_context(4);p.write(a+0x24c,0,1);append('lock 0');ending_pads(0,2);ending_pads(0x400)
   assert p.read(a+0x194,4)==(8<<16)|1 and p.read(o+0x24,4) in [189,190]
   ending_pads(0,90)
  for player,mirror,case in itertools.product(range(1 if quick else 2),range(1 if quick else 2),[0] if quick else [0,1,2]):
   label=f'ending-chain:{player}:{mirror}:{case}';ending_setup();ending_context(1 if case==0 else 5)
   if case==0:
    ending_request(0,39);ending_pads(0)
    run(0x14be28,[a,17]);defer_visits+=1;append('intro-defer 17');ending_pads(0x400,4)
    run(0x14bea0,[a]);release_visits+=1;append('intro-release');ending_request(0,0)
    ending_context(4);p.write(a+0x24c,0,1);append('lock 0');ending_pads(0,2);ending_pads(0x400)
    assert p.read(a+0x194,4)==(8<<16)|1;ending_pads(0,90)
    assert p.read(o+0x24,4) in [0,2];assert p.read(a+0x238,4)==0
   elif case==1:
    ending_request(0,52);ending_ready(52);ending_context(8,2);ending_life(100)
    ending_request(0,41);ending_ready(41);assert p.read(o+0x24,4)==499
   else:
    ending_life(0);ending_request(2,31)
    for _ in range(250):
     ending_pads(0x400)
     if p.read(a+0x260,4)==0x169a50 and p.read(a+0x274,4)==7:break
    else:raise AssertionError(('No KO before corpse',label))
    ending_context(7);ending_request(2,15);ending_ready(15);assert p.read(o+0x24,4)==48
   ending_chains.append(dict(label=label,state=p.read(a+0x194,4),action=p.read(o+0x24,4),timer34=p.read(a+0x238,4)))
  if not quick:assert {48,50,492,493,495,497,499,501}<=seen,('Missing ending bodies',seen)
 if colors:
  def color_context(rage,kind,order):
   for off,value in [(0x120,rage),(0xa2c,kind),(0xa28,order)]:p.write(a+off,value,4)
   append(f'color-context {rage} {kind} {order}')
  def color_timer(index,value):
   p.write(a+0x1b0+4*index,value,4);append(f'timer {index} {value}')
  def color_pads(held,count=1):
   nonlocal previous
   for _ in range(count):tick(player,held,previous);previous=held
  for player,mirror,rage in itertools.product(range(1 if quick else 2),range(1 if quick else 2),[1,2] if quick else range(4)):
   label=f'color-input:{player}:{mirror}:{rage}';reset(player,mirror);previous=0
   color_projection=True;append('colors');phases=contact_phases=True;append('combat')
   color_context(rage,0,0x43210000+player*256+rage)
   #Force an ordinary entry so rage selects its real idle body. Later rage
   #changes must not restart the same idle solely to change its appearance.
   run(0x14ff80,[a+0x18c,0,1]);append('state 1');tick(player)
   for _ in range(60):
    color_pads(0);idle=p.read(o+0x24,4)
    if p.read(a+0x194,4)==0 and idle in [0,2]:break
   else:raise AssertionError(('No idle after stand-up',label,idle))
   assert idle==(2 if rage in [1,2] else 0),(label,idle)
   color_timer(16,0x76ff);color_pads(0,44)
   color_timer(17,120*256);color_timer(18,2160);color_timer(33,0xa00)
   color_pads(0x400);assert p.read(a+0x194,4)==(8<<16)|1
   color_pads(0,2)
   #Supplied presentation selector, not a claim that an elemental hit
   #producer has been ported. It must bypass the active rage/flash branch.
   color_context(rage,3,0x43210100+player);color_pads(0,6)
   color_context(rage,0,0x43210200+player);color_pads(0,85)
   color_timer(17,0);color_pads(0,12)
   color_context(0 if rage else 1,0,0x43210300+player)
   color_pads(0x20,12);color_pads(0x420);assert p.read(a+0x194,4)==(9<<16)|1
   color_pads(0x20,95);color_pads(0,12)
  assert color_changes>0 and len(color_values)>20,(color_changes,len(color_values))
  assert {189,190}&seen and {195,196}&seen,seen
 if rounds:
  import random as random_module
  from validate_object_pools import OBJECTS,handle
  rng=random_module.Random(0x149008)
  modes=[0,3,4,10,11,14,15,19,20,21,24,25,26,29,30,31,34,35,37,38,69,70,0xffffffff,0x80000000]
  def round_pads(held,count=1):
   nonlocal previous
   for _ in range(count):tick(player,held,previous);previous=held
  def initialize_round(first):
   nonlocal round_images,round_visits,round_preserved_input
   owner_before=bytes(p.memory[a+0x2c4:a+0xa08])
   image=p.read(0x46a900,4);round_images=[]
   for _ in range(3):
    round_images.append(handle(image,OBJECTS,320));image=p.read(image+0x138,4)
   run(0x149008,[a,first]);round_visits+=1
   assert bytes(p.memory[a+0x2c4:a+0xa08])==owner_before,('Round entry changed input owner',label)
   round_preserved_input+=1;append(f'new-round {first}')
   round_traces.append(dict(label=label,first=first,old_body=p.read(o+0x24,4),queued=signed(p.read(a+0xa3c,4),32),
    history_body=p.read(a+0xa64,4),control_mode=p.read(a+0xc8,4),control_delay=p.read(a+0x10,4),
    rage=signed(p.read(a+0x120,4),32),objects=round_images.copy()))
   run(0x149918,[a]);append('commit-actor')
   run(0x11d8e0,[o]);append('commit-body');seen.add(p.read(o+0x24,4))
  cases=itertools.product(range(1 if quick else 2),range(2),[1] if quick else range(4),range(1 if quick else 2))
  for case,(player,first,rage,random_mode) in enumerate(cases):
   label=f'round-input:{player}:{first}:{rage}:{random_mode}';reset(player,1-player);previous=0
   round_projection.reset_storage(p,a,b,player,run);round_fields=True;append('round-storage')
   phases=contact_phases=True;append('combat')
   #Publish real nonempty command state and a partially played heavy body.
   #The round initializer must consume the same persistent actor/input.
   round_pads(0x400);round_pads(0,3)
   seed=case*271+19
   for address,values in [(HELD,[(seed+i*13)&0xffff for i in range(600)]),(PRESSED,[(seed*3+i*7)&0xffff for i in range(600)])]:
    p.memory[address:address+1200]=struct.pack('<600H',*values)
   append(f'round-replay {seed}')
   data=[0xfffffff2,0x12345678,0x1de0000,0x89abcdef,12345,19*256,1234,3456,
    0xa5a50010,0x101,0x12345678,modes[case%len(modes)],*[rng.getrandbits(32) for _ in range(8)],
    *[rng.getrandbits(32) for _ in range(20)],*[rng.randrange(256) for _ in range(23)],
    3 if random_mode else 0,rng.getrandbits(32),rng.getrandbits(64)]
   data[40+5]=[0x3e,0x3f,0x7f,0xbf][case%4]
   data[40+13]=[0x7e,0x7f,0xff,0x80][case%4]
   round_projection.seed_data(p,a,data);append('round-data '+' '.join(map(str,data)))
   for off,value in [(0x120,rage),(0x124,20000),(0xa2c,3),(0xa28,0x12340000+case)]:p.write(a+off,value,4)
   #color-context intentionally leaves the amount untouched; use a separate
   #probe seed for this reset input rather than inventing rage gameplay.
   append(f'round-meter {rage} 20000 3 {0x12340000+case}')
   for off,value in [(0xa30,-5),(0xa34,999),(0xa38,37)]:p.write(a+off,value,4)
   append('life -5 999 37')
   for i in range(35):
    value=-(i+1)*123 if i%3==0 else (i+1)*251
    p.write(a+0x1b0+4*i,value,4);append(f'timer {i} {value}')
   p.write(a+0x23c,0xf03bffff,4);p.write(a+0x244,0xefffffff,4);append('posture 4030463999 4026531839')
   #body metadata is inherited by all three real child allocations.
   body=[0,128,0x3fc00000,0x41280000,0x10203040,0x20304050,0x30405060,3.25,-2.5]
   for off,value in zip([0xc,0x30,0x70,0x48,0x64,0x68,0x6c],body[:7]):p.write(o+off,value,4)
   for off,value in zip([0xec,0xf0],body[7:]):p.memory[o+off:o+off+4]=struct.pack('<f',value)
   append('round-body '+' '.join(map(str,body)))
   initialize_round(first)
   if first:
    #The outer round controller is an explicit boundary here. Exercise
    #actual intro callbacks before supplying its release and normal0 request.
    p.write(b,2,4);append('round-context 2 0 2')
    round_pads(0,220)
    run(0x14bea0,[a]);release_visits+=1;append('intro-release')
    run(0x14ff80,[a+0x18c,0,0]);append('state 0');tick(player)
    p.write(b,4,4);append('round-context 4 0 2')
   round_pads(0,2);round_pads(0x400);assert p.read(a+0x194,4)==(8<<16)|1,(label,hex(p.read(a+0x194,4)))
   round_pads(0,3)
   #No probe.reset or input initialization at this second round boundary.
   initialize_round(0);round_pads(0,2);round_pads(0x400)
   round_pads(0,115)
   assert p.read(a+0x194,4)==0,(label,hex(p.read(a+0x194,4)))
   print(f'Completed {label}',file=sys.stderr,flush=True)
  assert {189,190}&seen and {0,2}&seen,seen
 report=dict(snapshots=len(expected),whole149d08_visits=visits,quick_subset=quick,
  stage_distance_slices=phase_visits,
  sampling_request_slices=raw_visits,original_instructions=instructions,actions=sorted(seen),
  scope='Resource00 armed/system0 ordinary states0..7/9..14: complete entry,metadata,callback registration/execution,tail entry and body commits. Persistent software-pad input trajectories compose actual171 features/63 command slots,permissions,request selection,state entry and ground bodies. Sampling and late tail are explicit1494f0 slices;149d08 and reached callees run unchanged. Compare represented state/metadata/conditions/callbacks/all35timers/body flags+motion+clocks/input progress+latches/saved variant/swordWait/opponentB8/marker/24c/contact history/override/shake fields. No whole battle or hardware comparison; attacks and damage have separate suites;dash/jump dispatch remains unimplemented in this ground component;current packaged battle still direct commands.')
 if boundaries:report['scope']+=' Additional raw pad guard-threat snapshots,request locks,held-down unlock,opposite directions,turn-enabled flags and opponent-side changes. Opponent attack/position are explicit fixtures,not contact simulation.'
 if attacks:
  report['whole151b00_visits']=report['whole151eb0_visits']=phase_visits
  report['scope']='Persistent resource00 armed/system0 human ground attacks0/1/8/9: original1428f4..142918 distance slice,151b00 gates,151eb0 timer pass,1494f0 sampling/request+tail slices,whole149d08 entry/metadata/registration/callback/tail and body commit. Both players/facings and supplied initial distances77/78;held/repeated buttons,recovery input,crouch+attack chords. Compare state/metadata/conditions/callbacks/all35timers/body flags+motion+clocks/171features/63command progress+results/12latches/swordWait/opponentB8/marker/objectD4+108. Auxiliary registrations include holes+aliases+two kind3 objects. Opponent position is supplied;full stage,contacts,whole original frame,PS2 hardware and live battle integration are not claimed.'
 if damage:
  report.update(whole151b00_visits=phase_visits,whole151eb0_visits=phase_visits,whole151968_visits=contact_visits,
   contact_postpass_slices=contact_visits,whole14d198_visits=hit_visits,whole14d5a0_visits=guard_visits,whole14d070_visits=clash_visits)
  report['scope']='Resource00 armed/system0 common guard0..5 and light/heavy hurts32/34/35/37/38/40/43/44/46/47/49 plus weapon-clash25/27/28/30. Whole149d08 and reached callees;composed original14d198/14d5a0/14d070 request producers,142580..142618 post-contact and1428f4..142918 distance slices,151b00/151eb0/151968,1494f0 input-request+tail slices. Explicit opponent/source snapshots and128/256speed boundary. Compare persistent input,all contact history(including seeded preservation/reset),callbacks/override,shake fields,flags/motion/clocks,timers,guard recovery,interruption and recovery gap. No contact geometry/damage amount,KO/downed callbacks,color,full original frame or live battle claim.'
 if downed:
  report.update(whole151b00_visits=phase_visits,whole151eb0_visits=phase_visits,whole151968_visits=contact_visits,
   contact_postpass_slices=contact_visits,whole14d198_visits=hit_visits,whole_first_landing_effects=total_dust,recovery_request_boundaries=recovery_requests)
  report['scope']='Resource00 armed/human/system0 persistent input through repeated-heavy14d198 ->damage64/384 ->16/48 ->7/52 ->normal, including attack interruption and incoming hits in rise/idle entry gaps. Whole149d08/reached callees with real170fa0 effect allocation and libc formatting;142580..142618 postcontact,1428f4..142918 distance and1494f0 input/tail are explicit slices. Shared callbacks/history/A4c,all timers,body clocks/motion/flags,input progress and dust birth counts compared. Manual recovery follows actual software pad through rolls54/55, timers6/25, movement, recovery flag, and next attack. Explicit finite FP model,source/position/speed boundary,initialized effect/libc pools. No whole collision/damage/frame,KO/color,hardware or live raw-input integration claim.'
 if rolls:
  report['scope']='Resource00 armed/system0 manual recovery after two heavy hits. Raw neutral/forward/back plus recovery button produces 54/55 and ACT70/76. Original 149d08 and reached callbacks vs native actor/body clocks, motion, states, timers, contact history, flags, input and subsequent attack. Both player slots and both facings. Collision and amount of the initial two hits are explicit inputs.'
 if ko:
  report.update(whole151b00_visits=phase_visits,whole151eb0_visits=phase_visits,whole151968_visits=contact_visits,
   contact_postpass_slices=contact_visits,whole14d198_visits=hit_visits,whole14b880_visits=watchdog_visits,
   watchdog_boundary_cases=watchdog_cases,whole_first_landing_effects=total_dust,ko_traces=ko_traces)
  report['scope']='Resource00 armed/human/system0 KO30/31, fatal guard/hurt174fe0 raw remap, downed64/16 holding, actual software input during fatal transitions and terminal hold. Original whole149d08,151b00/151eb0/151968,14b880 and reached callees including real effect allocation/libc logging; postcontact,distance,input/tail remain explicit slices. Compare shared state/metadata/conditions/callbacks/history/all timers/body clocks+motion+flags/input/HP+pending damage/dust and diagnostic counts. Explicit positive pending-damage/source/position/speed fixtures; not collision geometry/damage amount,full original actor/frame,KO round controller,color,hardware or live raw-input integration. Whole14b880 boundaries also compare living-air fallback,raw protected states,old-value threshold,overflow and preserved requests.'
 if ending:
  report.update(whole151b00_visits=phase_visits,whole151eb0_visits=phase_visits,whole151968_visits=contact_visits,
   contact_postpass_slices=contact_visits,whole14b880_visits=watchdog_visits,whole14be28_visits=defer_visits,
   whole14bea0_visits=release_visits,whole_first_landing_effects=total_dust,scenario_count=len(set(labels)),ending_traces=ending_traces,ending_chains=ending_chains)
  report['scope']='Resource00 armed/human/system0 normal39 introduction,52 winner wait,41 victory/final and damage15 corpse in persistent software input. Whole149d08 and reached entry/playback/auxiliary-null callees,151b00/151eb0/151968,14b880,explicit14be28/14bea0; postcontact,distance,input/tail are slices. Both players/facings,HP99/100,wins threshold,entry-only selection,all21 intro stages/zero hold,timer34 delayed restart/release,KO->corpse and winner wait->victory,holds under input. Compare existing full projected fields/HP/timers/input/callbacks/flags/motion/dust; caller-supplied round state,input lock,stats,life and requests. No full round controller/149008 reset,cross-character intro,unarmed final,color/audio,full original frame/hardware or live raw-input integration claim.'
 if colors:
  report.update(whole151b00_visits=phase_visits,whole151eb0_visits=phase_visits,whole151968_visits=contact_visits,
   contact_postpass_slices=contact_visits,color_changes=color_changes,distinct_color_words=len(color_values),scenario_count=len(set(labels)))
  report['scope']='Resource00 armed/system0 persistent software pad input with rage0..3,real idle selection,standing/crouching heavy,tail entry and body commit. Whole149d08 includes14b190 after tail entry/before149918;151b00/151eb0/151968 and explicit postcontact/distance/input slices. Existing state/input/callback/body/timer projection plus body8c/20,actorA28/A2c/rageState/rageAmount. Explicit rage/color/flash/fade timer seeds; color precedence,pulse wrap,fade and old-body classification across attacks/recovery. No elemental-hit producer,round reset,whole frame,draw-packet/GS output or live raw-input integration claim.'
 if rounds:
  report.update(whole149008_visits=round_visits,whole151b00_visits=phase_visits,whole151eb0_visits=phase_visits,
   whole151968_visits=contact_visits,contact_postpass_slices=contact_visits,whole14bea0_visits=release_visits,
   unchanged_input_owner_checks=round_preserved_input,scenario_count=len(set(labels)),round_traces=round_traces)
  report['scope']='Resource00 armed/human/system0 default-options persistent round initialization, whole149008 with all callees unmodified, followed by separate149918 and11d8e0. Both players,first/subsequent rounds,rage0..3,both RNG generators,seeded controls/timers/character bytes/body metadata,real three-afterimage allocations and all60 old-body history samples. Compare all256 task/object records using normalized pointer identities,free lists/registries/RNG/input definitions+features+progress+latches/shared600 recordings and existing ground projection. Continuous raw-pad heavy before/after two resets;normal39 introduction release is an explicit outer-controller boundary. Whole149d08/151b00/151eb0/151968 plus existing explicit postcontact/distance/input/tail slices. Body record sound selection preserves real1e83c0 RNG draws and both shared previous-choice words;no audible output or full sound-channel model. Finite FP model;no full13fd80/controller/actor/frame,task scheduler,render/hardware or live raw-input integration claim.'
 if quick:report['scope']='Quick subset of the matrix described below; not the full suite. '+report['scope']
 if not quick:
  assert pins==oracle_pins(),'Original oracle inputs changed during execution'
  #Save before native comparison so a C++ correction can reuse the exact
  #original trace. A failed comparison never writes a successful report.
  with gzip.open(cache,'wt',compresslevel=1) as stream:
   json.dump(dict(pins=pins,commands=commands,expected=expected,labels=labels,report=report),stream)
 report['native_sha256']=check_native(commands,expected,labels)
 report['status']='passed_for_projected_fields';report['oracle_cache_reused']=False
 if not quick:destination.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
