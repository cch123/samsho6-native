#!/usr/bin/env python3
"""Integration invariants + independent opaque-scene/PIL-alpha compositor.
This is not a full-frame original-game oracle; primitive reports are separate.
"""
import hashlib,json,random,struct,subprocess,math
from functools import lru_cache
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];ASSETS=ROOT/'work/ss6/extracted/resources';OUT=ROOT/'outputs/ss6-feasibility'
PROBE=ROOT/'work/ss6/build-native/ss6-contact-trial-probe';VIEWER=ROOT/'work/ss6/build-native/ss6-viewer'
def run(commands):
 r=subprocess.run([str(PROBE),str(ASSETS)],input='\n'.join(commands)+'\n',text=True,capture_output=True,timeout=30)
 assert r.returncode==0,(commands[-10:],r.stderr,r.stdout[-1200:])
 rows=[[float(x) for x in line.split()] for line in r.stdout.splitlines()]
 assert len(rows)==len(commands)
 return rows
def main():
 cases=[]
 for defender in [0,3,4]:
  rows=run(['place 280 344',f'command 1 {defender}','tick 1','command 0 5']+['tick 1']*40)
  final=rows[-1];assert final[2]==200 and final[13]==(192 if not defender else 200)
  assert final[11:13]==([1,0] if not defender else [0,1])
  assert final[3]==final[14]==0
  active=next(r for r in rows if r[11]+r[12])
  assert active[8]==(128 if not defender else 768)
  assert active[19]==(128 if not defender else 1280 if defender==4 else 768)
  cases.append(f'one_contact_defense_{defender}')
 rows=run(['place 280 344','command 0 5','command 1 5','tick 40']);assert rows[-1][2]==rows[-1][13]==192;cases.append('trade')
 rows=run(['place 280 420','command 0 5','tick 60']);assert rows[-1][13]==200 and rows[-1][11]==0;cases.append('miss')
 rows=run(['place 280 344','command 1 5','tick 40']);assert rows[-1][2]==192 and rows[-1][13]==200;cases.append('mirrored_hit')
 rows=run(['place 310 318','tick 20']);assert rows[-1][18]-rows[-1][7]>8;cases.append('push_separates')
 for distance,action in [(77.75,185),(78,186),(78.25,186)]:
  row=run([f'place 280 {280+distance}','command 0 5','tick 1'])[-1]
  assert row[5]==action,(distance,row)
 cases.append('inclusive_near_far_boundary')
 rows=run(['place 280 380','command 0 5','command 1 5']+['tick 1']*60)
 assert any(r[5]==r[16]==141 for r in rows)
 assert rows[-1][5]==rows[-1][16]==0 and rows[-1][2]==rows[-1][13]==200
 cases.append('weapon_clash_recoil_recovers')
 rows=run(['place 280 460','command 0 5']+['tick 1']*300)
 assert min(r[24] for r in rows)==96*256 and rows[-1][24]==100*256
 waiting=next(i for i,r in enumerate(rows) if r[26]==20)
 assert [r[26] for r in rows[waiting:waiting+21]]==list(range(20,-1,-1))
 assert len({r[24] for r in rows[waiting:waiting+21]})==1
 assert rows[waiting+21][24]>rows[waiting+20][24]
 cases.append('whiff_cost_delay_and_recovery')
 for a,b,x,center in [(2,1,34,160),(1,2,606,480)]:
  rows=run([f'command 0 {a}',f'command 1 {b}']+['tick 1']*400)
  end=rows[-1];assert end[7 if a==2 else 18]==x and end[36]==center
  assert end[2]==end[13]==200 and end[38]==320
  assert all(34<=r[7]<=606 and 34<=r[18]<=606 for r in rows)
  assert all(abs(b[36]-a[36])<=4 for a,b in zip(rows,rows[1:]))
 cases.append('both_absolute_stage_edges')
 rows=run(['command 0 2','command 1 2']+['tick 1']*400)
 end=rows[-1];assert end[7]==132 and end[18]==508 and end[36:41]==[320,120,444,98,542]
 assert all(abs(b[38]-a[38])<=2 for a,b in zip(rows,rows[1:]))
 cases.append('maximum_camera_separation')
 # Reach the wall through controls, then land a hit there. The attacker's
 # pushback comes from the defender's wall correction, not a position edit.
 rows=run(['command 0 1','command 1 2','tick 400','command 0 0','command 1 0','tick 1','command 0 5']+['tick 1']*40)
 assert rows[-1][13]==192 and rows[-1][7]<rows[6][7] and rows[-1][18]<=606
 cases.append('wall_hit_pushback')
 # Reach zero life through actual movement and repeated attacks, with no
 # position/life edits between strikes. KO must continue into the original
 # body callback and camera queue, then finish the non-final victory clip.
 commands=['place 280 344']
 for i in range(120):commands+=['command 0 5','tick 40','command 0 1','tick 8','command 0 0','tick 1']
 rows=run(commands);final=rows[-1]
 assert final[1]==0 and final[13]==0 and final[2]==200,final
 ko=next(r for r in rows if r[1]>=0)
 assert final[0]>ko[0] and final[4:6]==[41,495] and final[15:17]==[15,48]
 assert final[52:55]==[0,1,1] and final[57:60]==[8,8,1] and final[68]==1,final
 cases.append('movement_attack_damage_ko')
 reset=run(commands+['reset'])[-1]
 assert reset[0:3]==[0,-1,200] and reset[13]==200 and reset[7]==240 and reset[18]==400;cases.append('reset')
 assert run(commands)==rows;cases.append('deterministic_replay')
 rng=random.Random(154678);commands=[]
 for episode in range(48):
  commands+=['reset',f'place {280+rng.randrange(-12,13)} {320+rng.randrange(-12,90)}']
  for i in range(80):commands += [f'command {rng.randrange(2)} {rng.randrange(6)}',f'tick {rng.randrange(1,10)}']
 random_rows=run(commands);cases.append('random_sequences')
 pixels=validate_pixels()
 report=dict(status='passed_for_integration_fixture',scenarios=cases,random_snapshots=len(random_rows),**pixels,
  ko_update=int(ko[0]),hits_to_ko=int(ko[11]),probe_sha256=hashlib.sha256(PROBE.read_bytes()).hexdigest(),
  viewer_sha256=hashlib.sha256(VIEWER.read_bytes()).hexdigest(),
  scope='Integration invariants and independent decoded-PIL pixel composition using original anchor projection, not a full original-frame oracle or hardware GS comparison. Raw standing-light selection; direct guard/movement state requests; automatic near/far selection, ordinary gauge update, recoil, stage/camera and ending states4/5/7/8 with ordinary40+2pause, camera queue and non-final victory. KO15/18 and landing29 have separate effect/image reports. 400x160 crop and nearest preview rasterizer; GS coverage unverified. Full input, route7/8 effects/audio, other pause paths and complete round controller remain pending. Damage/recovery/camera use explicit provisional finite-FP model.')
 (OUT/'contact_trial_validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
def validate_pixels(heavy=False,crouching=False):
 aid,act,pil,idx,maps,tiles,pal=[(ASSETS/f).read_bytes() for f in ['aid_00.bin','act_00.bin','pil_00.bin','idx_00.bin','map_00.bin','chr_00.bin','pal_all.bin']]
 @lru_cache(None)
 def image(index):
  entry=struct.unpack_from('<I',idx,index*4)[0];bank,offset=entry>>24,entry&0xffffff;assert bank in (0,1,26)
  tw,th=maps[offset:offset+2];w,h=tw*8,th*8;pixels=bytearray()
  colors=[bytes((((c>>10)&31)*255//31,((c>>5)&31)*255//31,(c&31)*255//31,255 if c&0x8000 else 0)) for c, in struct.iter_unpack('<H',pal[bank*32:bank*32+32])]
  for y in range(h):
   for x in range(w):
    tx,ty=x//8,y//8;slot=(ty//2)*tw*2+(tx//2)*4+(ty%2)*2+tx%2
    tile=int.from_bytes(maps[offset+2+slot*3:offset+5+slot*3],'little');packed=tiles[tile*32+y%8*4+x%8//2]
    pixels.extend(colors[(packed>>(x%2*4))&15])
  return w,h,pixels
 # Projection comes from original instructions, independently of the C++
 # renderer and helper. Pixel sampling remains a preview rasterizer check.
 from mips_probe import Probe
 from validate_stage_camera import bits
 original=Probe((ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes(),finite_model=True)
 def scalar(v):return struct.unpack('<f',struct.pack('<I',v))[0]
 #Heavy/light suites may run independently; neither may replace the other's
 #script or dump between rendering and the pixel comparison.
 suffix=('crouch-' if crouching else '')+('heavy' if heavy else 'light')
 pixel_cases=0;alpha_parts=0;additive_parts=0;far_steps=set();scratch=ROOT/f'work/ss6/actions/trial-comparison-{suffix}.rgba'
 scenes=[(64,0,d,c) for d,c in [('neutral',0),('stand',3),('crouch',4)]]
 scenes += [(100,i,d,c) for i in range(2) for d,c in [('neutral',0),('stand',3),('crouch',4)]]
 scenes += [(180,i,'neutral',0) for i in range(2)]
 scenes += [(-1,0,'neutral',0),(-2,0,'neutral',0),(-3,1,'neutral',0)]
 if heavy:
  scenes=[(distance,i,d,c) for distance in [64,100,180] for i in range(2) for d,c in [('neutral',0),('stand',3),('crouch',4)]]
 if crouching:
  scenes=[(distance,i,d,c) for distance in [64,100,180] for i in range(2) for d,c in [('neutral',0),('stand',3),('crouch',4),('low-idle',7)]]
 heavy_steps={189:set(),190:set()};hurt_steps=set()
 crouch_steps={195:set(),196:set()} if heavy else {191:set(),192:set()}
 for distance,attacker,defense,cmd in scenes:
  setup=[f'place 280 {280+distance}',f'command {1-attacker} {cmd}','tick 1',f'command {attacker} {6 if heavy else 5}']
  if crouching:setup.insert(2,f'command {attacker} 7')
  if distance<0:
   moves={-1:(2,2),-2:(1,2),-3:(2,1)}[distance]
   setup=[f'command 0 {moves[0]}',f'command 1 {moves[1]}','tick 400','command 0 0','command 1 0','tick 1',f'command {attacker} {6 if heavy else 5}']
  script=ROOT/f'work/ss6/actions/trial-preview-{suffix}.txt';script.write_text('\n'.join(setup)+'\n')
  states=run(setup+['tick 1']*(120 if heavy or crouching else 45))
  updates=[0,1,4,5,6,8,10,14,18,24,35,45] if distance==64 else [0,1,4,6,7,8,10,11,12,13,14,16,20,25,27,29,40]
  if heavy or crouching:
   seen=set();updates=[]
   for update in range(121):
    row=states[len(setup)-1+update];key=tuple(row[n] for n in [5,6,16,17])
    if key not in seen:updates.append(update);seen.add(key)
  for update in updates:
   state=states[len(setup)-1+update]
   original.floats[12:15]=list(map(bits,state[36:39]));original.run(0x122ed8)
   original.floats[12]=bits(0);original.run(0x122ff0)
   scale=int(scalar(original.floats[0])*128)/128
   canvas=bytearray()
   for y in range(160):
    for x in range(400):
     v=29 if (x//8+y//8)%2 else 34;canvas.extend([v,v+6,v+12,255])
   for i in range(2):
    base=2+i*11;action,step,x=int(state[base+3]),int(state[base+4]),state[base+5]
    original.floats[12:15]=[bits(x),bits(0),bits(0)];original.run(0x123020,[0x1e10000])
    ox=int(40+scalar(original.read(0x1e10000,4))*.5);oy=int(scalar(original.read(0x1e10004,4))*.5-68)
    if action==186:far_steps.add(step)
    if action in heavy_steps:heavy_steps[action].add(step)
    if action in crouch_steps:crouch_steps[action].add(step)
    if action==342:hurt_steps.add(step)
    start=struct.unpack_from('<h',aid,action*2)[0];parts=[]
    for ref in struct.unpack_from('<5h',act,(start+step)*60+4):
     if ref:
      cell,px,py,z,tint,flags,unknown=struct.unpack_from('<4hI2H',pil,(ref-1)*16)
      assert flags&0x7ff0 in (0x10,0x30)
      if flags&0x7ff0==0x10:assert tint&0xffffff==0x808080
      if cell:parts.append((flags&15,cell-1,px,py,tint,flags))
    for _,cell,px,py,tint,flags in sorted(parts,key=lambda p:p[0]):
     w,h,pixels=image(cell);alpha=((tint>>24)+1)//2;alpha_parts+=alpha!=128
     additive=bool(flags&0x20);additive_parts+=additive
     mirror=bool(i);left=ox+(-px-w if mirror else px)*scale;top=oy-py*scale
     for dy in range(max(0,math.ceil(top-.5)),min(160,math.ceil(top+h*scale-.5))):
      for dx in range(max(0,math.ceil(left-.5)),min(400,math.ceil(left+w*scale-.5))):
       sy=min(h-1,max(0,int((dy+.5-top)/scale)));sx=min(w-1,max(0,int((dx+.5-left)/scale)))
       sourceX=w-1-sx if bool(flags&0x8000)!=mirror else sx
       c=pixels[(sy*w+sourceX)*4:(sy*w+sourceX+1)*4]
       if not c[3]:continue
       p=(dy*400+dx)*4
       for channel in range(3):
        if additive:
         modulation=(((tint>>(8*channel))&255)+1)//2
         canvas[p+channel]=min(255,canvas[p+channel]+c[channel]*modulation//128)
        else:canvas[p+channel]=(c[channel]*alpha+canvas[p+channel]*(128-alpha))//128
    # No floating accumulator or per-actor transparency flattening in Python.
   subprocess.run([str(VIEWER),'--assets',str(ASSETS),'--mode','trial','--trial-script',str(script),'--updates',str(update),'--dump',str(scratch)],check=True,timeout=10)
   raw=scratch.read_bytes();assert struct.unpack('<II',raw[:8])==(400,160)
   assert raw[8:]==canvas,(distance,attacker,defense,update,'PIL scene mismatch')
   pixel_cases+=1
 if crouching:
  counts={195:15,196:15} if heavy else {191:6,192:12}
  assert crouch_steps=={k:set(range(v)) for k,v in counts.items()},crouch_steps
 elif heavy:
  assert heavy_steps=={189:set(range(14)),190:set(range(16))},heavy_steps
  assert hurt_steps==set(range(7)),hurt_steps
 else:assert alpha_parts>0 and additive_parts>0 and far_steps==set(range(14)),far_steps
 return dict(pixel_scenes=pixel_cases,translucent_part_instances=alpha_parts,additive_part_instances=additive_parts,
  far_action_steps=sorted(far_steps),heavy_action_steps={str(k):sorted(v) for k,v in heavy_steps.items()},heavy_hurt_steps=sorted(hurt_steps),
  crouch_action_steps={str(k):sorted(v) for k,v in crouch_steps.items()} if crouching else {})

if __name__=='__main__':main()
