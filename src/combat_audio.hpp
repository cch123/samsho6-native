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
    int playVoice(int character,int tone,unsigned voiceVariant=0);
    int playResidentJingle(int tone,int volumeCode);
    // The EE stream entry points that fill the request block.
    enum class MusicEntry { Play /*213ff0, behind 1e7c00*/, Gallery /*214060*/, Preload /*2140b8*/ };
    // flag is the second argument of the entry point (the IOP repeat flag).
    void requestMusic(MusicEntry entry,int variant,int track,int flag,int volume);
    void preloadMusic(int variant,int track);
    void startMusic(int volume);
    void playMusic(int variant,int track,int volume);
    // 1e79c8(group - 1, bank) -> 212dd8: BVOICE2[bank] into group 0 (common), 1 or 2.
    void loadBank(int group,int bank);
    void stopMusic();
    void stop(int physicalChannel);
    void stopGroup(int group);
    void clearVoices();
    void reset();
    void tick();
    const CombatMusic& music() const {return music_;}
    // Inspection for validators: the sample a physical voice reads and the
    // largest absolute output it produced in the last render() call.
    const CombatSoundSample* channelSample(unsigned i) const {return channels_.at(i).sample;}
    int channelPeak(unsigned i) const {return peaks_.at(i);}
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
    unsigned common_=50;
    CombatMusic music_;
    std::array<Channel,22> channels_{};
    std::array<int,22> peaks_{};
    std::array<Request,4> queue_{};
    unsigned nextEffect_=14,write_=0,read_=0,transfer_=0;
    int playEffect(const CombatSoundSample*,int volumeCode);
};
}
