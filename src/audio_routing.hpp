#pragma once
#include "arcade_session.hpp"
#include "combat_audio.hpp"
#include "sound_selection.hpp"
#include "system_data.hpp"
#include <span>
#include <vector>

namespace ss6 {
// The requests of one frame, in call order, to the mixer. Shared by the
// viewer and the scene-audio validator so both drive the same paths.
void routeBattleSounds(CombatAudio& mixer,std::span<const BattleSoundEvent> events);
// Arcade presentation scenes: the soundtrack (43d056) and narration language
// (43d055) bytes are read when the request is made.
void routeSceneSounds(CombatAudio& mixer,const SystemData& system,const std::vector<ArcadeSceneSound>& sounds);
}
