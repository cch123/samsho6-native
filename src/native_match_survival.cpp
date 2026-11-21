#include "native_match.hpp"
#include "fighter_roster.hpp"
#include <algorithm>
#include <cstdio>

namespace ss6 {
namespace {
// 118128 words of the software controller, as the menu tasks read them.
uint32_t physicalPad(uint32_t logical) {
    constexpr std::array<uint32_t,8> physical{0x400,0x200,2,4,0x400000,0x800000,0x100000,0x200000};
    uint32_t bits=logical&0xf8;
    if(logical&PadSelect)bits|=0x80000;
    for(unsigned i=0;i<physical.size();++i)if(logical&(PadLight<<i))bits|=physical[i];
    return bits;
}
// Provisional English labels for the text view. The original strings (tables
// 59cf38, 59cf60 and 4ee870) are Shift-JIS and are kept in survival_run.bin.
constexpr std::array<const char*,22> missionNames{
    "WIN UNARMED","WIN WITH A HEAVY SLASH","WIN WITH A PURSUIT ATTACK","WIN WITH A GUARD BREAK",
    "WIN WITH A SPECIAL MOVE","WIN WITH A HYPER SLASH","WIN WITH A COMBO SLASH","WIN WITH A WEAPON BREAKING MOVE",
    "WIN WITH A WEAPON FLIPPING MOVE","WIN WITH A SECRET MOVE","WIN WITH ISSEN","WIN IN THE STATE OF NOTHINGNESS",
    "CONNECT 3 OR MORE SLASHES","TAUNT 3 TIMES","BECOME A DOLL 3 TIMES","3 SUCCESSFUL MIKIRI SLIDES",
    "EACH SUCCESSFUL DEFLECTION","EACH COUNTER HIT","EACH THROWN ITEM THAT HITS","EACH ITEM DEFLECTED",
    "EACH SUCCESSFUL AIR GUARD","WIN"};
constexpr std::array<const char*,9> rewardNames{
    "LIFE +10","LIFE +20","LIFE +30","LIFE +50","TIME +10","TIME +20","TIME +30","LIFE AND TIME FULL","NONE"};
constexpr std::array<const char*,9> spiritNames{"RAGE","SHIN","ZAN","TEN","ZERO","KEN","CUSTOM","MA","KEMONO"};
constexpr std::array<const char*,14> messageNames{
    "SELECT THE CONDITIONS OF THE NEXT MATCH","SURVIVAL MODE CLEARED","PROCEEDING TO THE NEXT STAGE",
    "BONUS CONDITION ACHIEVED","BONUS CONDITION NOT ACHIEVED",
    "LIFE RECOVERED BY 10","LIFE RECOVERED BY 20","LIFE RECOVERED BY 30","LIFE RECOVERED BY 50",
    "TIME RECOVERED BY 10 COUNTS","TIME RECOVERED BY 20 COUNTS","TIME RECOVERED BY 30 COUNTS",
    "LIFE AND TIME FULLY RECOVERED","THERE WAS NO BONUS"};
}
void NativeMatch::openSurvivalSelect(unsigned seat) {
    // 1cd494: mode word b/c (1ccfb8), g+0x10 = seat ^ 1, 111710, 139280(2)
    // and sub-mode 4 before scene 128008. The select has no spirit page.
    battle_.gameMode=0xb+int(seat);battle_.matchEnd.submodeA0=4;
    openCharacterSelect(true);
    characterSelect_->configure(0xb+int(seat));
    characterSelect_->random=battle_.random;
    soloSelection_.reset();
    selectAudioPending_=false;enterSelectAudio();
}
int NativeMatch::survivalFade() const {
    return survival_&&!characterSelect_&&!title_?survival_->run.fade:0;
}
void NativeMatch::survivalReleaseStage() {
    battle_.entry.tasks.cancelTasks(0xfa1); // 112a70(fa1)
}
void NativeMatch::tickSurvival(const std::array<NormalizedPadSample,2>& pads) {
    auto& s=*survival_;auto& run=s.run;auto& b=battle_;
    if(s.ended)return; // 1252f0(2,0,139778,138340): the session owns the scene switch
    // 139118 / 13913c: the request 1392e8 made on the previous frame holds 140270.
    const bool hold=s.pauseRequested;s.pauseRequested=false;
    const bool counted=battleFrame(pads,hold);
    // 139140: a frame of the KO pause leaves s4 clear even though 140270 did not run.
    const bool skipped=hold&&!counted;
    const unsigned h=unsigned(s.humanSeat());
    if(b.modeMatchEnded&&!survivalEndHandled_) {
        // 143484 -> 145628, inside this frame's 140270 and before 180630.
        survivalEndHandled_=true;
        s.end=survivalMatchEnd(run,b.random,*system_,s.modeWord,b.matchEnd.winner08,s.config,s.setup,b.timers.values[0],s.flags);
        b.matchEnd.endFlagA4=0;
        if(s.end.finished)s.ended=true;
    }
    // 180630(s4)
    const unsigned port=unsigned(SurvivalRun::padPort(s.modeWord));
    const auto menuPads=menuRepeat_.sample({physicalPad(pads[0].held),physicalPad(pads[1].held)},
                                           {physicalPad(pads[0].pressed),physicalPad(pads[1].pressed)});
    const SurvivalPad pad{physicalPad(pads[port].held),menuPads[port].pressed,menuPads[port].repeat};
    auto& f=fighters_[h];auto& a=f.actor;
    const auto& own=b.match.players[h];const auto& other=b.match.players[1-h];
    SurvivalHuman human;
    human.seat=int(h);human.flags23c=int32_t(a.flags23c);human.life=a.fieldA30;human.lifeA38=a.pendingDamageA38;
    human.word248=int32_t(a.flags248);human.x=f.body.timeline.motion().x;human.events=a.characterBytesF22;
    SurvivalBattle battle;
    battle.state=b.requestedState;battle.round=b.match.roundIndex;battle.winner=b.match.result.winner;
    battle.clock=b.timers.values[0];battle.finish=own.outcome1c;battle.special=own.outcome20;
    battle.opponentWins=other.wins;battle.opponentRequired=other.requiredWins;
    const auto events=run.tick(skipped,pad,human,battle,b.random,s.modeWord,s.config,s.setup);
    a.fieldA30=human.life;a.characterBytesF22=human.events;b.timers.values[0]=battle.clock;
    for(int id:events.sounds)sounds_.sample(-1,id);
    if(events.pauseRequests)s.pauseRequested=true;
    if(events.continueFlag)b.matchEnd.continue2c=1;
    // 1b5b80(0, x, 50): the heal label of the item notices, without its sound.
    if(events.lifeEffect)b.itemNotices.show(StageItemLabel::Heal,events.lifeEffectX);
    if(events.reload) {
        // 1e7df0 and 1815b0 here; 13a6c0 has rewritten the setup. The session
        // loads the arena and the fighters (1a4a98, 13f9f0(1)) on the next two frames.
        sounds_.stopMusic();sounds_.stopGroup(2);
        s.reload=true;
    }
}
std::vector<std::string> NativeMatch::survivalOverlay() const {
    std::vector<std::string> lines;
    if(!survival_||characterSelect_||title_)return lines;
    const auto& s=*survival_;const auto& run=s.run;
    char buffer[160];
    const auto row=[&](const SurvivalCandidate& c,bool cursor) {
        const unsigned sp=unsigned(c.humanSpirit),m=unsigned(c.mission),r=unsigned(c.reward);
        std::snprintf(buffer,sizeof buffer,"%s SPIRIT %-6s VS %-16s %s / BONUS %s",cursor?">":" ",
                      sp<spiritNames.size()?spiritNames[sp]:"?",versusFighterName(logicCharacter(unsigned(c.character))),
                      m<missionNames.size()?missionNames[m]:"?",r<rewardNames.size()?rewardNames[r]:"?");
        return std::string(buffer);
    };
    // Header 1bb2c8 prints 181488() (word 582244) beside the CPU seat.
    std::snprintf(buffer,sizeof buffer,"SURVIVAL (PROVISIONAL TEXT VIEW)   DEFEATED %d",run.winCount());
    lines.push_back(buffer);
    if(run.hud.visible) {
        // Panel 1810f8.
        std::snprintf(buffer,sizeof buffer,"ELAPSED %02d:%02d:%02d",run.hud.hours,run.hud.minutes,run.hud.seconds);
        lines.push_back(buffer);
        if(!run.hud.boss) {
            const unsigned m=unsigned(run.hud.mission),r=unsigned(run.hud.reward);
            lines.push_back(std::string("BONUS ")+(r<rewardNames.size()?rewardNames[r]:"?"));
            lines.push_back(std::string(run.hud.line==2?"ACHIEVED ":run.hud.line==1?"CONDITION (EACH TIME) ":"CONDITION ")+
                            (m<missionNames.size()?missionNames[m]:"?"));
            if(run.hud.progress){std::snprintf(buffer,sizeof buffer,"PROGRESS %02d",run.hud.progressValue);lines.push_back(buffer);}
        }
    }
    // Message window 12d4d48 and candidate selector 12d4eb0.
    if(run.message.open&&run.messageText>=0&&unsigned(run.messageText)<messageNames.size())
        lines.push_back(messageNames[unsigned(run.messageText)]);
    if(run.selectorActive&&run.state==1) {
        for(unsigned i=0;i<3;++i)lines.push_back(row(run.rows[i],int(i)==run.cursor));
        lines.push_back("UP/DOWN: SELECT   CONFIRM: DECIDE");
    } else if(run.state==2||(run.state==3&&run.delay==0&&run.lifeGain==0&&run.clockGain==0))
        lines.push_back("ANY BUTTON: NEXT");
    if(!s.notice.empty())lines.push_back(s.notice);
    return lines;
}
}
