#pragma once
#include "character_select.hpp"
#include "versus_result_art.hpp"
#include <map>
#include <optional>

namespace ss6 {
class CharacterSelectArt {
public:
    explicit CharacterSelectArt(const std::filesystem::path& assets);
    void paint(const CharacterSelect&,std::span<uint8_t> rgba) const;
private:
    struct Quad {
        int depth,x,y,right,bottom,u,v,endU,endV;
        unsigned slot,substitution,cell,blend,color;
    };
    struct Atlas {
        int width;
        std::vector<uint8_t> indices;
        std::array<uint32_t,256> palette;
    };
    struct Draw { Quad quad;const Atlas* atlas; };
    std::filesystem::path assets_;
    VersusResultArt menu_;
    std::array<std::array<int,2>,54> faces_;
    std::array<std::array<int,2>,49> names_;
    std::vector<Quad> quads_;
    void loadPages(std::istream&,unsigned count,unsigned lists,unsigned frames,unsigned family);
    void spiritSeat(const CharacterSelect&,unsigned,std::vector<Draw>&) const;
    std::vector<std::vector<unsigned>> lists_;
    std::map<std::array<unsigned,4>,unsigned> pages_;
    std::array<unsigned,31> headers_{};
    std::map<unsigned,Atlas> fixed_;
    mutable std::map<int,Atlas> portraits_;
    Atlas loadAtlas(const std::string&,int width,bool embedded) const;
    const Atlas& portrait(int id) const;
    static void raster(const Draw&,std::span<uint8_t>);
};
}
