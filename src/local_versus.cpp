#include <cstdlib>
#include <cstdio>
#include "local_versus.hpp"
#include "fighter_roster.hpp"
#include "arcade_presentation.hpp"
#include "console_versus_session.hpp"
#include <istream>
#include <utility>
#include <stdexcept>

namespace ss6 {
std::array<bool,2> versusCpuSeats(std::string_view name) {
    if(name=="p1")return {true,false};
    if(name=="p2")return {false,true};
    if(name=="both")return {true,true};
    throw std::invalid_argument("--cpu expects p1, p2 or both");
}
unsigned versusSpirit(std::string_view name) {
    if(name=="rage")return 0;
    if(name=="shin")return 1;
    if(name=="zan")return 2;
    if(name=="ten")return 3;
    if(name=="zero")return 4;
    if(name=="ken")return 5;
    throw std::invalid_argument("Expected a versus spirit of rage, shin, zan, ten, zero or ken");
}
bool readVersusReplaySegment(std::istream& input,unsigned& ticks,std::array<uint32_t,2>& held) {
    input>>std::ws;
    if(input.bad())throw std::runtime_error("Cannot read match replay");
    if(input.eof())return false;
    // A final malformed number also sets eofbit. Only accept EOF before
    // starting a record, so a failed parse cannot publish a partial WAV.
    if(!(input>>ticks>>held[0]>>held[1]) || ticks>1000000)
        throw std::runtime_error("Invalid match replay");
    return true;
}

LocalVersus::LocalVersus(const std::filesystem::path& assets,int roundTime,VersusMode mode,std::array<unsigned,2> spirits,bool startAtSelect)
    :LocalVersus(assets,roundTime,mode,spirits,startAtSelect?VersusEntry::CharacterSelect:VersusEntry::Fight) {}

LocalVersus::LocalVersus(const std::filesystem::path& assets,int roundTime,VersusMode mode,
                         std::array<unsigned,2> spirits,VersusEntry entry,std::array<bool,2> cpuSeats)
    :assets_(assets),roundTime_(roundTime),mode_(mode),spirits_(spirits),entry_(entry),cpuSeats_(cpuSeats),
     system_(std::make_shared<SystemData>(assets)) {
    // SS6_SUBSTITUTE="seat:character[,seat:character]" (debug harnesses, see substituteCharacter).
    if(const char* s=std::getenv("SS6_SUBSTITUTE")) {
        unsigned seat=0,character=0;int used=0;
        while(std::sscanf(s,"%u:%u%n",&seat,&character,&used)==2) {
            substituteCharacter(seat,character);s+=used;if(*s!=',')break;++s;
        }
    }
    restart();
}

void LocalVersus::configureControllers(NativeMatch& match) const {
    for(unsigned seat=0;seat<2;++seat)if(cpuSeats_[seat])match.enableCpu(seat);
}

MatchRules LocalVersus::versusRules() const {
    // 1116d8 copies VS MATCH POINT to both seats; 13f9f0 reads GAME TIME.
    const auto& data=match_->system();
    MatchRules rules;
    rules.requiredWins={data.versusMatchPoint(),data.versusMatchPoint()};
    rules.gameTime=data.gameTime();rules.damagePercent=data.damageLevel();rules.gameLevel=data.gameLevel();
    return rules;
}
namespace {
// Menu tasks read the software controller's physical word (see resultPad).
uint32_t physicalPad(uint32_t logical) {
    constexpr std::array<uint32_t,8> physical{0x400,0x200,2,4,0x400000,0x800000,0x100000,0x200000};
    uint32_t bits=logical&0xf8;
    for(unsigned i=0;i<physical.size();++i)if(logical&(PadLight<<i))bits|=physical[i];
    return bits;
}
}
void LocalVersus::startArcade(unsigned seat,int character,int colour,int spirit) {
    arcade_=std::make_unique<ArcadeSession>(assets_,match_->system());
    arcade_->random=match_->battle().random;
    arcade_->start(seat);
    arcade_->selectRequested=false; // the mode menu's select has already run
    arcade_->selected(character,colour,spirit,0);
    arcadeSceneFlow();
}
void LocalVersus::startArcadeFight() {
    auto& run=arcade_->run;
    const auto setup=arcade_->enterBattle();
    const auto& data=match_->system();
    MatchRules rules;
    rules.gameMode=run.game.mode;rules.submode=1;rules.battleKind=0;
    rules.requiredWins={setup.roundWins[0],setup.roundWins[1]};
    rules.gameTime=data.gameTime();rules.damagePercent=data.damageLevel();rules.gameLevel=data.gameLevel();
    for(unsigned i=0;i<2;++i)if(setup.control[i]==1)rules.cpuLevel[i]=setup.stageIndex;
    arcadeNotice_.clear();
    rules.stage=setup.stage;
    if(!CombatStageState::supports(unsigned(setup.stage))) {
        // The arena is not ported yet; the fight is held on arena 0 instead.
        arcadeNotice_="STAGE "+std::to_string(setup.stage)+" IS IN DEVELOPMENT";
        rules.stage=0;
    }
    rules.score=run.game.score;rules.random=arcade_->random;
    VersusLineup lineup;
    for(unsigned i=0;i<2;++i)lineup[i]={unsigned(setup.character[i]),unsigned(setup.spirit[i]),unsigned(setup.colour[i])};
    try {
        auto next=std::make_unique<NativeMatch>(assets_,-1,VersusMode::Console,match_.get(),std::array<unsigned,2>{},
                                                lineup,rules.stage,std::array<CpuSeatDecision,2>{},&rules);
        match_=std::move(next);
        ++matchNumber_;
    } catch(const std::exception& error) {
        // A scheduled opponent or spirit without a native port ends the run.
        arcadeNotice_=std::string("ARCADE OPPONENT ")+std::to_string(setup.character[run.humanSeat()^1])+" IS IN DEVELOPMENT";
        // Validation fixture: a forced result stands in for the fight that cannot be built.
        if(forced_){fightMissing_=true;return;}
        arcade_->scene=ArcadeScene::None;arcade_->leftToTitle=true;
    }
}
void LocalVersus::tickArcade(const std::array<NormalizedPadSample,2>& pads) {
    auto& run=arcade_->run;
    if(arcadeSelecting_) {
        match_->tick(pads);
        if(observer_)observer_(*match_);
        // The shutter of the challenger banner (kind 4, state 3) opens over the new select.
        if(arcade_->transitionActive())arcade_->tickTransition();
        if(run.game.mode==3) {
            // The challenger's two-seat select (mode 3) ends with the face-off 125e10.
            if(!match_->faceoff()||!match_->faceoff()->complete)return;
            arcadeSelecting_=false;
            arcade_->random=match_->battle().random;
            const auto picks=match_->selectedLineup();
            for(unsigned i=0;i<2;++i) {
                auto& p=run.players[i];
                p.character=int(picks[i].character);p.colour=int(picks[i].palette&0xffff);p.versusSpirit=int(picks[i].spirit);
            }
            arcade_->versusSelected();
            arcadeSceneFlow();
            return;
        }
        const auto pick=match_->soloSelection();
        if(!pick)return;
        arcadeSelecting_=false;
        arcade_->random=match_->battle().random;
        arcade_->selected(pick->character,pick->colour&0xffff,pick->spirit,physicalPad(pads[run.humanSeat()].held));
        arcadeSceneFlow();
        return;
    }
    const std::array<uint32_t,2> pressed{physicalPad(pads[0].pressed),physicalPad(pads[1].pressed)};
    const uint32_t held=physicalPad(pads[run.humanSeat()].held);
    if(arcade_->scene==ArcadeScene::Battle) {
        if(arcade_->battleOver) {
            // 1252f0(2, 0, 139778, next): the last fight frame stays while the screen fades out.
            arcade_->tickTransition();
            deliverSceneSounds();
        } else if(forced_) {
            forced_=false;
            if(!std::exchange(fightMissing_,false))arcade_->random=match_->battle().random;
            arcade_->matchEnded(forcedWinner_,run.game.stage,0,0,held);
        } else {
            try {match_->tick(pads);}
            catch(const UnportedFighterState& move) {
                arcadeNotice_="MOVE "+std::to_string(move.table)+"/"+std::to_string(move.state)+" IS IN DEVELOPMENT";
                arcade_->scene=ArcadeScene::None;arcade_->leftToTitle=true;
            }
            if(arcade_->scene==ArcadeScene::Battle) {
                if(observer_)observer_(*match_);
                // The fade-in of the scene switch that started this fight.
                if(arcade_->transitionActive())arcade_->tickTransition();
                const auto& b=match_->battle();
                if(b.modeMatchEnded) {
                    const unsigned human=run.humanSeat();
                    // 143d6c and 145118 update the schedule record during the fight.
                    for(int i=0;i<b.arcadeQualifyingWins;++i)run.addRoundWin(run.players[human].stageIndex,1);
                    if(b.match.players[human^1].wins>0)run.disableSpecialOpponents();
                    run.game.score=match_->arcadeScore();
                    arcade_->random=b.random;
                    arcade_->matchEnded(b.matchEnd.winner08,int(b.matchEnd.metadataStage04),b.matchEnd.result8c,b.endingParameter2c,held);
                }
            }
        }
    } else if(arcade_->scene!=ArcadeScene::None) {
        arcade_->tickScene(pressed,held);
        deliverSceneSounds();
        // 10f158 writes the card only while AUTO SAVE is on.
        if(arcade_->autosave&&match_->system().autoSave())match_->system().saveFile();
    }
    if(arcadeSceneFlow())return;
    if(arcade_ && (arcade_->leftToTitle||arcade_->scene==ArcadeScene::None)) {
        // The ranking scene leads back to the title (127940).
        const auto system=match_->systemHandle();
        if(arcade_->presentation)arcadeLog_.insert(arcadeLog_.end(),arcade_->presentation->log.begin(),arcade_->presentation->log.end());
        arcade_.reset();
        // 124d50 after a survival run: the mode word, the sub-mode and the battle kind
        // of the last fight must not reach the title's battle block.
        MatchRules rules;
        const bool survival=std::exchange(survivalOver_,false);
        auto title=std::make_unique<NativeMatch>(assets_,roundTime_,mode_,match_.get(),spirits_,std::nullopt,0,
                                                 std::array<CpuSeatDecision,2>{},survival?&rules:nullptr);
        title->openTitle(false);
        match_=std::move(title);
    }
}
void LocalVersus::startSurvival(unsigned seat,int character,int colour,int spirit) {
    // 139660 for mode word b/c: 180510 (first candidates), 17ac98, 1398c0, 13f9f0(1).
    survival_=std::make_shared<SurvivalSession>(assets_);
    auto& s=*survival_;
    s.modeWord=0xb+int(seat);
    s.run.table=survivalTable_;
    auto& human=s.config[seat];
    human.character=character;human.colour=colour;human.spiritChosen=human.spirit=spirit;
    s.config[0].roundsToWin=s.config[1].roundsToWin=1; // 111710
    GameRandom random=match_->battle().random;
    s.pauseRequested=s.run.begin(random,s.modeWord,character).pauseRequests!=0; // 180510 calls 1392e8
    // 1398c0 reads the candidate copy T+0x104 before any row is confirmed: the
    // scene starts with a hidden placeholder fight built from the previous
    // run's last candidate (all zero after boot) and draws its RNG(6).
    survivalApplyCandidate(s.run.table,random,s.modeWord,s.config,s.setup,false);
    survivalReload_=0;
    if(!startSurvivalFight(random,false))endSurvival();
}
bool LocalVersus::startSurvivalFight(const GameRandom& random,bool confirmed) {
    auto& s=*survival_;
    const unsigned h=unsigned(s.humanSeat()),c=1-h;
    const auto& data=match_->system();
    MatchRules rules;
    rules.gameMode=s.modeWord;rules.submode=4;rules.battleKind=2;rules.requiredWins={1,1};
    rules.gameTime=data.gameTime();rules.damagePercent=data.damageLevel();rules.gameLevel=data.gameLevel();
    rules.cpuLevel[c]=s.setup.level;
    rules.stage=s.setup.stage;rules.random=random;rules.survival=survival_;
    if(confirmed)s.notice.clear();
    std::string notice;
    if(!CombatStageState::supports(unsigned(rules.stage))) {
        // The arena is not ported yet; the fight is held on arena 0 instead.
        notice="STAGE "+std::to_string(rules.stage)+" IS IN DEVELOPMENT";
        rules.stage=0;
    }
    VersusLineup lineup;
    for(unsigned i=0;i<2;++i) {
        lineup[i]={unsigned(s.setup.character[i]),unsigned(s.setup.spirit[i]),unsigned(s.setup.colour[i])};
        if(lineup[i].spirit>5&&lineup[i].spirit!=8) {
            // Spirits 6 and 7 have no native port; the fight runs with spirit 0.
            notice+=(notice.empty()?"":" / ")+std::string(i==h?"YOUR":"OPPONENT")+" SPIRIT "+std::to_string(lineup[i].spirit)+" IS IN DEVELOPMENT (SPIRIT 0 USED)";
            lineup[i].spirit=0;
        }
        if(!playableFighter(logicCharacter(lineup[i].character))) {
            if(confirmed) {
                s.notice=std::string(i==h?"FIGHTER ":"OPPONENT ")+std::to_string(lineup[i].character)+" IS IN DEVELOPMENT: THE RUN ENDS HERE";
                return false;
            }
            lineup[i].character=0; // the placeholder fight is never played
        }
    }
    try {
        auto next=std::make_unique<NativeMatch>(assets_,-1,VersusMode::Console,match_.get(),std::array<unsigned,2>{},
                                                lineup,rules.stage,std::array<CpuSeatDecision,2>{},&rules);
        match_=std::move(next);
        if(confirmed){s.notice=notice;++matchNumber_;}
        return true;
    } catch(const std::exception& error) {
        s.notice=std::string("SURVIVAL FIGHT IS IN DEVELOPMENT: ")+error.what();
        return false;
    }
}
void LocalVersus::endSurvival() {
    // 145628 -> 1252f0(2,0,139778,138340). The mode word is 1/2 from here on
    // and Task_GameOver stores the record (1384f8) before its common part.
    auto& s=*survival_;
    survivalTable_=s.run.table;
    const int word=s.modeWord==0xb?1:2;
    for(auto& seat:s.config)seat.arcadeProgress=0;
    arcadeNotice_=s.notice;
    arcade_=std::make_unique<ArcadeSession>(assets_,match_->system());
    arcade_->random=match_->battle().random;
    auto& run=arcade_->run;
    run.game.clear();
    for(unsigned i=0;i<2;++i) {
        run.resetPlayer(i);
        run.players[i].character=s.config[i].character;run.players[i].colour=s.config[i].colour;run.players[i].spirit=s.config[i].spirit;
    }
    run.game.mode=word;run.game.submode=4;run.game.stage=s.setup.stage;
    run.game.winner=match_->battle().matchEnd.winner08;
    // The winner display of a cleared run (138400, g+0x34 with sub-mode 4) is
    // not ported: the scene runs its ordinary GAME OVER part.
    run.game.levelEnding=0;
    survivalStoreRecord(match_->system(),word,s.config,s.run.winCount(),s.run.playSeconds());
    // The survival Game Over keeps its own path to the title (138340 is shared, the
    // arcade presentation scenes are not entered from here).
    arcade_->presentation.reset();
    arcade_->scene=ArcadeScene::GameOver;arcade_->gameOver.enter(run);
    survival_.reset();survivalReload_=0;
    survivalOver_=true;
}
void LocalVersus::tickSurvival(const std::array<NormalizedPadSample,2>& pads) {
    auto& s=*survival_;
    // 138f48 after 13a6c0: the next frame reloads the arena (123a0d0), the one
    // after it runs 13f9f0(1) (123a0cc) before its own battle-update decision.
    if(survivalReload_==1)survivalReload_=2;
    else if(survivalReload_==2) {
        survivalReload_=0;
        if(!startSurvivalFight(match_->battle().random,true)){endSurvival();return;}
    }
    try {match_->tick(pads);}
    catch(const UnportedFighterState& move) {
        s.notice="MOVE "+std::to_string(move.table)+"/"+std::to_string(move.state)+" IS IN DEVELOPMENT: THE RUN ENDS HERE";
        s.ended=true;
    }
    if(observer_)observer_(*match_);
    if(s.ended){endSurvival();return;}
    if(s.reload) {
        s.reload=false;survivalReload_=1;
        match_->survivalReleaseStage();
    }
}
bool LocalVersus::tickPracticeSession() {
    const int mode=match_->battle().gameMode;
    if(!practice_) {
        if(!match_->characterSelect()||(mode!=9&&mode!=10))return false;
        // 1cd428: 139280(1) and 210368 (settings defaults) at the mode-menu confirm.
        practice_=std::make_shared<PracticeState>();
        practice_->settings.reset();
        practice_->battleType=1;practice_->mode=mode;
        practiceRow_=match_->menuRow();
        return false;
    }
    if(const int exit=match_->practiceExit()) {
        // 180110: 1252f0(2,0,139778,128008 or 127940). Both leave the battle kind byte as it is;
        // the settings survive CHARACTER SELECT and end with the next mode-menu confirm.
        MatchRules rules;
        rules.gameMode=practice_->mode;rules.submode=3;rules.battleKind=0;
        const auto random=match_->battle().random;
        if(exit==1) {
            auto select=std::make_unique<NativeMatch>(assets_,roundTime_,mode_,match_.get(),spirits_,std::nullopt,0,
                                                      std::array<CpuSeatDecision,2>{},&rules);
            practice_->recording=false; // 139378(0)
            select->reopenPracticeSelect(random);
            match_=std::move(select);
        } else {
            rules.gameMode=3;rules.submode=2;
            auto title=std::make_unique<NativeMatch>(assets_,roundTime_,mode_,match_.get(),spirits_,std::nullopt,0,
                                                     std::array<CpuSeatDecision,2>{},&rules);
            title->openModeMenu(practiceRow_);
            match_=std::move(title);
            practice_.reset();
        }
        return true;
    }
    if(match_->faceoff()&&match_->faceoff()->complete) {
        // 1398c0 mode 9/10 and 13f9f0: one required win, no clock, the dummy seat is CPU kind 1.
        const auto& data=match_->system();
        MatchRules rules;
        rules.gameMode=practice_->mode;rules.submode=3;rules.battleKind=1;rules.requiredWins={1,1};
        rules.gameTime=data.gameTime();rules.damagePercent=data.damageLevel();rules.gameLevel=data.gameLevel();
        rules.practice=practice_;
        auto next=std::make_unique<NativeMatch>(assets_,-1,mode_,match_.get(),std::array<unsigned,2>{},
                                                match_->selectedLineup(),match_->characterSelect()->stage,
                                                std::array<CpuSeatDecision,2>{},&rules);
        ++matchNumber_;
        match_=std::move(next);
        return true;
    }
    return false;
}
std::vector<ArcadeSceneEntry> LocalVersus::arcadeLog() const {
    auto log=arcadeLog_;
    if(arcade_&&arcade_->presentation)log.insert(log.end(),arcade_->presentation->log.begin(),arcade_->presentation->log.end());
    return log;
}
bool LocalVersus::arcadeSceneFlow() {
    if(!arcade_)return false;
    auto& run=arcade_->run;
    if(arcade_->selectRequested) {
        arcade_->selectRequested=false;
        auto select=std::make_unique<NativeMatch>(assets_,roundTime_,mode_,match_.get(),spirits_);
        if(run.game.mode==3) {
            // 1253e0 switched the run to mode 3: both seats select (12eee8), then the face-off.
            select->openChallengerSelect();
        } else select->openSoloSelect(run.humanSeat()); // CONTINUE returns to 128008
        match_=std::move(select);
        arcadeSelecting_=true;
        return true;
    }
    if(arcade_->fightRequested) {
        arcade_->fightRequested=false;
        startArcadeFight();
    }
    return false;
}
void LocalVersus::deliverSceneSounds() {
    if(!arcade_||!arcade_->presentation)return;
    if(sceneSounds_)sceneSounds_(arcade_->presentation->sounds);
}
void LocalVersus::restart() {
    practice_.reset();practiceRow_=-1;
    survival_.reset();survivalReload_=0;survivalOver_=false;
    arcade_.reset();arcadeNotice_.clear();arcadeSelecting_=false;
    match_=std::make_unique<NativeMatch>(assets_,roundTime_,mode_,nullptr,spirits_,std::nullopt,stage_?pinnedStageBase+stage_:0);
    match_->adoptSystem(system_);
    if(entry_==VersusEntry::Arcade){startArcade(0,0,0,int(spirits_[0]));matchNumber_=1;return;}
    if(entry_==VersusEntry::Fight){configureControllers(*match_);if(items_)match_->setStageItems(true);}
    if(entry_==VersusEntry::CharacterSelect)match_->openCharacterSelect(true);
    if(entry_==VersusEntry::Title)match_->openTitle(false);
    matchNumber_=1;
}
void LocalVersus::tick(const std::array<NormalizedPadSample,2>& pads) {
    if(arcade_){tickArcade(pads);return;}
    if(survival_){tickSurvival(pads);return;}
    if(const auto pick=match_->soloSelection()) {
        const int word=match_->battle().gameMode;
        if(word==0xb||word==0xc)startSurvival(pick->seat,pick->character,pick->colour&0xffff,pick->spirit);
        else startArcade(pick->seat,pick->character,pick->colour&0xffff,pick->spirit);
        return;
    }
    try {match_->tick(pads);}
    catch(const UnportedFighterState& move) {
        if(mode_!=VersusMode::Console)throw;
        match_->leaveUnportedFight(move);
    }
    // Deliver the old match's last sound requests before its state is replaced.
    if(observer_)observer_(*match_);
    if(tickPracticeSession())return;
    if(match_->faceoff()&&match_->faceoff()->complete) {
        const auto rules=versusRules();
        auto lineup=match_->selectedLineup();
        for(unsigned seat=0;seat<2;++seat)if(substitute_[seat]>=0)lineup[seat].character=unsigned(substitute_[seat]);
        auto next=std::make_unique<NativeMatch>(assets_,-1,mode_,match_.get(),std::array<unsigned,2>{},
                                                lineup,match_->characterSelect()->stage,
                                                std::array<CpuSeatDecision,2>{},&rules);
        configureControllers(*next);
        if(entry_==VersusEntry::Fight || match_->updates!=0)++matchNumber_;
        match_=std::move(next);
        return;
    }
    if(mode_==VersusMode::Console && !match_->characterSelect() &&
       match_->battle().consoleMenu.destination==ConsoleVersusDestination::Rematch) {
        // The fade task creates the new fight after the old fight's update.
        // Its opening first receives a controller sample on the following tick.
        auto next=std::make_unique<NativeMatch>(assets_,-1,mode_,match_.get());
        configureControllers(*next);
        match_=std::move(next);
        ++matchNumber_;
    }
}
}
