#include "fighter_tables.hpp"
#include "fighter_roster.hpp"
#include <algorithm>
#include <fstream>
#include <stdexcept>

namespace ss6 {
namespace {
std::vector<uint8_t> readAll(const std::filesystem::path& p) {
    std::ifstream f(p,std::ios::binary);
    if(!f)throw std::runtime_error("Missing "+p.string());
    return {std::istreambuf_iterator<char>(f),{}};
}
uint32_t word(const uint8_t* p){return uint32_t(p[0])|uint32_t(p[1])<<8|uint32_t(p[2])<<16|uint32_t(p[3])<<24;}
std::vector<std::array<uint8_t,2>> pairs(const std::filesystem::path& p) {
    const auto data=readAll(p);
    if(data.size()<2||data.size()%2||data[data.size()-2]!=0xff)throw std::runtime_error("Invalid pair table "+p.string());
    std::vector<std::array<uint8_t,2>> out;
    for(size_t i=0;i+2<data.size();i+=2)out.push_back({data[i],data[i+1]});
    return out;
}
bool member(const std::vector<std::array<uint8_t,2>>& t,unsigned c,unsigned k) {
    return std::any_of(t.begin(),t.end(),[&](auto p){return p[0]==c&&p[1]==k;});
}
}
FighterTables::FighterTables(const std::filesystem::path& assets) {
    const auto stubs=readAll(assets/"fighter_stubs.bin");
    if(stubs.size()!=51*12)throw std::runtime_error("Invalid fighter_stubs.bin");
    for(unsigned c=0;c<51;++c) {
        const uint8_t* p=&stubs[c*12];
        stubs_[c]={word(p),word(p+4),p[8],p[9]};
    }
    facing_=pairs(assets/"victim_facing_pairs.bin");
    hold_=pairs(assets/"victim_hold_pairs.bin");
    const auto depth=readAll(assets/"depth_rules.bin");
    if(depth.size()<6||depth.size()%6)throw std::runtime_error("Invalid depth_rules.bin");
    for(size_t i=0;i+6<=depth.size();i+=6) {
        const auto act=int16_t(uint16_t(depth[i+2]|depth[i+3]<<8));
        if(act==-1)break;
        depth_.push_back({depth[i],unsigned(uint16_t(act)),depth[i+4]});
    }
    const auto forms=readAll(assets/"form_actions.bin");
    size_t at=0;
    for(auto& table:forms_) {
        if(at+4>forms.size())throw std::runtime_error("Invalid form_actions.bin");
        const unsigned rows=forms[at]|forms[at+1]<<8,width=forms[at+2]|forms[at+3]<<8;at+=4;
        if(width<2||width>3||at+2*width*rows>forms.size())throw std::runtime_error("Invalid form_actions.bin");
        for(unsigned r=0;r<rows;++r,at+=2*width) {
            std::array<int16_t,3> row{-1,-1,-1};
            for(unsigned k=0;k<width;++k)row[k]=int16_t(uint16_t(forms[at+2*k]|forms[at+2*k+1]<<8));
            table.push_back(row);
        }
    }
}
int FighterTables::formAction(unsigned character,uint32_t flags23c,int act,int* companion) const {
    const auto find=[&](unsigned t,unsigned column)->int {
        for(const auto& r:forms_[t])if(r[0]==act)return r[column];
        return -1;
    };
    if(companion)*companion=-1;
    if(flags23c&0x400000)return find(1,1);                                 // 14e628
    if(flags23c&0x800000){if(companion)*companion=find(2,2);return find(2,1);} // 14e680 / 14e6d8
    if(!(flags23c&0x100000))return -1;
    switch(character) {
    case 1:return find(0,1);  // 14e5d0
    case 22:return find(3,1); // 14e730
    case 23:return find(4,1); // 14e788
    case 25:return find(5,1); // 14e7e0
    default:return -1;
    }
}
uint32_t FighterTables::scriptAttack(unsigned c) const {
    if(c>=51||!scriptStubFighter(c))return 0;
    if(stubs_[c].attackForm!=1&&stubs_[c].attackForm!=2)throw std::runtime_error("Script fighter without the common attack stub");
    return stubs_[c].attack;
}
uint32_t FighterTables::scriptVictim(unsigned c) const {
    if(c>=51||!scriptStubFighter(c))return 0;
    if(stubs_[c].damageForm!=1&&stubs_[c].damageForm!=2)throw std::runtime_error("Script fighter without the common damage-source stub");
    return stubs_[c].damage;
}
bool FighterTables::noFacing(unsigned c,unsigned k) const {return member(facing_,c,k);}
bool FighterTables::weaponHold(unsigned c,unsigned k) const {return member(hold_,c,k);}
}
