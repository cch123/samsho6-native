#pragma once
#include <array>
#include <cstdint>
#include <filesystem>
#include <span>
#include <vector>

namespace ss6 {
class VsCurtain {
public:
    explicit VsCurtain(const std::filesystem::path& assets);
    void paint(unsigned frame, std::span<uint8_t> rgba) const;
private:
    struct Panel { int x, y, right, bottom, u, v, endU, endV; };
    std::array<std::vector<Panel>,33> frames_;
    std::vector<std::array<uint8_t,4>> pixels_;
};
}
