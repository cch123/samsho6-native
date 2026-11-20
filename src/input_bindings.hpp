#pragma once
#include "command_input.hpp"
#include <optional>
#include <vector>

namespace ss6 {
struct InputSystemConfig {
    unsigned system=0,character=0;
    //14f4e0/152758's selected descriptor, supplied by mode configuration.
    //System6 can use either a saved custom descriptor or a stock preset.
    std::optional<std::array<uint8_t,16>> descriptor;
};
struct InputBindingRecord {
    uint8_t character,priority;
    int16_t command;
    uint16_t condition,flags,systems,auxiliary;
};
class InputBindings {
public:
    explicit InputBindings(const std::filesystem::path& assets);
    void initialize(ActorCommandInput&,const InputSystemConfig* config) const;
    bool normalAvailable(unsigned index,const InputSystemConfig&) const;
    int techniqueCategorySlot(unsigned character,unsigned column) const;
    bool allowsTechniqueCategory(unsigned character,unsigned slot,const InputSystemConfig&) const;
    bool specialAvailable(unsigned record,unsigned slot,const InputSystemConfig&) const;
    const std::vector<InputBindingRecord>& specialRecords() const {return special_;}
    const std::array<InputBindingRecord,31>& normalRecords() const {return normal_;}
    bool specialCategory(unsigned character,int stateIndex) const; //168e00
    bool specialFirstCategory(unsigned character,int stateIndex) const;
    bool specialSecondCategory(unsigned character,int stateIndex) const;
private:
    std::array<InputBindingRecord,31> normal_;
    std::vector<InputBindingRecord> special_;
    std::array<std::array<int16_t,6>,51> characters_;
    std::array<std::array<uint8_t,5>,51> categories_;
    bool firstCategory(unsigned character,unsigned slot) const;
    bool secondCategory(unsigned character,unsigned slot) const;
};
}
