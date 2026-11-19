#!/usr/bin/env python3
"""Replay the original 斬 button selectors, actor callbacks and actual air blocks."""
from concurrent.futures import ProcessPoolExecutor
import json
from validate_shin_evasion import replay, setup_state, EXE
from validate_dash_motion import ELF, PIN, ROOT, digest
from validate_weapon_handling import setup
from validate_haohmaru_special import ContactOracle
from validate_collisions import ACTORS
from validate_haohmaru_whirlwind import contact as projectile_contact
from validate_haohmaru_special import pads_for

OUT=ROOT/'outputs/ss6-feasibility/zan_actions_validation.json'
A,B,C,D,E=256,512,1024,2048,4096


class ZanContacts(ContactOracle):
    def __init__(self, defender):
        super().__init__()
        self.defender=defender

    def install_player(self,row,slot):
        super().install_player(row,slot)
        self.probe.write(ACTORS+slot*0xf2c+0x10c,2 if slot==self.defender else 0,4)


def buttons(slot,name):
    front,back=(128,64) if not slot else (64,128)
    direction={'vertical':16,'forward':16|front,'back':16|back}.get(name.split('-')[-1],16)
    if name in ('dodge','dodge-far-forward','cross'):
        return [(E if name=='dodge' else E|front,0)]+[(0,0)]*90
    if name.startswith('charge'):
        duration=int(name.split('-')[1])
        return [(A|B,0)]*duration+[(0,0)]*18
    if name.startswith('block-') or name.startswith('late-'):
        attack={'A':A,'B':B,'C':C,'D':D}[name[-1]]
        press=20 if attack==B else 16
        if name.startswith('late'):press=35
        return [(16 if i==0 else E if i==press else 0,16 if i==0 else attack if i==12 else 0) for i in range(85)]
    if name.startswith('ground-'):
        attack={'B':B,'C':C}[name[-1]]
        return [(16 if i==0 else E if i==33 else 0,attack if i==23 else 0) for i in range(95)]
    if name.startswith('under-'):
        evade={'dodge':E,'cross':E|front,'standing':0}[name.split('-')[1]]
        return [(evade if i==5 else 0,C if i==0 else 0) for i in range(85)]
    return [(direction if i==0 else E if i==9 else 0,0) for i in range(75)]


def case(args):
    slot,name,bare=args
    front,back=(128,64) if not slot else (64,128)
    pair=lambda a,b:(b,a) if slot else (a,b)
    near=name=='cross' or name.startswith(('block-','ground-','late-','under-'))
    initial=[(500,0,0)]
    if bare:initial += [(1,*pair(front|8,0)),(135,0,0)]
    if near:
        # Keep the standing heavy's body push outside the player's path so
        # its air-block recoil can be compared to an isolated EE actor.
        approach=4 if name.startswith('ground-') else 24 if name=='cross' else 40 if name.startswith('under-') else 16
        initial += [(approach,*pair(front,back)),(8,0,0)]
    elif name.startswith('air-'):
        # Neither jump hits a stage boundary in the compared trace.
        initial += [(12,*(pair(front,back) if name=='air-back' else pair(back,front))),(8,0,0)]
    controls=buttons(slot,name)
    rows=replay(slot,'zan',initial+[(1,*pair(a,b)) for a,b in controls])[len(initial)-1:]
    c,cb,core=23+26*slot,88+27*slot,3+10*slot
    contacts=ZanContacts(slot).contacts(rows,1-slot) if near and name!='cross' else []
    got_guard=name.startswith(('block-','ground-'))
    if got_guard:
        assert len(contacts)==1 and contacts[0]['defense']==4 and contacts[0]['target_state']==6,(args,contacts)
    elif name.startswith('late-') or name=='under-standing':
        assert len(contacts)==1 and not contacts[0]['defense'],(args,contacts)
    elif name.startswith('under-'):
        assert not contacts,(args,contacts)
    if name.startswith(('late-','under-')):
        return dict(player=slot+1,case=name,armed=not bare,contacts=contacts,final_life=int(rows[-1][9+slot*10]))
    src,_=setup(slot);setup_state(src,2,0,rows[0],slot,bare)
    p,a,o=src.p,src.a,src.o
    trajectory=[]
    for i,((held,_),prev,now) in enumerate(zip(controls,rows,rows[1:])):
        # Supply the actual environment to the independent one-player update:
        # camera-stage positions and the other actor are published beforehand.
        other=23+26*(1-slot)
        p.write(o+0x1040,int(prev[other]),4)
        p.write(src.b+0x144,abs(int(float(prev[7]))-int(float(prev[17]))),4)
        if contacts and int(now[0])==contacts[0]['frame']:
            src.run(0x14d5a0,a,o+0x1000,4,0)
        desired=src.frame(held)
        got=[int(now[core])|(int(now[core+1])<<16),int(now[core+2]),int(now[core+3]),int(now[cb+11]),
             int(now[c+10]),int(now[c+5])&0x11038,*map(int,now[cb:cb+3]),
             int(now[cb+8]),int(now[cb+9]),int(now[c+1])]
        want=[desired[0],desired[54],desired[55],desired[56],desired[4],desired[5]&0x11038,
              *desired[12:15],desired[19],desired[20],desired[69]]
        got.append(int(now[c]));want.append(desired[68])
        assert got==want,(args,i,[(n,u,v) for n,(u,v) in enumerate(zip(got,want)) if u!=v],now[:23])
        record=(desired[0]&65535,desired[0]>>16,desired[54],hex(desired[12]))
        if not trajectory or record!=trajectory[-1][1]:trajectory.append((i,record))
        if i>1 and desired[0] in (0,4<<16) and desired[54] in (int(bare),44+int(bare)):
            if not name.startswith('charge') or i>=int(name.split('-')[1]):break
    observed={v[2] for _,v in trajectory}
    if name=='cross': required=74
    elif name.startswith('dodge'):required=72
    elif name.startswith('charge'):required=158
    else:required=308
    assert required+bare in observed,(args,trajectory)
    assert trajectory[-1][1][0]==0 and trajectory[-1][1][1] in (0,4),(args,trajectory)
    return dict(player=slot+1,case=name,armed=not bare,frames=i+1,original_instructions=src.instructions,
                contact=contacts,trajectory=trajectory,final_life=int(now[9+slot*10]))


def projectile_case(args):
    slot,strength=args
    front,back=(128,64) if not slot else (64,128)
    pair=lambda a,b:(b,a) if slot else (a,b)
    caster=1-slot
    command=pads_for(64+strength,caster)
    controls=[(16 if i==4 else E if i==38 else 0,command[i] if i<len(command) else 0) for i in range(110)]
    segments=[(500,0,0),(12,*pair(front,back)),(8,0,0)]+[(1,*pair(a,b)) for a,b in controls]
    rows=replay(slot,'zan',segments)
    guard_col=11+10*caster
    i=next(j for j in range(1,len(rows)) if int(rows[j][guard_col])>int(rows[j-1][guard_col]))
    hit=projectile_contact(ZanContacts(slot),rows[i-1],rows[i],caster,True)
    assert hit['defense']==4 and hit['damage']==1
    core=3+10*slot
    assert rows[i][core:core+3]==['2','6','308'] and rows[-1][core:core+3]==['0','0','0']
    return dict(defender=slot+1,strength=strength,contact=hit,final_life=int(rows[-1][9+10*slot]))


def main():
    assert digest(ELF)==PIN
    menu={0x4e3930:'斬スピリッツ',0x4e3a18:'避け',0x4e3a28:'回り込み',0x4e3a50:'空中ガード',0x4e3a70:'怒り溜め'}
    image=ELF.read_bytes()
    for offset,label in menu.items():assert image[offset:].startswith(label.encode('cp932'))
    names=['dodge','cross','dodge-far-forward','air-vertical','air-forward','air-back','charge-1','charge-45',
           'block-A','block-B','block-C','block-D','ground-B','ground-C','late-C','under-standing','under-dodge','under-cross']
    cases=[(s,n,b) for s in range(2) for n in names for b in
           ((False,True) if n in ('dodge','cross','air-vertical','charge-45','block-C') else (False,))]
    with ProcessPoolExecutor(8) as pool:
        results=list(pool.map(case,cases))
        projectiles=list(pool.map(projectile_case,[(slot,level) for slot in range(2) for level in range(3)]))
    OUT.write_text(json.dumps(dict(original_sha256=PIN,replay_sha256=digest(EXE),help=menu,cases=results,projectiles=projectiles),indent=2,ensure_ascii=False)+'\n')
    print(f'{len(results)+len(projectiles)} 斬 input, callback and contact cases matched the Japanese executable')

if __name__=='__main__':main()
