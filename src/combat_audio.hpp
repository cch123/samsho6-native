#pragma once
#include "combat_sound_bank.hpp"
#include "combat_music.hpp"
#include <array>
#include <cstdint>
#include <filesystem>
#include <span>

namespace ss6 {

// The IOP shares the rotating SE voices across both players and the resident
// voice bank. Keep the device-independent mixer alive across rounds/CONTINUE.
class CombatAudio {
public:
    explicit CombatAudio(const std::filesystem::path& assets);
    int play(int bank,int tone);
    void bindPlayers(std::array<unsigned,2> ids){players_=ids;clearVoices();}
    int playVoice(int character,int tone);
    int playResidentJingle(int tone,int volumeCode);
    void preloadMusic(int variant,int track);
    void startMusic(int volume);
    void playMusic(int variant,int track,int volume);
    void stopMusic();
    void stop(int physicalChannel);
    void stopGroup(int group);
    void clearVoices();
    void reset();
    void tick();
    void render(std::span<int16_t> interleavedStereo);
    static constexpr int sampleRate=48000;

private:
    enum class Envelope { Attack, Decay, Sustain, Release };
    struct Channel {
        const CombatSoundSample* sample=nullptr;
        uint64_t position=0;
        uint32_t decoded=0,streamEnd=0;
        bool repeat=false;
        int volume=0,level=0,sustainTicks=0;
        Envelope envelope=Envelope::Attack;
        int next();
    };
    struct Request {
        const CombatSoundSample* sample=nullptr;
        unsigned channel=0;
        bool pending=false;
    };
    CombatSoundBank bank_;
    std::array<unsigned,2> players_{};
    CombatMusic music_;
    std::array<Channel,22> channels_{};
    std::array<Request,4> queue_{};
    unsigned nextEffect_=14,write_=0,read_=0,transfer_=0;
    int playEffect(const CombatSoundSample*,int volumeCode);
};
}
