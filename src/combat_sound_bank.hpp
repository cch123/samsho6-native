#pragma once

#include <array>
#include <cstdint>
#include <filesystem>
#include <span>
#include <map>
#include <vector>

namespace ss6 {

// One history per physical ADPCM stream, preserved across buffer and DMA boundaries.
struct SpuAdpcmState { int recent{}, older{}; };
std::array<int16_t,28> decodeSpuAdpcmBlock(std::span<const uint8_t,16> block,SpuAdpcmState& history);

struct CombatSoundSample {
    // The original MSB offset is relative to the start of this character's group.
    uint32_t sourceOffset{};
    uint16_t pitch{};
    // BVOICE1 and NAL streams use the channel volume, not a per-sample volume.
    static constexpr uint16_t ChannelVolume = 0xffff;
    uint16_t volumeCode{ChannelVolume};
    // PCM coordinates. loopEnd is exclusive; both are -1 for a one-shot.
    int32_t loopStart{-1}, loopEnd{-1};
    std::vector<uint8_t> raw;
    std::vector<int16_t> pcm;
};

class CombatSoundBank {
public:
    explicit CombatSoundBank(const std::filesystem::path& assetDirectory);
    const CombatSoundSample* find(unsigned bank, unsigned tone) const;
    const CombatSoundSample* voice(unsigned tone) const;
    const CombatSoundSample* fighterEffect(unsigned id,unsigned tone);
    const CombatSoundSample* fighterVoice(unsigned id,unsigned tone);
    unsigned voiceCount(unsigned id);
    const CombatSoundSample* residentVoice(unsigned tone) const;
    const CombatSoundSample* narrator(unsigned tone, unsigned variant = 0) const;
private:
    std::array<std::vector<CombatSoundSample>, 6> groups_;
    std::filesystem::path directory_;
    std::map<std::pair<unsigned,bool>,std::vector<CombatSoundSample>> extra_;
    const std::vector<CombatSoundSample>& characterGroup(unsigned id,bool voice);
};

}
