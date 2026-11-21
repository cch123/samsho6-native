#include "native_match.hpp"
#include "practice_dummy.hpp"
#include <algorithm>
#include <cstdio>

namespace ss6 {
namespace {
// 118128 words of the software controller, as the menu tasks read them.
uint32_t physicalPad(uint32_t logical) {
    constexpr std::array<uint32_t,8> physical{0x400,0x200,2,4,0x400000,0x800000,0x100000,0x200000};
    uint32_t bits=logical&0xf8;
    if(logical&PadSelect)bits|=0x80000;
    for(unsigned i=0;i<physical.size();++i)if(logical&(PadLight<<i))bits|=physical[i];
    return bits;
}
std::string ascii(const std::string& text) {
    std::string out;
    for(unsigned char c:text)out.push_back(c<0x80?char(c):'?');
    return out;
}
}
void NativeMatch::openPracticeSelect(unsigned seat) {
    // 1cd428: mode word 9/10 (1ccfb8), g+0x10 = seat ^ 1, 1116f8, 139280(1),
    // 210368 and sub-mode 3 before scene 128008. The session resets the
    // settings (210368) when it sees this select open without a practice state.
    battle_.gameMode=9+int(seat);battle_.matchEnd.submodeA0=3;
    openCharacterSelect(true);
    characterSelect_->random=battle_.random;
    selectAudioPending_=false;enterSelectAudio();
}
void NativeMatch::reopenPracticeSelect(const GameRandom& random) {
    battle_.random=random;
    openCharacterSelect();
}
void NativeMatch::openModeMenu(int row) {
    menuRow_=row;
    returnToModeMenu();
    enterTitleAudio();
}
int NativeMatch::practiceBehaviour() const {
    if(!practice_)return 0x23;
    // 211c00: the menu dummy is the seat opposite the practising pad, whatever the recording swap.
    const auto& dummy=fighters_[unsigned(practice_->menuDummySeat())];
    return practice_->behaviour(PracticeSystem{int(dummy.config.system),nullptr});
}
void NativeMatch::enterPractice() {
    auto& b=battle_;
    practice_=rules_.practice?rules_.practice:std::make_shared<PracticeState>();
    if(!rules_.practice)practice_->settings.reset();
    practice_->battleType=1;practice_->mode=b.gameMode;
    b.practiceRules=practice_.get();
    practiceBattle_=std::make_unique<PracticeBattle>(assets_);
    auto& p=*practiceBattle_;
    // 17f5a0: the window opens in state 1 and requests the first pause (1392e8);
    // 210438 drops the STAND option 9 and the ACTION index of the last scene.
    practice_->settings.enterBattle();
    p.window.init(*practice_,p.help);
    practiceFrame(0); // 17f5a0 builds the help window 1822a0 for the local seat
    p.damage.reset();p.keys.clear();
    p.pauseRequested=true;
    b.practiceDamage=[this](const StateEntryActor& recipient,int32_t amount) {
        // 14a934: only the dummy seat (1394e0) feeds the counters.
        if(&recipient==&fighters_[unsigned(practice_->dummySeat())].actor)practiceBattle_->damage.add(amount);
    };
    // Either seat can become the CPU-driven one (recording swaps the control
    // kinds), and the perception passes 145ef0/146348 observe both.
    for(unsigned side=0;side<2;++side)
        cpuTactics_[side]=std::make_unique<CpuTactics>(assets_,fighters_[side].actor.character);
    for(unsigned i=0;i<2;++i) {
        // 14ff58 leaves both state words at -1: without an introduction the
        // first request is normal state 0, which must not read as a repeat.
        fighters_[i].actor.state194=0xffffffffu;
        buildPracticeActor(i);
    }
}
void NativeMatch::buildPracticeActor(unsigned i) {
    auto& f=fighters_[i];auto& a=f.actor;auto& b=battle_;
    // 1398c0: setup[2] = (mode == 10), setup[3] = (mode == 9); setup[0] (the
    // AI level) is not written for these modes and stays 0 from 13f930.
    a.controlKindA20=b.gameMode==10?i==0:i==1;
    const int code=practiceSupportedBehaviour(practiceBehaviour());
    // 13f9f0 reaches 148df0 twice per actor (directly and through 148ed8),
    // each time on a controller 1587d0 has just returned to code 0x23 and
    // level setup[0]. 158830 -> 15aa18 then installs the practice code; a
    // code other than 0x23 draws 112300(2) in 1588c0 on both passes.
    for(int pass=0;pass<2;++pass) {
        a.controlModeC8=0x23;cpuLevels_[i]=0;a.flags240=0;
        practiceRefreshBehaviour(a,code,cpuLevels_[i],b.random);
    }
    // 13fb64..13fd28
    PracticeRecordActor record{a.flags240,int(a.controlKindA20),int(i),0};
    practiceResetControl(record,*practice_);
    a.flags240=record.flags240;a.controlKindA20=uint32_t(record.controlKind);
    f.sampling.replayIndex=0; // actor+0x2c0 after the 148d58 clear
}
void NativeMatch::practiceRestart() {
    auto& b=battle_;auto& p=*practiceBattle_;
    BattleGauges::stop(b,players()); // 11e600
    for(unsigned i=0;i<2;++i) {
        // 148d58 clears the whole actor; 148ed8 keeps only its identity words
        // (+0xa0c, +0xa10/+0xa14, +0xa1c, +0xa20, +0xa24, +0xa28, +0x10c) and
        // re-creates the body object in place (11d528, 11d570).
        auto& f=fighters_[i];
        StateEntryActor fresh;
        fresh.character=f.actor.character;fresh.characterA14=f.actor.characterA14;
        fresh.damageCharacterA18=f.actor.damageCharacterA18;fresh.fieldA28=f.actor.fieldA28;
        fresh.flags23c=0x1000;fresh.state194=fresh.state1a4=0xffffffffu;fresh.fieldA30=200;fresh.registry28c[2]=0xffffffffu;
        f.actor=fresh;
        f.input=ActorCommandInput{};human_.initialize(f.input,f.config);
        f.sampling=ActorInputSampling{};
        f.sampling.player=i;f.sampling.expectedFacing=i!=0;f.sampling.gameMode=b.gameMode;
        f.hits=f.guards=0;
        sounds_.cutVoice(f.body.sound34);
        f.body.color8c=0xff808080;f.body.delta30=256;f.body.pendingFlags=0;
        f.body.timeline.setObjectFlags(0x10000000u|(i<<19),0x40000000,0x40);
        GroundStateRuntime::captureBody(f.body,f.actor);
        buildPracticeActor(i);
        b.match.players[i].requiredWins=1; // 13fb60
    }
    // 1432e0: requested = current = -1, round index 0, battle+8/+0xc = -1.
    b.currentState=b.requestedState=-1;b.match.roundIndex=0;
    initialize_.begin(ground_,players(),b,effects_); // 13fd80
    ++p.resets;
}
void NativeMatch::tickPractice(const std::array<NormalizedPadSample,2>& pads) {
    auto& b=battle_;auto& p=*practiceBattle_;
    if(p.exit) {
        // 1252f0(2,0,139778,x): black fade; the window sits in state 4 and keeps the battle held.
        if(!p.exitDone&&sceneFade_.tick()) {
            sounds_.stopMusic();sounds_.stopGroup(2);
            p.exitDone=p.exit;
        }
        return;
    }
    p.damage.beginFrame();                                   // 13908c
    if(p.resetRequested){p.resetRequested=false;practiceRestart();} // 13921c
    const bool hold=p.pauseRequested;p.pauseRequested=false;  // 139118 / 13913c
    battleFrame(pads,hold);
    {
        // 13a030(139488()): the practising player's command history.
        const auto& f=fighters_[unsigned(practice_->humanSeat())];
        if(f.body.delta30||(f.actor.flags23c&0x08000000)) {
            const auto& s=f.input.sampledFeatures;
            PracticeKeyFeatures k;
            for(unsigned n=0;n<6;++n)k.buttons[n]=int32_t(s[0x18/4+n]);
            constexpr std::array<unsigned,9> motion{0x158,0x154,0x150,0x15c,0xc4,0x14c,0x160,0x164,0x168};
            for(unsigned n=0;n<9;++n)k.motions[n]=int32_t(s[motion[n]/4]);
            p.keys.push(practiceKeyMask(k));
        }
    }
    // 17f790
    const unsigned port=unsigned(practice_->localSeat());
    const auto menuPads=menuRepeat_.sample({physicalPad(pads[0].held),physicalPad(pads[1].held)},
                                           {physicalPad(pads[0].pressed),physicalPad(pads[1].pressed)});
    const auto& dummyFighter=fighters_[unsigned(practice_->menuDummySeat())];
    const PracticeFighter dummy{PracticeSystem{int(dummyFighter.config.system),nullptr},int(dummyFighter.actor.character),
                                bool(dummyFighter.actor.flags23c&0x100000)};
    practiceFrame(1); // 1825b8 before the window update
    const auto gates=p.window.begin(menuPads[port],*practice_,dummy,p.tables);
    PracticeSubEvents sub;
    std::vector<int> tones;
    const auto widgetPad=[&](unsigned i){return WidgetPad{physicalPad(pads[i].held),menuPads[i].pressed,menuPads[i].repeat};};
    if(gates[0]&&p.keyConfigOpen) {
        const auto r=keyConfig_.tick({widgetPad(0),widgetPad(1)},*system_,*keyAssets_,false,tones);
        applyKeyMasks();
        if(r.returnedToPause){sub.keyConfig=5;p.keyConfigOpen=false;}
    }
    if(gates[1]&&p.skillListOpen&&skillList_) {
        // The ported skill list (13d680) runs its sub-list and detail pages itself:
        // the practice window stays in state 6 until it closes.
        auto r=skillList_->tick(widgetPad(port));
        tones=std::move(r.tones);
        if(r.event!=SkillListWindow::None){sub.list=5;p.skillListOpen=false;}
    }
    const int before=p.window.state;
    auto out=p.window.finish(menuPads[port],sub,*practice_,dummy);
    for(int id:out.sounds)sounds_.sample(-1,id);
    for(int id:tones)sounds_.sample(-1,id);
    p.help=std::move(out.help);
    practiceFrame(2);
    if(p.window.state!=before&&(p.window.state==5||p.window.state==6)) {
        if(!keyAssets_) {
            keyAssets_=std::make_unique<KeyConfigAssets>(assets_);
            widgetData_=std::make_unique<MenuWidgetData>(assets_);
            skillData_=std::make_unique<SkillListData>(assets_);
        }
        if(p.window.state==5){keyConfig_.start(*widgetData_,port);p.keyConfigOpen=true;}
        else {
            const auto& own=fighters_[port].actor;
            skillList_.emplace(*skillData_,*widgetData_,*system_);
            skillList_->gameMode=unsigned(b.gameMode);
            skillList_->listId=own.characterA14+((own.flags23c&0x100000)?0x32:0);
            skillList_->enter(port);p.skillListOpen=true;
        }
    }
    if(out.clearLockCounters) {
        // 142168
        for(auto& f:fighters_){f.actor.weaponLockPhaseA54=0;f.actor.weaponLockResultA58=0;}
        b.flags138&=~2u;
    }
    if(out.clearRecording){b.sampler.replayHeld.fill(0);b.sampler.replayPressed.fill(0);} // 1772d0
    if(out.reset)p.resetRequested=true;
    if(out.pause)p.pauseRequested=true;
    if(out.exit) {
        // 180110: g+0x18 = 1 and 1e7ad0 at once; the scene switches at the fade midpoint.
        b.matchEnd.field18=1;
        sounds_.stopMusic();
        p.exit=out.exit;sceneFade_.begin(false);
    }
    // 180260 for both actors, after the window update. 139308() is the pause
    // request this window has just made (123a0c4 was cleared at 13913c).
    for(unsigned i=0;i<2;++i) {
        auto& f=fighters_[i];auto& a=f.actor;
        PracticeGaugeActor g;
        g.system=PracticeSystem{int(f.config.system),nullptr};g.seat=int(i);
        g.controlKind=int(a.controlKindA20);g.behaviour=int(a.controlModeC8);
        g.character=int(a.character);g.alternate=a.flags23c&0x100000;
        g.life=a.fieldA30;g.maxLife=a.maximumLifeA34;
        g.rage={a.rageState120,a.rageAmount124,a.rageDecay128,a.rageCharge12c};
        g.sword={a.swordWait130,a.swordCurrent134,a.swordMaximum138};
        g.spirit={a.systemState13c,a.systemAmount140,a.systemTime144,a.systemDecay148};
        g.timeGauge={a.bonusState14c,a.bonusTime150,a.bonusRate154,a.systemMeter158};
        g.flags244=a.flags244;g.flags248=a.flags248;
        practiceEnforceGauges(g,*practice_,p.tables,p.pauseRequested);
        a.fieldA30=g.life;a.maximumLifeA34=g.maxLife;
        a.rageState120=g.rage[0];a.rageAmount124=g.rage[1];a.rageDecay128=g.rage[2];a.rageCharge12c=g.rage[3];
        a.swordWait130=g.sword[0];a.swordCurrent134=g.sword[1];a.swordMaximum138=g.sword[2];
        a.systemState13c=g.spirit[0];a.systemAmount140=g.spirit[1];a.systemTime144=g.spirit[2];a.systemDecay148=g.spirit[3];
        a.bonusState14c=g.timeGauge[0];a.bonusTime150=g.timeGauge[1];a.bonusRate154=g.timeGauge[2];a.systemMeter158=g.timeGauge[3];
        a.flags244=g.flags244;a.flags248=g.flags248;
        // 11ec9c: the gauge task recharges the time gauge up to 211198(seat) << 9 in practice.
        b.gauges.bonusLimits[i]=uint8_t(2*practice_->mikiri(int(i)));
    }
}
std::vector<std::string> NativeMatch::practiceOverlay() const {
    std::vector<std::string> lines;
    if(!practiceBattle_||!practice_||characterSelect_||title_)return lines;
    const auto& p=*practiceBattle_;const auto& w=p.window;const auto& s=practice_->settings;const auto& t=p.tables;
    char buffer[96];
    const auto clock=practiceClock(*practice_,{fighters_[0].sampling.replayIndex,fighters_[1].sampling.replayIndex});
    if(clock.shown) {
        std::snprintf(buffer,sizeof buffer,"%s %02d:%03d",clock.play?"PLAY":"REC",clock.seconds,clock.thousandths);
        lines.push_back(buffer);
    }
    if(s.dataDisplay()) {
        std::snprintf(buffer,sizeof buffer,"DAMAGE %3d   TOTAL DAMAGE %3d   MAX DAMAGE %3d",int(p.damage.last),int(p.damage.total),int(p.damage.maxDamage));
        lines.push_back(buffer);
        std::string keys="KEYS";
        for(int n=0;n<8;++n) {
            const auto entry=p.keys.shown[unsigned((p.keys.index+24-n)%24)];
            if(!entry)break;
            std::snprintf(buffer,sizeof buffer," %04X",unsigned(entry));keys+=buffer;
        }
        lines.push_back(keys);
    }
    if(w.state==5){lines.push_back("PRACTICE: KEY CONFIGURATION (SCREEN IN DEVELOPMENT) / SELECT: CLOSE");return lines;}
    if(w.state>=6){lines.push_back("PRACTICE: SKILL LIST (SCREEN IN DEVELOPMENT) / SELECT OR CANCEL: CLOSE");return lines;}
    if(w.state==2){lines.push_back("PRACTICE WINDOW OFF (ANY BUTTON: SHOW)");return lines;}
    if(w.state==0||!w.menu.active)return lines;
    lines.push_back("PRACTICE MENU (PROVISIONAL TEXT VIEW)");
    const auto& m=w.menu;
    for(int row=0;row<12;++row) {
        std::string line=std::string(row==m.rows.value?"> ":"  ")+ascii(t.text(PracticeTables::Rows,row));
        std::string value,option;
        switch(row) {
        case 2: {
            value=ascii(t.text(PracticeTables::CpuType,s.a[2]));
            const int slot=PracticeSettings::optionSlot(2,s.a[2]);
            if(slot==0&&s.b[0]==9&&m.standNinth>=0)option=ascii(t.text(PracticeTables::Misc,m.standNinth));
            else if(slot==0)option=ascii(t.text(PracticeTables::Stand,s.b[0]));
            else if(slot==1)option=ascii(t.text(PracticeTables::Crouch,s.b[1]));
            else if(slot>=2&&slot<=4)option=ascii(t.text(PracticeTables::Jump,s.b[unsigned(slot)]));
            else if(slot==5)option=ascii(t.text(PracticeTables::Action,s.b[5]));
            break;
        }
        case 3:value=ascii(t.text(PracticeTables::Ukemi,s.a[3]));break;
        case 4:
            std::snprintf(buffer,sizeof buffer,"%s%3d%%%3d%%:%s%3d%%%3d%%",ascii(t.text(PracticeTables::GaugeShort,s.b[6])).c_str(),int(s.b[8]),int(s.b[10])+1,
                          ascii(t.text(PracticeTables::GaugeShort,s.b[7])).c_str(),int(s.b[9]),int(s.b[11])+1);
            value=buffer;break;
        case 5:value=ascii(t.text(PracticeTables::Items,s.a[5]));break;
        case 6:value=ascii(t.text(PracticeTables::OffOn,s.a[6]));break;
        default:break;
        }
        const bool editing=row==m.rows.value&&m.level>0;
        if(!value.empty())line+=std::string(editing&&m.level==1?"  <":"   ")+value+(editing&&m.level==1?">":"");
        if(!option.empty())line+=std::string(editing&&m.level==2?"  <":"   ")+option+(editing&&m.level==2?">":"");
        lines.push_back(line);
    }
    if(m.gaugeWindow()) {
        for(int row=0;row<6;++row) {
            if(row<2)std::snprintf(buffer,sizeof buffer,"%s",ascii(t.text(PracticeTables::GaugeLong,s.b[unsigned(6+row)])).c_str());
            else std::snprintf(buffer,sizeof buffer,"%3d%%",int(s.b[unsigned(6+row)])+(row>=4));
            const bool cursor=m.level==1?m.values.value==row:s.a[4]==row;
            lines.push_back(std::string(cursor?"   > ":"     ")+ascii(t.text(PracticeTables::GaugeRows,row))+"  "+
                            (cursor&&m.level==2?"<":"")+buffer+(cursor&&m.level==2?">":""));
        }
    }
    if(w.state==3||w.state==4)
        lines.push_back(std::string(w.pendingKind==7?"RESELECT CHARACTERS?":"RETURN TO TITLE?")+(w.confirm.choice.value==0?"  [YES]  NO":"  YES  [NO]"));
    return lines;
}
}
