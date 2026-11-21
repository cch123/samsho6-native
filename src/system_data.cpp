#include "system_data.hpp"
#include <algorithm>
#include <fstream>
#include <stdexcept>

namespace ss6 {
SystemData::SystemData(const std::filesystem::path& assets) {
    const auto file=assets/"save_default.bin";
    std::ifstream in(file,std::ios::binary|std::ios::ate);
    if(!in||in.tellg()!=std::streamoff(imageSize))throw std::runtime_error("Invalid factory save image: "+file.string());
    in.seekg(0);
    if(!in.read(reinterpret_cast<char*>(factory_.data()),imageSize))
        throw std::runtime_error("Truncated factory save image: "+file.string());
    image_=factory_;
}
void SystemData::restoreFactory() {image_=factory_;}

uint16_t SystemData::checksum(std::span<const uint8_t> bytes) {
    // CRC-16, polynomial 1021, initial value 0, most significant bit first.
    uint32_t v=0;
    for(uint8_t b:bytes) {
        v^=uint32_t(b)<<8;
        for(int i=0;i<8;++i){v<<=1;if(v&0x10000)v^=0x1021;}
    }
    return uint16_t(v);
}
std::array<uint8_t,SystemData::fileSize> SystemData::seal(std::span<const uint8_t,imageSize> image) {
    std::array<uint8_t,fileSize> file{};
    std::copy(image.begin(),image.end(),file.begin());
    // The checksum covers the whole buffer with 1234 in its own slot.
    file[0x67fe]=0x34;file[0x67ff]=0x12;
    const auto crc=checksum(file);
    file[0x67fe]=uint8_t(crc);file[0x67ff]=uint8_t(crc>>8);
    return file;
}
bool SystemData::verify(std::span<const uint8_t,fileSize> file) {
    std::array<uint8_t,fileSize> copy;
    std::copy(file.begin(),file.end(),copy.begin());
    const uint16_t stored=uint16_t(copy[0x67fe]|copy[0x67ff]<<8);
    copy[0x67fe]=0x34;copy[0x67ff]=0x12;
    return checksum(copy)==stored;
}
bool SystemData::load(const std::filesystem::path& file) {
    std::ifstream in(file,std::ios::binary|std::ios::ate);
    if(!in||in.tellg()!=std::streamoff(fileSize))return false;
    std::array<uint8_t,fileSize> bytes;
    in.seekg(0);
    if(!in.read(reinterpret_cast<char*>(bytes.data()),fileSize)||!verify(bytes))return false;
    std::copy_n(bytes.begin(),imageSize,image_.begin());
    return true;
}
void SystemData::save(const std::filesystem::path& file) const {
    const auto bytes=seal(image_);
    // Replace atomically so an interrupted write cannot leave a corrupt file.
    auto temporary=file;temporary+=".tmp";
    {
        std::ofstream out(temporary,std::ios::binary|std::ios::trunc);
        if(!out.write(reinterpret_cast<const char*>(bytes.data()),bytes.size()))
            throw std::runtime_error("Cannot write save data: "+temporary.string());
    }
    std::filesystem::rename(temporary,file);
}
int32_t SystemData::word(size_t o) const {
    return int32_t(uint32_t(image_.at(o))|uint32_t(image_.at(o+1))<<8|uint32_t(image_.at(o+2))<<16|uint32_t(image_.at(o+3))<<24);
}
void SystemData::setWord(size_t o,int32_t value) {
    for(int i=0;i<4;++i)image_.at(o+i)=uint8_t(uint32_t(value)>>(8*i));
}
std::array<int,2> SystemData::cpuMatchWins() const {
    // Jump tables 5dd058 (human) and 5dd094 (CPU) behind 111558.
    static constexpr std::array<int,15> human{2,2,2,2,3,3,3,4,4,5,1,1,1,1,1};
    static constexpr std::array<int,15> cpu{2,3,4,5,3,4,5,4,5,5,1,2,3,4,5};
    const unsigned index=option(7);
    return {human.at(index),cpu.at(index)};
}
unsigned SystemData::modeMenuUnlock() const {
    unsigned seen=0;
    for(unsigned c=0;c<49;++c)seen+=option(0x47+c)!=0;
    return unsigned(option(0x7e)==1)|unsigned(seen!=0)<<1;
}
}
