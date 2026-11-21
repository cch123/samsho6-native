#include "local_versus.hpp"
#include <istream>
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
    :assets_(assets),roundTime_(roundTime),mode_(mode),spirits_(spirits),entry_(entry),cpuSeats_(cpuSeats) {restart();}

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
    arcade_->selected(character,colour,spirit,0);
    if(arcade_->scene==ArcadeScene::Battle)startArcadeFight();
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
        arcade_->scene=ArcadeScene::None;arcade_->leftToTitle=true;
    }
}
void LocalVersus::tickArcade(const std::array<NormalizedPadSample,2>& pads) {
    auto& run=arcade_->run;
    const std::array<uint32_t,2> pressed{physicalPad(pads[0].pressed),physicalPad(pads[1].pressed)};
    const uint32_t held=physicalPad(pads[run.humanSeat()].held);
    switch(arcade_->scene) {
    case ArcadeScene::Battle: {
        try {match_->tick(pads);}
        catch(const UnportedFighterState& move) {
            arcadeNotice_="MOVE "+std::to_string(move.table)+"/"+std::to_string(move.state)+" IS IN DEVELOPMENT";
            arcade_->scene=ArcadeScene::None;arcade_->leftToTitle=true;break;
        }
        if(observer_)observer_(*match_);
        const auto& b=match_->battle();
        if(!b.modeMatchEnded)return;
        const unsigned human=run.humanSeat();
        // 143d6c and 145118 update the schedule record during the fight.
        for(int i=0;i<b.arcadeQualifyingWins;++i)run.addRoundWin(run.players[human].stageIndex,1);
        if(b.match.players[human^1].wins>0)run.disableSpecialOpponents();
        run.game.score=match_->arcadeScore();
        arcade_->random=b.random;
        arcade_->matchEnded(b.matchEnd.winner08,int(b.matchEnd.metadataStage04),b.matchEnd.result8c,b.endingParameter2c,held);
        break;
    }
    case ArcadeScene::Continue:arcade_->tickContinue(pressed);break;
    case ArcadeScene::GameOver:arcade_->tickGameOver(pressed);break;
    default:break;
    }
    if(arcade_->scene==ArcadeScene::CharacterSelect) {
        // CONTINUE returns to the character select (128008). Until the
        // single-seat select is wired the same fighter continues.
        const auto& human=run.players[run.humanSeat()];
        arcade_->selected(human.character,human.colour,human.spirit,held);
    }
    if(arcade_->scene==ArcadeScene::Battle)startArcadeFight();
    if(arcade_ && (arcade_->leftToTitle||arcade_->scene==ArcadeScene::None)) {
        // The ranking scene leads back to the title (127940).
        const auto system=match_->systemHandle();
        arcade_.reset();
        auto title=std::make_unique<NativeMatch>(assets_,roundTime_,mode_,match_.get(),spirits_);
        title->openTitle(false);
        match_=std::move(title);
    }
}
void LocalVersus::restart() {
    arcade_.reset();arcadeNotice_.clear();
    match_=std::make_unique<NativeMatch>(assets_,roundTime_,mode_,nullptr,spirits_);
    if(entry_==VersusEntry::Arcade){startArcade(0,0,0,int(spirits_[0]));matchNumber_=1;return;}
    if(entry_==VersusEntry::Fight)configureControllers(*match_);
    if(entry_==VersusEntry::CharacterSelect)match_->openCharacterSelect(true);
    if(entry_==VersusEntry::Title)match_->openTitle(false);
    matchNumber_=1;
}
void LocalVersus::tick(const std::array<NormalizedPadSample,2>& pads) {
    if(arcade_){tickArcade(pads);return;}
    try {match_->tick(pads);}
    catch(const UnportedFighterState& move) {
        if(mode_!=VersusMode::Console)throw;
        match_->leaveUnportedFight(move);
    }
    // Deliver the old match's last sound requests before its state is replaced.
    if(observer_)observer_(*match_);
    if(match_->faceoff()&&match_->faceoff()->complete) {
        const auto rules=versusRules();
        auto next=std::make_unique<NativeMatch>(assets_,-1,mode_,match_.get(),std::array<unsigned,2>{},
                                                match_->selectedLineup(),match_->characterSelect()->stage,
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
