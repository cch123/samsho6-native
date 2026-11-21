#include "arcade_presentation.hpp"
#include "arcade_session.hpp"
#include "arcade_ending.hpp"
#include "combat_stage_state.hpp"
#include <algorithm>
#include <bit>
#include <cstring>
#include <type_traits>
#include <stdexcept>

namespace ss6 {
// ---------------------------------------------------------------------
// Fighter objects
ActionBank& ArcadeSceneObjects::bank(unsigned resource) {
    auto& slot=banks_[resource];
    // Muted inspection admits the ACT sound commands without a dispatcher;
    // the scene sound banks are not packaged (see ArcadePresentation::sounds).
    if(!slot)slot=std::make_unique<ActionBank>(assets_,true,resource);
    return *slot;
}
ArcadeSceneObjects::Object& ArcadeSceneObjects::at(int object) {
    const auto found=objects_.find(object);
    if(found==objects_.end())throw std::logic_error("Arcade scene object was not created");
    return found->second;
}
int ArcadeSceneObjects::create(int tag,int seat,int action,int x,int flags,int colour) {
    const int id=next_++;
    create(id,seat,action,x,0,uint32_t(flags),colour);
    objects_[id].tag=tag;
    return id;
}
void ArcadeSceneObjects::create(int object,int seat,int action,int x,int y,uint32_t flags,int colour) {
    // 11fed0(object, seat, action, x, y, flags): the body of the character bound to the seat's
    // resource slot, placed at (x, y) with the facing bit 0x80000 in object+38; +20 = colour.
    if(seat<0||seat>1)throw std::invalid_argument("Arcade scene object seat");
    Object o;
    o.seat=seat;o.character=characters[size_t(seat)];
    try {o.body=std::make_unique<PlayerObject>(bank(unsigned(o.character)),unsigned(action));}
    catch(const std::exception& error) {
        // An ACT outside the admitted subset: the object is left out of the picture and
        // counts as finished, so the scene's waits on +c0 still end.
        failures.push_back("CHARACTER "+std::to_string(o.character)+" ACTION "+std::to_string(action)+": "+error.what());
        objects_[object]=std::move(o);
        return;
    }
    o.body->timeline.setPosition(float(x),float(y));
    const auto& c=o.body->timeline.clock();
    o.body->timeline.setObjectFlags(c.objectFlags|flags,c.flags104,c.flags108);
    o.body->resourceSlot0c=uint32_t(seat);
    if(colour>=0)o.body->field20=uint32_t(colour);
    objects_[object]=std::move(o);
}
bool ArcadeSceneObjects::finished(int object) {
    const auto found=objects_.find(object);
    if(found==objects_.end())return false;
    return !found->second.body||found->second.body->timeline.clock().endReached!=0; // object+c0
}
void ArcadeSceneObjects::restart(int object,int action) {
    auto& o=at(object);
    if(!o.body)return;
    // 120390: the action restarts and +c0 clears; position and facing stay.
    try {o.body->timeline.start(bank(unsigned(o.character)).get(unsigned(action)));}
    catch(const std::exception& error) {
        failures.push_back("CHARACTER "+std::to_string(o.character)+" ACTION "+std::to_string(action)+": "+error.what());
        o.body.reset();
    }
}
void ArcadeSceneObjects::step(int object) {
    const auto found=objects_.find(object);
    if(found==objects_.end()||!found->second.body)return;
    auto& body=*found->second.body;
    // 120ce0: 120618 motion, 120880 -> 1207e8 queue copy, 120ac8 ACT clock.
    body.move(256);
    auto pose=body.childParentWords();
    pose[0x24/4]=body.timeline.action().id();
    pose[0x28/4]=body.timeline.clock().step;
    pose[0x104/4]=body.timeline.clock().flags104;
    pose[0x8c/4]=body.color8c;
    submitted.push_back(pose);
    body.animate(256);
}

// ---------------------------------------------------------------------
// Transition task 1251d0
void ArcadeTransitionTask::begin(const ArcadeTransition& t,ArcadeFade& fade) {
    request=t;phase=1;counter=0;frame={};
    fade.beginTransition(t.kind);
    if(t.kind==4)banner.begin();
}
void ArcadeTransitionTask::beginAtMidpoint(const ArcadeTransition& t,ArcadeFade& fade) {
    request=t;phase=3;counter=0;frame={};
    if(t.kind==1||t.kind==2) {
        fade.beginTransition(t.kind);
        fade.setLevel(256);
    } else phase=0;
}
int32_t ArcadeTransitionTask::worker(ArcadeFade& fade) {
    // 125498 for kinds 1 / 2: N = 10, 30, 60 by speed; the step is 0xff / N per frame.
    const int32_t n=request.speed==0?10:request.speed==1?30:request.speed==2?60:0;
    if(!n)throw std::runtime_error("1252f0 speed without a fade length");
    const uint32_t colour=request.kind==1?0xffffffffu:0xff000000u;
    switch(phase) {
    case 1:if(fade.level<0x100){fade.ramp(colour,0xff/n);return 1;}return 0;  // 125678
    case 2:return counter<2;                                                // 1256f0
    case 3:if(fade.level>0){fade.ramp(colour,-(0xff/n));return 1;}return 0;  // 125700
    default:return 0;
    }
}
ArcadeTransitionTask::Step ArcadeTransitionTask::visit(ArcadeFade& fade,bool bannerHidden) {
    if(!phase)return Step::None;
    if(request.kind==4) {
        frame=banner.tick(bannerHidden);
        if(frame.swap){phase=3;return Step::Midpoint;}
        if(frame.finished){phase=0;return Step::Finished;}
        return Step::None;
    }
    const int32_t r=worker(fade);
    ++counter;
    if(r!=0)return Step::None;
    counter=0;
    if(phase==1){phase=2;return Step::None;}
    if(phase==2){phase=3;return Step::Midpoint;}
    // 1251d0 phase 3: 3ebf18 &= ~2, g+94 = g+2c = 0.
    phase=0;fade.mode&=~2;fade.speed=0;
    return Step::Finished;
}

// ---------------------------------------------------------------------
namespace {
constexpr unsigned endingResource=endingObjectResource;
template<class T> void putBytes(std::vector<uint32_t>& out,const T& value) {
    static_assert(std::is_trivially_copyable_v<T>);
    std::vector<uint32_t> words((sizeof(T)+3)/4);
    std::memcpy(words.data(),&value,sizeof(T));
    out.insert(out.end(),words.begin(),words.end());
}
template<class T> void getBytes(std::span<const uint32_t>& in,T& value) {
    static_assert(std::is_trivially_copyable_v<T>);
    const size_t n=(sizeof(T)+3)/4;
    if(in.size()<n)throw std::invalid_argument("Truncated arcade state");
    std::memcpy(&value,in.data(),sizeof(T));
    in=in.subspan(n);
}
uint32_t checksum(const MenuDrawList& list) {
    uint32_t c=0x811c9dc5u;
    const auto mix=[&](uint32_t v){for(int i=0;i<4;++i){c^=(v>>(8*i))&0xff;c*=0x01000193u;}};
    for(const auto& r:list.records) {
        mix(uint32_t(r.kind)|uint32_t(r.font)<<8|uint32_t(r.slot)<<16|uint32_t(r.blend)<<24);
        mix(r.glyph);mix(r.colour);
        for(float f:{r.z,r.x,r.y,r.w,r.h,r.u,r.v,r.uw,r.vh})mix(std::bit_cast<uint32_t>(f));
        for(float f:r.corner)mix(std::bit_cast<uint32_t>(f));
    }
    return c;
}
// Records at or behind the queue depth of the fighter objects, and the rest.
std::array<MenuDrawList,2> split(const MenuDrawList& list,float objectDepth) {
    std::array<MenuDrawList,2> out{list,list};
    out[0].records.clear();out[1].records.clear();
    for(const auto& r:list.records)out[r.z>objectDepth].records.push_back(r);
    return out;
}
}

uint32_t arcadeDrawChecksum(const MenuDrawList& list,const MenuDrawList& back) {return checksum(list)^(checksum(back)*31u);}
std::vector<uint32_t> saveArcadeState(const ArcadeSession& session,const SystemData& system,const ArcadeMapState& map,
                                      const UnlockSessionFlags& unlock,const ArcadeEdgePulse& pulse) {
    std::vector<uint32_t> out;
    const auto& r=session.run;
    putBytes(out,r.game);putBytes(out,r.players);putBytes(out,r.versusCounters);putBytes(out,r.schedule);
    for(int32_t v:{r.intruderFight,r.mapStageIndex,r.dialoguePostFight,r.startHoldCounter,r.startHoldFlag,r.scoreShadow,r.rankingHighlight,int32_t(r.battleKind)})
        out.push_back(uint32_t(v));
    putBytes(out,r.transition);
    putBytes(out,session.random);
    putBytes(out,map);
    const auto& f=session.fade;
    for(uint32_t v:{uint32_t(f.mode),f.colour,uint32_t(f.level),uint32_t(f.speed),uint32_t(f.maximum),uint32_t(f.minimum),f.textColour,f.textShadow})
        out.push_back(v);
    const auto image=system.image();
    for(size_t i=SystemData::systemSetting;i<SystemData::ranking;i+=4) {
        uint32_t w=0;std::memcpy(&w,image.data()+i,4);out.push_back(w);
    }
    putBytes(out,unlock);putBytes(out,pulse);
    return out;
}
void loadArcadeState(std::span<const uint32_t> in,ArcadeRun& r,GameRandom& random,SystemData& system,ArcadeFade& f,
                     ArcadeMapState& map,UnlockSessionFlags& unlock,ArcadeEdgePulse& pulse) {
    getBytes(in,r.game);getBytes(in,r.players);getBytes(in,r.versusCounters);getBytes(in,r.schedule);
    std::array<int32_t,8> scalars{};getBytes(in,scalars);
    r.intruderFight=scalars[0];r.mapStageIndex=scalars[1];r.dialoguePostFight=scalars[2];r.startHoldCounter=scalars[3];
    r.startHoldFlag=scalars[4];r.scoreShadow=scalars[5];r.rankingHighlight=scalars[6];r.battleKind=uint8_t(scalars[7]);
    getBytes(in,r.transition);getBytes(in,random);getBytes(in,map);
    std::array<uint32_t,8> fade{};getBytes(in,fade);
    f.mode=int32_t(fade[0]);f.colour=fade[1];f.level=int32_t(fade[2]);f.speed=int32_t(fade[3]);
    f.maximum=int32_t(fade[4]);f.minimum=int32_t(fade[5]);f.textColour=fade[6];f.textShadow=fade[7];
    auto image=system.image();
    for(size_t i=SystemData::systemSetting;i<SystemData::ranking;i+=4) {
        if(in.empty())throw std::invalid_argument("Truncated arcade state");
        std::memcpy(image.data()+i,in.data(),4);in=in.subspan(1);
    }
    getBytes(in,unlock);getBytes(in,pulse);
}

ArcadePresentation::ArcadePresentation(const std::filesystem::path& assets,SystemData& system)
    :assets_(assets),system_(system),canvas_(assets),objects_(assets) {
    // Every table the scenes read is loaded up front, so a missing asset turns the
    // whole presentation off (ArcadeSession then skips the scenes as before).
    mapArt_=std::make_unique<ArcadeMapArt>(assets);
    talkTables_=std::make_unique<ArcadeTalkTables>(assets);
    talkArt_=std::make_unique<ArcadeTalkArt>(assets,*talkTables_);
    resultsTables_=std::make_unique<ArcadeResultsTables>(assets);
    resultsArt_=std::make_unique<ArcadeResultsArt>(assets);
    endingData_=std::make_unique<EndingData>(assets);
    endingArt_=std::make_unique<EndingArt>(assets);
    art_=std::make_unique<ArcadeArt>(assets);
    curtain_=std::make_unique<VsCurtain>(assets);
}
ArcadePresentation::~ArcadePresentation()=default;
bool ArcadePresentation::presents(ArcadeScene s) {
    using S=ArcadeScene;
    return s==S::Opening||s==S::Map||s==S::WalkIn||s==S::Dialogue||s==S::PreFinal||s==S::WinQuote||
           s==S::VersusResult||s==S::Ending||s==S::UnlockNotice||s==S::Ranking;
}
bool ArcadePresentation::alternateText() const {return system_.setting(2)!=0;}

void ArcadePresentation::setCamera(float x,float y,float z,float ox,float oy) {
    // 122e98(x, y, z) / 122eb8(ox, oy, 0). The native projection keeps the
    // ordinary horizontal offset -160 (4a2a64), which every scene camera uses.
    camera_=StageCamera{};
    camera_.projectionX=x;camera_.projectionY=y;camera_.depth=z;camera_.verticalOffset=oy;
    if(ox!=-160.f)notices.push_back("SCENE CAMERA X OFFSET "+std::to_string(int(ox))+" IS APPROXIMATED");
}
void ArcadePresentation::setCamera(const std::array<float,5>& c) {setCamera(c[0],c[1],c[2],c[3],c[4]);}

void ArcadePresentation::talkEvents(ArcadeSession& session,const std::vector<ArcadeTalkRecord>& events) {
    using E=ArcadeTalkEvent;
    auto& run=session.run;
    for(const auto& e:events) switch(e.kind) {
    case E::Music:sound(ArcadeSceneSound::Music,e.a[0],e.a[1]);break;
    case E::StopMusic:sound(ArcadeSceneSound::MusicStop);break;
    case E::Voice:sound(ArcadeSceneSound::Voice,e.a[0],e.a[1]);break;
    case E::CameraPosition:camera_.projectionX=e.f[0];camera_.projectionY=e.f[1];camera_.depth=e.f[2];break;
    case E::CameraOffset:camera_.verticalOffset=e.f[1];break;
    case E::StageBackground:stage_=e.a[0];break;
    case E::FreeStage:stage_=-1;break;
    case E::LoadCharacter:objects_.bind(unsigned(e.a[0]),e.a[1]);break;
    case E::MapResources:mapState_.reset(mapArt_->tables(),run.random());break; // 1c1e30
    case E::MapIcon:mapArt_->bindIcon(e.a[0]);break;
    case E::HandOff:handOffNext=ArcadeScene(uint32_t(e.a[1]));break;
    default:break; // portraits are read from ArcadeTalkScene::portraits; objects are already on the host
    }
}
void ArcadePresentation::resultEvents(const ArcadeResultEvents& e) {
    if(e.music>=0)sound(ArcadeSceneSound::Music,e.music,0);
    if(e.sound)sound(ArcadeSceneSound::Sound,e.soundA,e.soundB);
    if(e.voice)sound(ArcadeSceneSound::Voice,e.voiceA,e.voiceB);
}
void ArcadePresentation::endingEvents(ArcadeSession& session,const std::vector<EndingEvent>& events) {
    for(const auto& e:events) {
        endingArt_->apply(e);
        switch(e.kind) {
        case EndingEvent::Music:sound(ArcadeSceneSound::Music,e.a,e.b);break;
        case EndingEvent::MusicStop:sound(ArcadeSceneSound::MusicStop);break;
        case EndingEvent::Sound:sound(ArcadeSceneSound::Sound,e.a,e.b);break;
        case EndingEvent::ObjectSound:sound(ArcadeSceneSound::ObjectSound,e.b,int32_t(e.c));break;
        // 1a4a98(n < c): the battle stage loader 50e080[n]; the scripts name the stage of the last fight.
        case EndingEvent::BackgroundStage:stage_=session.run.game.stage;break;
        case EndingEvent::BackgroundClear:stage_=-1;break;
        default:break;
        }
    }
}
void ArcadePresentation::syncEndingFade(bool toEnding,ArcadeSession& session) {
    // The ending engine keeps the same registers (3ebf18..) in EndingFade.
    auto& a=session.fade;auto& e=ending_->playback.fade;
    if(toEnding) {e.mode=a.mode;e.colour=a.colour;e.level=a.level;e.step=a.speed;e.ceiling=a.maximum;e.floor=a.minimum;e.tones=a.flags;}
    else {a.mode=e.mode;a.colour=e.colour;a.level=e.level;a.speed=e.step;a.maximum=e.ceiling;a.minimum=e.floor;a.flags=e.tones;}
}

void ArcadePresentation::enter(ArcadeSession& session,ArcadeScene scene,uint32_t held) {
    using S=ArcadeScene;
    auto& run=session.run;auto& fade=session.fade;
    const unsigned h=run.humanSeat();
    failure.clear();
    objects_.clear();objects_.submitted.clear();
    // The entry frame has no submissions of the new scene yet (its task runs next frame).
    list_.beginFrame();back_.beginFrame();
    stage_=-1;handOffNext=S::None;
    current=scene;
    for(unsigned i=0;i<2;++i)objects_.bind(i,run.players[i].character);
    switch(scene) {
    case S::Opening:
        opening_=std::make_unique<ArcadeOpening>(*talkTables_);
        opening_->enter(run,fade,held);
        talkEvents(session,opening_->events);
        break;
    case S::Map: {
        map_.emplace();
        // 1c25a0: 11d488 for both seats.
        const auto e=map_->enter(run,mapState_,*mapArt_,objects_);
        if(e.music>=0)sound(ArcadeSceneSound::Music,e.music,0);
        setCamera(map_->camera);
        break;
    }
    case S::WalkIn:
        walkIn_.emplace();walkIn_->enter(run,*mapArt_);
        setCamera(walkIn_->camera);
        break;
    case S::Dialogue:
        dialogue_=std::make_unique<ArcadeDialogue>(*talkTables_);
        dialogue_->enter(run,fade);
        talkEvents(session,dialogue_->events);
        break;
    case S::PreFinal:
        preFinal_=std::make_unique<ArcadePreFinal>(*talkTables_);
        preFinal_->enter(run,fade);
        talkEvents(session,preFinal_->events);
        break;
    case S::WinQuote: {
        winQuote_.emplace();
        const auto e=winQuote_->enter(run,*resultsTables_);
        resultsArt_->bindBackground(0);resultsArt_->bindPortrait(winQuote_->draw.character);
        resultEvents(e);
        break;
    }
    case S::VersusResult: {
        versusResult_.emplace();
        const auto e=versusResult_->enter(run,*resultsTables_);
        resultsArt_->bindBackground(1);
        const auto& f=versusResult_->fighter;
        // 11d448 / 11d488(W, character) / 11d570 / 11d908(object, 0, 1, 0).
        objects_.bind(unsigned(f.seat),f.character);
        resultObject_=objects_.create(0xbc2,f.seat,f.action,f.x,f.flags,f.colour);
        setCamera(320,120,-400,-160,-120);
        resultEvents(e);
        break;
    }
    case S::Ending:
        ending_=std::make_unique<ArcadeEnding>(*endingData_);
        endingArt_=std::make_unique<EndingArt>(assets_);
        ending_->enter(run,alternateText());
        // 182968 loads resource "99a" into both slots; 1e79c8(0, 0x31) the scene sound bank.
        sound(ArcadeSceneSound::Music,-1,0x31);
        nameBefore_={};
        break;
    case S::UnlockNotice: {
        unlock_.emplace();
        const auto e=unlock_->enter(run,unlockSession);
        resultEvents(e);
        break;
    }
    case S::Ranking: {
        // 1e8850: 1483f8 draws the demonstration fight (battle RNG), then the display copy.
        if(!rankingArt_)rankingArt_=std::make_unique<ArcadeRankingArt>(assets_);
        ranking_=std::make_unique<ArcadeRanking>();
        ranking_->enter(*rankingArt_,system_,run.random(),run.rankingHighlight,held);
        rankingExit_=false;
        break;
    }
    default:throw std::logic_error("Not a presentation scene");
    }
    (void)h;
}
void ArcadePresentation::leave(ArcadeSession& session) {
    using S=ArcadeScene;
    auto& run=session.run;auto& fade=session.fade;
    switch(current) {
    case S::Opening:opening_->leave(run,fade);talkEvents(session,opening_->events);break;
    case S::Map:ArcadeMapScene::leave(run);break;
    case S::WalkIn:sound(ArcadeSceneSound::MusicStop);break;               // 1c44f0: 1e7ad0, 1e7b40
    case S::Dialogue:dialogue_->leave(run,fade);talkEvents(session,dialogue_->events);break;
    case S::PreFinal:preFinal_->leave(run,fade);talkEvents(session,preFinal_->events);break;
    case S::WinQuote:ArcadeWinQuote::leave(run);sound(ArcadeSceneSound::MusicStop);break; // 136288
    case S::VersusResult:sound(ArcadeSceneSound::MusicStop);break;         // 136f88
    case S::Ending:ArcadeEnding::leave(run);break;                          // 182a48
    case S::UnlockNotice:ArcadeUnlockNotice::leave(run);break;              // 1e6130
    case S::Ranking:ranking_->leave(run);break;                             // 1e89f0
    default:break;
    }
    objects_.clear();stage_=-1;resultObject_=loserObject_=-1;
    current=S::None;
}

bool ArcadePresentation::tick(ArcadeSession& session,std::array<uint32_t,2> pressed,uint32_t held) {
    using S=ArcadeScene;
    auto& run=session.run;auto& fade=session.fade;
    const unsigned h=run.humanSeat();
    handOffNext=S::None;
    objects_.submitted.clear();
    list_.beginFrame();back_.beginFrame();
    canvas_.setBrightness(system_.brightness());
    canvas_.setFade(fade.vertexFade(),fade.level,fade.colour);
    const ArcadeTalkInput input{pressed};
    bool handOff=false;
    switch(current) {
    case S::Opening: {
        // Task 1c6b10 (priority 0xa) draws the map picture and the clouds, then the coroutine runs.
        ArcadeMapFrame mapFrame;mapFrame.capture(mapState_);
        mapFrame.stage=run.game.stage;mapFrame.stageIndex=run.mapStageIndex;
        mapArt_->setFade(fade.vertexFade(),fade.level,fade.colour);
        const int before=back_.depth;
        mapArt_->ground(canvas_,back_,mapFrame);
        // 1c6b10 calls 1c2920 only: the 24 backdrop tiles of 1c2860 and their counter values are not submitted.
        const auto tiles=std::count_if(back_.records.begin(),back_.records.end(),[](const MenuDrawRecord& r){return r.slot==0x2a;});
        back_.records.erase(std::remove_if(back_.records.begin(),back_.records.end(),[](const MenuDrawRecord& r){return r.slot==0x2a;}),back_.records.end());
        for(auto& r:back_.records)r.z-=float(tiles);
        back_.depth=before+(back_.depth-before-int(tiles));
        mapArt_->clouds(canvas_,back_,mapFrame);
        mapState_.moveClouds(mapArt_->tables(),run.random());
        list_.depth=back_.depth;
        opening_->tick(run,fade,objects_,input);
        talkEvents(session,opening_->events);
        opening_->draw(canvas_,list_);
        handOff=handOffNext!=S::None;
        break;
    }
    case S::Map: {
        const auto e=map_->tick(run,mapState_,*mapArt_,objects_);
        if(e.voice>=0)sound(ArcadeSceneSound::Voice,0x31,e.voice);
        mapArt_->setFade(fade.vertexFade(),fade.level,fade.colour);
        map_->draw(*mapArt_,canvas_,list_);
        if(e.exit.requested&&e.exit.handOff){handOffNext=e.exit.next;handOff=true;}
        break;
    }
    case S::WalkIn: {
        const bool blank=fade.vertexFade()&&fade.level>=0x100;  // 3ec73c, latched by 113aa8
        const auto e=walkIn_->tick(run,mapState_,*mapArt_,objects_,held,pressed[h],alternateText(),blank);
        if(e.voice>=0)sound(ArcadeSceneSound::Voice,0x31,e.voice);
        mapArt_->setFade(fade.vertexFade(),fade.level,fade.colour);
        walkIn_->draw(*mapArt_,canvas_,list_);
        break;
    }
    case S::Dialogue:
        dialogue_->tick(run,fade,objects_,input);
        talkEvents(session,dialogue_->events);
        dialogue_->draw(canvas_,list_);
        break;
    case S::PreFinal:
        preFinal_->tick(run,fade,input);
        talkEvents(session,preFinal_->events);
        preFinal_->draw(canvas_,list_);
        break;
    case S::WinQuote: {
        resultsArt_->setFade(fade.vertexFade(),fade.level,fade.colour);
        const auto e=winQuote_->tick(run,pressed,held);
        drawArcadeWinQuote(canvas_,list_,*resultsTables_,winQuote_->draw);
        resultEvents(e);
        break;
    }
    case S::VersusResult: {
        resultsArt_->setFade(fade.vertexFade(),fade.level,fade.colour);
        const auto& objects=objects_.objects();
        const auto found=objects.find(resultObject_);
        const bool pose=found!=objects.end()&&found->second.body&&found->second.body->timeline.action().id()==0x1fb&&objects_.finished(resultObject_);
        const auto e=versusResult_->tick(run,pressed,held,pose?1:0);
        drawArcadeVersusResult(canvas_,list_,*resultsTables_,versusResult_->draw);
        // 136c58: the draw, then 11d6c8 / 11d868 / 11d730, then the counters and 11d908 at frame 64.
        objects_.step(resultObject_);
        if(e.objectAction)objects_.restart(resultObject_,e.action);
        resultEvents(e);
        break;
    }
    case S::Ending: {
        nameBefore_=ending_->nameEntry;
        syncEndingFade(true,session);
        ending_->tick(run,pressed,256);
        syncEndingFade(false,session);
        endingEvents(session,ending_->events);
        drawEnding(canvas_,list_,*endingData_,ending_->playback.frame);
        for(const auto& o:ending_->playback.frame.objects)objects_.submitted.push_back(o);
        if(nameBefore_.active) {
            // Task 1c9928: 1ca248 with the entry before its step, then 1c9ec8 after it.
            canvas_.setFade(false,0,0);
            drawArcadeNameCountdown(canvas_,back_,*resultsTables_,nameBefore_,run.game.mode);
            drawArcadeNameEntry(canvas_,back_,*resultsTables_,run.tables(),ending_->nameEntry,run.game.mode);
        }
        if(ending_->nameCommitted)session.autosave=true;
        break;
    }
    case S::Ranking: {
        // 1b9b80's START test, then 1e8b38. The destination (title, or the attract demos,
        // which are not ported and lead to the title) is requested once.
        bool alternate=false;
        const auto destination=ranking_->tick(((pressed[0]|pressed[1])&8)!=0,alternate);
        canvas_.setFade(fade.vertexFade(),fade.level,fade.colour);
        ranking_->draw(*rankingArt_,canvas_,list_);
        if(destination!=RankingDestination::None&&!rankingExit_) {
            rankingExit_=true;
            run.request(1,0,0x1e89f0,ArcadeScene(0x127940)); // the title scene
        }
        break;
    }
    case S::UnlockNotice: {
        const auto e=unlock_->tick(run,pressed);
        drawArcadeUnlockNotice(canvas_,list_,*resultsTables_,unlock_->draw,edgePulse);
        resultEvents(e);
        if(e.autosave)session.autosave=true;
        break;
    }
    default:break;
    }
    ++frame;
    return handOff;
}

void ArcadePresentation::enterLoser(ArcadeSession& session,ArcadeScene scene) {
    current=scene;objects_.clear();objects_.submitted.clear();stage_=-1;failure.clear();
    list_.beginFrame();back_.beginFrame();
    auto& run=session.run;
    for(unsigned i=0;i<2;++i)objects_.bind(i,run.players[i].character);
    const bool cont=scene==ArcadeScene::Continue;
    const int seat=cont?session.continueScene.draw.loserSeat:session.gameOver.draw.loserSeat;
    // 1a4a98(g+4): the arena of the lost fight behind the scene.
    if(cont||session.gameOver.draw.stageBackground)stage_=run.game.stage;
    setCamera(320,120,-400,-160,-120);
    loserObject_=-1;
    if(seat>=0&&seat<2) {
        // 11d570(object, seat, 0x140, 0, 0); 11d908(object, 700 / 701, 1, 0).
        const auto& p=run.players[size_t(seat)];
        objects_.bind(unsigned(seat),cont?session.continueScene.draw.loserCharacter:session.gameOver.draw.loserCharacter);
        loserObject_=objects_.create(0xbbd,seat,cont?0x700:0x701,0x140,0,cont?p.colour:-1);
    }
}
void ArcadePresentation::stepLoser() {
    objects_.submitted.clear();
    if(loserObject_>=0)objects_.step(loserObject_);
}

// ---------------------------------------------------------------------
void ArcadePresentation::stageBackground(int stage,std::span<uint8_t> rgba) {
    if(stage<0)return;
    if(!CombatStageState::supports(unsigned(stage))) {
        notices.push_back("STAGE "+std::to_string(stage)+" BACKGROUND IS IN DEVELOPMENT");
        return;
    }
    if(stageArtId_!=unsigned(stage)){stageArt_=std::make_unique<CombatStage>(assets_,unsigned(stage));stageArtId_=unsigned(stage);}
    CombatStageState state;state.stage=unsigned(stage);
    // A still backdrop from a fresh stage state. Stages after 0 draw the game
    // generator while they animate; a scratch generator keeps the session's
    // stream for the fights unchanged. The original runs the stage task during
    // the scene (1a4a98), so those draws are not reproduced here.
    GameRandom scratch;
    state.visit(StageCamera{},256,false,&scratch);
    std::vector<uint8_t> arena(640*448*4,0);
    std::array<uint16_t,1024> tones{};
    stageArt_->paint(state,tones,arena);
    std::copy(arena.begin(),arena.end(),rgba.begin());
}
void ArcadePresentation::composeObjects(std::span<uint8_t> rgba,const std::vector<AuxiliaryObject>& objects,std::array<unsigned,3> resources) {
    objectCount=objects.size();
    if(objects.empty())return;
    if(resources!=sceneResources_){scene_=std::make_unique<NativeScene>(assets_,resources);sceneResources_=resources;}
    queue_.beginFrame();
    for(const auto& o:objects)queue_.submit(o,GaugeState{});
    queue_.sort();
    std::vector<uint8_t> before(rgba.begin(),rgba.end());
    std::array<uint16_t,1024> tones{};
    // 1208b0 reads no clock or focus dimming in these scenes.
    scene_->paint(queue_,{camera_,{},-2,int(std::max(stage_,0))},EffectPalettes{},tones,rgba,{});
    // 116588 fades the character CLUTs with the scene; the native tiles carry no
    // fade, so the scene fade is applied to the pixels the objects changed.
    const auto& f=fadeShown;
    if(f.vertexFade()&&f.level>0) {
        const int level=std::min(f.level,256);
        const std::array<int,3> target{int((f.colour>>16)&0xff),int((f.colour>>8)&0xff),int(f.colour&0xff)};
        for(size_t i=0;i<rgba.size();i+=4) {
            if(rgba[i]==before[i]&&rgba[i+1]==before[i+1]&&rgba[i+2]==before[i+2])continue;
            for(unsigned c=0;c<3;++c)rgba[i+c]=uint8_t((rgba[i+c]*(256-level)+target[c]*level)>>8);
        }
    }
}
void ArcadePresentation::paint(const ArcadeSession& session,std::span<uint8_t> rgba) {
    using S=ArcadeScene;
    if(rgba.size()!=640*480*4)throw std::invalid_argument("Expected a 640x480 arcade scene surface");
    notices.clear();
    for(const auto& f:objects_.failures)notices.push_back(f.substr(0,f.find(':'))+" IS NOT DRAWN");
    for(size_t i=0;i<rgba.size();i+=4){rgba[i]=rgba[i+1]=rgba[i+2]=0;rgba[i+3]=255;}
    auto& run=session.run;
    const auto& fade=fadeShown;
    const std::array<unsigned,3> fighters{unsigned(objects_.characters[0]),unsigned(objects_.characters[1]),51};
    // Queue depth of the objects: 10000000 - z * 100 with z = 0, plus the character counter.
    constexpr float objectDepth=10000100.f;
    listChecksum=arcadeDrawChecksum(list_,back_);
    listRecords=list_.records.size()+back_.records.size();
    objectCount=0;
    paintError.clear();
    try {
    switch(current) {
    case S::Opening:
        mapArt_->setFade(fade.vertexFade(),fade.level,fade.colour);
        canvas_.setFade(fade.vertexFade(),fade.level,fade.colour);
        mapArt_->rasterise(canvas_,back_,rgba);
        composeObjects(rgba,objects_.submitted,fighters);
        talkArt_->rasterise(canvas_,list_,rgba,fade,opening_->portraits);
        break;
    case S::Map:case S::WalkIn: {
        mapArt_->setFade(fade.vertexFade(),fade.level,fade.colour);
        canvas_.setFade(fade.vertexFade(),fade.level,fade.colour);
        const auto parts=split(list_,objectDepth);
        mapArt_->rasterise(canvas_,parts[0],rgba);
        composeObjects(rgba,objects_.submitted,fighters);
        mapArt_->rasterise(canvas_,parts[1],rgba);
        break;
    }
    case S::Dialogue:case S::PreFinal: {
        ArcadeTalkScene& scene=current==S::Dialogue?static_cast<ArcadeTalkScene&>(*dialogue_):*preFinal_;
        stageBackground(stage_,rgba);
        const auto parts=split(list_,objectDepth);
        talkArt_->rasterise(canvas_,parts[0],rgba,fade,scene.portraits);
        composeObjects(rgba,objects_.submitted,fighters);
        talkArt_->rasterise(canvas_,parts[1],rgba,fade,scene.portraits);
        break;
    }
    case S::WinQuote:case S::VersusResult:case S::UnlockNotice: {
        resultsArt_->setFade(fade.vertexFade(),fade.level,fade.colour);
        canvas_.setFade(fade.vertexFade(),fade.level,fade.colour);
        const auto parts=split(list_,objectDepth);
        resultsArt_->rasterise(canvas_,parts[0],rgba);
        composeObjects(rgba,objects_.submitted,fighters);
        resultsArt_->rasterise(canvas_,parts[1],rgba);
        break;
    }
    case S::Ending: {
        const auto& f=ending_->playback.frame;
        stageBackground(stage_,rgba);
        endingArt_->setFade(f.fade);
        canvas_.setFade((f.fade.mode&2)!=0,f.fade.level,f.fade.colour);
        const auto parts=split(list_,objectDepth);
        endingArt_->rasterise(canvas_,parts[0],rgba);
        // The ending camera (4a2a58 / 4a2a64) after the visit.
        setCamera(f.camera[0],f.camera[1],f.camera[2],-160,f.cameraOffset[1]);
        composeObjects(rgba,objects_.submitted,{endingResource,endingResource,51});
        endingArt_->rasterise(canvas_,parts[1],rgba);
        if(!back_.records.empty()){resultsArt_->setFade(false,0,0);canvas_.setFade(false,0,0);resultsArt_->rasterise(canvas_,back_,rgba);}
        break;
    }
    case S::Ranking:
        // Phases 0..6 compose over the CPU demonstration fight, which is not run here.
        if(ranking_->control.draw.battleVisible())notices.push_back("RANKING DEMONSTRATION FIGHT IS NOT DRAWN");
        canvas_.setFade(fade.vertexFade(),fade.level,fade.colour);
        rankingArt_->rasterise(canvas_,list_,rgba);
        break;
    case S::Continue:case S::GameOver: {
        list_.beginFrame();
        canvas_.setBrightness(system_.brightness());
        canvas_.setFade(false,0,0);art_->setFade(false,0,0);
        const auto request=current==S::Continue
            ?drawArcadeContinue(canvas_,list_,art_->tables(),session.continueScene.draw)
            :drawArcadeGameOver(canvas_,list_,art_->tables(),session.gameOver.draw,run.game.levelEnding!=0);
        listChecksum=checksum(list_);listRecords=list_.records.size();
        stageBackground(stage_,rgba);
        art_->rasterise(canvas_,list_,rgba,0,request.underRecords);
        composeObjects(rgba,objects_.submitted,fighters);
        art_->rasterise(canvas_,list_,rgba,request.underRecords);
        break;
    }
    default:break;
    }
    } catch(const std::exception& error) {
        // A record of a sheet this composition does not load: keep the session running.
        paintError=error.what();
        notices.push_back(std::string("SCENE PICTURE INCOMPLETE: ")+error.what());
    }
    // Kind 4: the challenger banner (125c68) and the shutter over the scene.
    const auto& t=session.transitionTask();
    if(t.active()&&t.request.kind==4) {
        if(t.frame.banner) {
            MenuDrawList banner;
            canvas_.setFade(false,0,0);resultsArt_->setFade(false,0,0);
            drawArcadeBanner(canvas_,banner,*resultsTables_);
            resultsArt_->rasterise(canvas_,banner,rgba);
        }
        if(t.frame.curtain>=0)curtain_->paint(unsigned(t.frame.curtain),rgba);
    }
    for(size_t i=3;i<rgba.size();i+=4)rgba[i]=255;
}

// ---------------------------------------------------------------------
GalleryEndingPlayer::GalleryEndingPlayer(const std::filesystem::path& assets)
    :assets_(assets),canvas_(assets),data_(std::make_unique<EndingData>(assets)) {}
GalleryEndingPlayer::~GalleryEndingPlayer()=default;
void GalleryEndingPlayer::begin(int character,bool alternateText) {
    art_=std::make_unique<EndingArt>(assets_);
    playback_=std::make_unique<EndingPlayback>(*data_);
    // 182ce0: 4ef0c8 = 0 (colour), gallery exit 0x404.
    playback_->begin(EndingPlayback::Mode::Playback,unsigned(character),0,true,alternateText);
}
int GalleryEndingPlayer::galleryRow() const {return playback_?playback_->galleryRow():0;}
bool GalleryEndingPlayer::tick(uint32_t pressed,std::vector<ArcadeSceneSound>& sounds) {
    std::vector<EndingEvent> events;
    const bool done=playback_->tick(pressed,false,256,events);
    for(const auto& e:events) {
        art_->apply(e);
        if(e.kind==EndingEvent::Sound)sounds.push_back({ArcadeSceneSound::Sound,e.a,e.b});
        else if(e.kind==EndingEvent::Music)sounds.push_back({ArcadeSceneSound::Music,e.a,e.b});
        else if(e.kind==EndingEvent::MusicStop)sounds.push_back({ArcadeSceneSound::MusicStop});
    }
    if(!done) {
        list_.beginFrame();
        drawEnding(canvas_,list_,*data_,playback_->frame);
    }
    return done;
}
void GalleryEndingPlayer::paint(std::span<uint8_t> rgba) {
    for(size_t i=0;i<rgba.size();i+=4){rgba[i]=rgba[i+1]=rgba[i+2]=0;rgba[i+3]=255;}
    if(!playback_)return;
    const auto& f=playback_->frame;
    art_->setFade(f.fade);
    canvas_.setFade((f.fade.mode&2)!=0,f.fade.level,f.fade.colour);
    const auto parts=split(list_,10000100.f);
    art_->rasterise(canvas_,parts[0],rgba);
    if(!f.objects.empty()) {
        if(!scene_)scene_=std::make_unique<NativeScene>(assets_,std::array<unsigned,3>{endingResource,endingResource,51});
        StageCamera camera;
        camera.projectionX=f.camera[0];camera.projectionY=f.camera[1];camera.depth=f.camera[2];camera.verticalOffset=f.cameraOffset[1];
        queue_.beginFrame();
        for(const auto& o:f.objects)queue_.submit(o,GaugeState{});
        queue_.sort();
        std::array<uint16_t,1024> tones{};
        scene_->paint(queue_,{camera,{},-2,0},EffectPalettes{},tones,rgba,{});
    }
    art_->rasterise(canvas_,parts[1],rgba);
    for(size_t i=3;i<rgba.size();i+=4)rgba[i]=255;
}
}
