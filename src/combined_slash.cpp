#include "combined_slash.hpp"
#include "knockout.hpp"

namespace ss6 {
namespace {
void queueSlashPart(StateEntryActor& actor, int armedAction, uint32_t callback) {
    // 1494c0 reads the weapon flag again at the phase boundary.
    actor.queuedActionA3c = armedAction + !(actor.flags23c & 0x1000);
    actor.flags248 &= ~0x800u;
    actor.callbacks260[0] = callback;
    actor.callbacks260[1] = 1;
    actor.callbacks260[2] = 0xffffffff;
}
}
void beginCombinedSlash(StateEntryActor& actor) {
    queueSlashPart(actor, 264, 0x16c1d0);
    actor.flags23c |= 0x02000000;
}
void updateCombinedSlash(const PlayerObject& body, StateEntryActor& actor) {
    if (!actionEnded(body, actor.queuedActionA3c)) return;

    // 16c1d0 removes the attack flag before recovery playback begins. The
    // generic callback can return control only after this second clip ends.
    queueSlashPart(actor, 265, 0x169a50);
    actor.flags23c &= ~0x02000000u;
    actor.callbacks260[5] = 0;
}
void setCombinedSlashPause(const ReactionTables& reactions, unsigned state, bool guard,
                            ActorTimers& source, ActorTimers& target) {
    // The -2/-3 modes at 151578 read the selected reaction, including air
    // reactions. Other attacks may take their pause from a different state.
    const bool knockdown = !guard && state >= 62;
    const int scaled = 4 * reactions.descriptor(state).firstTimer;
    const int first = knockdown ? 32 : scaled;
    const int second = knockdown ? 16 : scaled;
    source.set(0, first);
    source.set(1, second);
    target.set(0, first + (state >= 3 && state <= 5 ? 2 : 0));
    target.set(1, second);
}
}
