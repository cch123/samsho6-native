#include "fighter_identity_hud.hpp"
#include "battle_round.hpp"
#include "hud_sprite.hpp"
#include <bit>

namespace ss6 {
void FighterIdentityHudState::sample(const BattleRoundState& battle,bool reset) {
    // 120ce0 queues before 120ac8 advances. The playable ACT489 records have
    // length zero and hold their pose; time retains only the fractional byte.
    portraitsAdvanced=visible;
    portraitTime=nextTime_;
    for(unsigned i=0;i<2;++i)nextTime_[i]=uint8_t(portraitTime[i]+resolveObjectDelta(256,i,battle.gauges));
    if(!visible||reset) {
        // The HUD copies GameData+38 when the scene creates or refreshes it.
        // Awarding the whole match while its menu opens must not update this
        // old HUD to the rematch's consecutive-win count.
        streak=battle.consoleMenu.session.streak;
        submode=battle.matchEnd.submodeA0;
        for(unsigned i=0;i<2;++i)required[i]=battle.match.players[i].requiredWins;
    }
    lastEntrant=battle.consoleMenu.session.lastEntrant;
    alternateText=battle.matchEnd.characterVersion43d052!=0;
    for(unsigned i=0;i<2;++i)wins[i]=battle.match.players[i].wins;
    visible=true;
}

FighterIdentityHud::FighterIdentityHud(const std::filesystem::path& assets)
    :atlas_(hud::loadAtlas(assets/"obj2_16.tex")) {}

void FighterIdentityHud::submitPortraits(ObjectDrawQueue& queue,const GaugeState& gauges,std::array<unsigned,3> resources,
                                      const FighterIdentityHudState& state) {
    for(unsigned i=0;i<2;++i) {
        // 1ba940 constructs a screen-space ACT489 per player. 11fef8 sets
        // its palette to the character's first color even in mirror matches.
        // The portrait ACTs have one held record; 120ce0 enqueues it like any fighter.
        AuxiliaryObject object{};
        object[0x0c/4]=object[0x10/4]=i;
        object[0x14/4]=resources[i];
        object[0x1c/4]=resources[i]*5;
        object[0x24/4]=489;
        object[0x30/4]=256;
        object[0x38/4]=0x10100000u|(i<<19);
        object[0x2c/4]=state.portraitTime[i];
        // The held portrait ends with code 0 for resource 00 and 1 for 01..03.
        object[0x3c/4]=state.portraitsAdvanced && resources[i]!=0;
        object[0xc0/4]=state.portraitsAdvanced;
        object[0x40/4]=std::bit_cast<uint32_t>(i?301.f:19.f);
        object[0x44/4]=std::bit_cast<uint32_t>(195.5f);
        object[0x70/4]=std::bit_cast<uint32_t>(.5f);
        object[0xb0/4]=std::bit_cast<uint32_t>(-290.f);
        queue.submit(object,gauges);
    }
}

void FighterIdentityHud::paint(const FighterIdentityHudState& state,std::span<uint8_t> rgba) const {
    if(!state.visible)return;
    if(rgba.size()!=hud::screenWidth*hud::screenHeight*4)throw std::invalid_argument("Expected a 640x448 battle HUD");
    const auto draw=[&](hud::Sprite s,int x,int y){hud::sprite(rgba,atlas_,s,x,y,s.w,s.h);};
    for(unsigned i=0;i<2;++i) {
        draw({254,i?191:133,62,57},i?574:4,28);
        // Console VS (submode 2) suppresses the challenger title. Only the
        // reigning winner gets the streak type and its right-aligned digits.
        const bool leader=state.streak>0 && int(i)!=state.lastEntrant;
        if(leader) {
            draw(state.alternateText?hud::Sprite{419,39,36,17}:hud::Sprite{317,20,52,18},i?392:224,10);
            int x=i?374:206;
            for(int value=state.streak;value>0;value/=10,x-=10)
                draw({1+(value%10)*18,494,17,17},x,10);
        }else if(state.submode==0) {
            draw(state.alternateText?hud::Sprite{317,39,101,17}:hud::Sprite{317,1,66,18},i?362:(state.alternateText?180:224),10);
        }
        // Empty rings are assembled first. A filled token has its own
        // nearer depth and overlaps the empty cell at the same position.
        for(int j=0;j<state.required[i];++j)draw({384,87,14,14},i?367+16*j:260-16*j,85);
        for(int j=0;j<state.wins[i];++j)draw({399,87,14,14},i?367+16*j:260-16*j,85);
    }
}
}
