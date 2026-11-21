#pragma once
#include "arcade_art.hpp"
#include "arcade_session.hpp"
#include "arcade_ranking.hpp"
#include "arcade_map.hpp"
#include "arcade_results.hpp"
#include "arcade_talk.hpp"
#include "combat_stage.hpp"
#include "native_scene.hpp"
#include "player_object.hpp"
#include "vs_curtain.hpp"
#include <filesystem>
#include <map>
#include <memory>
#include <optional>
#include <span>
#include <string>
#include <vector>

namespace ss6 {
class ArcadeSession;
// arcade_ending.hpp (kept out of this header: see its inline namespace).
inline namespace arcade_scene {class EndingData;class EndingArt;class ArcadeEnding;class EndingPlayback;struct EndingEvent;}

// Fighter objects of the presentation scenes (11e2e8 / 11fed0 / 120390 /
// 120ce0 on the object queue 479250). Each object is an ordinary body of the
// character bound to its seat by 11d488; 120ce0 moves, submits and then
// advances the ACT clock, as PlayerObject does for 11d6c8 / 1207e8 / 11d730.
class ArcadeSceneObjects final:public ArcadeObjectHost,public ArcadeTalkObjects {
public:
    explicit ArcadeSceneObjects(std::filesystem::path assets):assets_(std::move(assets)) {}
    std::array<int,2> characters{0,0};            // resource of slots 0 / 1 (11d488)
    void bind(unsigned seat,int character) {characters.at(seat)=character;}
    void clear() {objects_.clear();failures.clear();}
    std::vector<std::string> failures;            // objects whose ACT is outside the admitted subset
    int create(int tag,int seat,int action,int x,int flags,int colour) override;          // map / walk-in
    void create(int object,int seat,int action,int x,int y,uint32_t flags,int colour) override; // talk scenes
    bool finished(int object) override;
    void restart(int object,int action) override;
    void action(int object,int action) override {restart(object,action);}
    void step(int object) override;
    // Records 1207e8 copied during this frame, in submission order.
    std::vector<AuxiliaryObject> submitted;
    struct Object {int seat=0,character=0,tag=0;std::unique_ptr<PlayerObject> body;}; // body null: not drawn
    const std::map<int,Object>& objects() const {return objects_;}
private:
    ActionBank& bank(unsigned resource);
    Object& at(int object);
    std::filesystem::path assets_;
    std::map<unsigned,std::unique_ptr<ActionBank>> banks_;
    std::map<int,Object> objects_;
    int next_=0x100;
};

// The transition task 1251d0 (priority 0x3c) for the kinds the arcade uses:
// 1 / 2 (white / black palette fade, speed 0 / 1 / 2 = 10 / 30 / 60 steps)
// and 4 (challenger banner and shutter). Kind 3 (the plain shutter) is drawn
// by the character select itself and is not run here.
class ArcadeTransitionTask {
public:
    enum class Step {None,Midpoint,Finished};
    ArcadeTransition request;
    int32_t phase=0,counter=0;       // 1239da4, 1239da8
    ArcadeChallengerBanner banner;
    ArcadeBannerFrame frame;         // kind 4: the visit's banner / shutter draw
    bool active() const {return phase!=0;}
    void begin(const ArcadeTransition& t,ArcadeFade& fade);          // 1252f0
    // A request whose fade-out the previous scene already ran (12f100): the
    // destructor and entry run now and the fade-in follows.
    void beginAtMidpoint(const ArcadeTransition& t,ArcadeFade& fade);
    Step visit(ArcadeFade& fade,bool bannerHidden);
private:
    int32_t worker(ArcadeFade& fade);                                // 125498
};

// Every presentation scene between the fights of an ARCADE run: the opening,
// map, walk-in, stage dialogue, pre-final demo, win quote, VS result, ending
// with its staff roll and name entry, the unlock notice, plus the drawing of
// CONTINUE and GAME OVER with their loser object. The logic of each scene is
// its validated module; this class sequences them in the original task
// order and composes their pictures with the fighter objects.
class ArcadePresentation {
public:
    explicit ArcadePresentation(const std::filesystem::path& assets,SystemData& system);
    ~ArcadePresentation();
    // Scenes whose task runs here (Continue and Game Over run in ArcadeSession).
    static bool presents(ArcadeScene scene);
    // Scene entry (1252f0 midpoint or 1c1ac0 hand-off). Throws for an
    // unported branch; the caller then skips the scene as before.
    void enter(ArcadeSession& session,ArcadeScene scene,uint32_t held);
    // The destructor of the current scene (run at the transition midpoint).
    void leave(ArcadeSession& session);
    // One frame of the current scene's task(s), before the transition task.
    // Returns true when the scene handed off (1c1ac0) to `handOffNext`.
    bool tick(ArcadeSession& session,std::array<uint32_t,2> pressed,uint32_t held);
    ArcadeScene handOffNext=ArcadeScene::None;
    // Continue / Game Over: the loser object (11d570) and its per-frame step.
    void enterLoser(ArcadeSession& session,ArcadeScene scene);
    void stepLoser();
    // 640x480 RGBA of the frame after the last tick.
    void paint(const ArcadeSession& session,std::span<uint8_t> rgba);
    // Requests of the last frame.
    std::vector<ArcadeSceneSound> sounds;
    ArcadeScene current=ArcadeScene::None;
    uint32_t frame=0;
    std::vector<ArcadeSceneEntry> log;
    std::vector<std::string> notices;          // what this frame could not draw or play
    std::string failure;                       // set when a scene threw
    std::string paintError;                    // the last paint() could not compose every record
    // Draw-list checksum of the last painted frame per scene layer (validation).
    uint32_t listChecksum=0;
    size_t listRecords=0,objectCount=0;
    ArcadeFade fadeShown;                      // the fade the frame was drawn with
    const ArcadeMapState& mapState() const {return mapState_;}
    const MenuDrawList& drawList() const {return list_;}
    UnlockSessionFlags unlockSession{};        // 13430b0.. (survival writes them)
    ArcadeEdgePulse edgePulse;                 // 584ff8 / 584ffc, never reset
    bool alternateText() const;                // byte 43d052
private:
    void sound(ArcadeSceneSound::Kind kind,int a=0,int b=0) {sounds.push_back({kind,a,b});}
    void talkEvents(ArcadeSession& session,const std::vector<ArcadeTalkRecord>& events);
    void endingEvents(ArcadeSession& session,const std::vector<EndingEvent>& events);
    void resultEvents(const ArcadeResultEvents& e);
    void setCamera(const std::array<float,5>& c);
    void setCamera(float x,float y,float z,float ox,float oy);
    void syncEndingFade(bool toEnding,ArcadeSession& session);
    void stageBackground(int stage,std::span<uint8_t> rgba);
    void composeObjects(std::span<uint8_t> rgba,const std::vector<AuxiliaryObject>& objects,std::array<unsigned,3> resources);
    std::filesystem::path assets_;
    SystemData& system_;
    MenuCanvas canvas_;
    MenuDrawList list_,back_;                  // scene queue; back_: map task of the opening / name entry overlay
    // Scene modules (loaded on first use).
    std::unique_ptr<ArcadeMapArt> mapArt_;
    ArcadeMapState mapState_;
    std::unique_ptr<ArcadeTalkTables> talkTables_;
    std::unique_ptr<ArcadeTalkArt> talkArt_;
    std::unique_ptr<ArcadeResultsTables> resultsTables_;
    std::unique_ptr<ArcadeResultsArt> resultsArt_;
    std::unique_ptr<EndingData> endingData_;
    std::unique_ptr<EndingArt> endingArt_;
    std::unique_ptr<ArcadeArt> art_;
    std::unique_ptr<VsCurtain> curtain_;
    std::optional<ArcadeMapScene> map_;
    std::optional<ArcadeWalkInScene> walkIn_;
    std::unique_ptr<ArcadeOpening> opening_;
    std::unique_ptr<ArcadeDialogue> dialogue_;
    std::unique_ptr<ArcadePreFinal> preFinal_;
    std::optional<ArcadeWinQuote> winQuote_;
    std::optional<ArcadeVersusResult> versusResult_;
    std::unique_ptr<ArcadeEnding> ending_;
    std::optional<ArcadeUnlockNotice> unlock_;
    std::unique_ptr<ArcadeRankingArt> rankingArt_;   // loaded on the first ranking
    std::unique_ptr<ArcadeRanking> ranking_;
    bool rankingExit_=false;
    ArcadeNameEntry nameBefore_;               // the entry as 1ca248 draws it (before the tick)
    // Fighter objects and their renderer.
    ArcadeSceneObjects objects_;
    int resultObject_=-1,loserObject_=-1;
    std::unique_ptr<NativeScene> scene_;
    std::array<unsigned,3> sceneResources_{~0u,~0u,~0u};
    ObjectDrawQueue queue_;
    StageCamera camera_;
    // Stage picture behind the dialogue, Continue / Game Over and the ending (1a4a98).
    int stage_=-1;                             // battle arena, -1 none
    std::unique_ptr<CombatStage> stageArt_;
    unsigned stageArtId_=~0u;
};

// Validation support: the arcade state a scene entry reads, as words (run
// records, schedule, RNG, shared map state, fade registers, the option block
// 6184..6224, unlock session words, edge pulse), and the checksum of a frame's
// draw lists (ArcadePresentation::listChecksum).
std::vector<uint32_t> saveArcadeState(const ArcadeSession& session,const SystemData& system,const ArcadeMapState& map,
                                      const UnlockSessionFlags& unlock,const ArcadeEdgePulse& pulse);
void loadArcadeState(std::span<const uint32_t> words,ArcadeRun& run,GameRandom& random,SystemData& system,ArcadeFade& fade,
                     ArcadeMapState& map,UnlockSessionFlags& unlock,ArcadeEdgePulse& pulse);
uint32_t arcadeDrawChecksum(const MenuDrawList& list,const MenuDrawList& back);

// GALLERY MODE ending playback: 182ce0 calls 182a98(c) for the character the
// selection 13f4a8 returned (mode words d / e: the 0x404 exit with sound 25,
// START does not leave). One tick() is one coroutine visit.
class GalleryEndingPlayer {
public:
    explicit GalleryEndingPlayer(const std::filesystem::path& assets);
    ~GalleryEndingPlayer();
    void begin(int character,bool alternateText);
    // `pressed`: edge word of pad 178f90. Returns true on the visit in which
    // 182a98 returned; that visit continues into 182858 / 13f4a8 (no yield).
    bool tick(uint32_t pressed,std::vector<ArcadeSceneSound>& sounds);
    void paint(std::span<uint8_t> rgba);       // 640x480
    int galleryRow() const;                    // 4eefd4
private:
    std::filesystem::path assets_;
    MenuCanvas canvas_;
    MenuDrawList list_;
    std::unique_ptr<EndingData> data_;
    std::unique_ptr<EndingArt> art_;
    std::unique_ptr<arcade_scene::EndingPlayback> playback_;
    std::unique_ptr<NativeScene> scene_;
    ObjectDrawQueue queue_;
};
}
