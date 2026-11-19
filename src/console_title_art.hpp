#pragma once

#include <array>
#include <cstdint>
#include <filesystem>
#include <span>
#include <vector>

namespace ss6 {

enum class ConsoleTitlePrompt { Hidden, Start, Wait };

class ConsoleTitleArt {
public:
    explicit ConsoleTitleArt(const std::filesystem::path& assets);
    void paint(bool modeMenu,unsigned firstRow,int scrollDirection,unsigned scrollTick,
               unsigned titleTick,unsigned idleTick,std::span<uint8_t> rgba,
               ConsoleTitlePrompt prompt=ConsoleTitlePrompt::Hidden,unsigned fadeLevel=0,bool fadeWhite=false) const;

private:
    void label(unsigned item,int y,int intensity,int opacity,std::span<uint8_t> rgba) const;
    std::array<std::vector<uint8_t>,2> backgrounds_;
    std::array<uint16_t,256> backgroundPalette_{};
    std::vector<uint8_t> font_;
    std::array<std::vector<uint8_t>,2> prompts_;
    std::array<std::array<uint8_t,4>,256> fontColors_{};
};

}
