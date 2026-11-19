#!/usr/bin/env python3
"""Independent decoded-PIL scene checks for every admitted KO body stage."""
import hashlib,json,math,struct,subprocess,sys
from functools import lru_cache
from pathlib import Path
from mips_probe import Probe
from validate_stage_camera import bits
from validate_assets import png
from effect_oracle import OriginalEffects
ROOT=Path(__file__).resolve().parents[2];ASSETS=ROOT/'work/ss6/extracted/resources'
OUT=ROOT/'outputs/ss6-feasibility';BUILD=ROOT/'work/ss6/build-native'
def main():
 aid,act,pil,idx,maps,tiles,pal=[(ASSETS/f).read_bytes() for f in
  ['aid_00.bin','act_00.bin','pil_00.bin','idx_00.bin','map_00.bin','chr_00.bin','pal_all.bin']]
 @lru_cache(None)
 def image(index):
  entry=struct.unpack_from('<I',idx,index*4)[0];bank,offset=entry>>24,entry&0xffffff
  assert bank in (0,1,26)
  tw,th=maps[offset:offset+2];w,h=tw*8,th*8
  colors=[bytes((((c>>10)&31)*255//31,((c>>5)&31)*255//31,(c&31)*255//31,255 if c&0x8000 else 0))
          for c, in struct.iter_unpack('<H',pal[bank*32:bank*32+32])]
  pixels=bytearray()
  for y in range(h):
   for x in range(w):
    tx,ty=x//8,y//8;slot=(ty//2)*tw*2+(tx//2)*4+(ty%2)*2+tx%2
    tile=int.from_bytes(maps[offset+2+slot*3:offset+5+slot*3],'little')
    packed=tiles[tile*32+y%8*4+x%8//2];pixels.extend(colors[(packed>>(x%2*4))&15])
  return w,h,pixels
 p=Probe((ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes(),finite_model=True)
 scalar=lambda v:struct.unpack('<f',struct.pack('<I',v))[0]
 scratch=ROOT/'work/ss6/actions/knockout-comparison.rgba'
 comparisons=[];alpha_parts=0;additive_parts=0;vertical_parts=0;sheet=[];effect_vertices=0
 fixtures=[(a,m,'') for a in [400,401,402,403,382,383] for m in [0,1]]+[(None,m,'') for m in [0,1,2]]+[(None,m,'-low') for m in [0,1]]
 fixtures += [(None,m,s) for m in [0,1] for s in ['-final','-final-low']]
 fixtures += [(None,0,'-intro')]
 downed_only='--downed-only' in sys.argv
 if downed_only:fixtures=[(None,p,f'-downed-{d}') for p in [0,1] for d in [64,100]]
 for action,mirror,suffix in fixtures:
  final='final' in suffix
  intro=suffix=='-intro'
  downed=suffix.startswith('-downed-')
  updates=190 if downed else 205 if intro else 640 if final else 480 if action is None else 200
  if action is None:
   script=ROOT/'work/ss6/scenarios'/(f'heavy-knockdown-{mirror}-{suffix.rsplit("-",1)[1]}.txt' if downed else 'match-opening.txt' if intro else f'match-final-{mirror}-{99 if suffix.endswith("low") else 100}.txt' if final else f'battle-ending-{mirror}{suffix}.txt')
   commands=script.read_text().splitlines()+['tick 1']*updates
   viewer_args=['--mode','trial','--trial-script',str(script)]
  else:
   commands=[f'knockout {mirror} {action}']+['tick 1']*200
   viewer_args=['--mode','knockout','--action',str(action),'--dump-mirror',str(mirror)]
  result=subprocess.run([str(BUILD/'ss6-contact-trial-probe'),str(ASSETS)],input='\n'.join(commands)+'\n',capture_output=True,text=True,check=True)
  rows=[[float(v) for v in row.split()] for row in result.stdout.splitlines()]
  assert len(rows)==len(commands)
  rows=rows[-(updates+1):]
  seen=set();samples=[];effects=OriginalEffects();queued=[]
  for update,state in enumerate(rows):
   draws=effects.tick(state);queued.append(draws)
   key=tuple(state[j] for j in [5,6,16,17,36,37,38,45,46,51,52,57,58,59,68])+tuple((d[0x24:0x2c],d[0x74:0x80]) for d in draws)
   if key not in seen or update in [15,35,55,100,200]:seen.add(key);samples.append((update,state))
  if action is not None:
   assert {int(row[6+mirror*11]) for row in rows}==set(range(aid[0x1000+action]))
   assert rows[-1][46+mirror*6]==4 and rows[-1][47+mirror*6]==1 and rows[-1][48+mirror*6]==1
  elif downed:
   for a,n in [(384,12),(48,2),(52,5)]:
    assert {int(row[6+(1-mirror)*11]) for row in rows if row[5+(1-mirror)*11]==a}==set(range(n))
   assert rows[-1][3]==rows[-1][14]==0
  elif intro:
   for player in range(2):
    assert {int(row[6+player*11]) for row in rows if row[5+player*11]==492}==set(range(21))
   assert all(int(rows[-1][60+player])&0x40000000 for player in range(2))
  else:
   assert rows[-1][59]==1
   if mirror<2:assert {int(row[6+mirror*11]) for row in rows if row[5+mirror*11]==493}=={0,1,2}
   if mirror<2:
    victory=(497 if suffix.endswith('low') else 495)+(4 if final else 0)
    assert {int(row[6+mirror*11]) for row in rows if row[5+mirror*11]==victory}==set(range(aid[0x1000+victory]))
  for update,state in samples:
   p.floats[12:15]=list(map(bits,state[36:39]));p.run(0x122ed8)
   p.floats[12]=bits(0);p.run(0x122ff0);scale=int(scalar(p.floats[0])*128)/128
   canvas=bytearray()
   for y in range(160):
    for x in range(400):
     v=29 if (x//8+y//8)%2 else 34;canvas.extend([v,v+6,v+12,255])
   for player in range(2):
    base=2+player*11;a,step=int(state[base+3]),int(state[base+4]);x,y=state[base+5],state[45+player*6]
    p.floats[12:15]=[bits(x),bits(y),bits(0)];p.run(0x123020,[0x1e10000])
    ox=int(40+scalar(p.read(0x1e10000,4))*.5);oy=int(scalar(p.read(0x1e10004,4))*.5-68)
    start=struct.unpack_from('<h',aid,a*2)[0];parts=[]
    for ref in struct.unpack_from('<5h',act,(start+step)*60+4):
     if ref:
      cell,px,py,z,tint,flags,unknown=struct.unpack_from('<4hI2H',pil,(ref-1)*16)
      assert flags&0x3ff0 in (0x10,0x30)
      if flags&0x3ff0==0x10:assert tint&0xffffff==0x808080
      if cell:parts.append((flags&15,cell-1,px,py,tint,flags))
    for _,cell,px,py,tint,flags in sorted(parts,key=lambda q:q[0]):
     w,h,pixels=image(cell);alpha=((tint>>24)+1)//2;alpha_parts+=alpha!=128
     additive=bool(flags&0x20);additive_parts+=additive;vertical_parts+=bool(flags&0x4000)
     left=ox+(-px-w if player else px)*scale;top=oy-py*scale
     for dy in range(max(0,math.ceil(top-.5)),min(160,math.ceil(top+h*scale-.5))):
      for dx in range(max(0,math.ceil(left-.5)),min(400,math.ceil(left+w*scale-.5))):
       sy=min(h-1,max(0,int((dy+.5-top)/scale)));sx=min(w-1,max(0,int((dx+.5-left)/scale)))
       if bool(flags&0x8000)!=bool(player):sx=w-1-sx
       if flags&0x4000:sy=h-1-sy
       c=pixels[(sy*w+sx)*4:(sy*w+sx+1)*4]
       if c[3]:
        pos=(dy*400+dx)*4
        for channel in range(3):
         if additive:
          modulation=(((tint>>(8*channel))&255)+1)//2
          canvas[pos+channel]=min(255,canvas[pos+channel]+c[channel]*modulation//128)
         else:canvas[pos+channel]=(c[channel]*alpha+canvas[pos+channel]*(128-alpha))//128
   effects.paint(canvas,queued[update],state[36:39])
   subprocess.run([str(BUILD/'ss6-viewer'),'--assets',str(ASSETS),*viewer_args,
    '--updates',str(update),'--dump',str(scratch)],check=True)
   raw=scratch.read_bytes();assert struct.unpack('<II',raw[:8])==(400,160) and raw[8:]==canvas,(action,mirror,update)
   comparisons.append(dict(action=action,mirror=mirror,fixture_suffix=suffix,update=update,step=int(state[6+(mirror if mirror<2 else 0)*11]),
                           sha256=hashlib.sha256(canvas).hexdigest()))
   if action==400 and not mirror and update in [0,15,35,55,100,200]:sheet.append(canvas)
  effect_vertices+=effects.vertex_checks
 width,height=800,480;canvas=bytearray(width*height*4)
 for i,frame in enumerate(sheet):
  for y in range(160):
   start=((i//2*160+y)*width+(i%2)*400)*4;canvas[start:start+1600]=frame[y*1600:(y+1)*1600]
 if not downed_only:png(OUT/'knockout-contact-sheet.png',width,height,canvas)
 if not downed_only:assert vertical_parts>0 and additive_parts>0
 report=dict(status='passed',pixel_scenes=len(comparisons),translucent_parts=alpha_parts,additive_parts=additive_parts,vertical_parts=vertical_parts,effect_quad_slices=effect_vertices,comparisons=comparisons,
  viewer_sha256=hashlib.sha256((BUILD/'ss6-viewer').read_bytes()).hexdigest(),
  scope='Every stage of six resource00 KO actions, both facings, actual-contact endings, winner493/495/497/499/501, corpse48 and changing ending camera;21 first-introduction492 records on both players including translucent body and vertical+horizontal weapon flips. Final499 vertical weapon flip and501 bank26 additive layers included. Independent Python PIL compositing plus unmodified original effect playback and123840-to114ae8 quad slices for landing29 and KO15/16/18. Native fixture birth events, not full original battle/scheduler oracle. Character RGB1555 and PS2 effect_pal_data.bin colors with nearest preview rasterizer; GS blending/order, audio and cross-round images excluded.')
 if downed_only:report['scope']='Four real follow-up heavy contacts from explicit initial342hurt;all12stages384,2stages48,5stages52,both facings and near/far heavy189/190. Independent decoded PIL/body/weapon composite and original effect29/quad generation,including moving airborne Y. Native contact birth schedule supplied;not whole original battle or hardware GS/audio comparison.'
 (OUT/('knockdown_image_validation.json' if downed_only else 'knockout_image_validation.json')).write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:v for k,v in report.items() if k!='comparisons'},indent=2))
if __name__=='__main__':main()
