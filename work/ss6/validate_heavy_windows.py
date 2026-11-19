#!/usr/bin/env python3
"""Packaged standing/crouching heavy SDL windows and the user launcher."""
import hashlib,json,struct,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def check_attack_boxes(binary,assets):
 # Only pixels inside the playfield that change when H is toggled count.
 # Otherwise a red HUD or sprite pixel could hide a missing attack outline.
 scenarios=ROOT/'work/ss6/scenarios'
 def capture(script,tick,enabled,path):
  subprocess.run([binary,'--assets',assets,'--mode','trial','--trial-script',script,
                  '--updates',str(tick),'--boxes',str(int(enabled)),'--snapshot',path],check=True,timeout=20)
  bmp=path.read_bytes()
  assert bmp[:2]==b'BM' and struct.unpack_from('<iiHH',bmp,18)==(960,672,1,32)
  assert struct.unpack_from('<IIII',bmp,54)==(0xff0000,0xff00,0xff,0xff000000)
  start=struct.unpack_from('<I',bmp,10)[0]
  return b''.join(bmp[start+((671-y)*960+32)*4:start+((671-y)*960+928)*4] for y in range(172,531))
 with tempfile.TemporaryDirectory() as tmp:
  tmp=Path(tmp)
  light=tmp/'light.txt'
  light.write_text('place 280 344\ntick 1\ncommand 0 5\n')
  scenes=[('near-189',scenarios/'heavy-near.txt',14,True),('far-190',scenarios/'heavy-far.txt',18,True),
          ('mirrored-190',scenarios/'heavy-mirrored.txt',18,True),('crouch-near-195',scenarios/'crouch-6-0-64-0.txt',19,True),
          ('crouch-far-196',scenarios/'crouch-6-1-100-7.txt',19,True),('before-active',scenarios/'heavy-near.txt',1,False),
          ('recovered',scenarios/'heavy-near.txt',125,False),('near-light-185',light,5,True)]
  result={}
  for name,script,tick,active in scenes:
   old=capture(script,tick,False,tmp/'off.bmp')
   new=capture(script,tick,True,tmp/'on.bmp')
   def changed(color):
    return sum(new[i:i+4]==color and old[i:i+4]!=color for i in range(0,len(new),4))
   attack=changed(bytes((96,112,250,255)))
   hurt=changed(bytes((245,199,120,255)))
   assert (attack>0)==active and hurt>0,(name,attack,hurt)
   result[name]=dict(red_attack_pixels=attack,blue_hurt_pixels=hurt)
  return result

def main():
 binary=ROOT/'outputs/ss6-feasibility/native-viewer/ss6-viewer';assets=binary.parent/'assets';out=ROOT/'outputs/ss6-feasibility'
 assert binary.read_bytes()==(ROOT/'work/ss6/build-native/ss6-viewer').read_bytes()
 checks=[]
 for name,updates in [('near',[13,15,17,60,120]),('far',[17,19,24,75,120]),('mirrored',[19,24,120]),
                      ('guard',[20,40,120]),('crouch',[20,40,120]),('clash-0',[8,20]),('clash-1',[8,20]),
                      ('match-00',[0]),('match-11',[0]),('match-010',[0]),
                      ('knockdown-0-64',[16,40,76,107,139,164]),('knockdown-1-100',[20,44,80,111,143,168])]:
  for update in updates:
   args=[str(binary),'--assets',str(assets),'--mode','trial','--trial-script',str(ROOT/'work/ss6/scenarios'/f'heavy-{name}.txt'),'--updates',str(update)]
   result=subprocess.run(args+['--smoke-updates','6'],capture_output=True,text=True,timeout=20)
   assert result.returncode==0,(name,update,result.stderr)
   checks.append(dict(scenario=name,updates=update,rendered_iterations=6,stderr=result.stderr))
   if (name,update) in [('near',15),('far',19),('mirrored',19),('guard',20),('match-010',0),('knockdown-0-64',40),('knockdown-1-100',143)]:
    target=out/f'heavy-{name}-preview.bmp'
    subprocess.run(args+['--snapshot',str(target)],check=True,timeout=20)
    subprocess.run(['/usr/bin/sips','-s','format','png',str(target),'--out',str(target.with_suffix('.png'))],check=True,capture_output=True)
 #Keep crouching attacks and the actual launcher in the same package check:
 #a valid build alone does not prove the installed binary finds its assets.
 for name,update in [('crouch-6-0-64-0',23),('crouch-6-1-100-7',23),
                     ('crouch-match-00',0),('crouch-match-11',0),('crouch-match-010',0)]:
  args=[str(binary),'--assets',str(assets),'--mode','trial','--trial-script',str(ROOT/'work/ss6/scenarios'/f'{name}.txt'),'--updates',str(update)]
  result=subprocess.run(args+['--smoke-updates','6'],capture_output=True,text=True,timeout=20)
  assert result.returncode==0,(name,update,result.stderr)
  checks.append(dict(scenario=name,updates=update,rendered_iterations=6,stderr=result.stderr))
 launch=subprocess.run([str(ROOT/'battle.command'),'--smoke-updates','6'],cwd='/private/tmp',capture_output=True,text=True,timeout=20)
 assert launch.returncode==0,launch.stderr
 report=dict(status='passed',viewer_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),scenes=checks,attack_box_pixels=check_attack_boxes(binary,assets),
  launcher=dict(path=str(ROOT/'battle.command'),working_directory='/private/tmp',rendered_iterations=6,stderr=launch.stderr),
  scope='43 actual macOS SDL window creation/render/clean exit checks plus battle.command startup outside the project directory;packaged189/190 near/far and mirrored heavy,hurt hold/recovery,stand/crouchguard,mixed light/heavy clash,384 knockdown/landing/48 down/52 rise on both players,and three standing plus three crouching natural matches at state10,near/far crouching195/196. Scripted controls,not physical keyboard automation or original hardware frame comparison.')
 for name in ['heavy_window_validation.json','heavy_request_smoke_validation.json']:
  (out/name).write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(dict(status=report['status'],windows=len(checks),viewer_sha256=report['viewer_sha256']),indent=2))
if __name__=='__main__':main()
