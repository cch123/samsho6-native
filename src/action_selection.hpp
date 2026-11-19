#pragma once
#include "input_bindings.hpp"

namespace ss6 {
//Snapshot at the selector boundary. Selecting a state does not start its
//animation, consume commands, or bypass the caller's permission checks.
struct SelectionActor {
    uint32_t flags23c=0,flags244=0,flags248=0;
    uint32_t flags240=0,controlKindA20=0,controlModeC8=0;
    uint8_t flags24c=0;
    uint32_t state194=0,state1a4=0,character=0;
    int32_t variantA48=0;
    uint32_t bodyFlags38=0;
    uint32_t bodyFlags104=0;
    int32_t bodyAction24=0;
    uint32_t auxiliaryState128=0,auxiliaryFlag134=0; //The separate actor+4 object.
    uint16_t bodyPendingFE=0;
    uint32_t request18c=0;
    int16_t pendingTable=-1,pendingIndex=-1;
    float x=0,opponentX=0;
    int stateTable() const;
    int stateIndex() const;
    bool faceOpponent(bool force=false);
};
struct SelectionThreat {
    int32_t distance=0; //Battle+144 cache, not a new float-distance calculation.
    std::array<std::optional<int32_t>,48> opponentObjectKinds{};
};
class ActionSelection {
public:
    explicit ActionSelection(const std::filesystem::path& assets);
    uint8_t normalTransition(unsigned state,unsigned input,uint32_t flags23c) const;
    uint8_t attackTransition(unsigned state,unsigned input,uint32_t flags23c,bool chain=false) const;
    uint8_t systemNormal(const SelectionActor&,const ActorCommandInput&,unsigned state,const InputSystemConfig&,bool restricted=false) const;
    unsigned normal(SelectionActor&,const ActorCommandInput&,unsigned state,bool opponentThreat,const InputSystemConfig&) const;
    unsigned restrictedNormal(SelectionActor&,const ActorCommandInput&,unsigned state,const InputSystemConfig&) const;
    int attack(SelectionActor&,const ActorCommandInput&,unsigned state,bool chain=false) const;
    //150aa8/150b60 return table*256+state, or-1. They deliberately bypass
    //the flag800000 transition remaps used by the ordinary selectors.
    int supplemental(SelectionActor&,const ActorCommandInput&,unsigned state,bool systemOnly=false) const;
    uint8_t restrictedState(unsigned state) const;
    bool opponentThreat(const SelectionActor&,const SelectionActor& opponent,const SelectionThreat&) const;
    int translateNormalState(const SelectionActor&,int state) const;
    //14c2d0 /14c3b0 write the original pending-state request only. The
    //1491e0 entry dispatcher still owns animation and callback changes.
    bool requestAttack(SelectionActor&,const ActorCommandInput&) const;
    bool requestChain(SelectionActor&,const SelectionActor& opponent,const ActorCommandInput&,const InputSystemConfig&) const;
    bool requestSupplemental(SelectionActor&,const ActorCommandInput&,bool systemOnly=false) const;
    bool requestNormal(SelectionActor&,const SelectionActor& opponent,const ActorCommandInput&,const InputSystemConfig&,const SelectionThreat&,bool restricted=false) const;
private:
    std::array<uint8_t,64*31> normal_;
    std::array<uint8_t,64*17> attack_,chain_;
    std::array<uint8_t,64> normalMap_;
    std::array<uint8_t,64*2> attackMap_;
    std::array<uint8_t,64*5> normalDescriptors_;
    std::array<uint8_t,51> characterFlags_;
    std::array<uint8_t,9*4> threatActions_;
};
//14f5d8's per-system movement/evasion column, including custom system6.
unsigned inputSystemColumn(const InputSystemConfig&);
bool inputGuardAllowed(const SelectionActor&,const InputSystemConfig&);
}
