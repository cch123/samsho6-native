#include "local_versus.hpp"
#include "arcade_presentation.hpp"
#include <fstream>
#include <algorithm>
#include <iostream>
#include <bit>
#include <string_view>
#include <stdexcept>

// Consume normalized inputs through the same match that drives the window.
// Each line supplies a held mask per player; the following ticks have no new
// edges until another button goes down.
int main(int argc,char** argv) {
    try {
        if(argc<2)throw std::runtime_error("Expected an asset directory");
        std::string_view trace;
        std::string arcadeDump;
        std::array<bool,2> cpuSeats{};
        auto mode=ss6::VersusMode::FixedMatch;
        bool unlockModes=false,unlockAll=false;std::string saveFile;
        int roundTime=-1;bool timed=false;auto entry=ss6::VersusEntry::Fight;std::array<unsigned,2> spirits{};
        for(int i=2;i<argc;++i) {
            const std::string_view arg=argv[i];
            if(arg=="--round-time"&&i+1<argc){roundTime=std::stoi(argv[++i]);timed=true;}
            else if(arg=="--unlock-modes")unlockModes=true; // byte 43d0d6: SURVIVAL and SPIRITS EDIT rows
            else if(arg=="--unlock-all")unlockModes=unlockAll=true; // and one seen ending: the GALLERY row
            else if(arg=="--save"&&i+1<argc)saveFile=argv[++i];
            else if(arg=="--arcade-dump"&&i+1<argc)arcadeDump=argv[++i]; // 640x480 RGBA of each segment's arcade scene
            else if(arg=="--cpu"&&i+1<argc)cpuSeats=ss6::versusCpuSeats(argv[++i]);
            else if((arg=="--p1-spirit"||arg=="--p2-spirit")&&i+1<argc)spirits[arg=="--p2-spirit"]=ss6::versusSpirit(argv[++i]);
            else if(arg=="--mode"&&i+1<argc) {
                const std::string_view name=argv[++i];
                entry=name=="title"?ss6::VersusEntry::Title:name=="select"?ss6::VersusEntry::CharacterSelect:ss6::VersusEntry::Fight;
                if(entry==ss6::VersusEntry::Fight&&name!="versus"&&name!="fixed-versus")throw std::runtime_error("Unknown match mode");
                mode=name=="fixed-versus"?ss6::VersusMode::FixedMatch:ss6::VersusMode::Console;
            } else if(trace.empty())trace=arg;
            else throw std::runtime_error("Unexpected replay argument");
        }
        const bool selectFields=trace=="--select-fields",titleFields=trace=="--title-fields";
        const bool soundFields=trace=="--sound-fields";
        const bool shakeFields=trace=="--shake-fields";
        const bool stageFields=trace=="--stage-fields",itemFields=trace=="--stage-item-fields";
        const bool resultFields=trace=="--result-fields",menuFields=trace=="--vs-menu-fields";
        const bool lifeFields=trace=="--life-hud-fields";
        const bool hudFields=trace=="--rage-hud-fields",rageFields=hudFields||trace=="--rage-fields";
        const bool mikiriFields=trace=="--mikiri-fields";
        const bool kenFields=trace=="--ken-fields";
        const bool zeroFields=trace=="--zero-fields";
        const bool spiritFields=trace=="--spirit-fields";
        const bool shinFields=trace=="--shin-fields";
        const bool wallFields=trace=="--wall-fields",whirlwindFields=shinFields||wallFields||trace=="--whirlwind-fields";
        const bool risingFields=trace=="--rising-fields",finishFields=trace=="--finish-fields";
        const bool contactFields=finishFields||whirlwindFields||risingFields||trace=="--contact-fields";
        const bool projectileFields=trace=="--projectile-fields";
        const bool practiceFields=trace=="--practice-fields";
        const bool survivalFields=trace=="--survival-fields";
        const bool sceneFields=trace=="--scene-fields";
        const bool arcadeFields=trace=="--arcade-fields";
        std::vector<uint8_t> arcadePixels(640*480*4);unsigned segment=0;
        if(!trace.empty()&&!selectFields&&!titleFields&&!soundFields&&!shakeFields&&!stageFields&&!itemFields&&!resultFields&&!menuFields&&!rageFields&&!lifeFields&&!contactFields&&!projectileFields&&!spiritFields&&!zeroFields&&!kenFields&&!mikiriFields&&!survivalFields&&!practiceFields&&!sceneFields&&!arcadeFields)
            throw std::runtime_error("Unknown replay trace");
        if(menuFields)mode=ss6::VersusMode::Console;
        ss6::LocalVersus session(argv[1],roundTime,mode,spirits,entry,cpuSeats);
        if(unlockModes||!saveFile.empty()) {
            auto& data=session.system();
            data.file=saveFile;data.loadFile();
            if(unlockModes)data.option(0x7e)=1;
            if(unlockAll&&!(data.modeMenuUnlock()&2))data.markEndingSeen(0);
            session.restart();
        }
        std::vector<ss6::BattleSoundEvent> sounds;
        ss6::GameRandom soundRandom=session.match().battle().random;
        if(soundFields)session.onTick([&](const ss6::NativeMatch& match) {
            auto frame=match.soundEvents();
            sounds.assign(frame.begin(),frame.end());
            soundRandom=match.battle().random;
        });
        std::array<uint32_t,2> previous{},held{};unsigned n;
        while(ss6::readVersusReplaySegment(std::cin,n,held)) {
            if(soundFields)sounds.clear();
            for(unsigned tick=0;tick<n;++tick) {
                std::array<ss6::NormalizedPadSample,2> pads;
                // Arcade validation fixture: bit 31 / 30 of the second word ends the running
                // arcade fight with a win of the arcade seat / of its opponent (bit 29: a draw).
                std::array<uint32_t,2> word=held;
                if(arcadeFields&&(held[1]>>29)&&!(previous[1]>>29)) if(const auto* a=session.arcade()) {
                    const int human=int(a->run.humanSeat());
                    session.forceArcadeResult(held[1]>>31?human:(held[1]>>30)&1?human^1:-1);
                }
                word[1]&=0x1fffffffu;
                for(unsigned i=0;i<2;++i)pads[i]={word[i],word[i]&~(previous[i]&(i?0x1fffffffu:~0u))};
                session.tick(pads);previous=held;
            }
            const auto& match=session.match();
            std::cout<<match.updates<<' '<<match.battle().currentState<<' '<<match.finished;
            for(unsigned i=0;i<2;++i) {
                const auto& f=match.fighter(i);const auto& t=f.body.timeline;
                std::cout<<' '<<f.actor.stateTable()<<' '<<f.actor.stateIndex()<<' '<<t.action().id()<<' '<<t.clock().step
                    <<' '<<t.motion().x<<' '<<t.motion().y<<' '<<f.actor.fieldA30<<' '<<f.hits<<' '<<f.guards<<' '<<match.battle().match.players[i].wins;
            }
            if(itemFields) {
                const auto& b=match.battle();
                const auto& d=b.stageItems;
                std::cout<<' '<<b.stageItemsOption4c3828<<' '<<b.lastItemSecond<<' '<<b.timers.values[3]
                         <<' '<<d.busy()<<' '<<d.courierActive()<<' '<<d.itemIndex()<<' '<<d.itemX()
                         <<' '<<d.courier()[0x24/4]<<' '<<d.item()[0x24/4]<<' '<<d.itemCallback()
                         <<' '<<match.fighter(0).actor.pickedItemA40<<' '<<match.fighter(1).actor.pickedItemA40
                         <<' '<<b.itemNotices.draws().size();
                // Read each registry independently: both sides of a bomb stay
                // in the stage registry even when one of the fighters throws it.
                auto items=[&](std::span<const uint32_t> registry) {
                    unsigned count=0;int action=-1;float x=0;
                    for(auto task:registry)if(task) {
                        const auto& o=b.entry.tasks.objects.at(b.entry.tasks.tasks.at(task-1)[7]-1);
                        if(o[0xcc/4]!=5)continue;
                        if(!count){action=int(o[0x24/4]);x=std::bit_cast<float>(o[0x40/4]);}
                        ++count;
                    }
                    std::cout<<' '<<count<<' '<<action<<' '<<x;
                };
                items(b.objectTasks);
                for(unsigned side=0;side<2;++side)items(match.fighter(side).storage.objectTasks);
            }
            if(soundFields) {
                std::cout<<' '<<soundRandom.gameSeed<<' '<<soundRandom.librarySeed<<' '<<sounds.size();
                for(const auto& sound:sounds)std::cout<<' '<<int(sound.kind)<<' '<<sound.bank<<' '<<sound.tone;
            }
            if(practiceFields) {
                // Columns from 23: scene words, then the practice window, counters and both actors.
                const auto& b=match.battle();
                const auto* p=match.practiceBattle();
                const auto state=match.practiceState();
                std::cout<<' '<<b.gameMode<<' '<<bool(match.title())<<' '<<bool(match.characterSelect())<<' '<<bool(match.faceoff())
                         <<' '<<bool(session.practice())<<' '<<bool(p)<<' '<<b.requestedState<<' '<<b.match.roundIndex;
                if(p&&state) {
                    const auto& w=p->window;const auto& s=state->settings;
                    std::cout<<' '<<w.state<<' '<<w.lastState<<' '<<w.menu.rows.value<<' '<<w.menu.level<<' '<<w.menu.values.value
                             <<' '<<w.confirm.choice.value<<' '<<state->recording<<' '<<state->replay
                             <<' '<<p->damage.last<<' '<<p->damage.total<<' '<<p->damage.maxDamage<<' '<<p->damage.newCombo
                             <<' '<<p->resets<<' '<<p->exit<<' '<<p->exitDone<<' '<<p->pauseRequested
                             <<' '<<s.committedA[2]<<' '<<s.committedA[3]<<' '<<s.committedA[5]<<' '<<s.committedA[6]<<' '<<s.committedB[0]
                             <<' '<<s.committedB[6]<<' '<<s.committedB[10]<<' '<<p->keys.index<<' '<<p->keys.shown[unsigned(p->keys.index)];
                    for(unsigned i=0;i<2;++i) {
                        const auto& f=match.fighter(i);const auto& a=f.actor;
                        std::cout<<' '<<a.controlKindA20<<' '<<int32_t(a.controlModeC8)<<' '<<a.flags240<<' '<<f.sampling.replayIndex
                                 <<' '<<a.maximumLifeA34<<' '<<a.rageState120<<' '<<a.rageAmount124<<' '<<a.timers[28]<<' '<<match.cpuLevel(i)
                                 <<' '<<a.flags23c;
                    }
                    std::cout<<' '<<b.random.gameSeed;
                }
            }
            if(survivalFields) {
                const auto& b=match.battle();
                const auto* run=session.survival();
                const auto* arcade=session.arcade();
                std::cout<<' '<<b.gameMode<<' '<<bool(match.title())<<' '<<bool(match.characterSelect())<<' '<<bool(run)
                         <<' '<<(arcade?int(arcade->scene):-1)<<' '<<session.matchNumber()<<' '<<b.requestedState
                         <<' '<<b.timers.values[0]<<' '<<b.remainingSeconds()<<' '<<b.random.gameSeed<<' '<<b.matchEnd.metadataStage04
                         <<' '<<b.match.result.winner<<' '<<b.matchEnd.winner08;
                if(run) {
                    const auto& r=run->run;const auto& t=r.table;
                    const unsigned h=unsigned(run->humanSeat());
                    std::cout<<' '<<r.state<<' '<<r.prev<<' '<<r.delay<<' '<<r.fade<<' '<<t.wins<<' '<<r.wins<<' '<<r.elapsedFrames
                             <<' '<<r.savedLife<<' '<<r.savedClock<<' '<<r.pendingReward<<' '<<r.lifeGain<<' '<<r.clockGain
                             <<' '<<r.messageTimer<<' '<<r.messageText<<' '<<r.cursor<<' '<<r.selectorFocus<<' '<<r.hud.line
                             <<' '<<run->pauseRequested<<' '<<run->notice.empty();
                    for(const auto* c:{&r.rows[0],&r.rows[1],&r.rows[2],&t.current})
                        std::cout<<' '<<c->stage<<' '<<c->humanSpirit<<' '<<c->character<<' '<<c->colour<<' '<<c->reward<<' '<<c->mission;
                    const auto& u=run->setup;
                    std::cout<<' '<<u.level<<' '<<u.stage;
                    for(unsigned i=0;i<2;++i)std::cout<<' '<<u.control[i]<<' '<<u.character[i]<<' '<<u.colour[i]<<' '<<u.spirit[i];
                    for(unsigned i=0;i<2;++i) {
                        const auto& f=match.fighter(i);
                        std::cout<<' '<<f.actor.characterA14<<' '<<f.config.system<<' '<<f.actor.controlKindA20<<' '<<match.cpuLevel(i)
                                 <<' '<<f.actor.flags248<<' '<<b.match.players[i].outcome1c<<' '<<b.match.players[i].outcome20;
                    }
                    for(auto v:r.mission)std::cout<<' '<<v;
                    for(auto v:match.fighter(h).actor.characterBytesF22)std::cout<<' '<<unsigned(v);
                    const auto record=ss6::survivalRecord(session.system(),unsigned(ss6::survivalRecordIndex(run->config[h])));
                    std::cout<<' '<<record.wins<<' '<<record.seconds;
                } else if(arcade) {
                    const auto& g=arcade->run.game;
                    const auto& p=arcade->run.players[g.mode==2?1:0];
                    const auto record=ss6::survivalRecord(session.system(),unsigned(p.character));
                    std::cout<<' '<<g.mode<<' '<<g.submode<<' '<<g.winner<<' '<<arcade->gameOver.frame<<' '<<p.character
                             <<' '<<record.wins<<' '<<record.seconds<<' '<<session.arcadeNotice().empty();
                }
            }
            if(arcadeFields) {
                // Columns from 23: the arcade session, its transition task, the run words and
                // the presentation picture (checksum of its draw lists, record / object counts).
                const auto* a=session.arcade();
                if(!a)std::cout<<" -1";
                else {
                    const auto& r=a->run;const auto& g=r.game;const auto& t=a->transitionTask();
                    const auto& p=r.players[r.humanSeat()];
                    auto* pres=a->presentation.get();
                    uint32_t check=0;size_t records=0,objects=0;
                    const bool picture=pres&&(ss6::ArcadePresentation::presents(a->scene)||
                        ((a->scene==ss6::ArcadeScene::Continue||a->scene==ss6::ArcadeScene::GameOver)&&pres->current==a->scene));
                    if(picture) {
                        pres->paint(*a,arcadePixels);
                        check=pres->listChecksum;records=pres->listRecords;objects=pres->objectCount;
                        if(!arcadeDump.empty()) {
                            std::ofstream out(arcadeDump+"/"+std::to_string(segment)+".rgba",std::ios::binary);
                            out.write(reinterpret_cast<const char*>(arcadePixels.data()),std::streamsize(arcadePixels.size()));
                        }
                    }
                    std::cout<<' '<<std::hex<<unsigned(a->scene)<<' '<<unsigned(pres?pres->current:ss6::ArcadeScene::None)<<std::dec
                             <<' '<<t.active()<<' '<<t.phase<<' '<<t.request.kind<<' '<<t.request.speed<<' '<<a->fade.level<<' '<<a->fade.mode
                             <<' '<<g.mode<<' '<<g.stage<<' '<<p.stageIndex<<' '<<p.progress<<' '<<p.preFinalSeen<<' '<<g.versusInterrupted
                             <<' '<<g.challengerInhibit<<' '<<g.transitionLock<<' '<<g.levelEnding<<' '<<g.score<<' '<<g.winner<<' '<<g.versusStreak
                             <<' '<<(pres?pres->frame:0)<<' '<<check<<' '<<records<<' '<<objects<<' '<<(a->notice.empty()?0:1)
                             <<' '<<(pres?pres->log.size():0)<<' '<<a->gameOver.frame<<' '<<a->continueScene.frame
                             <<' '<<unsigned(session.system().option(size_t(0x47+std::clamp(p.character,0,48))))
                             <<' '<<a->random.librarySeed<<' '<<a->random.gameSeed<<' '<<p.character<<' '<<r.players[r.humanSeat()^1].character
                             <<' '<<a->battleOver<<' '<<r.intruderFight<<' '<<r.dialoguePostFight<<' '<<picture
                             <<' '<<(pres&&!pres->paintError.empty()?1:0);
                    // Diagnostic text for a scene frame that could not be composed.
                    if(pres&&!pres->paintError.empty())std::cerr<<"paint error at frame "<<pres->frame<<": "<<pres->paintError<<'\n';
                    // The character select of the run (CONTINUE / challenger) and its face-off.
                    const auto& select=match.characterSelect();
                    std::cout<<' '<<bool(select)<<' '<<(match.faceoff()?1+int(match.faceoff()->complete):0);
                    for(unsigned i=0;i<2;++i)std::cout<<' '<<(select?select->seats[i].phase:-1)<<' '<<(select?select->seats[i].selected:-1);
                    std::cout<<' '<<(select?int(select->complete):-1)<<' '<<match.battle().gameMode;
                    // Fade colour, the other seat's pre-final flag, the spirit clear record 81 + spirit.
                    std::cout<<' '<<a->fade.colour<<' '<<r.players[r.humanSeat()^1].preFinalSeen
                             <<' '<<unsigned(session.system().option(size_t(0x81+std::clamp(p.spirit,0,8))));
                }
                ++segment;
            }
            if(sceneFields) {
                // Columns from 23: scene, title, mode menu, row, mode word, sub-mode, fade level, library seed,
                // CRCs of the edit block, the spirit records and the key masks, AUTO SAVE, submission count,
                // four scene words, the 16 fighter button masks, the library seed at the scene entry,
                // CRCs of the runtime palette tables 3ec740 / 3f28c0, character select open.
                const auto crc=[&](size_t at,size_t size) {
                    uint32_t c=~0u;
                    for(const uint8_t byte:session.system().image().subspan(at,size)) {
                        c^=byte;for(int k=0;k<8;++k)c=(c>>1)^(0xedb88320u&(0u-(c&1)));
                    }
                    return ~c;
                };
                using Scene=ss6::NativeMatch::MenuScene;
                const auto scene=match.menuScene();
                const auto& title=match.title();
                std::cout<<' '<<int(scene)<<' '<<bool(title)<<' '<<(title?title->draw.modeMenu:false)<<' '<<(title?int(title->draw.firstRow):-1)
                         <<' '<<match.battle().gameMode<<' '<<match.battle().matchEnd.submodeA0<<' '<<match.sceneFade().level()
                         <<' '<<match.battle().random.librarySeed
                         <<' '<<crc(ss6::SystemData::editData,0x6180)<<' '<<crc(ss6::SystemData::records4d7068,0x80)
                         <<' '<<crc(ss6::SystemData::keyMasks,0x40)<<' '<<session.system().autoSave()<<' '<<match.menuDrawList().records.size();
                std::array<int,4> words{-1,-1,-1,-1};
                if(scene==Scene::SpiritsEdit) {
                    const auto& e=*match.spiritsEdit();
                    words={e.state,e.slots.list.cursor,e.editor.categories.list.cursor,e.editor.options.list.cursor};
                } else if(scene==Scene::ColorEdit) {
                    const auto& e=*match.colorEdit();
                    words={e.state(),e.character(),e.colour(),int(e.sliderWord()&0xffffff)};
                } else if(scene==Scene::KeyConfig) {
                    const auto& k=*match.optionKeyConfig();
                    words={k.closing,k.finished,k.widget.selector[0].current,k.widget.selector[1].current};
                } else if(scene!=Scene::None&&scene!=Scene::Option)words={match.galleryRow(),match.galleryCursor(),-1,-1};
                for(int w:words)std::cout<<' '<<w;
                for(unsigned i=0;i<2;++i)for(auto mask:match.inputMapping(i).normal)std::cout<<' '<<mask;
                std::cout<<' '<<match.menuEntrySeed();
                for(const auto& table:match.editedPalettes()->runtime) {
                    uint32_t c=~0u;
                    for(const uint8_t byte:table){c^=byte;for(int k=0;k<8;++k)c=(c>>1)^(0xedb88320u&(0u-(c&1)));}
                    std::cout<<' '<<~c;
                }
                std::cout<<' '<<bool(match.characterSelect());
            }
            if(titleFields) {
                const auto& title=match.title();
                const auto d=title?title->draw:ss6::ConsoleTitleFrame{};
                const auto& s=match.battle().consoleMenu.session;
                std::cout<<' '<<bool(title)<<' '<<d.modeMenu<<' '<<d.firstRow<<' '<<d.scrollDirection
                         <<' '<<d.scrollTick<<' '<<d.titleTick<<' '<<d.idleTick<<' '<<match.selectWhiteLevel()
                         <<' '<<bool(match.characterSelect())<<' '<<s.originalEntrant<<' '<<s.lastEntrant
                         <<' '<<s.wins[0]<<' '<<s.wins[1]<<' '<<s.losses[0]<<' '<<s.losses[1];
            }
            if(selectFields) {
                const auto& s=match.characterSelect();
                std::cout<<' '<<session.matchNumber()<<' '<<bool(s);
                for(unsigned i=0;i<2;++i) {
                    const auto& p=match.lineup()[i];
                    std::cout<<' '<<p.character<<' '<<p.spirit<<' '<<p.palette;
                    if(s){auto& a=s->seats[i];auto& b=s->spirits[i];
                        std::cout<<' '<<a.cell<<' '<<a.phase<<' '<<a.selected<<' '<<a.palette<<' '<<a.spirit<<' '<<b.phase<<' '<<b.cursor;
                    }else std::cout<<" -1 -1 -1 -1 -1 -1 -1";
                }
                std::cout<<' '<<(s?s->stage:-1)<<' '<<(s?s->stageOwner:-1)<<' '<<(s&&s->complete)
                         <<' '<<(match.faceoff()?match.faceoff()->drawFrame:-1)<<' '<<match.selectionUnavailable();
                const auto& b=match.battle();
                std::cout<<' '<<match.curtainFrame()<<' '<<match.selectWhiteLevel()<<' '<<b.matchEnd.metadataStage04
                         <<' '<<b.stageItemsOption4c3828<<' '<<b.consoleMenu.session.wins[0]<<' '<<b.consoleMenu.session.wins[1];
            }
            if(rageFields) {
                const auto& b=match.battle();
                for(unsigned i=0;i<2;++i) {
                    const auto& f=match.fighter(i);
                    const auto& a=f.actor;
                    std::cout<<' '<<a.rageState120<<' '<<a.rageAmount124<<' '<<a.rageDecay128
                             <<' '<<a.swordWait130<<' '<<a.swordCurrent134<<' '<<a.swordMaximum138
                             <<' '<<a.flags23c<<' '<<f.body.color8c<<' '<<f.body.timeline.clock().objectFlags
                             <<' '<<a.timers[16]<<' '<<a.fieldA2c;
                }
                const auto& tasks=b.entry.tasks.tasks;
                const auto active=std::count_if(tasks.begin(),tasks.end(),
                    [](const auto& task){return task[0]==0x11e708;});
                std::cout<<' '<<b.match.roundIndex<<' '<<b.requestedState<<' '<<b.field08
                         <<' '<<b.timers.lock<<' '<<b.gauges.paused46a940<<' '<<active;
            }
            if(resultFields) {
                const auto& s=match.battle().resultScreen;
                std::cout<<' '<<uint32_t(s.scene)<<' '<<uint32_t(s.nextScene)<<' '<<s.winner<<' '<<s.quoteIndex
                         <<' '<<s.streak<<' '<<s.draw.frame<<' '<<s.draw.backgroundFrame<<' '<<s.draw.glyphLimit
                         <<' '<<s.frame<<' '<<s.endFrame<<' '<<s.messageDone;
            }
            if(shakeFields) {
                const auto& c=match.battle().camera;
                const auto& backdrop=match.combatStage().camera;
                std::cout<<' '<<c.shakeX44<<' '<<c.shakeY48<<' '<<c.delta
                         <<' '<<match.fighter(0).body.pendingFlags<<' '<<match.fighter(1).body.pendingFlags;
                for(float v:{c.projectionX,c.projectionY,backdrop.projectionX,backdrop.projectionY})
                    std::cout<<' '<<std::bit_cast<uint32_t>(v);
                for(unsigned i=0;i<2;++i) {
                    const auto& clock=match.fighter(i).body.timeline.clock();
                    std::cout<<' '<<clock.objectFlags<<' '<<clock.flags104;
                }
            }
            if(stageFields) {
                const auto& b=match.battle();
                const auto& stage=match.combatStage();
                const auto& c=stage.camera;
                std::cout<<' '<<stage.visible;
                for(float value:{c.projectionX,c.projectionY,c.depth,c.depthOffset,c.verticalOffset})
                    std::cout<<' '<<std::bit_cast<uint32_t>(value);
                for(const auto& layer:stage.layers)
                    std::cout<<' '<<layer.elapsed<<' '<<layer.picture<<' '<<layer.step;
                std::cout<<' '<<b.gauges.delta46a908<<' '<<b.timers.rawDelta;
            }
            if(menuFields) {
                const auto& b=match.battle();
                const auto& m=b.consoleMenu;
                std::cout<<' '<<session.matchNumber()<<' '<<m.active<<' '<<m.draw.visible
                         <<' '<<m.draw.frame<<' '<<m.draw.selection<<' '<<m.draw.dialog<<' '<<m.draw.choice
                         <<' '<<unsigned(m.pending)<<' '<<unsigned(m.destination)<<' '<<m.fadeAlpha;
                for(unsigned i=0;i<2;++i)std::cout<<' '<<m.session.wins[i]<<' '<<m.session.losses[i];
                std::cout<<' '<<m.session.lastWinner<<' '<<m.session.streak<<' '<<m.session.lastEntrant
                         <<' '<<b.remainingSeconds()<<' '<<b.matchEnd.metadataStage04<<' '<<b.random.gameSeed
                         <<' '<<b.random.librarySeed<<' '<<m.draw.helpRevision<<' '<<m.draw.borderFrame
                         <<' '<<m.draw.panelAlpha<<' '<<m.draw.textAlpha<<' '<<m.draw.backgroundAlpha;
            }
            if(lifeFields) {
                const auto& hud=match.rageGauge();
                const auto& clock=match.hudClock();
                std::cout<<' '<<clock.visible<<' '<<hud.resetOnLastVisit<<' '<<clock.seconds<<' '<<clock.stopped
                         <<' '<<match.battle().match.roundIndex<<' '<<match.battle().consoleMenu.active<<' '<<session.matchNumber();
                for(const auto& p:hud.players) {
                    const auto& s=p.lifeGauge;
                    for(int value:{p.system,p.sampledLife,s.sword,s.swordMax,s.reserve,s.phase,s.opponentHits,
                                   int(s.inPersistentHurt),p.lifeX,p.lifeWidth,p.lifeTrail,s.life,p.woundX,p.woundWidth,
                                   p.storedWoundWidth,int(p.woundActive),p.lifeDelay,int(p.lifeHealing),
                                   p.zanLifePulse,p.lifePulse,p.swordPulse,p.state})std::cout<<' '<<value;
                }
            }
            if(hudFields) {
                for(const auto& hud:match.rageGauge().players)
                    std::cout<<' '<<hud.state<<' '<<hud.displayed<<' '<<hud.pulse
                             <<' '<<hud.emblemCounter<<' '<<hud.emblemExpansion<<' '<<hud.pulseDirection;
                std::cout<<' '<<match.battle().phase130;
            }
            if(timed&&!resultFields&&!menuFields) {
                const auto& b=match.battle();
                std::cout<<' '<<b.remainingSeconds()<<' '<<b.timers.values[0]<<' '<<b.requestedState
                         <<' '<<b.match.roundIndex<<' '<<b.match.result.ui<<' '<<b.match.result.winner
                         <<' '<<b.field140<<' '<<b.timers.rawDelta<<' '<<b.timers.delta<<' '<<b.field08
                         <<' '<<b.timers.values[5]<<' '<<b.timers.values[6]<<' '<<b.pause.paused;
                for(unsigned i=0;i<2;++i)std::cout<<' '<<match.fighter(i).actor.rageState120;
            }
            if(contactFields)for(unsigned i=0;i<2;++i) {
                const auto& f=match.fighter(i);const auto& a=f.actor;
                const auto& t=f.body.timeline;const auto c=t.clock();
                // Exact position bits matter when two JDG edges just touch.
                std::cout<<' '<<std::bit_cast<uint32_t>(t.motion().x)<<' '<<std::bit_cast<uint32_t>(t.motion().y)
                    <<' '<<c.objectFlags<<' '<<c.flags104<<' '<<c.flags108<<' '<<a.flags23c<<' '<<a.flags240
                    <<' '<<a.flags244<<' '<<a.flags248<<' '<<unsigned(a.flags24c)<<' '<<unsigned(a.effectiveFlags())
                    <<' '<<a.timers[6]<<' '<<a.controlModeC8<<' '<<f.input.sampledFeatures[0xfc/4]
                    <<' '<<f.input.sampledFeatures[0xd8/4]<<' '<<f.input.sampledFeatures[0xd4/4]
                    <<' '<<a.rageState120<<' '<<a.rageAmount124<<' '<<a.swordCurrent134<<' '<<a.swordMaximum138
                    <<' '<<unsigned(a.previousReaction)<<' '<<a.heavyReaction<<' '<<a.fieldA50
                    <<' '<<unsigned(a.field250)<<' '<<unsigned(a.field251)<<' '<<unsigned(a.contactKind252);
            }
            if(finishFields)for(const auto& s:match.battle().match.players)
                std::cout<<' '<<s.hitCount0c<<' '<<s.field18<<' '<<s.outcome1c<<' '<<s.outcome20;
            if(risingFields) {
                // Observe the queue used by the window after following the
                // parent, including precise pose alignment during hitstop.
                for(unsigned i=0;i<2;++i) {
                    unsigned count=0;
                    const ss6::ObjectDrawQueue::Record* first=nullptr;
                    for(const auto& draw:match.objectDraws().active()) {
                        const unsigned act=draw[0x24/4];
                        if(draw[0xcc/4]!=6||draw[0xc/4]!=i||
                           !((act>=555&&act<=557)||(act>=571&&act<=573)))continue;
                        ++count;
                        if(!first)first=&draw;
                    }
                    std::cout<<' '<<count;
                    for(unsigned off:{0x24u,0x28u,0x40u,0x44u})
                        std::cout<<' '<<(first?(*first)[off/4]:0);
                }
            }
            if(whirlwindFields) {
                for(unsigned i=0;i<2;++i) {
                    const auto& f=match.fighter(i);const auto& a=f.actor;const auto& c=f.body.timeline.clock();
                    for(auto v:a.registry28c)std::cout<<' '<<v;
                    for(auto v:a.callbacks260)std::cout<<' '<<v;
                    std::cout<<' '<<a.bodyField124<<' '<<a.timers[0]<<' '<<a.timers[1]<<' '<<a.timers[23]
                             <<' '<<c.fractionalTime<<' '<<c.endControl<<' '<<c.endReached;
                }
                const auto& pools=match.battle().entry.tasks;
                for(unsigned i=0;i<2;++i)for(auto task:match.fighter(i).storage.objectTasks)if(task) {
                    const auto handle=pools.tasks.at(task-1)[7];const auto& o=pools.objects.at(handle-1);
                    if(o[0xcc/4]!=2)continue;
                    std::cout<<' '<<handle<<' '<<pools.tasks.at(task-1)[0];
                    for(auto word:o)std::cout<<' '<<word;
                }
            }
            if(mikiriFields) {
                const auto& b=match.battle();
                std::cout<<' '<<match.mikiriWhiteFrame()<<' '<<b.timers.lock<<' '<<b.gauges.focus46a948;
                for(unsigned seat=0;seat<2;++seat) {
                    const auto& f=match.fighter(seat);
                    auto& a=f.actor;
                    std::cout<<' '<<unsigned(a.characterBytesF22[3])<<' '<<a.systemMeter158
                             <<' '<<a.timers[0]<<' '<<a.timers[31]<<' '<<a.timers[33];
                    std::vector<const ss6::AuxiliaryObject*> images;
                    for(auto t:f.storage.objectTasks)if(t) {
                        const auto& o=b.entry.tasks.objects.at(b.entry.tasks.tasks.at(t-1)[7]-1);
                        if(o[0xcc/4]==9)images.push_back(&o);
                    }
                    std::cout<<' '<<images.size();
                    for(const auto* image:images)for(auto word:*image)std::cout<<' '<<word;
                }
            }
            if(kenFields) {
                for(unsigned seat=0;seat<2;++seat) {
                    const auto& a=match.fighter(seat).actor;
                    std::cout<<' '<<a.bonusState14c<<' '<<a.bonusTime150<<' '<<a.bonusRate154<<' '<<a.systemMeter158
                             <<' '<<a.rageState120<<' '<<a.rageAmount124<<' '<<a.swordCurrent134<<' '<<a.fieldA30;
                }
            }
            if(zeroFields) {
                const auto& b=match.battle();
                for(unsigned seat=0;seat<2;++seat) {
                    const auto& a=match.fighter(seat).actor;
                    std::cout<<' '<<a.systemState13c<<' '<<a.systemAmount140<<' '<<a.systemTime144
                             <<' '<<a.systemDecay148<<' '<<unsigned(a.concentrationUsed11c)
                             <<' '<<a.rageState120<<' '<<a.rageAmount124<<' '<<b.gauges.words910[seat];
                }
                std::cout<<' '<<b.gauges.scale1239d84<<' '<<b.gauges.paletteTones[512]<<' '<<b.match.roundIndex;
            }
            if(spiritFields) {
                const auto& b=match.battle();
                for(unsigned seat=0;seat<2;++seat) {
                    const auto& fighter=match.fighter(seat);
                    std::cout<<' '<<fighter.config.system<<' '<<unsigned(fighter.actor.characterBytesF22[2])
                             <<' '<<fighter.actor.flags244<<' '<<fighter.actor.swordMaximum138;
                }
                std::cout<<' '<<session.matchNumber()<<' '<<b.match.roundIndex;
                for(auto handle:b.objectTasks)if(handle) {
                    const auto& task=b.entry.tasks.tasks.at(handle-1);
                    const auto& obj=b.entry.tasks.objects.at(task[7]-1);
                    if(obj[0xcc/4]==7&&obj[0x24/4]==54) {
                        for(unsigned off:{0x118u,0x24u,0x28u,0x40u,0x44u,0xb0u,0x104u,0x108u})
                            std::cout<<' '<<obj[off/4];
                    }
                }
            }
            if(shinFields) {
                const auto& battle=match.battle();
                const auto& pools=battle.entry.tasks;
                for(unsigned slot=0;slot<2;++slot) {
                    const auto& fighter=match.fighter(slot);
                    std::vector<uint32_t> weapons;
                    for(auto handle:fighter.storage.objectTasks)if(handle) {
                        const auto& object=pools.objects.at(pools.tasks.at(handle-1)[7]-1);
                        if(object[0xcc/4]==4||object[0xcc/4]==6)weapons.push_back(handle);
                    }
                    std::cout<<' '<<fighter.actor.timers[14]<<' '<<weapons.size();
                    for(auto handle:weapons) {
                        const auto& task=pools.tasks.at(handle-1);
                        const auto& object=pools.objects.at(task[7]-1);
                        for(unsigned off:{0x24u,0x28u,0x40u,0x44u,0x104u,0x108u})std::cout<<' '<<object[off/4];
                        std::cout<<' '<<task[0];
                    }
                }
                std::cout<<' '<<battle.timers.values[5]<<' '<<battle.timers.values[6]
                         <<' '<<battle.gauges.focus46a948<<' '<<battle.timers.lock
                         <<' '<<battle.field140<<' '<<battle.gauges.paletteTones[512];
            }
            if(wallFields) {
                const auto& battle=match.battle();
                const auto& camera=battle.camera;
                std::cout<<' '<<camera.left<<' '<<camera.right<<' '<<camera.commands.size()
                         <<' '<<(camera.commands.empty()?0:camera.commands.front().kind)
                         <<' '<<(camera.commands.empty()?0:camera.commands.front().parameter)<<' '<<battle.flags138;
                for(unsigned i=0;i<2;++i) {
                    const auto& a=match.fighter(i).actor;
                    std::cout<<' '<<unsigned(a.landingCount253)<<' '<<a.bodyState128;
                }
                std::cout<<' '<<camera.delta;
                for(float value:{camera.x,camera.y,camera.width})std::cout<<' '<<std::bit_cast<uint32_t>(value);
                std::cout<<' '<<camera.left<<' '<<camera.right<<' '<<camera.top;
                for(float value:{camera.targetX,camera.targetY,camera.targetWidth})std::cout<<' '<<std::bit_cast<uint32_t>(value);
                std::cout<<' '<<camera.vx<<' '<<camera.vy<<' '<<camera.vwidth;
            }
            if(projectileFields) {
                const auto& pools=match.battle().entry.tasks;
                for(unsigned i=0;i<2;++i) {
                    const auto& f=match.fighter(i);
                    unsigned count=0;
                    const ss6::AuxiliaryObject* first=nullptr;
                    for(auto handle:f.storage.objectTasks)if(handle) {
                        const auto& task=pools.tasks.at(handle-1);
                        const auto& o=pools.objects.at(task[7]-1);
                        if(o[0xcc/4]!=2)continue;
                        ++count;
                        if(!first)first=&o;
                    }
                    std::cout<<' '<<count;
                    for(unsigned off:{0x24u,0x28u,0x104u,0x108u,0x100u,0xdcu,0xfcu}) {
                        unsigned value=first?(*first)[off/4]:0;
                        if(off==0x100 || off==0xfc)value&=255;
                        std::cout<<' '<<value;
                    }
                }
                // A single spark may allocate several sprites under one effect
                // task. Count the descriptor task so its parts count as one.
                unsigned sparks=0;
                for(const auto& task:pools.tasks)
                    if(task[0]==0x124898 && task[8]==0x100+25)++sparks;
                std::cout<<' '<<sparks;
                for(unsigned i=0;i<2;++i)std::cout<<' '<<match.fighter(i).actor.timers[0];
            }
            std::cout<<'\n';
            if(arcadeFields)std::cout.flush(); // the arcade validator drives one process interactively
        }
        if(arcadeFields) {
            const auto* a=session.arcade();
            // The scenes entered and how: transition kind (-1 = 1c1ac0 hand-off) and speed.
            for(const auto& e:session.arcadeLog()) {
                std::cout<<"#scene "<<std::hex<<unsigned(e.scene)<<std::dec<<' '<<e.kind<<' '<<e.speed<<' '<<e.frame<<' '<<e.state.size();
                for(auto w:e.state)std::cout<<' '<<w;
                std::cout<<'\n';
            }
            if(a&&!a->notice.empty())std::cout<<"#notice "<<a->notice<<'\n';
        }
    } catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
