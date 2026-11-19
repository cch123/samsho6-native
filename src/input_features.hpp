#pragma once
#include "command_input.hpp"

namespace ss6 {
//118128's software pad boundary, after the platform controller driver.
//These words use the original normalized bit layout, not SDL button IDs.
struct NormalizedPadSample {uint32_t held=0,pressed=0;};
struct InputMapping {
    std::array<uint32_t,8> normal{},mode6{};
};
struct InputSamplingContext {
    bool facing=false,actualFacing=false,reverseDirections=false;
    bool playback=false;
    int32_t replayIndex=-1,gameMode=0;
};
struct InputSampler {
    InputFeatures features{};
    std::array<std::array<uint8_t,6>,2> pressLatches{};
    //The original recording arrays are shared, not one recording per actor.
    //The caller chooses which actor/index to record or replay.
    std::array<uint16_t,600> replayHeld{},replayPressed{};
    void resetRoundSampling() { //177258, distinct from1772d0 recording clear
        features.fill(0);for(auto& player:pressLatches)player.fill(0);
    }
    void clearPressLatches(unsigned player) {pressLatches.at(player).fill(0);} //178920
    void sampleRaw(unsigned player,const NormalizedPadSample&,const InputMapping&,const InputSamplingContext&);
    void advance(unsigned player,const NormalizedPadSample&,const InputMapping&,const InputSamplingContext&);
};
}
