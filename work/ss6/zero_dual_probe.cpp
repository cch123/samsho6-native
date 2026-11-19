#include "local_versus.hpp"
#include <iostream>

int main(int argc, char** argv) {
    if (argc != 2) return 1;
    ss6::LocalVersus session(argv[1], -1, ss6::VersusMode::Console, {4, 4});
    std::array<unsigned, 2> previous{}, held{};
    unsigned duration;
    while (std::cin >> duration >> held[0] >> held[1]) {
        for (unsigned tick = 0; tick < duration; ++tick) {
            std::array<ss6::NormalizedPadSample, 2> pads;
            for (unsigned side = 0; side < 2; ++side)
                pads[side] = {held[side], held[side] & ~previous[side]};
            previous = held;
            session.tick(pads);
        }
        const auto& match = session.match();
        if (match.updates < 7468) continue;
        const auto& battle = match.battle();
        std::cout << match.updates;
        for (unsigned side = 0; side < 2; ++side) {
            const auto& a = match.fighter(side).actor;
            std::cout << ' ' << a.state194 << ' ' << a.systemState13c << ' ' << a.systemAmount140
                      << ' ' << a.systemTime144 << ' ' << a.systemDecay148 << ' ' << battle.gauges.words910[side]
                      << ' ' << a.fieldA30 << ' ' << match.fighter(side).body.timeline.clock().step;
        }
        std::cout << ' ' << battle.gauges.scale1239d84 << ' ' << battle.gauges.delta46a908
                  << ' ' << battle.gauges.paletteTones[512] << ' ' << battle.gauges.words910[5];
        const auto& pool = battle.entry.tasks;
        for (unsigned side = 0; side < 2; ++side) {
            // Task slots retain their old contents after reclamation. Only
            // active descriptor 1 chains belong to the current burst of rays.
            const auto tag = ((side + 4) << 16) + 0x1b5b;
            std::vector<uint32_t> chain;
            for (const auto& task : pool.tasks)
                if (task[1] == 0x10 && task[0] == 0x124898 && task[8] == 0x101 && task[5] == tag)
                    for (auto h = task[7]; h; h = pool.objects.at(h-1)[0]) chain.push_back(h);
            std::cout << ' ' << chain.size();
            for (auto h : chain) {
                const auto& obj = pool.objects.at(h-1);
                for (auto offset : {0x14,0x24,0x28,0x2c,0x30,0xc0}) std::cout << ' ' << obj[offset/4];
            }
        }
        std::cout << '\n';
    }
}
