#!/usr/bin/env python3
"""Packaged SDL crouching attacks, recovery interruption and natural matches."""
import hashlib,itertools,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def main():
 out=ROOT/'outputs/ss6-feasibility';binary=out/'native-viewer/ss6-viewer';assets=binary.parent/'assets'
 assert binary.read_bytes()==(ROOT/'work/ss6/build-native/ss6-viewer').read_bytes()
 scenes=[]
 fixtures=[]
 for player,distance,defense in itertools.product([0,1],[64,100],[0,4,7]):
  fixtures += [(f'crouch-6-{player}-{distance}-{defense}',t) for t in [1,23,110]]
 for player,distance in itertools.product([0,1],[64,100]):
  fixtures += [(f'crouch-5-{player}-{distance}-0',t) for t in [6,40]]
 fixtures += [(f'crouch-match-{order}',0) for order in ['00','11','010']]
 fixtures += [('crouch-recovery-interrupt',18),('crouch-recovery-interrupt',19)]
 for name,updates in fixtures:
  args=[str(binary),'--assets',str(assets),'--mode','trial','--trial-script',str(ROOT/'work/ss6/scenarios'/f'{name}.txt'),'--updates',str(updates)]
  result=subprocess.run(args+['--smoke-updates','6'],text=True,capture_output=True,timeout=20)
  assert result.returncode==0,(name,updates,result.stderr)
  scenes.append(dict(scenario=name,updates=updates,rendered_iterations=6,stderr=result.stderr))
  if (name,updates) in [('crouch-6-0-64-0',23),('crouch-6-1-100-7',23),('crouch-5-0-100-0',6),('crouch-match-010',0)]:
   target=out/f'{name}-preview.bmp'
   subprocess.run(args+['--snapshot',str(target)],check=True,timeout=20)
   subprocess.run(['/usr/bin/sips','-s','format','png',str(target),'--out',str(target.with_suffix('.png'))],check=True,capture_output=True)
 report=dict(status='passed',scenes=scenes,viewer_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
  scope='Actual macOS SDL windows/create/render/clean exit for191/192/195/196,both players,near/far,stand/crouch hurt,guard,recovery interruption and natural2-0/0-2/2-1 terminal matches. Scripted controls,not physical keyboard or PS2 hardware comparison.')
 (out/'crouching_window_validation.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(dict(status='passed',windows=len(scenes),viewer_sha256=report['viewer_sha256']),indent=2))
if __name__=='__main__':main()
