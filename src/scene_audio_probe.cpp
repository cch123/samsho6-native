// Replays a session like ss6-match-replay (same pad protocol and arcade
// result fixture) and drives the mixer exactly as the viewer does, printing
// one line per mixer frame: the requests, then every keyed physical voice
// with a hash of the sample it reads and its peak output in that frame.
#include "audio_routing.hpp"
#include "arcade_presentation.hpp"
#include "local_versus.hpp"
#include <array>
#include <iostream>
#include <string_view>

namespace {
uint64_t fnv(const uint8_t* p,size_t n) {
    uint64_t h=1469598103934665603ull;
    for(size_t i=0;i<n;++i){h^=p[i];h*=1099511628211ull;}
    return h;
}
// SE and voice samples keep their ADPCM bytes; music sides only their PCM.
uint64_t identity(const ss6::CombatSoundSample& s) {
    if(!s.raw.empty())return fnv(s.raw.data(),s.raw.size());
    return fnv(reinterpret_cast<const uint8_t*>(s.pcm.data()),std::min<size_t>(s.pcm.size(),112)*2);
}
}

// Every GALLERY ending playback (mode word d) as NativeMatch routes it:
// 120110's bank 49 load, then each visit's requests until 182a98 returns.
int endings(const std::filesystem::path& assets) {
    ss6::SystemData system(assets);
    ss6::SoundSelection selection(assets);
    ss6::GameRandom random;
    std::array<int16_t,2*800> pcm;
    for(int c=0;c<50;++c) {
        ss6::CombatAudio mixer(assets);
        ss6::GalleryEndingPlayer player(assets);
        player.begin(c,false);
        selection.beginFrame();selection.loadBank(0,0x31);
        for(unsigned visit=0;visit<40000;++visit) {
            std::vector<ss6::ArcadeSceneSound> requests;
            const bool done=player.tick(0,requests);
            ss6::selectEndingSounds(selection,system,requests,13,random);
            ss6::routeBattleSounds(mixer,selection.events());
            mixer.tick();mixer.render(pcm);
            std::cout<<"F "<<visit<<' '<<c<<" E";
            for(const auto& e:selection.events())std::cout<<' '<<int(e.kind)<<','<<e.bank<<','<<e.tone<<','<<e.extra;
            std::cout<<" |";
            for(unsigned i=0;i<22;++i)if(const auto* s=mixer.channelSample(i))
                std::cout<<' '<<i<<':'<<std::hex<<identity(*s)<<std::dec<<':'<<mixer.channelPeak(i);
            std::cout<<'\n';
            selection.beginFrame();
            if(done)break;
        }
    }
    return 0;
}

int main(int argc,char** argv) {
    try {
        if(argc<2)throw std::runtime_error("Expected an asset directory");
        if(argc>2&&std::string_view(argv[2])=="--endings")return endings(argv[1]);
        bool unlockModes=false;auto entry=ss6::VersusEntry::Fight;auto mode=ss6::VersusMode::FixedMatch;
        for(int i=2;i<argc;++i) {
            const std::string_view arg=argv[i];
            if(arg=="--unlock-modes")unlockModes=true;
            else if(arg=="--mode"&&i+1<argc) {
                const std::string_view name=argv[++i];
                entry=name=="title"?ss6::VersusEntry::Title:name=="select"?ss6::VersusEntry::CharacterSelect:ss6::VersusEntry::Fight;
                mode=name=="fixed-versus"?ss6::VersusMode::FixedMatch:ss6::VersusMode::Console;
            } else throw std::runtime_error("Unexpected argument");
        }
        ss6::LocalVersus session(argv[1],-1,mode,{},entry,{});
        if(unlockModes) {
            // As ss6-match-replay --unlock-modes (no save file).
            auto& data=session.system();
            data.file.clear();data.loadFile();data.option(0x7e)=1;
            session.restart();
        }
        ss6::CombatAudio mixer(argv[1]);
        unsigned tick=0;
        std::array<int16_t,2*800> pcm;
        const auto frame=[&](char kind,auto&& requests) {
            mixer.tick();
            mixer.render(pcm);
            const auto* a=session.arcade();
            std::cout<<"F "<<tick<<' '<<std::hex<<(a?uint32_t(a->scene):0u)<<std::dec<<' '<<kind;
            requests();
            std::cout<<" |";
            for(unsigned i=0;i<22;++i)if(const auto* s=mixer.channelSample(i))
                std::cout<<' '<<i<<':'<<std::hex<<identity(*s)<<std::dec<<':'<<mixer.channelPeak(i);
            std::cout<<'\n';
        };
        session.onTick([&](const ss6::NativeMatch& match) {
            const auto events=match.soundEvents();
            ss6::routeBattleSounds(mixer,events);
            frame('B',[&]{for(const auto& e:events)std::cout<<' '<<int(e.kind)<<','<<e.bank<<','<<e.tone<<','<<e.extra;});
        });
        session.onSceneSounds([&](const std::vector<ss6::ArcadeSceneSound>& sounds) {
            ss6::routeSceneSounds(mixer,session.system(),sounds);
            frame('S',[&]{for(const auto& e:sounds)std::cout<<' '<<int(e.kind)<<','<<e.a<<','<<e.b<<','<<e.c;});
        });
        std::array<uint32_t,2> previous{},held{};unsigned n;
        while(ss6::readVersusReplaySegment(std::cin,n,held)) {
            for(unsigned t=0;t<n;++t) {
                std::array<ss6::NormalizedPadSample,2> pads;
                // ss6-match-replay's arcade fixture: bit 31 / 30 / 29 of the second word.
                std::array<uint32_t,2> word=held;
                if((held[1]>>29)&&!(previous[1]>>29)) if(const auto* a=session.arcade()) {
                    const int human=int(a->run.humanSeat());
                    session.forceArcadeResult(held[1]>>31?human:(held[1]>>30)&1?human^1:-1);
                }
                word[1]&=0x1fffffffu;
                for(unsigned i=0;i<2;++i)pads[i]={word[i],word[i]&~(previous[i]&(i?0x1fffffffu:~0u))};
                session.tick(pads);previous=held;++tick;
            }
        }
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<e.what()<<'\n';
        return 1;
    }
}
