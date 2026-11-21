#include "arcade_session.hpp"
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
}
ArcadeSession::ArcadeSession(const std::filesystem::path& assets,SystemData& system)
    :system_(system),tables_(loadTables(assets)),run(*tables_,system,random) {}

void ArcadeSession::start(unsigned seat) {
    run.game.clear();
    for(unsigned i=0;i<2;++i)run.resetPlayer(i);
    run.confirmMenu(seat);
    leftToTitle=false;
    enter(run.transition.next);
}
void ArcadeSession::selected(int character,int colour,int spirit,uint32_t held) {
    auto& human=run.players[run.humanSeat()];
    human.character=character;human.colour=colour;human.spirit=spirit;
    run.selectExit(held);
    follow(held);
}
ArcadeBattleSetup ArcadeSession::enterBattle() {return run.battleSetup();}
void ArcadeSession::matchEnded(int winner,int stage,int endingChoice,int bonus,uint32_t held) {
    // 145118 publishes the result before 145628 reads it.
    run.game.winner=winner;run.game.word20[2]=stage;run.game.endingChoice=endingChoice;
    if(run.game.mode==1||run.game.mode==2)run.players[run.humanSeat()].previousCharacter=run.players[run.humanSeat()].character;
    run.matchEnd(bonus);
    follow(held);
}
void ArcadeSession::enter(ArcadeScene next) {
    scene=next;
    if(next==ArcadeScene::Continue)continueScene.enter(run,countdown);
    if(next==ArcadeScene::GameOver)gameOver.enter(run);
}
void ArcadeSession::follow(uint32_t held) {
    for(unsigned guard=0;guard<16;++guard) {
        const auto next=run.transition.next;
        const unsigned h=run.humanSeat(),c=h^1;
        auto& human=run.players[h];
        switch(next) {
        case ArcadeScene::Opening:
            // 1c6328 + 1c2420 at entry; the coroutine ends with P+18 = 1.
            run.buildSchedule(human.character,true,held);run.game.scheduleValid=1;
            run.prepareFight();human.progress=1;
            run.request(3,0,0x1c61b8,ArcadeScene::Map);
            continue;
        case ArcadeScene::Map:
            // 1c1b20: a run that did not come from the opening draws its next fight here.
            if(human.progress!=1)run.prepareFight();
            human.progress=2;
            run.request(3,0,0x1c1de8,ArcadeScene::WalkIn);
            continue;
        case ArcadeScene::WalkIn: {
            // 1c4634..1c4678: the CPU never shares the human's colour.
            auto& cpu=run.players[c];
            if(human.character!=cpu.character)cpu.colour=0;
            else if(human.colour==cpu.colour)cpu.colour=human.colour!=0?0:1;
            // 1c6068: stages 3 and 5..7 play the pre-fight dialogue unless the intruder appears.
            const int index=human.stageIndex;
            const bool dialogue=(index==3||(index>=5&&index<=7))&&run.intruderFight!=1;
            run.request(2,0,0x1c44f0,dialogue?ArcadeScene::Dialogue:ArcadeScene::Battle);
            continue;
        }
        case ArcadeScene::Dialogue:
            if(run.dialoguePostFight==0)run.request(2,0,0x1c53e0,ArcadeScene::Battle);
            else {
                run.dialoguePostFight=0; // destructor 1c53e0
                if(human.stageIndex==7)run.request(1,1,0x1c53e0,ArcadeScene::PreFinal);
                else run.request(run.intruderDue()?4:2,run.intruderDue()?1:0,0x1c53e0,ArcadeScene::Map);
            }
            continue;
        case ArcadeScene::PreFinal:
            // 1c6d50 draws the final fight; 1c7a30 marks the demo as seen.
            run.prepareFight();
            run.players[0].preFinalSeen=run.players[1].preFinalSeen=1;
            run.request(2,0,0x1c6d70,ArcadeScene::Battle);
            continue;
        case ArcadeScene::WinQuote:run.winQuoteExit(held);continue;
        case ArcadeScene::VersusResult:run.versusResultExit(held);continue;
        case ArcadeScene::Ending:
            // 182de4: the ending task records that this fighter's ending was seen.
            if(human.character>=0&&human.character<49)system_.markEndingSeen(unsigned(human.character));
            run.game.levelEnding=1;
            run.request(2,0,0x182a48,ArcadeScene::GameOver);
            continue;
        default:
            enter(next);
            return;
        }
    }
    throw std::logic_error("Arcade scene chain did not settle");
}
int ArcadeSession::tickContinue(std::array<uint32_t,2> pressed) {
    countdown.tick();
    const int sound=continueScene.tick(run,countdown,pressed);
    if(run.transition.next!=ArcadeScene::Continue){continueScene.leave(run);enter(run.transition.next);}
    return sound;
}
void ArcadeSession::tickGameOver(std::array<uint32_t,2> pressed) {
    const int seat=ArcadeGameOver::padSeat(run);
    const auto next=gameOver.tick(run,seat>=0&&seat<2?pressed[unsigned(seat)]:0,false);
    // The ranking display (1e8850) returns to the title scene.
    if(next!=ArcadeScene::None){scene=ArcadeScene::None;leftToTitle=true;}
}
}
