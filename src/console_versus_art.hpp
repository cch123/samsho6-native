#pragma once
#include "console_versus_menu.hpp"
#include <array>
#include <filesystem>
#include <span>
#include <vector>

namespace ss6 {
class ConsoleVersusArt {
public:
    explicit ConsoleVersusArt(const std::filesystem::path& assets);
    // The original menu composes over the paused battle (including its HUD).
    void paint(const ConsoleVersusMenuDraw& draw,std::span<uint8_t> rgba) const;
private:
    struct Sprite { int width,height; std::vector<uint8_t> pixels; };
    struct Placement { unsigned sprite;int x,y; };
    std::array<std::array<uint8_t,4>,60> borders_{};
    std::vector<Sprite> sprites_;
    std::array<std::vector<Placement>,11> groups_;
    void group(unsigned index,int alpha,std::span<uint8_t> rgba) const;
};
}
