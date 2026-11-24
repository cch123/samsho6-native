#include "asset_files.hpp"
#include "sound_selection.hpp"
#include <bit>
#include <fstream>
#include <stdexcept>

namespace ss6 {
namespace {
bool acceptsRecord(int16_t command,const ActionClock& clock) {
    return command&&command!=0x4000&&!(clock.flags104&0x200)&&
           ((clock.objectFlags&0x10000000)||!(uint16_t(command)&0x8000));
}
}
SoundSelection::SoundSelection(const std::filesystem::path& assets) {
    std::ifstream in(resolveAsset(assets/"sound_selection.bin"),std::ios::binary|std::ios::ate);
    if(!in||in.tellg()!=176)throw std::runtime_error("Invalid sound selection tables");
    std::array<uint8_t,176> bytes{};in.seekg(0);
    if(!in.read(reinterpret_cast<char*>(bytes.data()),bytes.size()))throw std::runtime_error("Truncated sound selection tables");
    for(unsigned i=0;i<table_.size();++i) {
        uint32_t word=0;for(unsigned b=0;b<4;++b)word|=uint32_t(bytes[i*4+b])<<(b*8);
        table_[i]=std::bit_cast<int32_t>(word);
    }
    for(unsigned i=0;i<categories_.size();++i) {
        categories_[i]=bytes[140+i];if(categories_[i]>2)throw std::runtime_error("Invalid sound stage category");
    }
    reset();
}
void SoundSelection::reset(){
    previous={table_[9],table_[19]};
    previousImpact_=guardVariant_=0;nextChannel_=14;beginFrame();
}
int32_t SoundSelection::resolve(int32_t command,int32_t stage,GameRandom& random) {
    if(uint32_t(command)-150>=11)return -1;
    if(command<156) {
        const unsigned group=unsigned(command-150)/3,base=group*10+unsigned(command-150)%3*3;
        unsigned choice=unsigned(random.bounded(3));
        //Only one draw: a repeated choice advances cyclically rather than
        //rerolling. All three commands in a group share the previous value.
        if(table_[base+choice]==previous[group])choice=(choice+1)%3;
        const auto result=table_[base+choice];
        if(result!=-1)previous[group]=result;
        return result;
    }
    const unsigned group=unsigned(command-156)/2;
    const unsigned category=uint32_t(stage)<12?categories_[group*12+unsigned(stage)]:0;
    return table_[20+unsigned(command-156)*3+category];
}
void SoundSelection::record(int16_t command,const ActionClock& clock,int32_t stage,GameRandom& random) {
    // Standalone muted probes still exercise the original random decision.
    if(acceptsRecord(command,clock))resolve(uint16_t(command)&0xfff,stage,random);
}
int SoundSelection::sample(int seat,int tone) {
    if(seat < -1 || seat > 1)throw std::runtime_error("Unmapped battle sound bank");
    events_.push_back({BattleSoundKind::Sample,seat+1,tone});
    // The IOP returns the next of eight physical voices, even if its
    // previous sample is still playing. Stopping it never rewinds the ring.
    const int channel=nextChannel_;
    nextChannel_=channel==21?14:channel+1;
    return channel;
}
void SoundSelection::stop(uint32_t& word) {
    if(!(word&0x4000))return;
    events_.push_back({BattleSoundKind::Stop,0,int(word&0xfff)});
    word=0;
}
void SoundSelection::cutVoice(uint32_t word) {
    if(word&0x8000)events_.push_back({BattleSoundKind::Stop,0,int(word&7)});
}
void SoundSelection::voice(int character,int tone,int language) {
    events_.push_back({BattleSoundKind::Voice,character,tone,language});
    // 213378 keys on a short physical channel for character 50 and
    // character 29's first eight spoken lines.
    if(character==50||(character==29&&tone>=0&&tone<8))nextChannel_=nextChannel_==21?14:nextChannel_+1;
}
void SoundSelection::bindPlayers(unsigned first,unsigned second) {
    events_.push_back({BattleSoundKind::BindPlayers,int(first),int(second)});
}
void SoundSelection::residentJingle(int tone,int volumeCode) {
    events_.push_back({BattleSoundKind::ResidentJingle,volumeCode,tone});
    nextChannel_=nextChannel_==21?14:nextChannel_+1;
}
void SoundSelection::stopGroup(int group) {
    events_.push_back({BattleSoundKind::StopGroup,0,group});
}
void SoundSelection::preloadMusic(int variant,int track) {
    events_.push_back({BattleSoundKind::MusicPreload,variant,track});
}
void SoundSelection::startMusic(int volume) {
    events_.push_back({BattleSoundKind::MusicStart,0,volume});
}
void SoundSelection::stopMusic() {
    events_.push_back({BattleSoundKind::MusicStop,0,0});
}
void SoundSelection::playMusic(int track,int volume) {
    events_.push_back({BattleSoundKind::MusicPlay,volume,track});
}
void SoundSelection::requestMusic(int entry,int variant,int track,int flag) {
    events_.push_back({BattleSoundKind::MusicRequest,variant,track,entry<<8|(flag&0xff)});
    // 213ff0 plays track 23 as the resident jingle on the next short voice.
    if(entry==0&&track==23)nextChannel_=nextChannel_==21?14:nextChannel_+1;
}
void SoundSelection::loadBank(int group,int bank) {
    events_.push_back({BattleSoundKind::LoadBank,group,bank});
}
void SoundSelection::enterBattleScene(bool victoryMusicGate) {
    // 139678..139688. The gated stop remains a second IOP command when
    // returning from the victory music, even after a successful first stop.
    stopMusic();
    stopGroup(2);
    if(victoryMusicGate)stopMusic();
}
int SoundSelection::record(int16_t command,const ActionClock& clock,int seat,int character,
                           uint32_t actorFlags,int gameMode,int stage,GameRandom& random) {
    if(!acceptsRecord(command,clock))return -1;
    return act(command,seat,character,actorFlags,gameMode,stage,random);
}
int SoundSelection::act(int command,int seat,int character,uint32_t actorFlags,int gameMode,int stage,GameRandom& random) {
    int id=uint16_t(command)&0xfff;
    const int picked=resolve(id,stage,random);
    // The silent sentinels apply to the lookup result only. An ordinary
    // command takes the -1 fallthrough and keeps its own number.
    if(picked==0||picked==259)return 0;
    if(picked!=-1)id=picked;
    if(gameMode!=13&&gameMode!=14&&(actorFlags&0x80)&&id>=170&&id<198)return 0;
    if(id>=300)return sample(seat,id-300);
    if(id>=260) {
        voice(character,id-260);
        return 0; // 1e8388 discards the streaming layer's result.
    }
    if(id>=170)return sample(seat,id-170);
    if(id>=100)return sample(seat,id-100);
    return sample(-1,id-1);
}
void SoundSelection::contact(unsigned group,unsigned defense,bool armed,bool finishing,bool counter,
                             int attackerAction,GameRandom& random) {
    // 156ec4: group 5 is heard as a blunt strike on hit, silent on guard.
    if(group==5) {
        if(defense)return;
        group=2;
    }
    if(defense) {
        if(defense>4)return;
        // 1e8080's material matrix for the current Haohmaru mirror:
        // a sword and Haohmaru's group-2 attack both use material 1.
        if(armed&&group<=2) {
            sample(-1,20+guardVariant_);
            guardVariant_^=1;
        } else sample(-1,14);
        return;
    }
    if(group<4) {
        int tone;
        if(finishing)tone=group<2?51:49;
        else {
            constexpr int regular[]={4,5,6,7},special[]={9,10,11,12},blunt[]={13,15,16};
            const std::span<const int> choices=group>=2?std::span<const int>(blunt):
                attackerAction>=529?std::span<const int>(special):std::span<const int>(regular);
            auto index=unsigned(random.bounded(int(choices.size())));
            if(choices[index]==previousImpact_)index=(index+1)%choices.size();
            tone=previousImpact_=choices[index];
        }
        sample(-1,tone);
    }
    if(counter)sample(-1,61);
}
}
