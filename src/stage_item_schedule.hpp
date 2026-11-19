#pragma once
#include <array>
#include <cstdint>
#include <filesystem>
#include <optional>

namespace ss6 {
struct BattleRoundState;
struct StageEventPlayers;
struct StageItemDrop {int kind,targetX,fromRight;};

// The local VS controller rolls on its own repeating 60-count clock, including
// in unlimited-time fights. The match RNG is shared with both fighters.
class StageItemSchedule {
public:
    explicit StageItemSchedule(const std::filesystem::path&);
    std::optional<StageItemDrop> next(BattleRoundState&,const StageEventPlayers&) const;
private:
    std::array<uint8_t,384> table_{};
    int roll(BattleRoundState&,unsigned stage,int second) const;
};
}
