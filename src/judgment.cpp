#include "asset_files.hpp"
#include "judgment.hpp"
#include "fighter_resource_path.hpp"
#include <algorithm>
#include <bit>
#include <cmath>
#include <fstream>
#include <stdexcept>

namespace ss6 {
JudgmentData::JudgmentData(const std::filesystem::path& assets,unsigned resource) {
    std::ifstream in(resolveAsset(fighterResourcePath(assets,"jdg",resource)),std::ios::binary|std::ios::ate);
    if (!in) throw std::runtime_error("Cannot open JDG resource");
    const auto length=in.tellg();
    if (length<=0 || length%16 || length>16*1024*1024) throw std::runtime_error("Invalid JDG size");
    std::vector<uint8_t> bytes(static_cast<size_t>(length));
    in.seekg(0);
    if (!in.read(reinterpret_cast<char*>(bytes.data()),length)) throw std::runtime_error("Truncated JDG");
    auto half=[&](size_t o) { return std::bit_cast<int16_t>(uint16_t(bytes[o]|uint16_t(bytes[o+1])<<8)); };
    for (size_t o=0; o<bytes.size(); o+=16) {
        uint32_t metadata=0;
        for (unsigned i=0; i<4; ++i) metadata |= uint32_t(bytes[o+i])<<(8*i);
        records_.push_back({uint32_t(o/16),metadata,half(o+4),half(o+6),half(o+8),half(o+10),half(o+12),half(o+14)});
    }
}
std::vector<Judgment> JudgmentData::forRecord(const ActionRecord& record) const {
    std::vector<Judgment> result;
    // 0x152fd8 takes the low THREE count bits; 0x11db40 indexes JDG directly.
    // Unlike PIL, JDG is zero-based: reference zero is a real collision box.
    for (unsigned i=0; i<(record.judgmentFlags&7); ++i) {
        const auto index=record.judgmentRefs[i];
        if (index<0 || size_t(index)>=records_.size()) throw std::runtime_error("JDG reference out of bounds");
        result.push_back(records_[size_t(index)]);
    }
    return result;
}
namespace {
int32_t truncate(float value) {
    // Inspection coordinates stay finite and small. Reject unvalidated PS2
    // exceptional conversions instead of invoking undefined C++ casts.
    if (!std::isfinite(value) || value < -2147483648.0f || value >= 2147483648.0f)
        throw std::runtime_error("JDG world coordinate outside supported range");
    return int32_t(value);
}
}
Rect worldRect(const Judgment& j, float x, float y, bool mx, bool my) {
    const int32_t left=std::min(j.x1,j.x2), bottom=std::min(j.y1,j.y2);
    const int32_t width=std::abs(int32_t(j.x2)-j.x1), height=std::abs(int32_t(j.y2)-j.y1);
    Rect r{};
    // 0x153170 truncates the first world endpoint, then derives the other
    // from that integer. Truncating both float endpoints independently is
    // different when a rectangle crosses zero at a fractional position.
    if (mx) { r.right=truncate(x-float(left)); r.left=truncate(float(r.right)-float(width)); }
    else { r.left=truncate(x+float(left)); r.right=truncate(float(r.left)+float(width)); }
    if (my) { r.top=truncate(y-float(bottom)); r.bottom=truncate(float(r.top)-float(height)); }
    else { r.bottom=truncate(y+float(bottom)); r.top=truncate(float(r.bottom)+float(height)); }
    return r;
}
bool intersect(const Rect& a, const Rect& b, Intersection& out) {
    out.touches=false;
    // 0x1532d0 uses inclusive endpoints: touching edges and a single shared
    // point count. A generic half-open rectangle intersection is incompatible.
    if (b.right<a.left || a.right<b.left || b.top<a.bottom || a.top<b.bottom) return false;
    const int32_t left=std::max(a.left,b.left), right=std::min(a.right,b.right);
    const int32_t bottom=std::max(a.bottom,b.bottom), top=std::min(a.top,b.top);
    out.touches=true;
    out.width=std::bit_cast<int32_t>(uint32_t(right)-uint32_t(left)+1);
    out.centerX=std::bit_cast<int32_t>(uint32_t(left)+uint32_t(right))/2;
    out.centerY=std::bit_cast<int32_t>(uint32_t(bottom)+uint32_t(top))/2;
    return true;
}
} // namespace ss6
