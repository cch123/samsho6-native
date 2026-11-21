#include "arcade_run.hpp"
#include "game_random.hpp"
#include "system_data.hpp"
#include <algorithm>
#include <cstring>
#include <stdexcept>

namespace ss6 {
namespace {
constexpr uint32_t battleDestructor=0x139778,selectDestructor=0x12f800,quoteDestructor=0x136288,
                   resultDestructor=0x136f88,continueDestructor=0x137c68,gameOverDestructor=0x138a48,
                   menuDestructor=0x127d70;
constexpr size_t streakTable=SystemData::ranking,scoreTable=SystemData::ranking+0x28; // 43d0f0, 43d118

[[noreturn]] void unsupported(const char* what) {throw std::logic_error(what);}
bool same(const std::array<char,4>& text,const char* literal) {return std::strncmp(text.data(),literal,4)==0;}
}

ArcadeTables::ArcadeTables(std::span<const uint8_t> asset) {
    if(asset.size()<byteSize)throw std::invalid_argument("arcade_run.bin is truncated");
    size_t at=0;
    auto read=[&](auto& value) {std::memcpy(&value,asset.data()+at,sizeof value);at+=sizeof value;};
    read(opponents);read(stages);read(bosses);read(intruder);read(versusLimits);read(glyphs);read(names);
    uint32_t count=0;read(count);
    if(count>filtered.size()||at+4*count>asset.size())throw std::invalid_argument("arcade_run.bin name filter");
    filteredCount=count;
    std::memcpy(filtered.data(),asset.data()+at,4*count);
}

int ArcadeRun::drawOpponents(int character) {
    // An unknown key falls back to row 0. Slots 3, 5 and 6 are fixed per row.
    size_t key=0;
    for(size_t i=0;i<tables_.opponents.size();++i)if(tables_.opponents[i][0]==character){key=i;break;}
    const auto& row=tables_.opponents[key];
    std::array<bool,10> used{};
    for(unsigned slot:{0u,1u,2u,4u}) {
        int r=random_.bounded(10);
        while(used.at(r)||row[1+r]==-1)r=(r+1)%10;
        used[r]=true;schedule.opponents[slot]=row[1+r];
    }
    schedule.opponents[3]=row[11];schedule.opponents[5]=row[12];schedule.opponents[6]=row[13];
    // The count covers slots 0..4 only, so a home-stage fighter in slot 5 is not counted.
    int home=0;
    for(unsigned i=0;i<5;++i)home+=uint16_t(schedule.opponents[i]-30)<3;
    return home;
}

void ArcadeRun::buildSchedule(int character,bool reroll,uint32_t held) {
    auto& s=schedule;
    // A rejected attempt keeps its four draws; never replace this by a constructive pick.
    while(drawOpponents(character)<2) {}
    // 17abd8: a held direction requests one boss for every placeholder 51.
    const int requested=held&0x10?11:held&0x20?13:held&0x80?27:held&0x40?26:-1;
    if(requested>=0&&requested!=character&&std::find(s.opponents.begin(),s.opponents.end(),requested)==s.opponents.end())
        std::replace(s.opponents.begin(),s.opponents.end(),int16_t(51),int16_t(requested));
    // 17a8f0: candidates already present or equal to the player are removed.
    // A chosen candidate is not marked, so two placeholders may repeat it.
    std::array<int32_t,4> candidates=tables_.bosses;
    for(auto& c:candidates)if(c==character)c=-1;
    for(int16_t id:s.opponents)for(auto& c:candidates)if(id==c)c=-1;
    for(auto& id:s.opponents)if(id==51) {
        int r=random_.bounded(4);
        while(candidates.at(r)==-1)r=(r+1)%4;
        id=int16_t(candidates[r]);
    }
    // 17aa00: fixed stages 9/10 are written before the home-stage rule.
    s.stages.fill(-1);s.stages[5]=9;s.stages[6]=10;
    for(unsigned i=0;i<7;++i)if(s.stages[i]==-1&&s.opponents[i]>=30&&s.opponents[i]<=32)s.stages[i]=int16_t(s.opponents[i]-30);
    std::array<bool,5> usedStage{};
    for(auto& stage:s.stages)if(stage==-1) {
        int r=random_.bounded(5);
        while(usedStage.at(r))r=(r+1)%5;
        usedStage[r]=true;stage=int16_t(tables_.stages[r]);
    }
    if(reroll) { // 17ab78
        for(unsigned i=0;i<7;++i) {s.rolls[i]=uint8_t(random_.bounded(100)+1);s.bonus[i]=0;s.wins[i]=0;}
        s.substitutionDisabled=0;s.intruderDisabled=0;
    }
    // 17bb38: each draw precedes its store; the swap partner spans all 49 entries.
    s.word11c=s.word11e=-1;
    for(unsigned i=0;i<49;++i) {s.characterRolls[i]=int16_t(random_.bounded(12));s.characterOrder[i]=int16_t(i);}
    for(unsigned i=0;i<49;++i)std::swap(s.characterOrder[i],s.characterOrder.at(random_.bounded(49)));
}

int ArcadeRun::opponentAt(int index) const {
    if(game.submode==5)unsupported("17bbe0 network opponent");
    if(index==-1)return 33;
    if(index==-2)return 43;
    // Out of range the original prints an assertion and returns 0.
    return index>=0&&index<7?schedule.opponents[index]:0;
}
int ArcadeRun::stageAt(int index) {
    if(game.submode==5)unsupported("17bcc0 network stage");
    // The draw is unconditional; its table value is returned only on the assertion path.
    const int32_t fallback=tables_.stages.at(random_.bounded(5));
    if(index==-1)return 3;
    if(index==-2)return 11;
    return index>=0&&index<7?schedule.stages[index]:fallback;
}
bool ArcadeRun::intruderDue() const {
    if(schedule.intruderDisabled||game.submode==5)return false;
    const int index=game.mode==1?players[0].stageIndex:game.mode==2?players[1].stageIndex:0;
    // 4ee530 is indexed before the range test; index 8 reads the -1 that follows the table.
    if(index<=0||index>=7)return false;
    const int threshold=tables_.intruder[index];
    return threshold>0&&schedule.rolls[index]<threshold+schedule.bonus[index-1];
}
bool ArcadeRun::substituteKuroko() {
    if(schedule.substitutionDisabled||game.submode==5||(game.mode!=1&&game.mode!=2))return false;
    const auto& human=players[game.mode-1];
    if(human.stageIndex!=4)return false;
    const int wins=schedule.wins[0]+schedule.wins[1]+schedule.wins[2]+schedule.wins[3];
    if(wins<3*human.roundWins)return false;
    schedule.opponents[4]=48;
    return true;
}
void ArcadeRun::addBonus(int index,int amount) {if(index>=0&&index<7)schedule.bonus[index]=uint8_t(schedule.bonus[index]+amount);}
void ArcadeRun::addRoundWin(int index,int amount) {if(index>=0&&index<7)schedule.wins[index]=uint8_t(schedule.wins[index]+amount);}

void ArcadeRun::prepareFight() {
    intruderFight=0;
    const bool intruder=intruderDue();
    intruderFight=intruder;
    if(game.mode!=1&&game.mode!=2)return;
    auto& human=players[game.mode-1];auto& cpu=players[2-game.mode];
    // Index 7 is the fixed final opponent 43 on stage 11; the intruder is 33 on stage 3.
    const int index=intruder?-1:human.stageIndex==7?-2:human.stageIndex;
    cpu.character=opponentAt(index);
    game.stage=stageAt(index);
    mapStageIndex=human.stageIndex;
}

void ArcadeRun::request(int kind,int speed,uint32_t destructor,ArcadeScene next) {
    transition={kind,speed,destructor,next};
    if(kind>=1&&kind<=3)game.transitionLock=1;
    else if(kind==4&&speed==0)game.challengerBanner=1;
}

void ArcadeRun::applyRoundWins() {
    unsigned seat;
    if(game.mode==4||game.mode==1)seat=0;
    else if(game.mode==5||game.mode==2)seat=1;
    else return;
    if(system_.option(7)>=15)return;
    const auto wins=system_.cpuMatchWins();
    players[seat].roundWins=wins[0];players[seat^1].roundWins=wins[1];
}
void ArcadeRun::resetPlayer(unsigned seat) {
    auto& p=players.at(seat);
    const int32_t wins=p.roundWins;
    p={};p.spirit=p.versusSpirit=5;p.roundWins=wins;
    applyRoundWins();
}
void ArcadeRun::confirmMenu(unsigned seat) {
    request(1,0,menuDestructor,ArcadeScene::CharacterSelect);
    game.mode=int32_t(seat)+1;
    battleKind=0; // 139280(0)
    game.submode=1;
    applyRoundWins();
}

void ArcadeRun::selectExit(uint32_t held) {
    if(game.mode!=1&&game.mode!=2)unsupported("12f100 exit outside modes 1/2");
    auto& human=players[game.mode-1];
    if(human.stageIndex==7) {
        prepareFight();request(1,1,selectDestructor,ArcadeScene::Battle);
    } else if(human.progress==0) {
        if(game.submode==5)unsupported("network arcade");
        request(1,1,selectDestructor,ArcadeScene::Opening);
    } else {
        // After CONTINUE or a challenger match the schedule survives unless the character changed.
        if(human.previousCharacter!=human.character) {
            buildSchedule(human.character,true,held);prepareFight();game.scheduleValid=1;
        }
        request(1,1,selectDestructor,ArcadeScene::Map);
        resetScore();
    }
}

ArcadeBattleSetup ArcadeRun::battleSetup(int selectedStage) {
    ArcadeBattleSetup out;
    if(game.mode==1||game.mode==2) {
        const unsigned h=game.mode-1,c=h^1;
        auto& human=players[h];auto& cpu=players[c];
        out.stageIndex=human.stageIndex;out.stage=game.stage;
        out.control[h]=0;out.control[c]=1;out.spirit[h]=human.spirit;
        if(game.submode==5)cpu.colour=random_.bounded(5);
        // 139c50: the final opponent and the four extra fighters have fixed spirits.
        const int drawn=random_.bounded(6);
        cpu.spirit=cpu.character==43?7:cpu.character>=44&&cpu.character<=47?8:drawn;
        out.spirit[c]=cpu.spirit;
        if(human.character==cpu.character) {
            if(human.colour==cpu.colour)cpu.colour=human.colour==0;
        } else if(game.submode!=5)cpu.colour=0;
    } else if(game.mode==0||game.mode==0xb||game.mode==0xc) {
        unsupported("1398c0 demo/survival setup");
    } else {
        // 139be8: +00 keeps whatever the parameter block held.
        int stage=random_.bounded(10);
        if((game.submode==2||game.submode==3)&&selectedStage!=10)stage=selectedStage;
        out.stage=game.stage=stage;
        out.control={game.mode==10,game.mode==9};
        out.spirit={players[0].versusSpirit,players[1].versusSpirit};
    }
    for(unsigned i=0;i<2;++i) {
        out.character[i]=players[i].character;out.colour[i]=players[i].colour;out.roundWins[i]=players[i].roundWins;
    }
    return out;
}

bool ArcadeRun::postFightDialogue() const {
    const int index=game.mode==1?players[0].stageIndex:game.mode==2?players[1].stageIndex:0;
    return index==4||(index>=6&&index<=8);
}

void ArcadeRun::matchEnd(int bonus) {
    auto go=[&](ArcadeScene next) {request(2,0,battleDestructor,next);game.wordA4=0;};
    // The console VS menu path returns through 124da0 without a scene request.
    if(game.submode==2) {recordVersus();return;}
    if(system_.option(2)!=0) {go(ArcadeScene::GameOver);return;}
    const int mode=game.mode;
    if(mode==3) {
        recordVersus(); // rewrites g+0 to winner+1
        if(versusLimitReached()) {go(ArcadeScene::GameOver);return;}
        if(game.winner==-1) {
            if(game.submode==6)unsupported("network versus draw");
            game.versusInterrupted=0;go(ArcadeScene::GameOver);return;
        }
        if(game.winner==game.selectingSeat) {resetScore();clearStartHold();}
        if(game.submode==6)unsupported("network versus result");
        go(ArcadeScene::WinQuote);
    } else if(mode==1||mode==2) {
        if(game.winner==mode-1) {
            auto& human=players[mode-1];
            // Beating the intruder 33 cancels further intrusions and keeps the index.
            if(players[2-mode].character==33&&game.submode!=5)schedule.intruderDisabled=1;
            else {addBonus(human.stageIndex,bonus);++human.stageIndex;}
            if(substituteKuroko())schedule.substitutionDisabled=1;
            if(game.submode==5)unsupported("network arcade");
            if(human.stageIndex>=8)go(ArcadeScene::Ending);
            else if(!postFightDialogue()||intruderFight!=0)go(ArcadeScene::WinQuote);
            else {dialoguePostFight=1;go(ArcadeScene::Dialogue);}
        } else {
            clearStartHold();
            if(game.winner==-1)game.winner=mode==1; // a draw counts as a CPU win
            if(game.submode==5)unsupported("network arcade");
            go(system_.option(0)!=0?ArcadeScene::GameOver:ArcadeScene::Continue);
        }
    } else if(mode==0xb||mode==0xc) {
        unsupported("survival match end");
    } else game.wordA4=0;
}

void ArcadeRun::winQuoteExit(uint32_t held) {
    const unsigned seat=game.mode!=1;
    if(game.versusInterrupted==0) {
        if(players[seat].progress==0)request(1,1,quoteDestructor,ArcadeScene::Opening);
        else if(intruderDue()) {game.transitionLock=1;request(4,1,quoteDestructor,ArcadeScene::Map);}
        else request(1,1,quoteDestructor,ArcadeScene::Map);
    } else if(intruderDue()) {
        // 17a2c8(character, 0): the opponents are redrawn but rolls and flags are kept.
        if(players[seat].randomSelect==1)buildSchedule(players[seat].character,false,held);
        game.transitionLock=1;request(4,1,quoteDestructor,ArcadeScene::Map);
    } else request(1,1,quoteDestructor,ArcadeScene::VersusResult);
}

void ArcadeRun::versusResultExit(uint32_t held) {
    const auto& winner=players.at(game.winner);
    if(winner.progress==0)request(1,1,resultDestructor,ArcadeScene::Opening);
    else if(winner.stageIndex==7&&winner.preFinalSeen==0)request(1,1,resultDestructor,ArcadeScene::PreFinal);
    else if(winner.stageIndex==7) {prepareFight();request(1,1,resultDestructor,ArcadeScene::Battle);}
    else {
        if(game.scheduleValid==0) {buildSchedule(winner.character,true,held);prepareFight();}
        request(1,1,resultDestructor,ArcadeScene::Map);
    }
}

bool ArcadeRun::pollChallenger(std::array<uint32_t,2> pressed,uint32_t currentDestructor) {
    if(game.transitionLock||game.challengerInhibit||game.submode!=1||(game.mode!=1&&game.mode!=2))return false;
    const unsigned challenger=game.mode==1;
    if(!(pressed[challenger]&8))return false;
    game.transitionLock=1;game.selectingSeat=int32_t(challenger);
    players[challenger]={};
    players[0].roundWins=players[1].roundWins=system_.option(8); // 1116d8
    game.versusInterrupted=1;game.challengerFreeze=1;
    request(4,0,currentDestructor,ArcadeScene::CharacterSelect);
    return true;
}
void ArcadeRun::idleRandom() {if(uint32_t(random_.mode)<2)random_.nextLibrary();}

void ArcadeRun::reselectRandom(unsigned seat,std::span<const int32_t> pool) {
    auto& p=players.at(seat);
    if(p.randomSelect!=1)return;
    const int32_t r=int32_t(random_.nextLibrary()&0x7fff);
    game.scheduleValid=0;
    p.character=pool[size_t((r*int32_t(pool.size()))>>15)];
}
void ArcadeRun::transitionMidpoint(std::span<const int32_t> pool) {
    game.challengerFreeze=0;
    if(transition.kind!=4||transition.speed!=0)return;
    game.mode=3;
    if(game.submode==5)game.submode=6;
    resetPlayer(unsigned(game.selectingSeat));
    reselectRandom(unsigned(game.selectingSeat^1),pool);
}

void ArcadeRun::recordVersus() {
    auto bump=[](int32_t& counter) {if(++counter>=1000)counter=999;};
    if(game.submode==2) {
        if(game.winner==-1) {
            for(auto& seat:versusCounters)bump(seat[1]);
            game.selectingSeat=game.drawSeat;
        } else {
            bump(versusCounters.at(game.winner)[0]);bump(versusCounters[game.winner^1][1]);
            game.selectingSeat=game.winner^1;
        }
    }
    const int winner=game.winner;
    if(winner==-1) {
        recordStreak(game.selectingSeat^1);
        game.previousWinner=-1;game.versusStreak=0;
        clearStartHold();
        return;
    }
    if(game.previousWinner!=winner) {
        recordStreak(winner^1);
        game.previousWinner=winner;game.versusStreak=1;
        game.defeated[0]=players.at(winner^1).character;
    } else {
        game.defeated.at(game.versusStreak%20)=players.at(winner^1).character;
        ++game.versusStreak;
    }
    if(game.submode!=2) {
        // The winner's seat becomes the arcade seat and the loser's record is reset.
        game.mode=winner==0?1:2;
        resetPlayer(winner==0);
    }
}
bool ArcadeRun::versusLimitReached() const {
    const unsigned setting=system_.option(1);
    return setting!=0&&game.versusStreak>=tables_.versusLimits.at(setting-1);
}
void ArcadeRun::recordStreak(int seat) {
    // 1c4e50 over the five 8-byte rows at 43d0f0: strict <, so ties stay above.
    const auto image=system_.image();
    auto value=[&](unsigned row) {return uint32_t(system_.word(streakTable+8*row));};
    const uint32_t streak=uint32_t(game.versusStreak);
    if(!(value(4)<streak))return;
    const auto& p=players.at(seat);
    std::array<uint8_t,8> entry{};
    std::memcpy(entry.data(),&streak,4);entry[4]=uint8_t(p.character);entry[5]=uint8_t(p.spirit);
    for(int row=4;row>=0&&value(row)<streak;--row) {
        if(row<4)std::memcpy(&image[streakTable+8*(row+1)],&image[streakTable+8*row],8);
        std::memcpy(&image[streakTable+8*row],entry.data(),8);
    }
}
bool ArcadeRun::scoreQualifies() const {return uint32_t(system_.word(scoreTable+12*19))<uint32_t(game.score);}
int ArcadeRun::recordScore(unsigned seat,const char* name) {
    // 1c4ff8 over the twenty 12-byte rows at 43d118 {score, character, name[4], spirit}.
    const auto image=system_.image();
    auto value=[&](unsigned row) {return uint32_t(system_.word(scoreTable+12*row));};
    const uint32_t score=uint32_t(game.score);
    const auto& p=players.at(seat);
    std::array<uint8_t,12> entry{};
    std::memcpy(entry.data(),&score,4);entry[4]=uint8_t(p.character);
    std::strncpy(reinterpret_cast<char*>(&entry[5]),name,3);entry[9]=uint8_t(p.spirit);
    int placed=-1;
    for(int row=19;row>=0&&value(row)<score;--row) {
        if(row<19)std::memcpy(&image[scoreTable+12*(row+1)],&image[scoreTable+12*row],12);
        std::memcpy(&image[scoreTable+12*row],entry.data(),12);
        placed=row;
    }
    if(placed>=0)rankingHighlight=placed;
    return placed;
}

void ArcadeCountdown::tick() {
    if(delay) {--delay;return;}
    if(!paused)++count;
    if(!(count<limit))count=limit;
}

void ArcadeContinue::enter(ArcadeRun& run,ArcadeCountdown& countdown) {
    frame=accepted=latch=0;fadeRequested=false;draw={};
    const auto& g=run.game;
    const int seat=g.mode==1?0:g.mode==2?1:g.mode==3?g.selectingSeat^1:-1;
    if(seat>=0)draw.loserSeat=seat,draw.loserCharacter=run.players.at(seat).character,draw.loserColour=run.players[seat].colour;
    run.resetScore();
    run.players[1].randomSelect=0;run.game.scheduleValid=0;run.players[0].randomSelect=0;
    countdown.start();countdown.limit=0x4eb;
    entryMode=g.mode;
    run.game.challengerInhibit=1;
}
int ArcadeContinue::tick(ArcadeRun& run,ArcadeCountdown& countdown,std::array<uint32_t,2> pressed) {
    auto& g=run.game;
    const uint32_t remaining=countdown.remaining();
    const unsigned seat=g.mode==2;
    fadeRequested=false;
    if(latch==0&&remaining!=0&&remaining<0x4ce) {
        if(pressed[seat]&8) {
            // 137cb8 copies the run position to the other record too, so the
            // stage index, progress and pre-final flag survive the reselect.
            const int loser=g.mode==1?0:g.mode==2?1:g.mode==3?g.selectingSeat^1:-1;
            if(loser>=0) {
                auto& p=run.players.at(loser);auto& o=run.players[loser^1];
                p.spirit=p.versusSpirit=5;p.previousCharacter=p.character;p.colour=0;
                o.previousCharacter=p.character;o.stageIndex=p.stageIndex;o.progress=p.progress;
                o.preFinalSeen=p.preFinalSeen;o.spirit=o.versusSpirit=5;o.colour=0;
            }
            g.mode=int32_t(seat)+1; // a mode-3 entry always resumes as seat 0
            run.applyRoundWins();
            run.players[1].selected=0;run.players[0].selected=0;
            fadeRequested=true;
            countdown.paused=1;
            latch=1;accepted=1;
            g.previousWinner=-1;g.defeated.fill(0);g.versusStreak=0;
            run.request(3,0,continueDestructor,ArcadeScene::CharacterSelect);
        } else if((pressed[seat]&0x607)&&g.mode>=1&&g.mode<=3&&remaining<0x3fc) {
            countdown.advance(remaining%60+1); // skip to the next second
        }
    }
    // 137db8 re-reads the counter after the input above.
    const uint32_t shown=countdown.remaining();
    draw.frame=frame;draw.remaining=shown;
    draw.seconds=int32_t(shown/60);draw.phase=int32_t(shown%60);
    draw.tens=int32_t(shown/600);draw.ones=draw.seconds%10;
    draw.twoDigits=draw.seconds>=10;draw.animated=draw.phase<0x15;
    int sound=-1;
    if(shown!=0&&draw.phase==0x3b) {
        const int who=g.mode==1?0:g.mode==2?1:g.mode==3?g.selectingSeat^1:-1;
        if(who>=0&&run.players.at(who).selected!=0)sound=0xf;
    }
    ++frame;
    if(latch==0&&remaining==0) {latch=1;run.request(1,1,continueDestructor,ArcadeScene::GameOver);}
    return sound;
}

void ArcadeGameOver::enter(ArcadeRun& run) {
    frame=0;fadeRequested=voiceRequested=soundStopped=autosave=false;draw={};
    auto& g=run.game;
    if(g.levelEnding==0) {
        draw.stageBackground=run.system().option(0)!=0||run.system().option(2)!=0||g.mode==3;
        const int seat=g.mode==1?0:g.mode==2?1:g.mode==3?g.selectingSeat^1:-1;
        if(seat>=0) {
            draw.loserSeat=seat;draw.loserCharacter=run.players.at(seat).character;
            // The streak holder is the winner at the limit, otherwise the surviving seat.
            run.recordStreak(run.versusLimitReached()?g.winner:g.mode==3?g.selectingSeat^1:g.winner^1);
        }
    } else {
        if(g.submode==4)unsupported("survival Game Over records");
        run.recordStreak(g.winner);
    }
    g.challengerInhibit=1;
}
ArcadeScene ArcadeGameOver::tick(ArcadeRun& run,uint32_t pressed,bool unlockPending) {
    auto& g=run.game;
    if(g.levelEnding!=0&&g.submode==4)unsupported("survival Game Over");
    fadeRequested=voiceRequested=soundStopped=autosave=false;
    if(uint32_t(frame-0x1e)<0xfa&&(pressed&4)) {
        soundStopped=true; // 1e7b40
        if(frame<0xc8)fadeRequested=true;
        frame=0x118;
    }
    draw.frame=frame;draw.textVisible=frame>=0x88;
    if(frame==0x1e)voiceRequested=true;  // 1e7d60(31,4b)
    if(frame==0x50)fadeRequested=true;   // 138e18: 1170d8(-1); 117170(1)
    if(++frame!=0x12c)return ArcadeScene::None;
    if(unlockPending) {leave(run,true);return ArcadeScene::UnlockNotice;}
    autosave=true; // 10f158
    run.request(1,1,gameOverDestructor,ArcadeScene::Ranking);
    return ArcadeScene::Ranking;
}
void ArcadeGameOver::leave(ArcadeRun& run,bool unlockPending) {
    run.resetPlayer(0);run.resetPlayer(1);
    if(!unlockPending)run.game.clear();
    run.game.transitionLock=1;run.game.challengerInhibit=0;
}

bool ArcadeNameEntry::begin(const ArcadeRun& run) {
    if(!run.scoreQualifies())return false;
    *this={};
    active=true;
    return true;
}
void ArcadeNameEntry::previous() {
    if(cursor==2&&name[2]!=0)glyph=glyph==0x2c?0x2b:0x2c; // a full name offers only "<-" and "END"
    else if(--glyph<0)glyph=0x2c;
    blinkOn=1;blinkCounter=0x1e;
}
void ArcadeNameEntry::next() {
    if(cursor==2&&name[2]!=0)glyph=glyph==0x2b?0x2c:0x2b;
    else if(++glyph>=0x2d)glyph=0;
    blinkOn=1;blinkCounter=0x1e;
}
void ArcadeNameEntry::finish() {cursor=2;glyph=0x2c;blinkOn=0;finished=1;blinkCounter=0;}
void ArcadeNameEntry::useDefault(const ArcadeRun& run) {
    const auto& fallback=run.tables().names.at(run.players[run.game.mode!=1].character);
    std::strncpy(name.data(),fallback.data(),4);name[3]=0;
}
void ArcadeNameEntry::input(const ArcadeRun& run,uint32_t pressed) {
    const auto& glyphs=run.tables().glyphs;
    if(pressed&0x40)previous();
    if(pressed&0x80)next();
    erase=0;
    if(pressed&6) {
        const auto& text=glyphs.at(glyph);
        if(same(text,"END"))finish();
        else if(same(text,"<-"))erase=1;
        else if(cursor<2) {name[cursor]=text[0];name[cursor+1]=0;++cursor;}
        else if(cursor==2) {name[2]=text[0];name[3]=0;glyph=0x2c;}
    }
    if((pressed&0x600)||erase==1) {
        if(cursor==2&&name[2]!=0)name[2]=0;
        else if(cursor!=0)name[--cursor]=0;
    }
    if(pressed&8)finish();
    if(finished==1&&filtered==0) {
        // 110bf8: an exact match with the filter list selects the fallback name
        // (its length test cannot fire for three letters); so does an empty name.
        const auto& t=run.tables();
        for(unsigned i=0;i<t.filteredCount;++i)
            if(std::strncmp(name.data(),t.filtered[i].data(),4)==0) {useDefault(run);break;}
        if(name[0]==0)useDefault(run);
        filtered=1;
    }
}
bool ArcadeNameEntry::tick(ArcadeRun& run,uint32_t pressed) {
    bool committed=false;
    if(finished==0) {
        // 1ca248: thirty seconds; expiry finishes without moving the cursor.
        if(seconds>=0&&++secondFrame==0x3c) {
            secondFrame=0;
            if(--seconds==-1)finished=1;
        }
        input(run,pressed);
    }
    if(finished==1&&++commitFrames>=0xb4) {
        run.recordScore(run.game.mode!=1,name.data());
        active=false;committed=true;
    }
    // 1c9d20, evaluated by the draw routine 1c9ec8 on every visit.
    if(blinkOn==0) {if(++blinkCounter>=0x1e)blinkOn=1;}
    else if(--blinkCounter==0)blinkOn=0;
    blinkShown=blinkOn;
    return committed;
}
}
