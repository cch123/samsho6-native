#!/usr/bin/env python3
"""Drive a whole ARCADE MODE run through the replay binary and check the presentation scenes.

Route: title -> mode menu -> ARCADE -> character select -> opening -> map -> walk-in -> fight 1
(played out, with the round tally) -> win quote -> ... -> stage-index-3 walk-in -> pre-fight
dialogue -> fight -> loss -> CONTINUE -> reselect -> map -> challenger (seat 2 START: banner,
shutter, two-seat select, face-off, mode-3 fight) -> win quote -> VS result -> map -> post-fight
dialogues -> camera pan -> pre-final demo -> final fight -> ending -> staff roll -> GAME OVER ->
unlock notice -> ranking -> title.

Fights after the first are ended by the replay fixture of match_replay (bit 31 / 30 of the second
pad word: a win of the arcade seat / of its opponent); a final opponent without a native port is
replaced by the same fixture. Everything else is the shipping session code.

Checks:
  1. the scene sequence and the kind / speed of every scene switch (1252f0 kinds 1 / 2 / 4, 1c1ac0
     hand-offs -1, direct calls 0), against the original rules (docs/mode-arcade-*.txt);
  2. state hand-over: g+1c cleared by 136288, 1c7cb0 writes only the arcade seat's +1c, the
     ending writes option 81 + spirit and 47 + character and holds g+30, the fights receive the
     schedule's stage;
  3. every presentation frame of the session against the validated scene modules: a reference
     driver (compiled here against the same library) restores the state each scene entry read
     (saveArcadeState), enters the module itself and replays the recorded pads and fade registers
     frame by frame; the draw-list checksums must be identical on every frame;
  4. pictures: no composition error, fighter objects present where the original queues them,
     and the written PNG samples (outputs/ss6-feasibility/arcade-session/) for inspection."""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
OUT=ROOT/'outputs/ss6-feasibility'
Z=(0,0)
UP,DOWN,LEFT,RIGHT=0x10,0x20,0x40,0x80
LIGHT,MEDIUM,HEAVY,START=0x100,0x200,0x400,8
WIN,LOSE=0x80000000,0x40000000
# Columns of --arcade-fields (after the 23 common columns).
(SCENE,CURRENT,TACTIVE,TPHASE,TKIND,TSPEED,FLEVEL,FMODE,MODE,STAGE,INDEX,PROGRESS,PREFINAL,INTERRUPTED,INHIBIT,LOCK,
 LEVELEND,SCORE,WINNER,STREAK,PFRAME,CHECK,RECORDS,OBJECTS,NOTICE,LOGSIZE,GOFRAME,CONTFRAME,ENDSEEN,LIBSEED,GAMESEED,
 CHAR,CPUCHAR,BATTLEOVER,INTRUDER,POSTFIGHT,PICTURE,PAINTERR,SELECT,FACEOFF,S0PHASE,S0SEL,S1PHASE,S1SEL,SCOMPLETE,
 GAMEMODE,FCOLOUR,OTHERPREFINAL,SPIRITSEEN)=range(23,72)
S=dict(select='128008',opening='1c60c8',map='1c1b20',walkin='1c4428',dialogue='1c5290',prefinal='1c6cc0',battle='139760',
       winquote='135e30',title='127940',result='136a60',cont='1376d0',gameover='138340',ending='182968',unlock='1e5d88',ranking='1e8850')
PRESENTED={S[k] for k in ('opening','map','walkin','dialogue','prefinal','winquote','result','ending','unlock','ranking')}


class Live:
    """One replay process driven a frame at a time (the binary flushes every arcade row)."""
    def __init__(self,binary,assets,dump):
        cmd=[str(binary),str(assets),'--mode','title','--unlock-modes','--arcade-fields','--arcade-dump',str(dump)]
        self.p=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
        self.rows,self.pads=[],[]
    def tick(self,a=0,b=0):
        self.p.stdin.write(f'1 {a} {b}\n');self.p.stdin.flush()
        line=self.p.stdout.readline()
        if not line:raise RuntimeError('replay ended: '+self.p.stderr.read()[-2000:])
        r=line.split();self.rows.append(r);self.pads.append((a,b));return r
    def idle(self,n):
        for _ in range(n):self.tick()
    def tap(self,a=0,b=0,gap=6):
        self.tick(a,b);self.idle(gap)
    def until(self,cond,limit=20000,pad=lambda i:Z,what=''):
        for i in range(limit):
            if cond(self.tick(*pad(i))):return
        raise AssertionError(f'{what} not reached; last row '+' '.join(self.rows[-1][23:48]))
    def close(self):
        self.p.stdin.close();rest=self.p.stdout.read();self.p.wait()
        assert self.p.returncode==0,self.p.stderr.read()[-2000:]
        return rest


def scene(r):return r[SCENE] if len(r)>SCENE else '-'
def press(i):return (LIGHT,0) if i%30==0 else Z


def play(binary,assets,dump):
    L=Live(binary,assets,dump)
    marks={}
    L.idle(32);L.tap(START,0,15);L.tap(HEAVY,0,40);L.idle(150);L.tap(HEAVY,0,30)
    in_fight=lambda r:scene(r)==S['battle'] and r[TACTIVE]=='0' and r[BATTLEOVER]=='0'
    def leave_fight():L.until(lambda r:scene(r)!=S['battle'],limit=4000,pad=press,what='scene after the fight')
    # Fight 1 is played out: walk forward and slash until 145628 (round tally included).
    L.until(in_fight,limit=4000,pad=press,what='first fight')
    marks['fight1']=len(L.rows)
    forward=lambda i:(RIGHT,0) if i%40<10 else (HEAVY,0) if i%40 in (10,23) else Z
    L.until(lambda r:r[BATTLEOVER]=='1' or scene(r)!=S['battle'],limit=12000,pad=forward,what='end of fight 1')
    assert L.rows[-1][WINNER]=='0','the scripted first fight must be won by seat 1: '+' '.join(L.rows[-1][:13]+L.rows[-1][23:48])
    leave_fight()
    # Fights at schedule indices 1..2 (forced wins), index 3 behind the pre-fight dialogue (forced loss).
    for k in range(3):
        L.until(in_fight,limit=6000,pad=press,what=f'fight {k+2}');L.idle(30)
        if k==2:marks['dialogue_fight']=len(L.rows)
        L.tick(0,WIN if k<2 else LOSE);L.idle(2);leave_fight()
    L.until(lambda r:scene(r)==S['cont'],limit=100,what='CONTINUE')
    L.idle(60);L.tap(START,0,10)
    L.until(lambda r:scene(r)==S['select'],limit=200,what='reselect')
    L.idle(200);L.tap(HEAVY,0,40);L.idle(100);L.tap(HEAVY,0,30)
    L.until(lambda r:scene(r)==S['map'],limit=3000,pad=press,what='map after CONTINUE')
    L.idle(40)
    # Challenger: seat 2 presses START while the map runs.
    marks['challenger']=len(L.rows)
    L.tap(0,START,4)
    L.until(lambda r:r[GAMEMODE]=='3' and scene(r)==S['select'] and r[TACTIVE]=='0',limit=600,what='two-seat select')
    for _ in range(6):
        L.idle(60);L.tap(HEAVY,HEAVY,30)
    L.until(in_fight,limit=3000,what='challenger fight');L.idle(60)
    L.tick(0,WIN);L.idle(2)
    L.until(lambda r:scene(r)==S['result'],limit=3000,pad=press,what='VS result')
    L.until(lambda r:scene(r)==S['map'],limit=3000,what='map after the VS result')
    # Remaining schedule: forced wins; the final opponent is forced before its fight starts.
    for _ in range(12):
        L.until(lambda r:scene(r) in (S['battle'],S['ending'],S['prefinal']),limit=8000,pad=press,what='next fight')
        if scene(L.rows[-1])==S['ending']:break
        if scene(L.rows[-1])==S['prefinal']:
            L.tick(0,WIN);L.idle(2)
            L.until(lambda r:scene(r)!=S['prefinal'],limit=3000,pad=press,what='final fight');continue
        L.until(lambda r:r[TACTIVE]=='0',limit=100);L.idle(30)
        L.tick(0,WIN);L.idle(2);leave_fight()
    # Ending: watch it, then START skips the rest of the ending and the staff roll.
    L.idle(900);L.tap(START,0,10);L.idle(600);L.tap(START,0,10)
    L.until(lambda r:scene(r)!=S['ending'],limit=6000,what='GAME OVER')
    L.until(lambda r:scene(r)==S['ranking'],limit=3000,pad=lambda i:(HEAVY,0) if i%90==0 else Z,what='ranking')
    L.idle(2000);L.tap(START,0,4)
    L.until(lambda r:scene(r)=='-1',limit=400,what='title')
    L.idle(30)
    tail=L.close()
    log=[]
    for line in tail.splitlines():
        if line.startswith('#scene'):
            f=line.split()
            n=int(f[5])
            log.append(dict(scene=f[1],kind=int(f[2]),speed=int(f[3]),frame=int(f[4]),state=[int(w) for w in f[6:6+n]]))
    return L,log,marks


DRIVER=r'''
#include "arcade_presentation.hpp"
#include "arcade_ending.hpp"
#include <iostream>
#include <sstream>
#include <string>
using namespace ss6;
// Mirror of ArcadePresentation::tick for one scene, written against the scene modules only.
static uint32_t physicalPad(uint32_t logical) {
    constexpr std::array<uint32_t,8> physical{0x400,0x200,2,4,0x400000,0x800000,0x100000,0x200000};
    uint32_t bits=logical&0xf8;
    for(unsigned i=0;i<physical.size();++i)if(logical&(0x100u<<i))bits|=physical[i];
    return bits;
}
static uint32_t destructorOf(uint32_t s) {
    switch(s){case 0x1c60c8:return 0x1c61b8;case 0x1c1b20:return 0x1c1de8;case 0x1c4428:return 0x1c44f0;case 0x1c5290:return 0x1c53e0;
    case 0x1c6cc0:return 0x1c6d70;case 0x135e30:return 0x136288;case 0x136a60:return 0x136f88;case 0x182968:return 0x182a48;case 0x1e5d88:return 0x1e6130;}
    return 0;
}
int main(int argc,char** argv) {
    const std::filesystem::path assets=argv[1];
    SystemData system(assets);
    ArcadeSession session(assets,system);   // supplies ArcadeRun / tables / RNG / fade storage
    auto& run=session.run;
    MenuCanvas canvas(assets);
    ArcadeMapArt mapArt(assets);ArcadeTalkTables talk(assets);ArcadeResultsTables results(assets);EndingData endingData(assets);
    ArcadeRankingArt rankingArt(assets);
    ArcadeMapState map;UnlockSessionFlags unlock{};ArcadeEdgePulse pulse;
    ArcadeSceneObjects objects(assets);
    std::optional<ArcadeMapScene> mapScene;std::optional<ArcadeWalkInScene> walkIn;
    std::unique_ptr<ArcadeOpening> opening;std::unique_ptr<ArcadeDialogue> dialogue;std::unique_ptr<ArcadePreFinal> preFinal;
    std::optional<ArcadeWinQuote> quote;std::optional<ArcadeVersusResult> result;std::unique_ptr<ArcadeEnding> ending;
    std::optional<ArcadeUnlockNotice> notice;std::unique_ptr<ArcadeRanking> ranking;
    int resultObject=-1;bool rankingExit=false;
    uint32_t current=0;
    MenuDrawList list,back;
    const auto talkEvents=[&](const std::vector<ArcadeTalkRecord>& events) {
        for(const auto& e:events) {
            if(e.kind==ArcadeTalkEvent::MapResources)map.reset(mapArt.tables(),run.random());
            if(e.kind==ArcadeTalkEvent::MapIcon)mapArt.bindIcon(e.a[0]);
            if(e.kind==ArcadeTalkEvent::LoadCharacter)objects.bind(unsigned(e.a[0]),e.a[1]);
        }
    };
    std::string line;
    while(std::getline(std::cin,line)) {
        std::istringstream in(line);std::string op;in>>op;
        if(op=="scene") {
            unsigned n;in>>std::hex>>current>>std::dec>>n;
            std::vector<uint32_t> words(n);for(auto& w:words)in>>w;
            loadArcadeState(words,run,session.random,system,session.fade,map,unlock,pulse);
            uint32_t held;in>>held;held=physicalPad(held);
            objects.clear();objects.submitted.clear();list.beginFrame();back.beginFrame();
            for(unsigned i=0;i<2;++i)objects.bind(i,run.players[i].character);
            auto& fade=session.fade;
            switch(current) {
            case 0x1c60c8:opening=std::make_unique<ArcadeOpening>(talk);opening->enter(run,fade,held);talkEvents(opening->events);break;
            case 0x1c1b20:mapScene.emplace();mapScene->enter(run,map,mapArt,objects);break;
            case 0x1c4428:walkIn.emplace();walkIn->enter(run,mapArt);break;
            case 0x1c5290:dialogue=std::make_unique<ArcadeDialogue>(talk);dialogue->enter(run,fade);talkEvents(dialogue->events);break;
            case 0x1c6cc0:preFinal=std::make_unique<ArcadePreFinal>(talk);preFinal->enter(run,fade);talkEvents(preFinal->events);break;
            case 0x135e30:quote.emplace();quote->enter(run,results);break;
            case 0x136a60: {
                result.emplace();result->enter(run,results);const auto& f=result->fighter;
                objects.bind(unsigned(f.seat),f.character);resultObject=objects.create(0xbc2,f.seat,f.action,f.x,f.flags,f.colour);break;
            }
            case 0x182968:ending=std::make_unique<ArcadeEnding>(endingData);ending->enter(run,system.setting(2)!=0);break;
            case 0x1e5d88:notice.emplace();notice->enter(run,unlock);break;
            case 0x1e8850:ranking=std::make_unique<ArcadeRanking>();ranking->enter(rankingArt,system,run.random(),run.rankingHighlight,held);rankingExit=false;break;
            }
            std::cout<<arcadeDrawChecksum(list,back)<<std::endl;
        } else if(op=="tick") {
            uint32_t p0,p1,held,mode,colour;int level,lock;in>>p0>>p1>>held>>mode>>colour>>level>>lock;
            auto& fade=session.fade;
            // The transition task (not part of the scene modules) ends with 1252e4: g+2c / g+94 = 0.
            if(run.game.transitionLock&&!lock)run.transitionFinished();
            fade.mode=int32_t(mode);fade.colour=colour;fade.level=level;
            const std::array<uint32_t,2> pressed{physicalPad(p0),physicalPad(p1)};
            held=physicalPad(held);
            const unsigned h=run.humanSeat();
            run.idleRandom();
            run.transition={};
            run.pollChallenger(pressed,destructorOf(current));
            objects.submitted.clear();list.beginFrame();back.beginFrame();
            canvas.setBrightness(system.brightness());
            canvas.setFade(fade.vertexFade(),fade.level,fade.colour);
            const ArcadeTalkInput input{pressed};
            switch(current) {
            case 0x1c60c8: {
                ArcadeMapFrame f;f.capture(map);f.stage=run.game.stage;f.stageIndex=run.mapStageIndex;
                mapArt.setFade(fade.vertexFade(),fade.level,fade.colour);
                const int before=back.depth;
                mapArt.ground(canvas,back,f);
                const auto tiles=std::count_if(back.records.begin(),back.records.end(),[](const MenuDrawRecord& r){return r.slot==0x2a;});
                back.records.erase(std::remove_if(back.records.begin(),back.records.end(),[](const MenuDrawRecord& r){return r.slot==0x2a;}),back.records.end());
                for(auto& r:back.records)r.z-=float(tiles);
                back.depth=before+(back.depth-before-int(tiles));
                mapArt.clouds(canvas,back,f);
                map.moveClouds(mapArt.tables(),run.random());
                list.depth=back.depth;
                opening->tick(run,fade,objects,input);talkEvents(opening->events);opening->draw(canvas,list);
                break;
            }
            case 0x1c1b20:
                mapScene->tick(run,map,mapArt,objects);
                mapArt.setFade(fade.vertexFade(),fade.level,fade.colour);   // 1c32c8 fades the picture vertices itself
                mapScene->draw(mapArt,canvas,list);break;
            case 0x1c4428:
                walkIn->tick(run,map,mapArt,objects,held,pressed[h],system.setting(2)!=0,fade.vertexFade()&&fade.level>=0x100);
                mapArt.setFade(fade.vertexFade(),fade.level,fade.colour);
                walkIn->draw(mapArt,canvas,list);break;
            case 0x1c5290:dialogue->tick(run,fade,objects,input);talkEvents(dialogue->events);dialogue->draw(canvas,list);break;
            case 0x1c6cc0:preFinal->tick(run,fade,input);preFinal->draw(canvas,list);break;
            case 0x135e30:quote->tick(run,pressed,held);drawArcadeWinQuote(canvas,list,results,quote->draw);break;
            case 0x136a60: {
                const auto& all=objects.objects();const auto found=all.find(resultObject);
                const bool pose=found!=all.end()&&found->second.body&&found->second.body->timeline.action().id()==0x1fb&&objects.finished(resultObject);
                const auto e=result->tick(run,pressed,held,pose?1:0);
                drawArcadeVersusResult(canvas,list,results,result->draw);
                objects.step(resultObject);
                if(e.objectAction)objects.restart(resultObject,e.action);
                break;
            }
            case 0x182968: {
                const auto before=ending->nameEntry;
                auto& e=ending->playback.fade;
                e.mode=fade.mode;e.colour=fade.colour;e.level=fade.level;e.step=fade.speed;e.ceiling=fade.maximum;e.floor=fade.minimum;e.tones=fade.flags;
                ending->tick(run,pressed,256);
                drawEnding(canvas,list,endingData,ending->playback.frame);
                if(before.active) {
                    canvas.setFade(false,0,0);
                    drawArcadeNameCountdown(canvas,back,results,before,run.game.mode);
                    drawArcadeNameEntry(canvas,back,results,run.tables(),ending->nameEntry,run.game.mode);
                }
                break;
            }
            case 0x1e5d88:notice->tick(run,pressed);drawArcadeUnlockNotice(canvas,list,results,notice->draw,pulse);break;
            case 0x1e8850: {
                bool alternate=false;
                const auto d=ranking->tick(((pressed[0]|pressed[1])&8)!=0,alternate);
                canvas.setFade(fade.vertexFade(),fade.level,fade.colour);
                ranking->draw(rankingArt,canvas,list);
                if(d!=RankingDestination::None)rankingExit=true;
                break;
            }
            }
            std::cout<<arcadeDrawChecksum(list,back)<<std::endl;
        }
    }
}
'''


def compile_driver(build,work):
    src=work/'driver.cpp';src.write_text(DRIVER)
    exe=work/'driver'
    cmd=['c++','-std=c++20','-ffp-contract=off','-O2','-I',str(ROOT/'src'),str(src),str(build/'libss6-runtime.a'),'-o',str(exe)]
    r=subprocess.run(cmd,capture_output=True,text=True)
    assert r.returncode==0,r.stderr[-4000:]
    return exe


def reference(exe,assets,L,log):
    """Replays every presentation scene instance through the driver; returns (frames, mismatches)."""
    rows,pads=L.rows,L.pads
    entries=[]   # (log index, first row)
    for i,e in enumerate(log):
        if e['scene'] not in PRESENTED:continue
        first=next(k for k,r in enumerate(rows) if len(r)>LOGSIZE and int(r[LOGSIZE])>i)
        entries.append((i,first))
    script=[];expect=[]
    held_prev=[0,0]
    def held_of(k,seat):return pads[k][seat]&0x1fffffff
    for n,(i,first) in enumerate(entries):
        e=log[i]
        stop=next((f for j,f in entries if j>i),len(rows))
        # The rows of this scene: from its entry row while the session still runs it.
        human=1 if rows[first][MODE]=='2' else 0
        script.append(f"scene {e['scene']} {len(e['state'])} "+' '.join(map(str,e['state']))+f" {physicalHeld(pads,first,human)}")
        expect.append((first,int(rows[first][CHECK]),e['scene']));base=first
        for k in range(first+1,stop):
            r=rows[k]
            if scene(r)!=e['scene'] or r[CURRENT]!=e['scene'] or int(r[LOGSIZE])!=i+1:break
            prev=rows[k-1]
            a,b=pads[k];pa,pb=pads[k-1]
            b&=0x1fffffff;pb&=0x1fffffff
            script.append(f'tick {a&~pa} {b&~pb} {[a,b][human]} {prev[FMODE]} {prev[FCOLOUR]} {prev[FLEVEL]} {prev[LOCK]}')
            expect.append((k,int(r[CHECK]),e['scene']+f'@{k-base}'))
    r=subprocess.run([str(exe),str(assets)],input='\n'.join(script)+'\n',text=True,capture_output=True)
    assert r.returncode==0,r.stderr[-3000:]
    got=[int(x) for x in r.stdout.split()]
    assert len(got)==len(expect),(len(got),len(expect))
    mismatch=[(row,sc) for (row,want,sc),value in zip(expect,got) if want!=value]
    per={}
    for (row,want,sc),value in zip(expect,got):
        d=per.setdefault(sc.split('@')[0],[0,0]);d[0]+=1;d[1]+=want!=value
    return len(expect),mismatch,per


def physicalHeld(pads,k,human):return pads[k][human]&0x1fffffff


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--build',default='work/ss6/build-cutscenes')
    parser.add_argument('--assets',default='outputs/ss6-feasibility/native-viewer/assets')
    args=parser.parse_args()
    build=ROOT/args.build;assets=ROOT/args.assets
    report=dict(build=str(args.build),checks={})
    with tempfile.TemporaryDirectory() as tmp:
        tmp=Path(tmp);dump=tmp/'frames';dump.mkdir()
        L,log,marks=play(build/'ss6-match-replay',assets,dump)
        rows=L.rows
        seq=[(e['scene'],e['kind'],e['speed']) for e in log]
        report['frames']=len(rows);report['scenes']=[f'{s}:{k}:{v}' for s,k,v in seq]
        # 1. Scene switches.
        def follows(a,b):
            return [(seq[i+1][1],seq[i+1][2]) for i in range(len(seq)-1) if seq[i][0]==S[a] and seq[i+1][0]==S[b]]
        expect_kinds={('select','opening'):(1,1),('opening','map'):(-1,0),('map','walkin'):(-1,0),('walkin','battle'):(2,0),
                      ('walkin','dialogue'):(2,0),('dialogue','battle'):(2,0),('battle','winquote'):(2,0),('winquote','map'):{(1,1),(4,1)},('dialogue','map'):{(2,0),(4,1)},
                      ('battle','cont'):(2,0),('cont','select'):(3,0),('select','map'):(1,1),('map','select'):(4,0),
                      ('select','battle'):(1,1),('winquote','result'):(1,1),('result','map'):(1,1),('battle','dialogue'):(2,0),
                      ('dialogue','prefinal'):(1,1),('prefinal','battle'):(1,2),('battle','ending'):(2,0),('ending','gameover'):(1,1),
                      ('gameover','unlock'):(0,0),('unlock','ranking'):(1,1),('ranking','title'):(1,0)}
        seen={}
        # 17a548: the intruder announcement replaces the fade (kind 4, speed 1) when it is due.
        seen['intruder banners']=sum(1 for i in range(len(seq)-1) if seq[i+1][0]==S['map'] and seq[i+1][1:]==(4,1))
        for (a,b),kind in expect_kinds.items():
            got=follows(a,b)
            if got:
                allowed=kind if isinstance(kind,set) else {kind}
                assert all(g in allowed for g in got),f'{a}->{b}: {got} not in {allowed}'
                seen[f'{a}->{b}']=len(got)
        for need in ('opening->map','map->walkin','walkin->dialogue','dialogue->battle','battle->winquote','winquote->map','battle->cont',
                     'cont->select','map->select','winquote->result','result->map','dialogue->prefinal','prefinal->battle',
                     'battle->ending','ending->gameover','gameover->unlock','unlock->ranking','ranking->title'):
            assert need in seen,f'scene switch {need} missing from {seq}'
        report['checks']['switches']=seen
        names={v:k for k,v in S.items()}
        order=[names.get(s,s) for s,_,_ in seq]
        assert order[:5]==['select','opening','map','walkin','battle'],order
        assert order[-5:]==['ending','gameover','unlock','ranking','title'],order
        # The run ends at the title (the arcade session is gone).
        assert rows[-1][SCENE]=='-1'
        # 2. State hand-over.
        res=[k for k,r in enumerate(rows) if scene(r)==S['result']]
        rows=[r for r in rows]
        assert res and all(rows[k][INTERRUPTED]=='0' for k in res[1:]),'136288 must clear g+1c before the VS result runs'
        assert order.count('result')==1,'after one challenger fight every later win quote must lead to the map'
        pre=[r for r in rows if scene(r)==S['prefinal']]
        assert pre and pre[-1][PREFINAL]=='1' and all(r[OTHERPREFINAL]=='0' for r in pre),'1c7cb0 writes only the arcade seat'
        end=[r for r in rows if scene(r)==S['ending'] and r[CURRENT]==S['ending']]
        assert end and all(r[INHIBIT]=='1' for r in end[1:]),'182968 holds g+30'
        assert end[-1][ENDSEEN]=='1' and end[-1][SPIRITSEEN]=='1','the ending writes options 47 + character and 81 + spirit'
        assert any(scene(r)==S['dialogue'] and len(r)>INDEX and r[INDEX]=='3' for r in rows),'the stage-index-3 dialogue'
        assert any(len(r)>GAMEMODE and r[GAMEMODE]=='3' and scene(r)==S['battle'] for r in rows),'the challenger fight runs in mode 3'
        report['checks']['state']=dict(versus_result_frames=len(res),prefinal_frames=len(pre),ending_frames=len(end))
        # 4. Pictures.
        pictured=[r for r in rows if len(r)>PAINTERR and r[PICTURE]=='1']
        assert not [r for r in pictured if r[PAINTERR]!='0'],'a scene frame could not be composed'
        objects={}
        for r in pictured:objects.setdefault(names.get(scene(r),scene(r)),set()).add(int(r[OBJECTS]))
        for name,count in (('walkin',2),('dialogue',2),('result',1),('cont',1),('opening',1),('ending',2),('map',1)):
            assert max(objects.get(name,{0}))>=count,f'{name}: fighter objects {objects.get(name)}'
        report['checks']['objects']={k:sorted(v) for k,v in objects.items()}
        # 3. Frames against the scene modules.
        exe=compile_driver(build,tmp)
        total,mismatch,per=reference(exe,assets,L,log)
        report['checks']['reference']=dict(frames=total,mismatches=len(mismatch),first=mismatch[:5],per_scene=per)
        firsts={};[firsts.setdefault(row-int(sc.split('@')[1]) if '@' in sc else row,(row,sc)) for row,sc in mismatch]
        assert not mismatch,f'{sorted(firsts.values())} {len(mismatch)} of {total} presentation frames differ from the scene modules: {mismatch[:5]} {per}'
        # PNG samples for inspection.
        from PIL import Image
        sample=OUT/'arcade-session';sample.mkdir(exist_ok=True)
        firsts={}
        for k,r in enumerate(rows):
            if len(r)>PICTURE and r[PICTURE]=='1' and int(r[RECORDS])>0:firsts.setdefault(names.get(scene(r),scene(r)),[]).append(k)
        written=[]
        for name,ks in firsts.items():
            k=ks[len(ks)//2]
            raw=(dump/f'{k}.rgba').read_bytes()
            Image.frombytes('RGBA',(640,480),raw).convert('RGB').save(sample/f'{name}.png');written.append(name)
        report['samples']=sorted(written)
    report['marks']=marks
    report['passed']=True
    (OUT/'arcade_session_validation.json').write_text(json.dumps(report,indent=1))
    print(f"arcade session: {len(rows)} frames, {len(seq)} scenes, {total} presentation frames identical to the scene modules")


if __name__=='__main__':
    main()
