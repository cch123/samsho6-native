#pragma once
#include "battle_round.hpp"
#include "fighter_tables.hpp"

namespace ss6 {
// 148550, resource00. Prepare the original layer values before copying the
// bodies and owner registries into the drawing queue (including paused draws).
void updateFighterDepths(BattleRoundState&,const std::array<RoundPlayerRef,2>&,const FighterTables&);
// 148900 compares the actual ACT IDs in both body records. This is also the
// raw-record boundary when examining actions normally spawned as projectiles.
void applyHaohmaruDepthOverride(const FighterTables&,const std::array<unsigned,2>& actions,uint32_t& p1Depth,uint32_t& p2Depth);
}
