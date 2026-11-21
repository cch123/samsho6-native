#include "audio_routing.hpp"
#include <algorithm>

namespace ss6 {
namespace {
// 5a9e78, the stream volume of every request the native callers make.
constexpr int streamVolume=0x3200;
}
void routeBattleSounds(CombatAudio& mixer,std::span<const BattleSoundEvent> events) {
    using K=BattleSoundKind;
    for(const auto& e:events) switch(e.kind) {
    case K::BindPlayers:mixer.bindPlayers({unsigned(e.bank),unsigned(e.tone)});break;
    case K::Sample:mixer.play(e.bank,e.tone);break;
    case K::Voice:mixer.playVoice(e.bank,e.tone,unsigned(e.extra!=0));break;
    case K::ResidentJingle:mixer.playResidentJingle(e.tone,e.bank);break;
    case K::Stop:mixer.stop(e.tone);break;
    case K::StopGroup:mixer.stopGroup(e.tone);break;
    case K::MusicPreload:mixer.preloadMusic(e.bank,e.tone);break;
    case K::MusicStart:mixer.startMusic(e.tone);break;
    case K::MusicStop:mixer.stopMusic();break;
    case K::MusicPlay:mixer.playMusic(0,e.tone,e.bank);break;
    case K::MusicRequest:mixer.requestMusic(CombatAudio::MusicEntry(e.extra>>8),e.bank,e.tone,e.extra&0xff,streamVolume);break;
    case K::LoadBank:mixer.loadBank(e.bank+1,e.tone);break;
    }
}
void routeSceneSounds(CombatAudio& mixer,const SystemData& system,const std::vector<ArcadeSceneSound>& sounds) {
    using K=ArcadeSceneSound;
    for(const auto& e:sounds) switch(e.kind) {
    // 1e7c00 -> 213ff0 (track 23 is the resident jingle there).
    case K::Music:mixer.requestMusic(CombatAudio::MusicEntry::Play,system.setting(6)!=0,e.a,e.b,streamVolume);break;
    case K::MusicStop:mixer.stopMusic();break;
    // 1e7968 maps the EE group -1 / 0 / 1 to IOP group 0 / 1 / 2.
    case K::Sound:mixer.play(e.a+1,e.b);break;
    case K::Voice:mixer.playVoice(e.a,e.b,unsigned(system.setting(5)!=0));break;
    case K::LoadBank:mixer.loadBank(e.a+1,e.b);break;
    case K::EffectsStop:mixer.stopGroup(2);break;                // 1e7b40 -> 213be8(2)
    case K::ObjectSound:break; // ArcadePresentation lists the Sound / Voice it selects after it
    }
}
void selectEndingSounds(SoundSelection& selection,const SystemData& system,const std::vector<ArcadeSceneSound>& sounds,
                        int gameMode,GameRandom& random) {
    using K=ArcadeSceneSound;
    for(const auto& r:sounds) switch(r.kind) {
    case K::Music:selection.requestMusic(0,system.setting(6)!=0,r.a,r.b);break;
    case K::Sound:selection.sample(std::clamp(r.a,-1,1),r.b);break;
    case K::MusicStop:selection.stopMusic();break;
    case K::ObjectSound:selection.act(r.a,r.c,r.b,0,gameMode,0,random);break;
    default:break;
    }
}
}
