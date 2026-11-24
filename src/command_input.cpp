#include "asset_files.hpp"
#include "command_input.hpp"
#include "input_features.hpp"
#include <fstream>
#include <stdexcept>

namespace ss6 {
namespace {
uint32_t feature(const InputFeatures& f,unsigned index,bool alternate) {
    //1789d0 substitutes the whole17-word direction block, including its
    //edge predicates. It is not a generic left/right bit swap.
    if(alternate&&index>=49&&index<=65)index+=17;
    return f.at(index);
}
}
CommandInput::CommandInput(const std::filesystem::path& assets) {
    std::ifstream in(resolveAsset(assets/"input_commands.bin"),std::ios::binary);
    for(auto& d:definitions_) {
        std::array<uint8_t,17> raw{};
        if(!in.read(reinterpret_cast<char*>(raw.data()),raw.size()))throw std::runtime_error("Truncated original input command table");
        for(unsigned i=0;i<14;++i) {
            if(raw[i]>=171&&raw[i]!=255)throw std::runtime_error("Unknown input feature in command table");
            d.tokens[i]=raw[i];
        }
        d.timeout=raw[14];d.buffer=raw[15];d.resetFeature=raw[16];
        if(d.resetFeature>=171&&d.resetFeature!=255)throw std::runtime_error("Unknown command reset feature");
    }
    if(in.peek()!=EOF)throw std::runtime_error("Unexpected input command table size");
}
bool CommandInput::chargeHeld(unsigned token,const InputFeatures& f,bool alternate) {
    //178dc8 maps button-edge predicates back to held predicates, while
    //only the listed direction classes may sustain a charge.
    if(token<5)token+=91;
    else if(!((token>=91&&token<=95)||token==46||(token>=50&&token<=57)||(token>=62&&token<=65)))return false;
    return feature(f,token,alternate)!=0;
}
bool CommandInput::evaluate(unsigned id,CommandProgress& p,const InputFeatures& f,bool alternate) const {
    //The original invalid-id/step path logs and clears only progress.
    //An existing completion buffer survives that failed recognition.
    if(id>=Count||p.step>=14){p.clearProgress();return false;}
    const auto& d=definitions_[id];
    for(;;) {
        const auto token=d.tokens[p.step];
        if(d.resetFeature!=255&&feature(f,d.resetFeature,alternate)&&p.step) {
            p.clearProgress();return false;
        }
        if(token==48) {
            if(p.step&&chargeHeld(d.tokens[p.step-1],f,alternate)) {
                if(p.charge<6000)++p.charge;
                return false;
            }
            //The first direction only enters the charge marker.52 further
            //held visits are required; release can consume the next token
            //in this same call, without an extra manufactured input frame.
            if(p.charge<52){p.clearProgress();return false;}
            ++p.step;p.elapsed=0;p.charge=0;
            if(p.step>=14)throw std::runtime_error("Charge marker terminates an original command");
            continue;
        }
        if(p.step)++p.elapsed; //Original byte counter wraps before comparison.
        if(p.elapsed>=d.timeout){p.clearProgress();return false;}
        if(token!=255&&!feature(f,token,alternate))return false;
        ++p.step;p.elapsed=0;p.charge=0;
        if(p.step>=14||d.tokens[p.step]==255) {
            p.clearProgress();p.buffered=d.buffer;return true;
        }
        const auto next=d.tokens[p.step];
        //Only direction->button predicates coalesce in one call. Two
        //successive directional tokens still require separate visits.
        if(token>=49&&token<=101&&next>=6&&next<=45)continue;
        return false;
    }
}
void ActorCommandInput::clearBuffers() {
    for(auto& s:normal)s.progress.clearBuffered();
    for(auto& s:special)s.progress.clearBuffered();
}
void ActorCommandInput::clearPublished() {
    //The original sentinel is the binding start, not enabled/count. Unused
    //special results survive, but even their completion buffers are cleared.
    if(specialStart==-1)return;
    if(specialCount>32)throw std::runtime_error("Invalid original special-command count");
    sampledFeatures.fill(0);
    for(auto& s:normal)s.recognized=0;
    for(int i=0;i<specialCount;++i)special[i].recognized=special[i].cancelAllowed=0;
    clearBuffers();
}
void ActorCommandInput::advance(const CommandInput& input,const InputFeatures& features,bool advanceBuffers) {
    if(!enabled)return;
    if(specialCount<-1||specialCount>32)throw std::runtime_error("Invalid original special-command count");
    const auto visit=[&](CommandSlot& s) {
        const bool matched=s.definition!=-1&&input.evaluate(uint16_t(s.definition),s.progress,features,s.alternateDirections);
        s.recognized=matched||s.progress.buffered;
    };
    for(auto& s:normal)visit(s);
    for(int i=0;i<specialCount;++i){special[i].cancelAllowed=0;visit(special[i]);}
    //Results see the old buffer, then all slots age, even unused special
    //slots. A disabled definition can still expose a previously buffered
    //match; clearing it on -1 would change179530's fallback behavior.
    if(advanceBuffers) {
        for(auto& s:normal)s.progress.elapseBuffer();
        for(auto& s:special)s.progress.elapseBuffer();
    }
}
void ActorCommandInput::sampleAndAdvance(const CommandInput& input,InputSampler& sampler,unsigned player,
                                       const NormalizedPadSample& pad,const InputMapping& mapping,
                                       const InputSamplingContext& context,bool advanceBuffers) {
    if(!enabled)return;
    sampler.advance(player,pad,mapping,context);
    sampledFeatures=sampler.features; //1788e8 copies all171 words before recognition.
    advance(input,sampledFeatures,advanceBuffers);
}
}
