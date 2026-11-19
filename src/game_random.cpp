#include "game_random.hpp"
#include <bit>

namespace ss6 {
uint32_t GameRandom::nextGame() {
    const int32_t seed=std::bit_cast<int32_t>(gameSeed);
    const int32_t quotient=seed/127773; //EE DIV truncates toward zero.
    const uint32_t remainder=gameSeed-uint32_t(quotient)*127773u;
    gameSeed=remainder*16807u-uint32_t(quotient)*2836u+1u;
    if(std::bit_cast<int32_t>(gameSeed)<0)gameSeed+=0x7fffffffu;
    return gameSeed&0x7fffffffu;
}
uint32_t GameRandom::nextLibrary() {
    //Literal64-bit multiplier read at ELF67ab58; unsigned overflow is the
    //source helper30ede0's low64-bit product, including the final +1.
    librarySeed=librarySeed*0x5851f42d4c957f2dull+1;
    return uint32_t(librarySeed>>32)&0x7fffffffu;
}
int32_t GameRandom::bounded(int32_t bound) {
    if(mode==0||mode==-2) {
        const uint32_t product=(nextLibrary()&0x7fff)*uint32_t(bound);
        return std::bit_cast<int32_t>(product)>>15;
    }
    //The game generator uses a64-bit product, unlike the library branch.
    //The original DSLL1/DSRA32 keeps the signed highword after doubling.
    const uint64_t product=uint64_t(nextGame())*uint64_t(int64_t(bound));
    return std::bit_cast<int32_t>(uint32_t((product<<1)>>32));
}
}
