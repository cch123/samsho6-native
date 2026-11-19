#!/usr/bin/env python3
"""Actual local SDL windows and reviewable ending screenshots."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def main():
 binary=ROOT/'outputs/ss6-feasibility/native-viewer/ss6-viewer'
 assert binary.read_bytes()==(ROOT/'work/ss6/build-native/ss6-viewer').read_bytes()
 assets=ROOT/'outputs/ss6-feasibility/native-viewer/assets';out=ROOT/'outputs/ss6-feasibility'
 def command(fixture,update):
  return [str(binary),'--assets',str(assets),'--mode','trial','--trial-script',
   str(ROOT/'work/ss6/scenarios'/f'battle-ending-{fixture}.txt'),'--updates',str(update)]
 checks=[]
 for update in [1,63,97,102,103,120,205,206,236,237,267,437,438]:
  args=[str(binary),'--assets',str(assets),'--mode','trial','--trial-script',
        str(ROOT/'work/ss6/scenarios/match-opening.txt'),'--updates',str(update)]
  result=subprocess.run(args+['--smoke-updates','6'],text=True,capture_output=True,timeout=20)
  assert result.returncode==0,('introduction',update,result.stderr)
  checks.append(dict(introduction=True,updates=update,rendered_iterations=6,exit_code=result.returncode,stderr=result.stderr))
  if update in [63,103,267]:
   target=out/f'character-intro-{update}-preview.bmp'
   subprocess.run(args+['--snapshot',str(target)],check=True,timeout=20)
   subprocess.run(['/usr/bin/sips','-s','format','png',str(target),'--out',str(target.with_suffix('.png'))],check=True,capture_output=True)
 for fixture,update in [(0,20),(0,100),(0,78),(0,88),(0,89),(0,140),(1,140),(2,20),(2,100),(2,140),
                        (0,203),(0,248),(0,371),(1,249),('0-low',350),('1-low',412),(2,159)]:
  result=subprocess.run(command(fixture,update)+['--smoke-updates','6'],text=True,capture_output=True,timeout=20)
  assert result.returncode==0,(fixture,update,result.stderr)
  checks.append(dict(fixture=fixture,updates=update,rendered_iterations=6,exit_code=result.returncode,stderr=result.stderr))
 for label,update in [(1,1),(1,30),(1,100),(1,175),(1,200),(1,201),(2,30),(2,80),(2,110),(10,30),(10,111)]:
  args=[str(binary),'--assets',str(assets),'--mode','trial','--trial-script',
        str(ROOT/'work/ss6/scenarios'/f'round-opening-{label}.txt'),'--updates',str(update)]
  result=subprocess.run(args+['--smoke-updates','6'],text=True,capture_output=True,timeout=20)
  assert result.returncode==0,(label,update,result.stderr)
  checks.append(dict(opening_label=label,updates=update,rendered_iterations=6,exit_code=result.returncode,stderr=result.stderr))
  if label==1 and update==30:
   target=out/'opening-window-preview.bmp'
   subprocess.run(args+['--snapshot',str(target)],check=True,timeout=20)
   subprocess.run(['/usr/bin/sips','-s','format','png',str(target),'--out',str(target.with_suffix('.png'))],check=True,capture_output=True)
 for fixture,update,name in [(0,140,'battle-ending-0'),(2,140,'battle-ending-2'),
                             (0,20,'effects-ko-preview'),(0,100,'effects-landing-preview'),(2,20,'effects-double-ko-preview'),
                             (0,371,'victory-preview'),('0-low',350,'victory-low-preview')]:
  target=out/f'{name}.bmp'
  subprocess.run(command(fixture,update)+['--snapshot',str(target)],check=True,timeout=20)
  subprocess.run(['/usr/bin/sips','-s','format','png',str(target),'--out',str(target.with_suffix('.png'))],check=True,capture_output=True)
 # These prefixes are generated from matches played using movement and
 # attacks. They preserve cross-round state, unlike initial-life fixtures.
 flow=json.loads((out/'match_flow_validation.json').read_text())
 for case in flow['cases'][:3]:
  order=''.join(map(str,case['order']));source=ROOT/'work/ss6/scenarios'/f'match-{order}.txt'
  samples=[(case['resets'][0]+1,'reset'),(case['resets'][0]+62,'round2'),(case['resets'][0]+143,'fight2'),(case['updates'],'complete')]
  if len(case['resets'])>1:samples.append((case['resets'][1]+62,'deciding'))
  for update,name in samples:
   lines=[];elapsed=0
   for line in source.read_text().splitlines():
    if line.startswith('tick '):
     count=int(line.split()[1]);remaining=update-elapsed
     if remaining<=0:break
     lines.append(f'tick {min(count,remaining)}');elapsed+=min(count,remaining)
     if elapsed==update:break
    else:lines.append(line)
   assert elapsed==update
   script=ROOT/'work/ss6/scenarios'/f'match-window-{order}-{name}.txt';script.write_text('\n'.join(lines)+'\n')
   args=[str(binary),'--assets',str(assets),'--mode','trial','--trial-script',str(script)]
   result=subprocess.run(args+['--smoke-updates','6'],text=True,capture_output=True,timeout=20)
   assert result.returncode==0,(order,name,result.stderr)
   checks.append(dict(match=order,phase=name,updates=update,rendered_iterations=6,exit_code=result.returncode,stderr=result.stderr))
   if order=='010' and name in ['round2','deciding','complete']:
    target=out/f'match-{name}-preview.bmp'
    subprocess.run(args+['--snapshot',str(target)],check=True,timeout=20)
    subprocess.run(['/usr/bin/sips','-s','format','png',str(target),'--out',str(target.with_suffix('.png'))],check=True,capture_output=True)
 for winner,life,update in [(0,100,20),(1,100,20),(0,100,350),(1,100,350),(0,99,280),(1,99,280),(2,1,500)]:
  script=ROOT/'work/ss6/scenarios'/f'match-final-{winner}-{life}.txt'
  args=[str(binary),'--assets',str(assets),'--mode','trial','--trial-script',str(script),'--updates',str(update)]
  result=subprocess.run(args+['--smoke-updates','6'],text=True,capture_output=True,timeout=20)
  assert result.returncode==0,(winner,life,update,result.stderr)
  checks.append(dict(final_winner=winner,initial_life=life,updates=update,rendered_iterations=6,exit_code=result.returncode,stderr=result.stderr))
  if winner==0 and life==100 and update==20:
   target=out/'match-final-ko-preview.bmp'
   subprocess.run(args+['--snapshot',str(target)],check=True,timeout=20)
   subprocess.run(['/usr/bin/sips','-s','format','png',str(target),'--out',str(target.with_suffix('.png'))],check=True,capture_output=True)
 report=dict(status='passed',viewer_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),scenes=checks,
  scope='Actual WindowServer create/render/clean exit for first-round initialization/character492 introduction,zero-duration hold/release,KO/doubleKO/final UI, landing29, final UI draw/removal, battle pause, airborne KO, camera movement, winners495/497/499/501 and ending completion; first/second/final round UI with PS2 effects CLUT, rotated fans and input-unlock boundary. Natural complete-match prefixes cover both2-0winners and2-1decider including restored life, preserved wins, next-round opening and terminal result. Scripted controls; not physical keyboard automation or full original round/hardware comparison.')
 (out/'battle_ending_window_validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
