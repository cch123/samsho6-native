#pragma once
#include "combat_sound_bank.hpp"
#include <array>
#include <filesystem>
#include <vector>

namespace ss6 {

// The music service owns SPU voices 0 (left) and 1 (right). A preload
// fills their ring buffers, but the round dispatcher separately releases them.
class CombatMusic {
public:
    enum class Event { None, Silence, KeyOn, Fade };
    // One 1553b40 request block: 213ff0 / 214060 / 2140b8 all store the
    // track + 1, the soundtrack byte 43d056 and their second argument (5a9e80,
    // the IOP repeat flag). 2140b8 sets the preload word 1553b58; 214060 sets
    // 5a9e84, which turns the next 214150 into the 213db0 fade-out.
    struct Request {
        int variant=0,track=0;
        bool repeat=false,preload=false,fadeStop=false;
    };
    struct Track {
        std::array<CombatSoundSample,2> sides;
        unsigned samples=0;   // decoded period, without the three wrap taps
        int key=-1;
    };
    explicit CombatMusic(const std::filesystem::path& assets);
    static constexpr int tracks=28;
    bool exists(int variant,int track) const;
    void request(const Request&,int volume);
    void release(int volume);
    // 214150. `streaming` is the IOP answer of 213db0: a keyed, unfinished stream.
    void stop(bool streaming);
    void reset();
    Event tick(bool streaming);
    const Track& track() const {return tracks_[slot_];}
    const Request& pending() const {return request_;}
    unsigned endSample() const {return endSample_;}
    bool repeat() const {return repeat_;}
    int volume() const {return volume_;}
    int fadeLevel() const {return fadeLevel_;}
    bool fading() const {return keyOff_!=0;}
    bool fadeActive() const {return fading_;}
    // The 1553b44 state of the EE request machine while a request is open
    // (-1 once the request has reached the IOP or none is pending).
    int requestState() const;
private:
    enum class Phase { Idle, StopPrevious, WaitFade, WaitIdle, Open, WaitOpen, RequestDMA, Loading, Ready };
    struct Entry { uint32_t bytes=0; bool own=false; std::array<std::vector<uint8_t>,2> tail; };
    std::filesystem::path assets_;
    std::array<Entry,2*tracks> catalogue_;
    std::array<Track,2> tracks_;
    Request request_;
    Phase phase_=Phase::Idle;
    unsigned slot_=0,playingSlot_=0,endSample_=0;
    int volume_=0,ticksToReady_=0,fadeLevel_=0,keyOff_=0;
    bool repeat_=false,released_=false,fadeStop_=false,fading_=false;
};
}
