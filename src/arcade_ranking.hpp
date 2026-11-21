#pragma once
#include "console_attract_ranking.hpp"
#include "menu_canvas.hpp"
#include "scalar_float.hpp"
#include <array>
#include <cstdint>
#include <filesystem>
#include <span>
#include <vector>

namespace ss6 {
class SystemData;
class ArcadeRun;
struct GameRandom;

// One 0x18-byte display row of 13735b0. Rows 0..4 copy the streak table
// (43d0f0), rows 5..24 the score table (43d118); see 1e88d8..1e8978.
struct RankingDisplayRow {
    int32_t index=0;            // +00: position inside its own table
    int32_t value=0;            // +04: streak or score
    int32_t spirit=0;           // +08: record byte 5 (streak) / 9 (score)
    int32_t character=0;        // +0c: record byte 4
    std::array<uint8_t,8> name{}; // +10: SJIS of 1ea578, score rows only
};
struct RankingTable {
    std::array<RankingDisplayRow,25> rows{};
    bool overseas=false;        // 585290 = byte 43d052 != 0
};
// 585294 / 585298: the grey pulse of the inserted score row (1e9c40).
struct RankingPulse {
    int32_t counter=0,direction=0;
    // Grey level of the row colour whose blue byte is `blue`, before this visit's step.
    int32_t level(int32_t blue) const {return direction?blue*counter/60:blue+(-blue*counter)/60;}
    void advance() {if(counter<60)++counter;else {counter=0;direction=!direction;}}
};

// Tables, sheets and rasteriser of the ranking scene 1e8850 (arcade_ranking.bin,
// work/ss6/extract_arcade_ranking.py; rank_obj, map_main, cloud_l, cloud_r, face).
//
// Record conventions of the emitted MenuDrawList (in addition to menu_canvas.hpp):
//  - Quad slots 0x08 rank_obj, 0x29 map_main, 0x1e cloud_l, 0x2b cloud_r and
//    0x0a face are sampled by rasterise() below; slot 0x0a carries the
//    character in `glyph` (its CLUT is the 115d40(character*5, 31) bank).
//  - Glyph and Flat records are those of MenuCanvas and are resolved by it.
class ArcadeRankingArt {
public:
    explicit ArcadeRankingArt(const std::filesystem::path& assets);
    // 1e88c0..1e8980: the display copy made at scene entry.
    RankingTable table(const SystemData& system) const;
    // The phase callback of one 1e8b38 visit for `frame` (the state the
    // callback starts from: ConsoleAttractRanking::draw). `highlight` is
    // 582450 and `pulse` the 585294/585298 pair before the visit.
    void draw(const MenuCanvas& canvas,MenuDrawList& list,const RankingFrame& frame,const RankingTable& table,
              int32_t highlight,RankingPulse pulse) const;
    // Composes the list over the existing 640x480 RGBA frame in ascending depth.
    // Phases 0..6 draw over the demonstration battle, phases 7..12 over the
    // black target of a fresh display buffer: the caller supplies either.
    void rasterise(const MenuCanvas& canvas,const MenuDrawList& list,std::span<uint8_t> rgba) const;
    // 1ea4a8: cubic Bezier of the four control pairs at table offset `at`
    // (index into the 6632c0 literal block), `steps` samples, sample `t`.
    bool bezier(std::array<ScalarFloat,2>& out,unsigned at,int steps,int t) const;
private:
    struct Record {int32_t u,v,w,h,flags,slot;};
    struct Sheet {int w=0,h=0;std::vector<uint8_t> indices;};
    using Colour=std::array<uint8_t,4>;
    void picture(const MenuCanvas& canvas,MenuDrawList& list,unsigned record,int x,int y,float z) const;
    void map(const MenuCanvas& canvas,MenuDrawList& list,int x,int y,ScalarFloat scale) const;      // 1ea3d8
    void face(const MenuCanvas& canvas,MenuDrawList& list,int character,int x,int y) const;        // 1e9870
    void ordinal(const MenuCanvas& canvas,MenuDrawList& list,int x,int y,int index,bool overseas,float z) const; // 1e99c0 / 1e9c40
    void streakRow(const MenuCanvas& canvas,MenuDrawList& list,const RankingDisplayRow& row,int x,int y,bool overseas) const; // 1e9768
    void scoreRow(const MenuCanvas& canvas,MenuDrawList& list,const RankingDisplayRow& row,int x,int y,bool overseas,
                  int32_t highlight,RankingPulse pulse) const;                                     // 1e97d8
    ScalarFloat literal(uint32_t address) const;
    std::array<Record,60> records_{};
    std::array<uint32_t,93> floats_{};
    int32_t mapSlot_=0;
    std::array<uint32_t,4> mapRect_{};
    std::array<std::array<uint8_t,2>,256> glyphs_{};
    std::array<Colour,256> rankColours_{},mapColours_{};
    std::array<Colour,16> cloudColours_{};
    std::array<std::array<Colour,16>,52> faceColours_{};
    Sheet rank_,map_,cloudLeft_,cloudRight_,face_;
};

// Scene 1e8850 (task 1e8b38, priority 14, tag 1f42, destructor 1e89f0). The
// title attract loop and the arcade Game Over (1252f0(1,1,138a48,1e8850)) and
// unlock notice (1252f0(1,1,1e6130,1e8850)) exits enter the same task; the
// only state that differs is the save image contents and 582450.
class ArcadeRanking {
public:
    ConsoleAttractRanking control;
    RankingTable table;
    int32_t highlight=-1;       // 582450 as read by 1c5280
    RankingPulse pulse;         // state after the last visit
    RankingPulse drawPulse;     // state the last visit's draw started from
    // 1e8850: 1483f8 (returned), the display copy, 585294 = 585298 = 0.
    // `held` is the direction word 1483f8 samples; `highlight` is
    // ArcadeRun::rankingHighlight (-1 in the attract loop).
    RankingDemoMatch enter(const ArcadeRankingArt& art,const SystemData& system,GameRandom& random,
                           int32_t highlight,uint32_t held=0);
    // One 1e8b38 visit after 1b9b80's START test. Returns the scene the
    // transition task has been asked for (sticky, as in ConsoleAttractRanking).
    RankingDestination tick(bool startPressed,bool& alternateDemo);
    void draw(const ArcadeRankingArt& art,const MenuCanvas& canvas,MenuDrawList& list) const {
        art.draw(canvas,list,control.draw,table,highlight,drawPulse);
    }
    // 1e89f0 at the transition midpoint: 148528 (the caller's battle), 1c5270.
    void leave(ArcadeRun& run);
};
}
