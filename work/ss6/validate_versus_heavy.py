#!/usr/bin/env python3
"""Drive the shipping SDL event loop and its normalized pad reference from the same opening."""
from itertools import groupby
import hashlib
import json
import os
from pathlib import Path
import shlex
import struct
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BUILD = HERE / "build-native"
OUTPUT = ROOT / "outputs/ss6-feasibility"
PKG = OUTPUT / "native-viewer"
ASSETS = PKG / "assets"
DUMMY = dict(os.environ, SDL_VIDEO_DRIVER="dummy", SDL_RENDER_DRIVER="software", SDL_AUDIO_DRIVER="dummy")


def run(args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, timeout=90, **kwargs)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pixels(path):
    data = path.read_bytes()
    start = struct.unpack_from("<I", data, 10)[0]
    width, height = struct.unpack_from("<ii", data, 18)
    assert (width, abs(height), struct.unpack_from("<H", data, 28)[0]) == (640, 480, 32)
    rows = [data[start + i*2560:start + (i+1)*2560] for i in range(abs(height))]
    if height > 0:
        rows.reverse()
    # N pauses the keyboard window. The reference snapshot has no PAUSED label.
    for y in range(120,128):
        rows[y]=rows[y][:272*4]+rows[y][320*4:]
    return b"".join(rows)


def replay(commands, *flags):
    result = run([BUILD / "ss6-match-replay", ASSETS, "--mode", "versus", *flags], input=commands, text=True)
    return [line.split() for line in result.stdout.splitlines()]


def validate(work):
    sdl = shlex.split(run(["pkg-config", "--cflags", "--libs", "sdl3"],text=True).stdout)
    harness = work / "key-loop"
    run([*shlex.split(os.environ.get("CXX", "c++")), "-std=c++20", "-O2", "-I", ROOT/"src",
         HERE/"sdl_slash_input_test.cpp", BUILD/"libss6-runtime.a", *sdl, "-o", harness])
    cases = []
    def case(name, prior, keys, normal, player, action):
        initial, reference = work/"prior.pad", work/"reference.pad"
        source = "500 0 0\n" + prior
        initial.write_text(source)
        reference.write_text(source + normal)
        actual, expected = work/"actual.bmp", work/"expected.bmp"
        shown=run([harness, ASSETS, initial, actual, "--versus", *keys], env=DUMMY, text=True)
        run([ROOT/"battle.command", "--match-replay", reference, "--snapshot", expected], cwd=work, env=DUMMY)
        rows = replay(source + normal,"--whirlwind-fields")
        last=rows[-1]
        observed=next(line.split()[1:] for line in shown.stdout.splitlines() if line.startswith("observed "))
        expected_words=[last[0]]
        for slot in (0,1):
            base=3+10*slot;timers=96+27*slot
            expected_words+=[*last[base:base+4],*last[base+6:base+9],*last[timers:timers+2]]
        assert observed==expected_words,(name,"rendered match state",observed,expected_words)
        assert int(rows[-1][5 + player*10]) == action, (name, rows[-1])
        assert pixels(actual) == pixels(expected), (name, "SDL versus normalized input")
        fighter=lambda who:tuple(map(int,rows[-1][3+10*who:6+10*who]))
        sample=dict(name=name, action=action, ticks=int(rows[-1][0]),
                    actors=[fighter(0),fighter(1)],life=[int(rows[-1][9]),int(rows[-1][19])],
                    hits=[int(rows[-1][10]),int(rows[-1][20])],
                    timers=[[int(last[96+27*i]),int(last[97+27*i])] for i in (0,1)],
                    pixels=hashlib.sha256(pixels(actual)).hexdigest())
        if name.endswith('-421-recoil'):
            entry=next(line for line in shown.stdout.splitlines() if line.startswith('camera '))
            remaining,y,stage_y=map(float,entry.split()[1:])
            # The first negative displacement is clipped by Y=120. On the
            # following update the fighters use +6.6, the scenery still uses 120.
            assert (remaining,y,stage_y)==(14*256,126.6,120.0),(name,entry)
            sample['vertical_shake_remaining']=int(remaining)
            sample['fighter_projection_y']=y
            sample['stage_projection_y']=stage_y
        cases.append(sample)
        return sample
    for player, heavy in enumerate(["L", "I"]):
        def pad(n, ours, theirs=0):
            return f"{n} {theirs if player else ours} {ours if player else theirs}\n"
        forward = 64 if player else 128
        for near in [False, True]:
            prior = pad(42 if near else 2, forward) + pad(1, 0)
            case(f"P{player+1}-standing-{'near' if near else 'far'}", prior, [heavy+"+", "N1"],
                 pad(1,1024), player, 189 if near else 190)
            prior += pad(12,32)
            case(f"P{player+1}-crouching-{'near' if near else 'far'}", prior,
                 ["Down+" if player else "S+",heavy+"+", "N1"], pad(1,1056),
                 player, 195 if near else 196)
        for direction, action in [(16,211),(16|forward,214)]:
            prior = pad(1,direction)+pad(17,0)
            case(f"P{player+1}-jump-{action}",prior,[heavy+"+","N4"],pad(4,1024),player,action)
        prior = pad(1,forward)+pad(1,0)+pad(13,forward)
        case(f"P{player+1}-dash",prior,[heavy+"+","N1"],pad(1,1024),player,221)
    # Drive movement, chord and attack edges through SDL. Only the neutral
    # 500-tick round opening is advanced by the scripted setup. A single
    # held mask can represent several SDL key events before one game tick.
    p1={8:"T",4096:"F",16:"W",32:"S",64:"A",128:"D",256:"J",512:"U",1024:"L",2048:"M"}
    p2={8:"Return",4096:"\\",16:"Up",32:"Down",64:"Left",128:"Right",256:"O",512:"[",1024:"I",2048:"]"}
    def live_case(name,segments,player,action):
        masks=[0,0];keys=[];normalized=[]
        for (a,b),rows in groupby(segments,key=lambda item:tuple(item[1:])):
            count=sum(item[0] for item in rows)
            normalized.append(f"{count} {a} {b}\n")
            for slot,held in enumerate((a,b)):
                for mask,key in (p1,p2)[slot].items():
                    if (masks[slot]^held)&mask:
                        keys.append(key+("+" if held&mask else "-"))
                masks[slot]=held
            keys.append(f"N{count}")
        return case(name,"",keys,"".join(normalized),player,action)

    def segment(player,n,ours,other=0):
        return (n,other,ours) if player else (n,ours,other)
    for player in range(2):
        forward=(128,64)[player];back=forward^192
        discard=[segment(player,1,forward|8)]
        ready=discard+[(125,0,0)]
        for name,trace,expected in [
                ("taunt",[segment(player,1,back|8)],150),
                ("discard",discard,135),
                ("unarmed",ready,1),
                ("barehand-taunt",ready+[segment(player,1,back|8)],151),
                ("pickup",ready+[segment(player,20,forward),(4,0,0),segment(player,1,256)],136)]:
            live_case(f"P{player+1}-{name}",trace,player,expected)
        # Steer the opponent into range after dropping the weapon. A light
        # press next to the fighter's own sword would pick it up instead.
        bare_setup=discard+[(115,0,0)]
        close=[segment(player,100,0,back),(15,0,0)]
        air_range=[segment(player,6,0,back),(15,0,0)]
        for move,approach,inputs,attacker_clip,victim_clip,remaining in (
                ("standing-medium",close,[(1,512),(8,0)],202,340,194),
                ("crouching-kick",close,[(10,32),(1,32|2048),(6,0)],207,344,197),
                ("jumping-light",air_range,[(1,16|forward),(29,0),(1,256),(11,0)],215,358,194),
                ("running-heavy",[(50,0,0)],[(1,forward),(1,0),(13,forward),(1,forward|1024),(5,0)],223,382,191)):
            trace=bare_setup+approach+[segment(player,n,mask) for n,mask in inputs]
            hit=live_case(f"P{player+1}-unarmed-{move}",trace,1-player,victim_clip)
            assert hit["actors"][player][2]==attacker_clip and hit["hits"][player]==1
            assert hit["life"][1-player]==remaining
        for label,button,delay,action,life in [('light',256,25,584,175),('heavy',1024,52,586,152)]:
            trace=[segment(player,1,m) for m in (back,32,back|32|button)]
            struck=live_case(f"P{player+1}-{label}-421-recoil",trace+[(delay,0,0)],player,action)
            assert struck['life'][1-player]==life
        parry=[segment(player,1,m) for m in (32,32|forward,forward|4096)]
        live_case(f"P{player+1}-armed-parry",parry,player,126)
        live_case(f"P{player+1}-barehand-catch",ready+parry,player,131)
        for backwards,clip in ((False,70),(True,76)):
            enemy=1-player
            # Opponent opens with a running heavy. E only qualifies in the
            # original recovery window, sampled before their second landing.
            roll_setup=[segment(enemy,1,forward^192),(1,0,0),segment(enemy,3,forward^192),
                        segment(enemy,1,(forward^192)|1024),(61,0,0),segment(player,1,4096|(back if backwards else 0)),(3,0,0)]
            live_case(f"P{player+1}-recovery-{clip}",roll_setup,player,clip)
        for bare in (False,True):
            approach=[segment(player,66,forward),(4,0,0)]
            if bare:approach += [segment(player,1,0,8|back),(125,0,0)]
            trace=approach+[(5,0,0),segment(player,1,256,32),segment(player,1,0,back|32),
                            segment(player,1,0,back|4096),(3,0,0)]
            result=live_case(f"P{player+1}-deflected-{'bare' if bare else 'armed'}",trace,player,133 if bare else 127)
            assert result["actors"][1-player][2]==(132 if bare else 126) and result["life"]==[200,200]
        # The sweep crosses under the victim. Down-forward for the pursuit
        # therefore uses the opposite world direction after the facing switch.
        chase=[segment(player,45,forward),(2,0,0),segment(player,1,2048|32|forward),(60,0,0),
               segment(player,1,1024|32|back),(38,0,0)]
        result=live_case(f"P{player+1}-pursuit-hit",chase,1-player,418)
        assert result["hits"][player]==2 and result["life"][1-player]==171
        # Build rage by taking three actual heavy slashes. Waiting out the
        # meter keeps the same distance, target health and counterattack ACT.
        primer=([segment(player,65,0,back),(5,0,0),segment(player,1,0,1024),(88,0,0)]*3)
        for wait,damage in ((140,57),(620,38)):
            trace=primer+[segment(player,1,0,back|8),(wait,0,0),segment(player,36,forward),(5,0,0),
                          segment(player,1,1024),(14,0,0)]
            name="active" if wait==140 else "expired"
            result=live_case(f"P{player+1}-rage-{name}-heavy",trace,player,189)
            assert result["hits"][player]==1 and result["life"][1-player]==200-damage
        for variant,direction,action in (("forward",forward,232),("back",back,234)):
            start=[(70,128,0),segment(player,1,1536|direction)]
            name=f"P{player+1}-{variant}-throw"
            caught=live_case(name+"-catch",start+[(3,0,0)],player,action)
            assert caught["actors"][player][:2]==(1,31)
            assert caught["actors"][1-player]==(2,13,404+action-232) and caught["life"]==[200,200]
            delay=53 if variant=="forward" else 75
            impact=live_case(name+"-impact",start+[(delay,0,0)],player,action)
            assert impact["actors"][1-player]==(2,59,400) and impact["life"][1-player]==186
        for name,motion,action,state in (
                ("light-medium",[768],264,21),
                ("down-forward-medium",[32|forward|512],239,22),
                ("214-kick",[32,32|back,back|2048],598,77),
                ("632146-light-medium",[forward,32|forward,32,32|back,back,forward|768],592,80)):
            inputs=[segment(player,1,mask) for mask in motion]
            start=live_case(f"P{player+1}-{name}",inputs,player,action)
            assert start["actors"][player][:2]==(1,state)
        for strength in range(3):
            button=256<<strength
            # The two forward presses, the running age, and the final
            # down-forward+slash all pass through the shipping input queue.
            approach=[segment(player,16,forward,back),(30,0,0)]
            motion=[segment(player,n,held) for n,held in ((1,0),(1,forward),(1,0),(16,forward),
                                                        (1,32),(1,32|forward|button))]
            start=approach+motion
            name=f"P{player+1}-dash-623-"+("light","medium","heavy")[strength]
            active=live_case(name+"-startup",start,player,568+strength)
            assert active["actors"][player][:2]==(1,71+strength)
            # Last hit of each version. The heavy has an additional raw34
            # launch before its final raw17 downs the opponent.
            after=(25,32,37)[strength]
            hit=live_case(name+"-last-hit",start+[(after,0,0)],player,568+strength)
            assert hit["actors"][1-player][:2]==(2,63)
            assert hit["life"][1-player]==(166,161,157)[strength] and hit["hits"][player]==(2,4,5)[strength]
            if strength==2:
                launch=live_case(name+"-launch",start+[(32,0,0)],player,570)
                assert launch["actors"][1-player][:2]==(2,72) and launch["hits"][player]==4
        # Alternate real button edges while hurt. The last hurt tick and
        # earliest counterattack come from validate_jump_light_stun.py's
        # independent Japanese actor/input trace for this forward jump.
        for posture,attack_at,contact,reaction,clip,exit_at,counter_at in (
                ("standing",32,42,41,356,9,11),("crouching",34,44,38,350,15,17),
                ("airborne",20,30,74,378,36,38)):
            trace=[]
            for tick in range(1,contact+counter_at+1):
                them=(32 if posture=="crouching" else 16 if posture=="airborne" and tick==1 else 0)
                if tick>=contact:them=256 if (tick-contact)%2==counter_at%2 else 0
                ours=(16|forward) if tick==1 else 256 if tick==attack_at else 0
                trace.append(segment(player,1,ours,them))
            victim=1-player
            label=f"P{player+1}-jump-light-{posture}"
            hurt=live_case(label+"-last-hurt",trace[:contact+exit_at-1],victim,clip)
            assert hurt["actors"][victim]==(2,reaction,clip) and hurt["life"][victim]==191
            assert hurt["hits"][player]==1 and hurt["hits"][victim]==0
            counter_clip=186 if posture=="airborne" else 185
            counter=live_case(label+"-first-counter",trace,victim,counter_clip)
            assert counter["actors"][victim]==(1,0,counter_clip) and counter["life"][victim]==191
            counter["updates_after_initial_hit"]=counter_at
    for variant,a,b in (("forward",1664,1600),("back",1600,1664)):
        mutual=live_case(f"mutual-{variant}-throw",[(70,128,0),(1,a,b),(2,0,0)],0,236)
        assert mutual["actors"]==[(0,37,236),(0,37,236)] and mutual["life"]==[200,200]
    naturals=[]
    for player in range(2):
        right = player == 0
        def step(n, ours, other=0):
            return f"{n} {ours if right else other} {other if right else ours}\n"
        commands = "440 0 0\n"+(step(45,128 if right else 64)+step(1,1024)+step(84,0))*50
        last = replay(commands)[-1]
        assert int(last[2])==1 and int(last[12+10*player])==2 and int(last[12+10*(1-player)])==0, last
        naturals.append(dict(winner=player+1, updates=int(last[0]), hits=int(last[10+10*player])))
    assert digest(PKG/"ss6-viewer") == digest(BUILD/"ss6-viewer")
    return dict(status="passed",viewer_sha256=digest(PKG/"ss6-viewer"), keyboard=cases, natural_matches=naturals,
                scope="Real SDL keyboard event queue and gameplay/renderer from the shipping viewer, dummy video driver. "
                      "Compares both actors' states, ACT and record, timers 0/1, health and hit counts plus 640x480 pixels "
                      "outside the 48x8 paused text label. The neutral round opening is replayed; both throw and running "
                      "623 inputs, both directions and jump-light counterpresses use keyboard events.")


if __name__=="__main__":
    with tempfile.TemporaryDirectory(prefix="versus-heavy-") as t:
        result=validate(Path(t))
    (OUTPUT/"versus_heavy_validation.json").write_text(json.dumps(result,indent=2)+"\n")
    print(f"{len(result['keyboard'])} SDL input comparisons, {len(result['natural_matches'])} first-to-two matches")
