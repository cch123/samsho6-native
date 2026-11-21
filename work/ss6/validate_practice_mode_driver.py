"""C++ driver of validate_practice_mode.py: one command per line, one line of integers back."""
DRIVER = r'''
#include "practice_mode.hpp"
#include <iostream>
#include <sstream>
using namespace ss6;
static std::array<std::array<uint8_t,8>,3> descriptors;
static PracticeSystem readSystem(std::istream& in,int slot) {
    int id,custom;in>>id>>custom;
    for(auto& v:descriptors[slot]){int x;in>>x;v=uint8_t(x);}
    return {id,custom?descriptors[slot].data():nullptr};
}
template<class T> static void put(std::ostream& o,const T& values){for(auto v:values)o<<' '<<int64_t(v);}
static void put(std::ostream& o,const PracticeSlide& s) {
    put(o,std::array<int,13>{s.x,s.y,s.frames,s.duration,s.startX,s.startY,s.targetX,s.targetY,s.closed,s.closedX,s.closedY,s.openX,s.openY});
}
static void put(std::ostream& o,const PracticeSelector& s){put(o,std::array<int64_t,6>{s.flags,s.min,s.max,s.step,s.value,s.page});}
static void put(std::ostream& o,const PracticeSettings& s){put(o,s.a);put(o,s.committedA);put(o,s.b);put(o,s.committedB);put(o,s.actions);}
int main(int,char** argv) {
    PracticeTables tables(argv[1]);
    PracticeState state;
    PracticeWindow window;
    MenuPadRepeat repeat;
    std::array<PracticeGaugeActor,2> actors;
    PracticeDamage damage;
    PracticeKeyHistory keys;
    std::string line;
    while(std::getline(std::cin,line)) {
        std::istringstream in(line);std::ostringstream out;
        char op;in>>op;
        auto& s=state.settings;
        const auto row=[&] {
            auto& m=window.menu;auto& c=window.confirm;
            put(out,std::array<int,9>{window.state,window.lastState,window.dim,window.startCode,window.pendingKind,m.visible,m.scroll,m.active,m.focused});
            put(out,m.slide);put(out,m.rows);put(out,m.values);
            put(out,std::array<int,8>{m.counter,m.level,m.prevLevel,m.standNinth,c.visible,c.scroll,c.active,c.focused});
            put(out,c.slide);put(out,c.choice);out<<' '<<c.prompt;
            for(auto* w:{&window.keyConfig,&window.list,&window.subList}){out<<' '<<w->active<<' '<<w->focused;put(out,w->slide);}
            out<<' '<<window.detailActive<<' '<<window.detailFocused<<' '<<state.replay<<' '<<state.recording;
            put(out,s);
        };
        const auto actorRows=[&] {
            for(auto& a:actors){out<<' '<<a.life<<' '<<a.maxLife;put(out,a.rage);put(out,a.sword);put(out,a.spirit);put(out,a.timeGauge);out<<' '<<a.flags244<<' '<<a.flags248;}
        };
        const auto helpRows=[&](const std::vector<PracticeHelp>& help) {
            out<<' '<<help.size();
            for(auto& h:help)out<<' '<<h.kind<<' '<<h.id<<' '<<h.arg;
        };
        const auto dummy=[&] {
            const auto& a=actors[state.menuDummySeat()];
            return PracticeFighter{a.system,a.character,a.alternate};
        };
        if(op=='X') {
            int replay,recording;in>>state.battleType>>state.mode>>replay>>recording;
            state.replay=replay;state.recording=recording;state.otherModeSeat=practiceLocalSeat(state.mode,0,0);
            for(auto* v:{&s.a,&s.committedA,&s.b,&s.committedB})for(auto& x:*v)in>>x;
            for(auto& x:s.actions){int v;in>>v;x=uint8_t(v);}
            out<<0;
        } else if(op=='Q') {
            const auto system=readSystem(in,2);
            out<<s.behaviour(system)<<' '<<state.behaviour(system)<<' '<<state.ukemi()<<' '<<state.itemKind();
            for(int seat:{0,1})out<<' '<<state.spiritGauge(seat);
            for(int seat:{0,1})out<<' '<<state.mikiri(seat);
            for(int seat:{0,1})out<<' '<<state.lifePercent(seat);
            for(int seat:{0,1})out<<' '<<s.spiritGauge(seat);
            for(int seat:{0,1})out<<' '<<s.mikiri(seat);
            for(int seat:{0,1})out<<' '<<s.lifePercent(seat);
            out<<' '<<s.dataDisplay()<<' '<<s.ukemi()<<' '<<s.itemKind()<<' '<<state.practice()<<' '<<state.survival()<<' '
               <<state.replayActive()<<' '<<state.recordingActive()<<' '<<state.humanSeat()<<' '<<state.dummySeat()<<' '<<state.localSeat()
               <<' '<<system.hyperSlash()<<' '<<system.comboSlash()<<' '<<system.rageSkills()<<' '<<system.systemSkills()<<' '
               <<system.freeSystemSkill()<<' '<<system.hasSpiritGauge()<<' '<<system.hasTimeGauge();
        } else if(op=='R'||op=='C'||op=='E') {
            if(op=='R')s.reset();else if(op=='C')s.commit();else s.enterBattle();
            put(out,s);
        } else if(op=='O') {
            int r,v;in>>r>>v;out<<PracticeSettings::optionSlot(r,v);
        } else if(op=='K') {
            int id;in>>id;out<<tables.listStart(id)<<' '<<tables.listCount(id)<<' '<<tables.skillIndex(id,3);
        } else if(op=='S') {
            PracticeSelector sel;std::array<uint32_t,4> bitmap;int lo,hi,step,page;MenuPad pad;
            in>>sel.flags>>lo>>hi>>step>>page>>sel.value>>pad.pressed>>pad.repeat;
            for(auto& v:bitmap)in>>v;
            sel.disabled=bitmap.data();sel.setRange(lo,hi,step,page);
            out<<sel.min<<' '<<sel.max<<' '<<sel.step<<' '<<sel.value<<' '<<sel.page;
            std::vector<int> sounds;
            const int code=sel.input(pad,sounds);
            out<<' '<<code<<' '<<sel.value<<' '<<sounds.size();put(out,sounds);
        } else if(op=='A') {
            int seat,alt;in>>seat;auto& a=actors[seat];
            a.system=readSystem(in,seat);
            in>>a.seat>>a.controlKind>>a.behaviour>>a.character>>alt>>a.life>>a.maxLife;a.alternate=alt;
            for(auto* v:{&a.rage,&a.spirit})if(v==&a.rage){for(auto& x:a.rage)in>>x;for(auto& x:a.sword)in>>x;for(auto& x:a.spirit)in>>x;for(auto& x:a.timeGauge)in>>x;}
            in>>a.flags244>>a.flags248;
            out<<0;
        } else if(op=='N') {
            window=PracticeWindow{};repeat=MenuPadRepeat{};out<<0;
        } else if(op=='I') {
            std::vector<PracticeHelp> help;
            window.init(state,help);
            row();actorRows();helpRows(help);
        } else if(op=='T') {
            std::array<uint32_t,2> held,edges;int paused;PracticeSubEvents sub;
            in>>held[0]>>held[1]>>edges[0]>>edges[1]>>paused>>sub.keyConfig>>sub.list>>sub.subList>>sub.detail>>sub.listCursor;
            const auto pads=repeat.sample(held,edges);
            const auto& pad=pads[state.localSeat()];
            const auto who=dummy();
            window.begin(pad,state,who,tables);
            const auto result=window.finish(pad,sub,state,who);
            for(auto& a:actors)practiceEnforceGauges(a,state,tables,paused||result.pause);
            row();
            out<<' '<<pad.pressed<<' '<<pad.repeat<<' '<<result.sounds.size();put(out,result.sounds);
            out<<' '<<result.pause<<' '<<result.reset<<' '<<result.clearLockCounters<<' '<<result.clearRecording<<' '
               <<result.fillSubList<<' '<<result.openDetail<<' '<<result.exit;
            actorRows();helpRows(result.help);
        }
        else if(op=='L') {
            int life,pending,maximum;in>>life>>pending>>maximum;
            const auto r=practiceCommitLife(life,pending,maximum,state.practice());
            out<<r.life<<' '<<r.knockedOut<<' '<<r.armTimer28;
        } else if(op=='F') {
            int timer,character,action,kind,behaviour;uint32_t flags;in>>timer>>character>>action>>kind>>behaviour>>flags;
            out<<practiceRefillsLife(state,timer,character,action)<<' '<<practiceHumanSampled(kind,behaviour,flags);
        } else if(op=='M') {
            int option,link,clock;in>>option>>link>>clock;
            out<<practiceTimeMode(state,option,link)<<' '<<practiceCpuClock(state,clock);
        } else if(op=='D') {
            GameRandom random;random.mode=1;in>>random.gameSeed;
            out<<practiceItemDelivery(state,random)<<' '<<random.gameSeed;
        } else if(op=='U') {
            int32_t type;uint32_t flags;int kind;GameRandom random;random.mode=1;in>>type>>flags>>kind>>random.gameSeed;
            practiceGetUp(type,flags,kind,state,PracticeSystem{},random);
            out<<type<<' '<<flags<<' '<<random.gameSeed;
        } else if(op=='G') {
            int kind,value;in>>kind>>value;
            if(kind==0)damage.reset();else if(kind==1)damage.beginFrame();else if(kind==2)damage.comboEnded();else damage.add(value);
            out<<damage.newCombo<<' '<<damage.maxDamage<<' '<<damage.total<<' '<<damage.last<<' '<<damage.frameFlag;
        } else if(op=='H') {
            int kind;in>>kind;
            if(kind==0)keys.clear();
            else if(kind==1){uint32_t mask;in>>mask;keys.push(mask);}
            else {PracticeKeyFeatures f;for(auto& v:f.buttons)in>>v;for(auto& v:f.motions)in>>v;keys.push(practiceKeyMask(f));}
            out<<keys.neutral<<' '<<keys.index;put(out,keys.held);put(out,keys.shown);
        } else if(op=='P') {
            std::array<int,2> index;in>>index[0]>>index[1];
            const auto c=practiceClock(state,index);out<<c.shown<<' '<<c.play<<' '<<c.seconds<<' '<<c.thousandths;
        } else if(op=='V') {
            PracticeRecordActor a;int running;in>>a.flags240>>a.controlKind>>a.seat>>a.index>>running;
            const auto sampling=practiceSampling(a);
            auto advanced=a;practiceAdvanceRecording(advanced,running);
            const bool single=practiceResetControl(a,state);
            out<<single<<' '<<a.flags240<<' '<<a.controlKind<<' '<<sampling.port<<' '<<sampling.index<<' '<<sampling.playback<<' '<<advanced.index;
        } else if(op=='Y') {
            PracticeSelectRouting routing;int mode,seat;std::array<int,2> committed;in>>mode>>seat>>committed[0]>>committed[1]>>routing.delay;
            const int port=routing.characterPort(mode,seat,committed);out<<port<<' '<<routing.delay;
        } else if(op=='Z') {
            int mode,seat,submode;std::array<int,2> progress,spirit;in>>mode>>seat>>progress[0]>>progress[1]>>spirit[0]>>spirit[1]>>submode;
            out<<PracticeSelectRouting::spiritPort(mode,seat,progress,spirit)<<' '<<PracticeSelectRouting::stagePort(mode,seat)<<' '
               <<PracticeSelectRouting::itemOptionPage(submode);
        }
        std::cout<<out.str()<<std::endl;
    }
}
'''
