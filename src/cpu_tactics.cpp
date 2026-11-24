#include "asset_files.hpp"
#include "cpu_tactics.hpp"
#include <algorithm>
#include <bit>
#include <fstream>
#include <numeric>
#include <span>
#include <stdexcept>
#include <string>

namespace ss6 {
namespace {
void readTable(const std::filesystem::path& path,std::span<uint8_t> bytes) {
    std::ifstream in(resolveAsset(path),std::ios::binary);
    if(!in.read(reinterpret_cast<char*>(bytes.data()),bytes.size()) || in.peek()!=EOF)
        throw std::runtime_error("Invalid CPU table: "+path.string());
}
uint16_t word(std::span<const uint8_t> bytes,size_t offset) {
    return uint16_t(bytes[offset]|(unsigned(bytes[offset+1])<<8));
}
int drawWeighted(GameRandom& random,std::span<const uint8_t> weights) {
    // 15c050 consumes one draw even for zero total weight and assigns its
    // fallback to the last column. Skipping that draw changes later moves.
    int roll=random.bounded(std::max(1,std::accumulate(weights.begin(),weights.end(),0)));
    for(size_t i=0;i+1<weights.size();++i) {
        if(roll<weights[i])return int(i);
        roll-=weights[i];
    }
    return int(weights.size()-1);
}
}

CpuTactics::CpuTactics(const std::filesystem::path& assets,unsigned character) {
    readTable(assets/"cpu_technique_steps.bin",techniqueSteps_);
    readTable(assets/"cpu_technique_definitions.bin",techniqueDefinitions_);
    if(character>=51)throw std::out_of_range("CPU character");
    constexpr char hex[]="0123456789ABCDEF";
    std::string filename="sqData00.bin";
    filename[6]=hex[character/16];filename[7]=hex[character%16];
    readTable(assets/"cpu_technique_slots.bin",techniqueIds_);
    readTable(assets/"cpu_attack_situations.bin",attackSituations_);
    readTable(assets/"callback_special_parameters.bin",specials_);
    readTable(assets/"cpu_air_attack_timing.bin",airTimings_);
    readTable(assets/"cpu_guard_heights.bin",guardHeights_);
    readTable(assets/"projectile_descriptor_flags.bin",projectileFlags_);
    readTable(assets/"sqDataCm.bin",common_);
    readTable(assets/filename,character_);
    std::array<uint8_t,51*8> ranges;
    readTable(assets/"cpu_matchup_ranges.bin",ranges);
    // 1693f0 patches the first halfword of each eight-byte matchup record.
    // Attacker and defender contribute opposite columns in the second table.
    for(unsigned opponent=0;opponent<51;++opponent) {
        for(unsigned side=0;side<2;++side) {
            const auto value=word(ranges,8*character+4*side)+word(ranges,8*opponent+4*(1-side));
            const auto offset=0x220+0x340*side+8*opponent;
            character_[offset]=uint8_t(value);character_[offset+1]=uint8_t(value>>8);
        }
    }
}
uint8_t CpuTactics::characterByte(size_t offset) const {
    return character_.at(offset-8);
}
std::array<uint8_t,4> CpuTactics::sequence(unsigned id) const {
    if(id>255)throw std::out_of_range("CPU sequence");
    const uint8_t* row=id<128?common_.data()+0x5a0+4*id:character_.data()+0x20+4*(id-128);
    return {row[0],row[1],row[2],row[3]};
}
CpuProfileChoice CpuTactics::chooseProfile(GameRandom& random,int level,unsigned difficulty,int clock,int category) const {
    if(level<0 || clock< -1)throw std::invalid_argument("Invalid CPU profile inputs");
    CpuProfileChoice choice;
    const auto data=std::span(common_);
    const int column=random.bounded(4);
    choice.tierE4=data[(std::min(level,8)*8+std::min(difficulty,7u))*4+column];
    // Only an unlimited timer reports -1; timed rounds consume no random
    // draw for the 48-column time lookup. The table saturates at 47 seconds.
    const int timeColumn=clock==-1?random.bounded(48):std::min(clock,47);
    if(choice.tierE4>=16)throw std::runtime_error("Invalid CPU difficulty row");
    choice.patternE8=data[0x120+choice.tierE4*48+timeColumn];
    const size_t width=category==0||category==1?8:4;
    const size_t offset=category==0?0x420:category==1?0x4a0:0x520;
    const auto pattern=unsigned(choice.patternE8);
    if(pattern>=16)throw std::runtime_error("Invalid CPU profile row");
    choice.actionEC=drawWeighted(random,data.subspan(offset+width*pattern,width));
    choice.variantF0=drawWeighted(random,data.subspan(0x560+4*pattern,4));
    return choice;
}
int CpuTactics::techniqueScript(unsigned character,unsigned slot) const {
    if(character>=53 || slot>=32)throw std::out_of_range("CPU technique slot");
    return std::bit_cast<int16_t>(word(techniqueIds_,(32*character+slot)*2));
}
int CpuTactics::specialPattern(int index,bool projectile) const {
    // 168ee0 rejects missing moves before reading column 2. Projectile
    // selection (168f10) is called only with a resolved move in column 3.
    if(!projectile && (index<0 || index>=0x6a0))return 0;
    if(index<0 || index>=0x6a0)throw std::out_of_range("CPU projectile pattern");
    return specials_[4*index+(projectile?3:2)];
}
bool CpuTactics::guardsHigh(unsigned character,unsigned variant,unsigned move) const {
    if(character>=54||variant>=4||move>=96)return false;
    return guardHeights_[(character*4+variant)*12+move/8]&(1u<<(move%8));
}
int CpuTactics::techniqueStart(int script) const {
    for(size_t i=0;i<techniqueSteps_.size();i+=12)
        if(std::bit_cast<int16_t>(word(techniqueSteps_,i))==script)return int(i/12);
    return -1;
}
std::array<uint8_t,12> CpuTactics::techniqueRow(unsigned index) const {
    if(index>=techniqueSteps_.size()/12)throw std::out_of_range("CPU technique step");
    std::array<uint8_t,12> bytes;
    std::copy_n(techniqueSteps_.data()+12*index,12,bytes.begin());
    return bytes;
}
std::optional<std::array<uint8_t,12>> CpuTactics::techniqueDefinition(int character,unsigned ordinal) const {
    for(size_t i=0;i<techniqueDefinitions_.size();i+=12) {
        if(std::bit_cast<int16_t>(word(techniqueDefinitions_,i))!=character)continue;
        const auto index=i/12+ordinal;
        if(index>=techniqueDefinitions_.size()/12)throw std::out_of_range("CPU technique definition");
        std::array<uint8_t,12> bytes;
        std::copy_n(techniqueDefinitions_.data()+index*12,12,bytes.begin());
        return bytes;
    }
    return {};
}
int CpuTactics::distanceBand(unsigned pattern,ScalarFloat selfX,ScalarFloat otherX) const {
    if(pattern>=(common_.size()-0x7a0)/8)throw std::out_of_range("CPU distance pattern");
    const auto difference=selfX.sub(otherX).truncate();
    const auto distance=difference<0?std::bit_cast<int32_t>(0u-uint32_t(difference)):difference;
    const auto base=0x7a0+8*pattern;
    for(unsigned i=0;i<3;++i)
        if(distance<=std::bit_cast<int16_t>(word(common_,base+2*i)))return int(i);
    return 3;
}
}
