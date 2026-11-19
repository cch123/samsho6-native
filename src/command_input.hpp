#pragma once
#include <array>
#include <cstdint>
#include <filesystem>

namespace ss6 {
struct InputSampler;
struct NormalizedPadSample;
struct InputMapping;
struct InputSamplingContext;
//177908's derived predicates, before command recognition. These are not
//raw controller bits; the physical sampling/feature producer is separate.
using InputFeatures=std::array<uint32_t,171>;
struct CommandProgress {
    uint8_t step=0,elapsed=0;
    uint16_t charge=0;
    uint8_t buffered=0;
    void clearProgress() {step=elapsed=0;charge=0;}
    void clearBuffered() {buffered=0;} //178d30 does not erase partial motion.
    void elapseBuffer() {if(buffered)--buffered;}
};
struct CommandDefinition {
    std::array<uint8_t,14> tokens;
    uint8_t timeout,buffer,resetFeature;
};
class CommandInput {
public:
    static constexpr unsigned Count=273;
    explicit CommandInput(const std::filesystem::path& assets);
    const CommandDefinition& definition(unsigned id) const {return definitions_.at(id);}
    bool evaluate(unsigned id,CommandProgress& progress,const InputFeatures& features,bool alternateDirections=false) const;
    static bool chargeHeld(unsigned token,const InputFeatures& features,bool alternateDirections=false);
private:
    std::array<CommandDefinition,Count> definitions_;
};
struct CommandSlot {
    int16_t definition=-1;
    bool alternateDirections=false;
    CommandProgress progress;
    uint32_t recognized=0;
    //Special owner+3a8: generated cancel permission, not a consumed buffer.
    uint32_t cancelAllowed=0;
};
struct ActorCommandInput {
    InputFeatures sampledFeatures{};
    std::array<CommandSlot,31> normal;
    std::array<CommandSlot,32> special;
    int specialCount=-1;
    int specialStart=-1;
    std::array<uint8_t,32> specialPriority{};
    bool enabled=false;
    void clearBuffers(); //1797a8: all63 buffers, including unused slots.
    void clearPublished(); //179708: feature/results reset, partial motions survive.
    //179530 recognition phase. Input sampling and per-character binding
    //selection precede this boundary and are not replaced by this method.
    void advance(const CommandInput&,const InputFeatures&,bool advanceBuffers);
    //Whole179530 boundary: disabled owners must not sample, consume latch
    //time, touch the shared recording, or replace their previous features.
    void sampleAndAdvance(const CommandInput&,InputSampler&,unsigned player,const NormalizedPadSample&,
                          const InputMapping&,const InputSamplingContext&,bool advanceBuffers);
};
}
