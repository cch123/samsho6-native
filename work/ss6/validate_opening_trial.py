#!/usr/bin/env python3
"""Opening owner completion -> battle entry/input, plus original UI overlays."""
import hashlib,json,struct,subprocess
from pathlib import Path
from effect_oracle import OriginalEffects
from validate_round_intro import fixture
from validate_assets import png
ROOT=Path(__file__).resolve().parents[2]
ASSETS=ROOT/'work/ss6/extracted/resources'
BUILD=ROOT/'work/ss6/build-native'
OUT=ROOT/'outputs/ss6-feasibility'
def probe(commands):
 r=subprocess.run([str(BUILD/'ss6-contact-trial-probe'),str(ASSETS)],input='\n'.join(commands)+'\n',capture_output=True,text=True,check=True)
 return [[float(v) for v in line.split()] for line in r.stdout.splitlines()]
def dump(arguments):
 target=ROOT/'work/ss6/actions/opening-comparison.rgba'
 subprocess.run([str(BUILD/'ss6-viewer'),'--assets',str(ASSETS),'--mode','trial',*arguments,'--dump',str(target)],check=True)
 data=target.read_bytes();assert struct.unpack_from('<II',data)==(400,160)
 return bytearray(data[8:])
def main():
 controls=[];pixels=[];original_instructions=0
 for label in range(1,11):
  end=200 if label==1 else 110
  commands=['place 280 344',f'opening {label}']
  for _ in range(end):commands+=['command 0 5','command 1 5','tick 1']
  commands+=['command 0 5','command 1 5','tick 1','tick 40']
  rows=probe(commands)
  for row in rows[1:-4]:
   assert row[2]==row[13]==200 and row[5]==row[16]==0
   assert int(row[41])&1 and int(row[43])&1
  complete=rows[-5];entry=rows[-2];after=rows[-1]
  assert complete[0]==end and complete[57:59]==[3,4] and complete[104]==0 and complete[66]>0
  assert entry[0]==end+1 and entry[57:59]==[4,4] and entry[41]==entry[43]==0 and entry[66]==0
  assert entry[5]==entry[16]==185 and entry[98]==entry[100]==0
  assert after[2]==after[13]==192
  controls.append(dict(label=label,owner_finished=end,battle_entry=end+1,trade_life=[after[2],after[13]]))
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
 for label in [1,2,10]:
  end=200 if label==1 else 110;p=fixture(raw,label);renderer=OriginalEffects()
  states=probe([f'opening {label}']+['tick 1']*(end+1))
  baseline=probe(['reset']+['tick 1']*(end+1))
  script=ROOT/'work/ss6/scenarios'/f'round-opening-{label}.txt'
  previous=None
  for visit,state in enumerate(states):
   if visit:
    p.write(0x4a2250,0,4);_,n=p.run(0x112838,limit=100000);original_instructions+=n
   draws=[bytes(p.memory[0x479250+i*0x148:0x479250+i*0x148+0x138]) for i in range(p.read(0x4a2250,4))]
   key=tuple((d[0x14:0x18],d[0x24:0x2c]) for d in draws)
   sample=key!=previous or visit%10==0 or visit in [end-1,end,end+1]
   previous=key
   if not sample:continue
   # The UI check overlays original scheduler output onto the established
   # actor preview. Character compositing has its separate PIL oracle; do
   # not mislabel this overlay comparison as a second body renderer.
   for index in [5,6,7,16,17,18,36,37,38,45,51]:assert state[index]==baseline[visit][index]
   canvas=dump(['--updates',str(visit)])
   renderer.paint(canvas,draws,state[36:39])
   actual=dump(['--trial-script',str(script),'--updates',str(visit)])
   assert actual==canvas,(label,visit,[(i,a,b) for i,(a,b) in enumerate(zip(actual,canvas)) if a!=b][:8])
   pixels.append(dict(label=label,visit=visit,sha256=hashlib.sha256(canvas).hexdigest()))
   if (label,visit) in [(1,30),(2,30),(10,30),(2,80)]:
    name='fight-opening' if visit==80 else f'round-opening-{label}'
    png(OUT/f'{name}-preview.png',400,160,canvas)
 for label in range(3,10):
  # Each remaining number is covered by the whole scheduler/record tests;
  # also execute its native draw path to catch missing packaged textures.
  script=ROOT/'work/ss6/actions/opening-number.txt';script.write_text(f'opening {label}\n')
  dump(['--trial-script',str(script),'--updates','35'])
 report=dict(status='passed',input_cases=controls,pixel_scenes=len(pixels),pixels=pixels,
  original_scheduler_instructions=original_instructions,
  viewer_sha256=hashlib.sha256((BUILD/'ss6-viewer').read_bytes()).hexdigest(),
  probe_sha256=hashlib.sha256((BUILD/'ss6-contact-trial-probe').read_bytes()).hexdigest(),
  scope='Initial state3 fixture only. All10 labels reject attacks until owner completion, retain the final UI draw, enter4 on the next visit, then permit a real light-slash trade. Original scheduler/quad UI overlays independently rasterized over the established actor preview for first/second/final labels. Does not implement13fd80/149008, first-round character introductions, audio/replay initialization, GS coverage or automatic next round.')
 (OUT/'opening_trial_validation.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:v for k,v in report.items() if k!='pixels'},indent=2))
if __name__=='__main__':main()
