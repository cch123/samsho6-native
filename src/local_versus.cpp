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
void LocalVersus::restart() {
    match_=std::make_unique<NativeMatch>(assets_,roundTime_,mode_,nullptr,spirits_);
    if(entry_==VersusEntry::Fight)configureControllers(*match_);
    if(entry_==VersusEntry::CharacterSelect)match_->openCharacterSelect(true);
    if(entry_==VersusEntry::Title)match_->openTitle(false);
    matchNumber_=1;
}
void LocalVersus::tick(const std::array<NormalizedPadSample,2>& pads) {
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
