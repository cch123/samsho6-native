#pragma once
#include "combat_sound_bank.hpp"
#include <array>
#include <filesystem>

namespace ss6 {

// The music service owns SPU voices 0 (left) and 1 (right). A preload
// fills their ring buffers, but the round dispatcher separately releases them.
class CombatMusic {
public:
    enum class Event { None, Silence, KeyOn };
    struct Track {
        std::array<CombatSoundSample,2> sides;
        unsigned endSample=0;
        int tone=-1;
    };
    explicit CombatMusic(const std::filesystem::path& assets):assets_(assets) {}
    void request(int variant,int track,bool preload,int volume);
    void release(int volume);
    void stop();
    void reset();
    Event tick();
    const Track& track() const {return tracks_[slot_];}
    bool repeat() const {return repeat_;}
    int volume() const {return volume_;}
private:
    enum class Phase { Idle, StopPrevious, WaitFade, WaitIdle, Open, WaitOpen, RequestDMA, Loading, Ready };
    std::filesystem::path assets_;
    std::array<Track,2> tracks_;
    Phase phase_=Phase::Idle;
    unsigned slot_=0,playingSlot_=0;
    int volume_=0,ticksToReady_=0;
    bool repeat_=false,released_=false;
};
}
