#pragma once
#include <array>
#include <cstdint>
#include <filesystem>
#include <span>
#include <vector>

namespace ss6 {

struct BattleClockState;
struct LifeGaugeInput {
    int phase{},reserve{},remaining{},life{200},sword{},swordMax{},opponentHits{};
    bool inPersistentHurt{},holdLifeSampling{};
};
// Priority 20 samples the animation before advancing its counters. Rendering the
// same update twice (pause, screenshot) must reuse this exact draw state.
struct ComboFrame {
    int count{},previous{},entry{},bounce{},digit{},exit{-1};
    bool fixedTens{};
    int tensStep{};
};
struct ComboHud {
    ComboFrame next{},draw{};
    int held{},requested{};
    void advance(bool defenderStillHurt,bool frozen);
};
struct RageGaugePlayer {
    ComboHud combo{};
    int state{}, displayed{}, pulse{}, emblemCounter{}, emblemExpansion{};
    int pulseDirection{1};
    int system{},fireTicks{},fireFrame{};
    LifeGaugeInput lifeGauge{};
    int sampledLife{200},lifeX{73},lifeWidth{200},lifeTrail{200},lifeDelay{30};
    bool lifeHealing{},woundActive{};
    int woundX{},woundWidth{},storedWoundWidth{},lifeThreshold{-1};
    int lifePulse{},lifePulseDirection{1},zanLifePulse{},zanLifeDirection{1};
    int guardPulse{},guardPulseDirection{1};
    int swordPulse{},swordPulseDirection{1},concentrationTicks{},concentrationCell{};
};

struct RageGaugeState {
    std::array<RageGaugePlayer,2> players{};
    bool resetOnLastVisit{};
    RageGaugeState() { players[1].lifeX=366; }
    // The HUD task copies the current amounts when a new round/interface opens.
    void reset(const std::array<int32_t,2>& amount124);
    // Advance once per game tick, including ticks on which combat is stopped.
    void advance(const std::array<int32_t,2>& state120,const std::array<int32_t,2>& amount124,
                 const std::array<int32_t,2>& systems={},const std::array<uint32_t,2>& flags23c={},
                 const std::array<LifeGaugeInput,2>& lifeGauges={},bool comboFrozen=false);
};

class RageGaugeRenderer {
public:
    explicit RageGaugeRenderer(const std::filesystem::path& assets);
    void paint(const RageGaugeState&,std::span<uint8_t> rgba640x448) const;
    void paintLife(const RageGaugeState&,std::span<uint8_t> rgba640x448) const;
    void paintRage(const RageGaugeState&,std::span<uint8_t> rgba640x448) const;
    // The timer plate and its digits use the same two resident HUD atlases.
    void paintClock(const BattleClockState&,std::span<uint8_t> rgba640x448) const;
private:
    std::vector<uint8_t> gaugeAtlas_,commonAtlas_,slotOneAtlas_;
};

}
