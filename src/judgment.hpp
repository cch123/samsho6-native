#pragma once
#include "action_runtime.hpp"
#include <filesystem>
#include <vector>

namespace ss6 {
struct Judgment {
    uint32_t index, metadata;
    int16_t auxiliary, x1, y1, x2, y2, tail;
    unsigned type() const { return metadata >> 26; }
};
struct Rect { int32_t left, right, bottom, top; };
struct Intersection { bool touches=false; int32_t width=0, centerX=0, centerY=0; };
class JudgmentData {
public:
    explicit JudgmentData(const std::filesystem::path& assets,unsigned resource=0);
    std::vector<Judgment> forRecord(const ActionRecord& record) const;
private:
    std::vector<Judgment> records_;
};
Rect worldRect(const Judgment& judgment, float x, float y, bool mirrorX=false, bool mirrorY=false);
bool intersect(const Rect& a, const Rect& b, Intersection& result);
} // namespace ss6
