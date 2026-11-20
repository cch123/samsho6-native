#pragma once
#include "action_runtime.hpp"
#include "game_random.hpp"
#include <span>

namespace ss6 {
enum class BattleSoundKind { Sample, Voice, Stop, StopGroup, ResidentJingle, MusicPreload, MusicStart, MusicStop, MusicPlay, BindPlayers };
// Sample uses the two arguments to 212fa0. Voice uses character/line at
// 213378. Stop and StopGroup put the physical channel or group in tone.
// MusicPreload carries variant/track, MusicPlay carries raw volume/track
// for the factory variant, and MusicStart puts its raw volume in tone.
struct BattleSoundEvent { BattleSoundKind kind; int bank; int tone; };
class SoundSelection {
public:
    explicit SoundSelection(const std::filesystem::path&);
    std::array<int32_t,2> previous{}; //585224/58524c, shared across players
    void reset();
    int32_t resolve(int32_t command,int32_t stage,GameRandom&);
    int act(int command,int seat,int character,uint32_t actorFlags,int gameMode,int stage,GameRandom&);
    int record(int16_t command,const ActionClock&,int seat,int character,uint32_t actorFlags,int gameMode,int stage,GameRandom&);
    int sample(int seat,int tone); // 1e7b70, tone already zero-based
    void voice(int character,int tone);
    void residentJingle(int tone,int volumeCode);
    void preloadMusic(int variant,int track);
    void startMusic(int volume);
    void stopMusic();
    void playMusic(int track,int volume);
    void bindPlayers(unsigned first,unsigned second);
    void enterBattleScene(bool victoryMusicGate);
    void stop(uint32_t& objectSound34);
    // 120ee8: 1e7aa8(object+34 & 7) while bit 0x8000 is set; the word is kept.
    void cutVoice(uint32_t objectSound34);
    void stopGroup(int group);
    void contact(unsigned group,unsigned defense,bool armed,bool finishing,bool counter,int attackerAction,GameRandom&);
    void beginFrame(){events_.clear();}
    std::span<const BattleSoundEvent> events() const {return events_;}
    //The120e14..120ebc ordinary resource00 record-entry gates. A silent
    //output device is separate from the original object's mute flag200.
    void record(int16_t command,const ActionClock&,int32_t stage,GameRandom&);
private:
    std::vector<BattleSoundEvent> events_;
    int previousImpact_=0,guardVariant_=0,nextChannel_=14;
    std::array<int32_t,35> table_{};
    std::array<uint8_t,36> categories_{};
};
}
