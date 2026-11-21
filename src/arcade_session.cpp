#include "arcade_session.hpp"
#include <algorithm>
#include "arcade_presentation.hpp"
#include "arcade_ending.hpp"
#include "arcade_results.hpp"
#include "character_select.hpp"
#include <cstdio>
#include <fstream>
#include <stdexcept>
#include <vector>

namespace ss6 {
namespace {
std::unique_ptr<ArcadeTables> loadTables(const std::filesystem::path& assets) {
    const auto file=assets/"arcade_run.bin";
    std::ifstream in(file,std::ios::binary|std::ios::ate);
    if(!in||in.tellg()!=std::streamoff(ArcadeTables::byteSize))throw std::runtime_error("Invalid arcade tables: "+file.string());
    std::vector<uint8_t> bytes(ArcadeTables::byteSize);
    in.seekg(0);
    if(!in.read(reinterpret_cast<char*>(bytes.data()),bytes.size()))throw std::runtime_error("Truncated arcade tables: "+file.string());
    return std::make_unique<ArcadeTables>(bytes);
}
// 129168 draws from the other seat's random-select pool (4c8690 + d0*seat):
// every character of the active select cells.
std::span<const int32_t> randomPool() {
    static const auto pool=[] {
        std::vector<int32_t> v(CharacterSelect::randomPool.begin(),CharacterSelect::randomPool.end());
        return v;
    }();
    return pool;
}
std::string sceneName(ArcadeScene s) {
    char text[16];std::snprintf(text,sizeof text,"%x",unsigned(s));return text;
}
}
ArcadeSession::ArcadeSession(const std::filesystem::path& assets,SystemData& system)
    :system_(system),tables_(loadTables(assets)),run(*tables_,system,random),transitionTask_(std::make_unique<ArcadeTransitionTask>()) {
    try {presentation=std::make_unique<ArcadePresentation>(assets,system);}
    catch(const std::exception& error) {notice=std::string("ARCADE SCENES ARE SKIPPED: ")+error.what();}
}
ArcadeSession::~ArcadeSession()=default;

void ArcadeSession::start(unsigned seat) {
    run.game.clear();
    for(unsigned i=0;i<2;++i)run.resetPlayer(i);
    run.confirmMenu(seat);
    leftToTitle=false;
    enter(run.transition.next);
    if(presentation)presentation->log.push_back({scene,run.transition.kind,run.transition.speed,presentation->frame,{}});
}
void ArcadeSession::selected(int character,int colour,int spirit,uint32_t held) {
    auto& human=run.players[run.humanSeat()];
    human.character=character;human.colour=colour;human.spirit=spirit;
    run.transition={};
    run.selectExit(held);
    // 12f100's 1252f0(1, 1, ...) has already faded the select out (NativeMatch).
    if(presentation)arrive(held,true);
    else follow(held);
}
void ArcadeSession::versusSelected() {
    // 12eee8 -> Task_VS_Prev 125e10 (NativeMatch's face-off) -> 139760.
    selectRequested=false;
    enterScene(ArcadeScene::Battle,held_,1,1);
}
ArcadeBattleSetup ArcadeSession::enterBattle() {return run.battleSetup();}
void ArcadeSession::matchEnded(int winner,int stage,int endingChoice,int bonus,uint32_t held) {
    // 145118 publishes the result before 145628 reads it.
    run.game.winner=winner;run.game.word20[2]=stage;run.game.endingChoice=endingChoice;
    if(run.game.mode==1||run.game.mode==2)run.players[run.humanSeat()].previousCharacter=run.players[run.humanSeat()].character;
    run.transition={};
    run.matchEnd(bonus);
    if(!presentation){follow(held);return;}
    dropDeliveredSounds();
    // 145628 -> 1252f0(2, 0, 139778, next): the fade-out runs over the last fight frame.
    held_=held;
    if(run.transition.next!=ArcadeScene::None){battleOver=true;arrive(held,false);}
}
bool ArcadeSession::transitionActive() const {return transitionTask_->active();}

void ArcadeSession::arrive(uint32_t held,bool faded) {
    const auto t=run.transition;
    if(t.next==ArcadeScene::None)return;
    if(!faded&&(t.kind==1||t.kind==2||t.kind==4)) {transitionTask_->begin(t,fade);return;}
    if(faded)transitionTask_->beginAtMidpoint(t,fade);
    run.transitionMidpoint(randomPool());
    leaveScene();
    enterScene(t.next,held,t.kind,t.speed);
}
void ArcadeSession::leaveScene() {
    using K=ArcadeSceneSound;
    if(presentation&&ArcadePresentation::presents(scene))presentation->leave(*this);
    else if(scene==ArcadeScene::Continue) {
        continueScene.leave(run);
        if(presentation)presentation->sounds.push_back({K::MusicStop});                 // 137c68: 1e7ad0
    }
    else if(scene==ArcadeScene::GameOver&&!leftToTitle) {
        ArcadeGameOver::leave(run,false); // 138a48
        if(presentation){presentation->sounds.push_back({K::MusicStop});presentation->sounds.push_back({K::EffectsStop});}
    }
    if(presentation&&(scene==ArcadeScene::Continue||scene==ArcadeScene::GameOver))presentation->current=ArcadeScene::None;
}
void ArcadeSession::enterScene(ArcadeScene next,uint32_t held,int kind,int speed) {
    for(unsigned guard=0;guard<16;++guard) {
        battleOver=false;
        if(presentation&&ArcadePresentation::presents(next)) {
            try {
                auto state=saveArcadeState(*this,system_,presentation->mapState(),presentation->unlockSession,presentation->edgePulse);
                presentation->enter(*this,next,held);
                scene=next;
                presentation->log.push_back({next,kind,speed,presentation->frame,std::move(state)});
                return;
            } catch(const std::exception& error) {
                notice="SCENE "+sceneName(next)+" SKIPPED: "+error.what();
                presentation->failure=notice;presentation->current=ArcadeScene::None;
            }
            run.transition={};
            skip(next,held);
            next=run.transition.next;kind=run.transition.kind;speed=run.transition.speed;
            continue;
        }
        enter(next);
        if(presentation) {
            presentation->log.push_back({next,kind,speed,presentation->frame,{}});
            if(next==ArcadeScene::Continue||next==ArcadeScene::GameOver)presentation->enterLoser(*this,next);
            // 1376d0: 1e7c00(0x1a, 0); 138340 (every branch reaches 138474): 1e7c00(0x1b, 0).
            if(next==ArcadeScene::Continue)presentation->sounds.push_back({ArcadeSceneSound::Music,0x1a,0});
            if(next==ArcadeScene::GameOver)presentation->sounds.push_back({ArcadeSceneSound::Music,0x1b,0});
        }
        return;
    }
    throw std::logic_error("Arcade scene chain did not settle");
}
void ArcadeSession::enter(ArcadeScene next) {
    scene=next;
    if(next==ArcadeScene::Continue)continueScene.enter(run,countdown);
    if(next==ArcadeScene::GameOver)gameOver.enter(run);
    if(next==ArcadeScene::Battle)fightRequested=true;
    if(next==ArcadeScene::CharacterSelect)selectRequested=true;
    // Without the presentation (or after the ranking): the title scene 127940.
    if(next==ArcadeScene::Ranking||next==ArcadeScene::None||next==ArcadeScene(0x127940)){scene=ArcadeScene::None;leftToTitle=true;}
}

// The static fallback: the state changes of one skipped presentation scene,
// ending with the request its task would issue.
void ArcadeSession::skip(ArcadeScene next,uint32_t held) {
    const unsigned h=run.humanSeat(),c=h^1;
    auto& human=run.players[h];
    switch(next) {
    case ArcadeScene::Opening:
        // 1c6328 + 1c2420 at entry; the hand-off 1c1ac0 leaves P+18 = 1.
        run.buildSchedule(human.character,true,held);run.game.scheduleValid=1;
        run.prepareFight();human.progress=1;
        run.transition={0,0,0x1c61b8,ArcadeScene::Map};
        break;
    case ArcadeScene::Map:
        // 1c1b20: a run that did not come from the opening draws its next fight here.
        if(human.progress!=1)run.prepareFight();
        human.progress=2;
        run.transition={0,0,0x1c1de8,ArcadeScene::WalkIn};
        break;
    case ArcadeScene::WalkIn: {
        // 1c4634..1c4678: the CPU never shares the human's colour.
        auto& cpu=run.players[c];
        if(human.character!=cpu.character)cpu.colour=0;
        else if(human.colour==cpu.colour)cpu.colour=human.colour!=0?0:1;
        const bool dialogue=ArcadeWalkInScene::dialogueStage(run)&&run.intruderFight!=1;
        run.request(2,0,0x1c44f0,dialogue?ArcadeScene::Dialogue:ArcadeScene::Battle);
        break;
    }
    case ArcadeScene::Dialogue:
        if(run.dialoguePostFight==0)run.request(2,0,0x1c53e0,ArcadeScene::Battle);
        else {
            run.dialoguePostFight=0; // destructor 1c53e0
            if(human.stageIndex==7)run.request(1,1,0x1c53e0,ArcadeScene::PreFinal);
            else run.request(run.intruderDue()?4:2,run.intruderDue()?1:0,0x1c53e0,ArcadeScene::Map);
        }
        break;
    case ArcadeScene::PreFinal:
        // 1c6cc0 draws the final fight; 1c7cb0 writes only the human seat's +1c.
        run.prepareFight();
        human.preFinalSeen=1;
        run.request(1,2,0x1c6d70,ArcadeScene::Battle);
        break;
    case ArcadeScene::WinQuote:
        run.winQuoteExit(held);
        ArcadeWinQuote::leave(run); // 136288 clears g+1c after the exit has read it
        break;
    case ArcadeScene::VersusResult:run.versusResultExit(held);break;
    case ArcadeScene::Ending:
        // 182de4 / 182df0 write both clear records; 182a48 clears g+30.
        if(human.character>=0&&human.character<49)system_.markEndingSeen(unsigned(human.character));
        system_.option(size_t(0x81+human.spirit))=1;
        run.game.levelEnding=1;
        run.request(1,1,0x182a48,ArcadeScene::GameOver);
        ArcadeEnding::leave(run);
        break;
    case ArcadeScene::Ranking:run.transition={0,0,0x1e89f0,ArcadeScene(0x127940)};break;
    case ArcadeScene::UnlockNotice: {
        UnlockSessionFlags session{};
        unlockCollect(system_,session);
        run.request(1,1,0x1e6130,ArcadeScene::Ranking);
        ArcadeUnlockNotice::leave(run);
        break;
    }
    default:enter(next);run.transition={};break;
    }
}
void ArcadeSession::follow(uint32_t held) {
    for(unsigned guard=0;guard<16;++guard) {
        const auto next=run.transition.next;
        if(!ArcadePresentation::presents(next)){enter(next);return;}
        run.transition={};
        skip(next,held);
    }
    throw std::logic_error("Arcade scene chain did not settle");
}

void ArcadeSession::frameEnd() {
    if(!presentation){fade.endFrame();return;}
    presentation->fadeShown=fade;
    // 116588: the ending engine integrates the level inside its own frame.
    if(!(scene==ArcadeScene::Ending&&presentation->current==ArcadeScene::Ending))fade.endFrame();
}
void ArcadeSession::dropDeliveredSounds() {
    if(!presentation)return;
    auto& list=presentation->sounds;
    list.erase(list.begin(),list.begin()+long(std::min(soundsDelivered_,list.size())));
    soundsDelivered_=0;
}
void ArcadeSession::tickTransition() {
    // Called by LocalVersus during a fight's fade-out (delivered afterwards),
    // during a fight's fade-in (not delivered) and from tickScene.
    const bool delivering=scene==ArcadeScene::Battle&&battleOver;
    if(delivering)dropDeliveredSounds();
    struct Mark {ArcadeSession& s;bool on;~Mark(){if(on&&s.presentation)s.soundsDelivered_=s.presentation->sounds.size();}} mark{*this,delivering};
    auto& t=*transitionTask_;
    const auto step=t.visit(fade,false);
    if(presentation&&t.request.kind==4) {
        if(t.frame.voice)presentation->sounds.push_back({ArcadeSceneSound::Voice,0x31,0x4d});
        if(t.frame.stopSound)presentation->sounds.push_back({ArcadeSceneSound::Sound,-1,0xf});
    }
    if(step==ArcadeTransitionTask::Step::Midpoint) {
        // 1253e0, the old scene's destructor, then the new entry, in one visit.
        run.transition=t.request;
        run.transitionMidpoint(randomPool());
        leaveScene();
        enterScene(t.request.next,held_,t.request.kind,t.request.speed);
    } else if(step==ArcadeTransitionTask::Step::Finished) run.transitionFinished();
    frameEnd();
}
static uint32_t currentDestructor(ArcadeScene s) {
    using S=ArcadeScene;
    switch(s) {
    case S::Opening:return 0x1c61b8;case S::Map:return 0x1c1de8;case S::WalkIn:return 0x1c44f0;
    case S::Dialogue:return 0x1c53e0;case S::PreFinal:return 0x1c6d70;case S::WinQuote:return 0x136288;
    case S::VersusResult:return 0x136f88;case S::Ending:return 0x182a48;case S::UnlockNotice:return 0x1e6130;
    default:return 0;
    }
}
void ArcadeSession::tickScene(std::array<uint32_t,2> pressed,uint32_t held) {
    held_=held;autosave=false;
    if(!presentation) {
        // Static fallback: CONTINUE / GAME OVER switch scenes themselves, as before.
        if(scene==ArcadeScene::Continue)tickContinue(pressed);
        else if(scene==ArcadeScene::GameOver)tickGameOver(pressed);
        return;
    }
    dropDeliveredSounds();
    struct Mark {ArcadeSession& s;~Mark(){if(s.presentation)s.soundsDelivered_=s.presentation->sounds.size();}} mark{*this};
    // 118298 and 118148 run in the pad update before every scene task.
    run.idleRandom();
    run.transition={};
    const bool presented=presentation&&ArcadePresentation::presents(scene);
    if(presented)run.pollChallenger(pressed,currentDestructor(scene));
    bool handOff=false;
    if(presented) {
        try {handOff=presentation->tick(*this,pressed,held);}
        catch(const std::exception& error) {
            // An unported branch inside the scene: skip it as the static path did.
            notice="SCENE "+sceneName(scene)+" SKIPPED: "+error.what();
            presentation->failure=notice;presentation->current=ArcadeScene::None;
            const auto failed=scene;
            run.transition={};
            skip(failed,held);
            const auto t=run.transition;
            enterScene(t.next,held,t.kind,t.speed);
            frameEnd();
            return;
        }
    } else if(scene==ArcadeScene::Continue) {
        tickContinue(pressed);
        if(presentation)presentation->stepLoser();
    } else if(scene==ArcadeScene::GameOver) {
        tickGameOver(pressed);
        if(presentation&&scene==ArcadeScene::GameOver)presentation->stepLoser();
    }
    if(handOff) {
        // 1c1ac0: task 1c1ae8 runs the destructor and the next entry on this frame, without a fade.
        const auto next=presentation->handOffNext;
        leaveScene();
        enterScene(next,held,-1,0);
    }
    if(run.transition.next!=ArcadeScene::None) {
        const auto t=run.transition;
        if(t.kind==1||t.kind==2||t.kind==4)transitionTask_->begin(t,fade);
        else {
            // Kind 3 (CONTINUE -> select) cuts at once; the select draws its own shutter.
            run.transitionMidpoint(randomPool());
            leaveScene();
            enterScene(t.next,held,t.kind,t.speed);
        }
    }
    if(transitionTask_->active())tickTransition();
    else frameEnd();
}
int ArcadeSession::tickContinue(std::array<uint32_t,2> pressed) {
    countdown.tick();
    const int sound=continueScene.tick(run,countdown,pressed);
    if(!presentation&&run.transition.next!=ArcadeScene::Continue&&run.transition.next!=ArcadeScene::None) {
        continueScene.leave(run);enter(run.transition.next);
    }
    if(presentation&&sound>=0)presentation->sounds.push_back({ArcadeSceneSound::Sound,-1,sound});
    return sound;
}
void ArcadeSession::tickGameOver(std::array<uint32_t,2> pressed) {
    const int seat=ArcadeGameOver::padSeat(run);
    const bool pending=presentation&&unlockPending(system_,presentation->unlockSession);
    const auto next=gameOver.tick(run,seat>=0&&seat<2?pressed[unsigned(seat)]:0,pending);
    autosave=autosave||gameOver.autosave;
    if(presentation) {
        // 1387b8: the button skip's 1e7b40, then 138af0's 1e7d60(0x31, 0x4b) at frame 0x1e.
        if(gameOver.soundStopped)presentation->sounds.push_back({ArcadeSceneSound::EffectsStop});
        if(gameOver.voiceRequested)presentation->sounds.push_back({ArcadeSceneSound::Voice,0x31,0x4b});
    }
    if(next==ArcadeScene::None)return;
    if(!presentation){scene=ArcadeScene::None;leftToTitle=true;run.transition={};return;}
    if(next==ArcadeScene::UnlockNotice) {
        // 1387b8 runs 138a48 itself and calls 1e5d88 directly (no 1252f0).
        presentation->current=ArcadeScene::None;
        run.transition={};
        presentation->sounds.push_back({ArcadeSceneSound::MusicStop});presentation->sounds.push_back({ArcadeSceneSound::EffectsStop});
        enterScene(ArcadeScene::UnlockNotice,held_,0,0);
    }
    // Ranking: the white fade 1252f0(1, 1, 138a48, 1e8850) is the transition task's.
}
}
