#include "local_versus.hpp"
#include <istream>
#include <stdexcept>

namespace ss6 {
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
    :assets_(assets),roundTime_(roundTime),mode_(mode),spirits_(spirits),startAtSelect_(startAtSelect),
     match_(std::make_unique<NativeMatch>(assets,roundTime,mode,nullptr,spirits_)) {if(startAtSelect_)match_->openCharacterSelect(true); }

void LocalVersus::restart() {
    match_=std::make_unique<NativeMatch>(assets_,roundTime_,mode_,nullptr,spirits_);
    if(startAtSelect_)match_->openCharacterSelect(true);
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
        auto next=std::make_unique<NativeMatch>(assets_,-1,mode_,match_.get(),std::array<unsigned,2>{},
                                                match_->selectedLineup(),match_->characterSelect()->stage);
        if(!(startAtSelect_ && match_->updates==0))++matchNumber_;
        match_=std::move(next);
        return;
    }
    if(mode_==VersusMode::Console && !match_->characterSelect() &&
       match_->battle().consoleMenu.destination==ConsoleVersusDestination::Rematch) {
        // The fade task creates the new fight after the old fight's update.
        // Its opening first receives a controller sample on the following tick.
        auto next=std::make_unique<NativeMatch>(assets_,-1,mode_,match_.get());
        match_=std::move(next);
        ++matchNumber_;
    }
}
}
