#include "action_runtime.hpp"
#include <iostream>
#include <stdexcept>
#include <string>
#include <bit>
#include "judgment.hpp"

int main(int argc, char** argv) {
    try {
        if (argc != 4 && argc != 5) throw std::runtime_error("Usage: ss6-runtime-trace ASSETS UPDATES DELTA [ACTION]");
        const bool extended=argc==5;
        ss6::ActionClip action(argv[1],extended ? unsigned(std::stoul(argv[4])) : 0,extended);
        ss6::JudgmentData judgments(argv[1]);
        ss6::ActionTimeline timeline(action);
        const auto updates = std::stoul(argv[2]), delta = std::stoul(argv[3]);
        if (updates > 1000000 || delta > UINT32_MAX) throw std::runtime_error("Trace arguments out of bounds");
        std::cout << "update,step,time,end";
        if (extended) std::cout << ",control,flags,dx,vx,ax,dy,vy,ay,x_bits,y_bits,jdg_count,jdg_first";
        std::cout << '\n';
        for (unsigned i=0; i<=updates; ++i) {
            const auto& state = timeline.clock();
            std::cout << i << ',' << state.step << ',' << state.fractionalTime << ',' << state.endReached;
            if (extended) {
                const auto& m=timeline.motion();
                const auto boxes=judgments.forRecord(action.record(state.step));
                std::cout << ',' << state.endControl << ',' << state.objectFlags
                          << ',' << m.dx << ',' << m.vx << ',' << m.ax << ',' << m.dy << ',' << m.vy << ',' << m.ay
                          << ',' << std::bit_cast<uint32_t>(m.x) << ',' << std::bit_cast<uint32_t>(m.y)
                          << ',' << boxes.size() << ',' << (boxes.empty() ? -1 : int(boxes.front().index));
            }
            std::cout << '\n';
            if (i<updates) timeline.advance(uint32_t(delta));
        }
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
