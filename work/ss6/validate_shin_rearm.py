#!/usr/bin/env python3
"""Follow a weapon-breaking hit all the way to picking up and swinging the replacement sword."""
from pathlib import Path
import json
import struct
import subprocess
from validate_dash_motion import ROOT, ASSETS, PIN, ELF, digest

EXE=ROOT/'work/ss6/build-native/ss6-match-replay'
OUT=ROOT/'outputs/ss6-feasibility/shin_rearm_validation.json'

def run(slot):
    victim=1-slot
    def pair(n,ours,other=0):return (n,other,ours) if slot else (n,ours,other)
    f=(128,64)[slot]
    opening=[(500,0,0)]+[pair(65,0,f^192),pair(5,0),pair(1,0,1024),pair(88,0)]*4
    opening+=[pair(100,0),pair(75,f),pair(5,0)]+[pair(1,k) for k in (32,32|f,f|768)]
    def play(pads):
        args=[EXE,ASSETS,'--mode','versus',f'--p{slot+1}-spirit','shin','--shin-fields']
        result=subprocess.run(args,input=''.join('%d %d %d\n'%row for row in pads),capture_output=True,text=True,check=True)
        return [line.split() for line in result.stdout.splitlines()]
    def weapons(row):
        at=129
        for seat in range(2):
            clock,count=map(int,row[at:at+2]);at+=2
            objects=[list(map(int,row[at+j*7:at+(j+1)*7])) for j in range(count)]
            if seat==victim:return clock,objects
            at+=7*count
    def pos(bits):return struct.unpack('<f',struct.pack('<I',bits))[0]
    rows=play(opening+[(1,0,0)]*1250)[len(opening):]
    found=[]
    for row in rows:
        timer,objects=weapons(row)
        actions=[o[0] for o in objects]
        if not found or found[-1]['actions']!=actions:
            found.append(dict(tick=int(row[0]),actions=actions,timer14=timer,
                              positions=[[pos(o[2]),pos(o[3])] for o in objects]))
    transitions=[x['actions'] for x in found]
    assert transitions==[[],[468],[469,470,471],[470,471],[471],[],[466],[467]],transitions
    assert found[2]['timer14']==600*256
    landing=found[-1]['tick'];to_landing=landing-sum(n for n,a,b in opening)
    check=play(opening+[(to_landing,0,0),pair(1,0,256),(50,0,0),pair(1,0,1024)])
    at=3+10*victim;flags=28+26*victim
    assert not int(check[-4][flags])&4096 and check[-4][at+2]=='1'
    assert list(map(int,check[-3][at:at+3]))==[0,51,136] and int(check[-3][flags])&4096
    assert check[-2][at:at+3]==['0','0','0'] and check[-1][at:at+3]==['1','8','190']
    return dict(attacker=slot+1,transitions=found,picked_up=landing+1,armed_heavy=int(check[-1][0]))

if __name__=='__main__':
    assert digest(ELF)==PIN
    results=[run(slot) for slot in (0,1)]
    OUT.write_text(json.dumps(dict(status='passed',replay_sha256=digest(EXE),original=PIN,cases=results),indent=2)+'\n')
    print(OUT)
