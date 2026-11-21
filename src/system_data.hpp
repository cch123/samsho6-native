#pragma once
#include <array>
#include <cstdint>
#include <filesystem>
#include <span>

namespace ss6 {
// The persistent image at 5735c8 (65a8 bytes). 1b8b88 unpacks it into the
// live blocks and 1b8cf0 packs them back; natively the image is the single
// owner and the accessors below address the live fields inside it.
class SystemData {
public:
    static constexpr size_t imageSize=0x65a8,fileSize=0x6800;
    static constexpr size_t editData=4,systemSetting=0x6184,gameOption=0x618c,ranking=0x6224,
                            records4d7068=0x633c,keyMasks=0x63bc;
    // save_default.bin is the image written by the original 10f000.
    explicit SystemData(const std::filesystem::path& assets);
    void restoreFactory();
    // The PS2 file is 6800 bytes: image, zero padding and a CRC-16 at 67fe.
    // load() keeps the current image and returns false for a missing,
    // truncated or corrupt file, as 10f088 does after a failed card read.
    bool load(const std::filesystem::path& file);
    void save(const std::filesystem::path& file) const;
    static uint16_t checksum(std::span<const uint8_t> bytes); // 10dcc0
    static std::array<uint8_t,fileSize> seal(std::span<const uint8_t,imageSize> image); // 10ddd8
    static bool verify(std::span<const uint8_t,fileSize> file); // 10dd98

    uint8_t& option(size_t offset) {return image_.at(gameOption+offset);}
    uint8_t option(size_t offset) const {return image_.at(gameOption+offset);}
    uint8_t& setting(size_t offset) {return image_.at(systemSetting+offset);}
    uint8_t setting(size_t offset) const {return image_.at(systemSetting+offset);}
    int32_t autoSave() const {return word(0);}
    void setAutoSave(int32_t value) {setWord(0,value);}

    // g_GameOption 43d058.
    int gameLevel() const {return option(4);}          // 1..8
    int gameTime() const {return option(5);}           // 0: 60, 1: 90, 2: infinity
    bool arcadeRules() const {return option(6)==1;}    // 13a858
    int cpuMatchPoint() const {return option(7);}      // index 0..14
    int versusMatchPoint() const {return option(8);}   // 1..5
    int damageLevel() const {return option(9);}        // percent
    int32_t brightness() const {return word(gameOption+0xc);}
    int spiritsGauge(unsigned seat) const {return option(0x10+3*seat);}
    int mikiriGauge(unsigned seat) const {return option(0x11+3*seat);}
    int kyouchiGauge(unsigned seat) const {return option(0x12+3*seat);}
    bool fighterLocked(unsigned character) const {return option(0x16+character)!=0;}
    bool endingSeen(unsigned character) const {return option(0x47+character)!=0;}
    void markEndingSeen(unsigned character) {option(0x47+character)=1;}
    // 111558: wins needed by the human and by the CPU in a one-player match.
    std::array<int,2> cpuMatchWins() const;
    // Mode-menu row list selector (see consoleModeRows): bit 0 is byte
    // 43d0d6 == 1, bit 1 is 1e3f70's nonzero count over the 49 ending flags.
    unsigned modeMenuUnlock() const;

    int32_t word(size_t offset) const;
    void setWord(size_t offset,int32_t value);
    std::span<uint8_t,imageSize> image() {return image_;}
    std::span<const uint8_t,imageSize> image() const {return image_;}
private:
    std::array<uint8_t,imageSize> image_{},factory_{};
};
}
