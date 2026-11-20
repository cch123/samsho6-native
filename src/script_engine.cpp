#include <cstdio>
#include <cstdlib>
#include "script_engine.hpp"
#include "ground_state.hpp"
#include "battle_round.hpp"
#include "knockout.hpp"
#include "jump_motion.hpp"
#include "scalar_float.hpp"
#include "state_callbacks.hpp"
#include "sound_selection.hpp"
#include <bit>
#include <fstream>
#include <span>

namespace ss6 {
namespace {
std::vector<uint8_t> readAll(const std::filesystem::path& path) {
    std::ifstream in(path,std::ios::binary);
    if(!in)throw std::runtime_error("Missing script asset: "+path.string());
    return {std::istreambuf_iterator<char>(in),{}};
}
uint32_t word(const uint8_t* p) {return uint32_t(p[0])|uint32_t(p[1])<<8|uint32_t(p[2])<<16|uint32_t(p[3])<<24;}
int16_t half(const uint8_t* p) {return int16_t(uint16_t(p[0]|p[1]<<8));}
constexpr uint32_t none=0xffffffffu;

// 1699f8: completion test that always consumes the ACT hold marker 104:100.
bool consumeHold(PlayerObject& b,const StateEntryActor& a) {
    const auto c=b.timeline.clock();
    const bool done=actionEnded(b,a.queuedActionA3c)||(c.flags104&0x100);
    b.setFlags(c.flags104&~0x100u,c.flags108);
    return done;
}
int fighterRadius(unsigned character){return character==46?8:character==47?16:34;} //14adf0
void face(PlayerObject& b,StateEntryActor& a,const GroundStateFrame& f,bool force=false) { //14a978(actor, force)
    GroundStateRuntime::captureBody(b,a);
    a.opponentX=f.opponentX;a.faceOpponent(force);GroundStateRuntime::restoreBody(b,a);
}
}

ScriptTables::ScriptTables(const std::filesystem::path& assets) {
    const auto data=readAll(assets/"script_rows.bin");
    if(data.size()<51*8)throw std::runtime_error("Invalid script_rows.bin");
    size_t at=51*8;
    for(unsigned c=0;c<51;++c) {
        auto& t=tables_[c];t.base=word(&data[c*8]);
        const auto n=word(&data[c*8+4]);
        if(at+size_t(n)*20>data.size())throw std::runtime_error("Truncated script_rows.bin");
        for(unsigned i=0;i<n;++i,at+=20) {
            const uint8_t* p=&data[at];ScriptRow r;
            r.id=p[0];r.act=half(p+2);r.end=p[4];
            r.branch={half(p+6),half(p+8),half(p+10)};
            r.flags=p[12];r.spawnMode=p[13];r.projectile=half(p+14);r.type=p[19];
            t.rows.push_back(r);
        }
    }
    if(at!=data.size())throw std::runtime_error("Trailing bytes in script_rows.bin");
    const auto locks=readAll(assets/"action_locks.bin");
    if(locks.size()!=51*32)throw std::runtime_error("Invalid action_locks.bin");
    for(unsigned c=0;c<51;++c)for(unsigned i=0;i<16;++i)locks_[c][i]=half(&locks[c*32+i*2]);
}
uint32_t ScriptTables::find(unsigned character,unsigned id) const {
    const auto& t=tables_.at(character);
    for(size_t i=0;i<t.rows.size();++i) {
        if(t.rows[i].id==id)return t.base+uint32_t(20*i);
        if(t.rows[i].end==0xff)return 0;
    }
    return 0;
}
const ScriptRow& ScriptTables::row(uint32_t address) const {
    for(const auto& t:tables_)
        if(address>=t.base&&address<t.base+20*t.rows.size()&&(address-t.base)%20==0)
            return t.rows[(address-t.base)/20];
    throw std::runtime_error("Script row outside table A");
}
int ScriptTables::lockTicks(unsigned character,int action) const {
    const auto& l=locks_.at(character);
    for(unsigned i=0;i<8;++i)if(l[2*i]==action)return l[2*i+1];
    return 0;
}

const ScriptRow* ScriptEngine::current(const StateEntryActor& a) const {
    const auto& r=a.registry28c;
    return r[11]?&tables_.row(r[11]+20*r[0]):nullptr;
}
void ScriptEngine::queue(PlayerObject& b,StateEntryActor& a,const GroundStateFrame& f,int action) const {
    a.queuedActionA3c=action;a.flags248&=~0x800u;
    // 141318 freezes the rest of the battle and dims the stage palette.
    const int lock=tables_.lockTicks(a.character,action);
    if(lock<=0)return;
    if(!f.battle||!f.weaponLock)throw std::runtime_error("Action lock requires the live battle and opponent");
    auto& battle=*f.battle;
    battle.timers.lock=lock;
    // 14942c: Rasetsumaru's ACT 562 locks without focus or stage dimming
    // (141318 third argument 0) and marks 248 bit 0x800 instead.
    if(a.character==18&&action==0x232)a.flags248|=0x800u;
    else {
        battle.gauges.focus46a948=int32_t(b.ownerCC);
        for(auto& tone:std::span(battle.gauges.paletteTones).subspan(512))tone|=4;
    }
    a.flags23c|=0x08000000u;f.weaponLock->opponent.flags23c&=~0x08000000u;
}
bool ScriptEngine::enterAttack(PlayerObject& b,StateEntryActor& a,const GroundStateFrame& f) const {
    const int id=scriptId(a.callbacks260[2]);
    const auto flags=a.effectiveFlags();
    const unsigned variant=(flags&4)?2:(flags&2)?1:0;
    a.callbacks260[0]=0;
    if(id<0)return true;
    start(b,a,f,unsigned(id),variant);
    return false;
}
void ScriptEngine::start(PlayerObject& b,StateEntryActor& a,const GroundStateFrame& f,unsigned id,unsigned variant) const {
    auto& r=a.registry28c;
    // 163488 writes r[11] even when the id is absent and leaves r[4..10]/r[12].
    r[11]=tables_.find(a.character,id);
    if(!r[11])throw UnportedFighterState(a.character,a.stateTable(),a.stateIndex());
    r[2]=none;r[3]=variant;r[0]=0;r[1]=none;
    a.callbacks260[3]=variant;
    enterRow(b,a,f);
    // 1522a0 runs last, so callback words written by the row-0 event are replaced.
    a.callbacks260[0]=0x163610;a.callbacks260[1]=1;a.callbacks260[2]=none;
}
bool ScriptEngine::enterRow(PlayerObject& b,StateEntryActor& a,const GroundStateFrame& f) const {
    auto& r=a.registry28c;
    if(r[0]==r[1])return false;
    const auto& row=tables_.row(r[11]+20*r[0]);
    if(row.flags&8)face(b,a,f);
    // 164460: Yunfei rows 8..11 force the facing while 23c bit 0x100000 is set.
    if(a.character==23&&(a.flags23c&0x100000)&&row.id-8u<4)face(b,a,f,true);
    entryEvent(b,a,f,row.type);
    const auto var=int(r[3]);
    if(r[2]!=none)queue(b,a,f,int(r[2]));
    else if(row.act!=-1) {
        // 164460 tests the armed pair before the plain variant offset.
        if(row.flags&4)queue(b,a,f,row.act+2*var+((a.flags23c&0x1000)?0:1));
        else if(row.flags&2)queue(b,a,f,row.act+var);
        else queue(b,a,f,row.act);
    }
    r[2]=none;r[1]=r[0];
    r[6]=b.timeline.motion().y>0;
    b.scriptLatch134=0;
    return true;
}
// 165580(cb, amount, rage): self-drain that never drops below 1 life, then
// the rage gain. 14f2b8 scales with the factory 100% handicap.
void ScriptEngine::selfDrain(StateEntryActor& a,const GroundStateFrame& f,int32_t amount,int32_t rage) const {
    if(!f.battle||!f.weaponLock||!f.config||!callbacks_)throw std::runtime_error("Script self-drain requires the live battle and spirit");
    const int32_t scaled=std::bit_cast<int32_t>(uint32_t(amount)*100+99)/100;
    int32_t rest=a.fieldA30-scaled;if(rest<=0)rest=1;
    int32_t d=a.fieldA30-rest;
    if(scaled>0)d=d*amount/scaled;
    f.battle->queueLifeChange(a,f.weaponLock->opponent.flags23c,d);
    callbacks_->addRage(a,*f.config,rage);
}
void ScriptEngine::entryEvent(PlayerObject& b,StateEntryActor& a,const GroundStateFrame& f,uint8_t type) const {
    if(type==7)a.flags23c|=0x02000000u;else a.flags23c&=~0x02000000u;
    switch(type) {
    case 0xff:case 3:case 4:case 5:case 8:case 9:case 10:case 11:case 14:case 15:case 16:case 17:
    case 20:case 23:case 29:case 30:case 31:case 32:case 35:case 38:case 42:case 43:case 48:case 49:
    case 50:case 54:case 61:case 62:case 7:
        return;
    case 6:
        if(!f.weaponLock)throw std::runtime_error("Script contact event requires the opponent");
        f.weaponLock->opponent.flags244|=0x10;return;
    case 13:a.timers[17]=0x21c<<8;a.timers[18]=0x10<<8;return;
    case 56:case 57: { // body.x = (int)(cam.left + cam.width * k); face; 1414b8; 1414f8(3, 60)
        if(!f.weaponLock||!f.battle)throw std::runtime_error("Script events 56/57 need the camera");
        const auto& cam=f.weaponLock->camera;
        const uint32_t k=type==57?0x3f59999au:a.registry28c[3]==0?0x3e19999au:a.registry28c[3]==1?0x3ecccccdu:0x3f19999au; // 0.85 / 0.15 / 0.4 / 0.6
        const ScalarFloat x=ScalarFloat::integer(cam.left).add(ScalarFloat{std::bit_cast<uint32_t>(cam.width)}.mul(ScalarFloat{k}));
        b.timeline.setPosition(float(x.truncate()),b.timeline.motion().y);
        face(b,a,f); //14a978(actor, 0)
        f.battle->camera.commands.clear();f.battle->camera.appendCommand(3,60);
        return;
    }
    case 58:case 59: { // PakuPaku (47): 16ecf0 tests for any own object with d0 == 0xa8 (any kind)
        if(!f.pools)throw std::runtime_error("Script events 58/59 scan the own registry");
        const auto hasOrbit=[&]{
            for(auto t:f.ownObjectTasks)if(t&&f.pools->objects.at(f.pools->tasks.at(t-1)[7]-1)[0xd0/4]==0xa8)return true;
            return false;
        };
        auto& r=a.registry28c;
        if(type==58){if(hasOrbit())r[2]=0x24d;return;}
        if(b.timeline.action().id()==0x24d||hasOrbit())return;
        if(!f.weaponLock)throw std::runtime_error("16ed60 creates the orbiting objects");
        for(uint32_t i=0;i<4;++i) { // 16ed60: four kind-6 objects 90 degrees apart (tasks 16ee10 -> 16ee80)
            auto& w=*f.weaponLock;
            const auto h=w.objects.create(*f.pools,f.ownObjectTasks,f.seat,a.flags23c,b.childParentWords(),0x1396,6,0);
            if(!h)throw std::runtime_error("Original 16ed60 writes through a null object");
            auto& o=f.pools->objects.at(h-1);
            w.objects.request(o,0x24e,false,true); // 16c408 (108 |= 0x2000, cleared again below)
            o[0xd0/4]=0xa8;o[0x108/4]&=~0x2000u;f.pools->tasks.at(o[1]-1)[0]=0x16ee10;
            o[0x128/4]=i;o[0x12c/4]=0;o[0x130/4]=0;
        }
        return;
    }
    case 55: { // 209610(cb, 0): Poppy sends her first idle puppy (state < 3) to attack
        if(!f.pools)throw std::runtime_error("Script event 55 needs the own registry");
        for(auto t:f.ownObjectTasks)if(t) {
            auto& o=f.pools->objects.at(f.pools->tasks.at(t-1)[7]-1);
            if(int32_t(o[0x24/4])<0x301)continue;
            if(o[0x128/4]<3){o[0x128/4]=3;return;}
        }
        return;
    }
    case 0:stopAtGround(b);b.pendingFlags&=~8u;return; // 1697d0(cb); body.fe &= ~8
    case 63: { // Kuroko: pin the opponent 88 ahead, 1494c0(opp, 0x591, 0x592), clear its body latches 128..134
        if(!f.weaponLock)throw std::runtime_error("Script event 63 moves the opponent");
        auto& w=*f.weaponLock;
        const bool mirror=b.timeline.clock().objectFlags&0x80000;
        const ScalarFloat x{std::bit_cast<uint32_t>(b.timeline.motion().x)},d=ScalarFloat::integer(88);
        w.opponentBody.timeline.setPosition(std::bit_cast<float>((mirror?x.sub(d):x.add(d)).bits),w.opponentBody.timeline.motion().y);
        queue(w.opponentBody,w.opponent,f,0x591+((w.opponent.flags23c&0x1000)?0:1));
        w.opponent.flags244|=0x20000;
        {const auto k=w.opponentBody.timeline.clock();w.opponentBody.setFlags(k.flags104|0x80,k.flags108);}
        w.opponent.bodyState128=0;w.opponent.bodyLatch12c=0;w.opponent.bodyCounter130=0;w.opponentBody.scriptLatch134=0;
        GroundStateRuntime::captureBody(w.opponentBody,w.opponent); // the opponent's next visit restores from this
        return;
    }
    case 60: { // 11db88(body); actor.248 |= 0x200
        const auto k=b.timeline.clock();b.timeline.setObjectFlags(k.objectFlags^0x80000u,k.flags104,k.flags108);
        a.flags248|=0x200;return;
    }
    case 39: // 1493c0(opp, 0x62a, 1): a forced ACT on the opponent (the old body is marked first)
        if(!f.weaponLock)throw std::runtime_error("Script event 39 needs the opponent");
        f.weaponLock->opponentBody.markActorActionPending();
        queue(f.weaponLock->opponentBody,f.weaponLock->opponent,f,0x62a);
        return;
    case 40: { // character 33: a 1/16 draw picks the karuta variant (aux.130) and its voice
        if(!a.auxiliaryObject04||!f.pools||!f.random||!f.sound)throw std::runtime_error("Script event 40 needs the karuta, RNG and sound");
        auto& aux=f.pools->objects.at(a.auxiliaryObject04-1);
        const bool rare=f.random->bounded(16)==0;
        aux[0x130/4]=rare;
        const int h=f.sound->act(rare?0xcd:0xcc,int(f.seat),voiceCharacter(a),a.flags23c,3,0,*f.random);
        if(h>=0)b.sound34=uint32_t(h)|0xc000u;
        return;
    }
    case 12:case 41:case 44:case 45:case 46: { // companion commands (aux.128; event 12 also aux.130 = 26c)
        if(!a.auxiliaryObject04||!f.pools)throw std::runtime_error("Script companion event without a companion");
        auto& aux=f.pools->objects.at(a.auxiliaryObject04-1);
        aux[0x128/4]=type==12?6u:type==41?1u:type==44?0xdu:type==45?0x10u:0x11u;
        if(type==12)aux[0x130/4]=a.callbacks260[3];
        return;
    }
    case 47: {
        // 1efc70(body, 0) = 1efc98 then 11d990. 1efc98 stops the body, sets
        // y = 300.0 with a falling velocity and places it 20 units behind the
        // opponent's x by its own mirror bit; the trailing 11d990 clears the
        // velocity words again. 13a858 (byte 43d05e) is 0 under console VS.
        if(!f.weaponLock)throw std::runtime_error("Script drop event requires the opponent");
        const auto from=std::bit_cast<uint32_t>(f.weaponLock->opponentBody.timeline.motion().x);
        const ScalarFloat twenty{0x41a00000u};
        const auto x=(b.timeline.clock().objectFlags&0x80000)?ScalarFloat{from}.add(twenty):ScalarFloat{from}.sub(twenty);
        b.timeline.stopMotion();
        b.timeline.setPosition(std::bit_cast<float>(x.bits),300.f);
        b.timeline.stopMotion();
        a.flags23c|=0x30u;
        return;
    }
    case 28:selfDrain(a,f,0x20,0xb8);return;
    case 36: // 165180: reg[2] = variant + 0x24a unless the actor's own 244 bit 0x01000000 is set
        if(!(a.flags244&0x01000000))a.registry28c[2]=a.registry28c[3]+0x24a;
        return;
    case 37:--a.characterBytesF14[9];return; // actor.f1d -= 1 (byte wraps)
    case 51:a.registry28c[2]=(a.flags23c&0x1000)?0x263:0x264;return; // reg[2] by the armed bit
    case 18: { // 16c408(cb, 0x21d, 0, 0), 108 |= 0x8000; body+128 keeps it
        if(!f.weaponLock||!f.pools)throw std::runtime_error("Script event 18 requires the live object pools");
        auto& world=*f.weaponLock;
        const auto handle=world.objects.create(*f.pools,f.ownObjectTasks,f.seat,a.flags23c,b.childParentWords(),0x1396,6,0);
        if(!handle)throw std::runtime_error("Original 16c408 writes through a null object");
        auto& o=f.pools->objects.at(handle-1);
        world.objects.request(o,0x21d,false,true);o[0x108/4]|=0x2000|0x8000;
        a.bodyState128=handle;
        return;
    }
    case 19: { // body.x = opp.x -+ 8 (by the body's facing); the event-18 object follows
        if(!f.weaponLock||!f.pools||!a.bodyState128)throw std::runtime_error("Script event 19 requires the event-18 object");
        const bool mirror=b.timeline.clock().objectFlags&0x80000;
        const float ox=f.weaponLock->opponentBody.timeline.motion().x;
        const float x=std::bit_cast<float>(ScalarFloat{std::bit_cast<uint32_t>(ox)}.add(ScalarFloat{std::bit_cast<uint32_t>(mirror?8.f:-8.f)}).bits);
        b.timeline.setPosition(x,b.timeline.motion().y);
        f.pools->objects.at(a.bodyState128-1)[0x40/4]=std::bit_cast<uint32_t>(x);
        return;
    }
    case 25: { // var 2/1: 50 beside the opponent; otherwise the camera edge; then face
        if(!f.weaponLock)throw std::runtime_error("Script event 25 requires the opponent");
        const bool mirror=b.timeline.clock().objectFlags&0x80000;
        const ScalarFloat ox{std::bit_cast<uint32_t>(f.weaponLock->opponentBody.timeline.motion().x)},d=ScalarFloat::integer(50);
        const unsigned var=a.registry28c[3];
        float x;
        if(var==2)x=std::bit_cast<float>((mirror?ox.sub(d):ox.add(d)).bits);
        else if(var==1)x=std::bit_cast<float>((mirror?ox.add(d):ox.sub(d)).bits);
        else x=float(mirror?f.weaponLock->camera.right:f.weaponLock->camera.left);
        b.timeline.setPosition(x,b.timeline.motion().y);
        face(b,a,f);
        return;
    }
    case 26: { // 16c408(cb, 0x249, 0, 0); 80 behind the opponent by ITS facing; face
        if(!f.weaponLock||!f.pools)throw std::runtime_error("Script event 26 requires the live object pools");
        auto& world=*f.weaponLock;
        const auto handle=world.objects.create(*f.pools,f.ownObjectTasks,f.seat,a.flags23c,b.childParentWords(),0x1396,6,0);
        if(!handle)throw std::runtime_error("Original 16c408 writes through a null object");
        auto& o=f.pools->objects.at(handle-1);world.objects.request(o,0x249,false,true);o[0x108/4]|=0x2000;
        const bool oppMirror=world.opponentBody.timeline.clock().objectFlags&0x80000;
        const ScalarFloat ox{std::bit_cast<uint32_t>(world.opponentBody.timeline.motion().x)},d=ScalarFloat::integer(80);
        b.timeline.setPosition(std::bit_cast<float>((oppMirror?ox.add(d):ox.sub(d)).bits),b.timeline.motion().y);
        face(b,a,f);
        return;
    }
    case 27: // the first own kind-2 object with d0 0x2a/0x2b: unless at ACT 0x23b, override with 0x23c
        if(!f.pools)throw std::runtime_error("Script event 27 requires the live object pools");
        for(auto t:f.ownObjectTasks)if(t) {
            const auto& o=f.pools->objects.at(f.pools->tasks.at(t-1)[7]-1);
            if(o[0xcc/4]!=2)continue;
            if(o[0xd0/4]==0x2a||o[0xd0/4]==0x2b){if(o[0x24/4]!=0x23b)a.registry28c[2]=0x23c;return;}
        }
        return;
    case 21:a.flags23c|=0x400000u;return;
    case 22:a.flags23c&=~0x400000u;return;
    case 33:case 34:
        // Mina's volley and shoulder object need the live object pools.
        if(f.scriptEvent){f.scriptEvent(type);return;}
        throw UnportedFighterState(a.character,a.stateTable(),a.stateIndex());
    default:
        // Spawning, teleport and character-specific entry events are ported
        // by their characters; an unknown event must not be skipped.
        if(getenv("SS6_DEBUG_HANDLER"))fprintf(stderr,"event %u\n",unsigned(type));
        throw UnportedFighterState(a.character,a.stateTable(),a.stateIndex());
    }
}
bool ScriptEngine::rowComplete(PlayerObject& b,StateEntryActor& a,const ActorCommandInput& input,const GroundStateFrame& f) const {
    auto& r=a.registry28c;
    const auto& row=tables_.row(r[11]+20*r[0]);
    if(r[2]!=none)return true;
    if(row.type==0x1b&&b.timeline.action().id()==0x23c&&consumeHold(b,a))a.flags244|=0x400000u;
    unsigned end=row.end;
    if(a.character==22&&(a.flags23c&0x100000)&&end==4) {
        end=0;
        if(!(b.timeline.motion().y>0.f))b.timeline.stopMotion();
    }
    const float y=b.timeline.motion().y;
    const bool ended=actionEnded(b,a.queuedActionA3c);
    const auto& s=input.sampledFeatures;
    // 140d78(seat, n, 2): own kind-2 objects in registration order.
    const auto ownKind2=[&](const auto& visit) {
        if(!f.pools)throw std::runtime_error("Script end check requires the live object pools");
        for(auto t:f.ownObjectTasks)if(t) {
            const auto& o=f.pools->objects.at(f.pools->tasks.at(t-1)[7]-1);
            if(o[0xcc/4]==2&&visit(o))return true;
        }
        return false;
    };
    bool wait=true;
    switch(end) {
    case 0:if(ended)return true;break;
    case 1:if(y<=0||ended)return true;break;
    case 2:if(y>0||ended)return true;break;
    case 3:
        if(!r[6]){if(ended)return true;}
        else if(b.timeline.motion().vy<0)return true;
        break;
    case 4:if(touchedGround(b,a.queuedActionA3c)){stopAtGround(b);return true;}break;
    case 5:
        if(landingReady(b,a.queuedActionA3c)){stopAtGround(b);return true;}
        if(ended)return true;
        wait=false;break;
    case 6:
        if(consumeHold(b,a)||actionEnded(b,a.queuedActionA3c))return true;
        wait=false;break;
    case 7: { // 1648f8: the object with d0 == 10 (an ASSERT completes when none)
        const AuxiliaryObject* found=nullptr;
        ownKind2([&](const AuxiliaryObject& o){if(o[0xd0/4]==10){found=&o;return true;}return false;});
        if(!found)return true;
        const auto& o=*found;
        if((o[0x24/4]==0x25a&&o[0xc0/4]&&!(o[0x104/4]&1))||(o[0x104/4]&0x2c0000)||(o[0x100/4]&2))return true;
        const bool mirror=b.timeline.clock().objectFlags&0x80000;
        int state=-1;
        if(s[90])state=mirror?0x15:0x14;
        else if(s[88])state=mirror?0x14:0x15;
        else if(s[56])state=0x13;
        if(state>=0){a.pendingTable=0;a.pendingIndex=int16_t(state);} // 14ff80, 18c untouched
        wait=false;break;
    }
    case 8: // 164ac8: an unblocked ACT 0x263 object with d0 == 0x37
        if(ownKind2([](const AuxiliaryObject& o){
            return o[0xd0/4]==0x37&&o[0x24/4]==0x263&&o[0xc0/4]&&!(o[0x104/4]&1)&&!(o[0x108/4]&0x2000000);}))return true;
        break;
    case 9: // 164bc8
        if(!f.weaponLock)throw std::runtime_error("Script end 9 requires the opponent");
        if(ended&&f.weaponLock->opponent.state194!=0x150002)return true;
        break;
    case 10: { // 164c18: 16a830(cb, 16) or the end
        if(!f.weaponLock)throw std::runtime_error("Script end 10 requires the opponent");
        const float x=b.timeline.motion().x,ox=f.weaponLock->opponentBody.timeline.motion().x;
        const int radius=fighterRadius(a.character); // 14ae18 = radius, 14ae30 = (int)(640.0 - radius)
        const bool reached=(b.timeline.clock().objectFlags&0x80000)
            ?(x<=float(radius)||x<=std::bit_cast<float>(ScalarFloat{std::bit_cast<uint32_t>(ox)}.add(ScalarFloat::integer(16)).bits))
            :(float(int(640.f-float(radius)))<=x||std::bit_cast<float>(ScalarFloat{std::bit_cast<uint32_t>(ox)}.sub(ScalarFloat::integer(16)).bits)<=x);
        if(reached||ended)return true;
        break;
    }
    case 11: // never completes; at the end 169a50 mode 4 with table word 0
        if(ended){a.callbacks260[0]=0x169a50;a.callbacks260[1]=0;a.callbacks260[2]=none;a.callbacks260[5]=4;}
        break;
    case 12:updateAirLanding(b,a);return false; //173880, no r[6] update
    case 13:
        if(!(b.timeline.clock().flags108&0x40)){if(ended)return true;wait=false;break;}
        if(!s[92])return true;
        if(s[93]){wait=false;break;} // both held: continue
        return true;
    default:wait=false;break; // >= 14: ASSERT print only
    }
    if(wait)consumeHold(b,a);
    r[6]=b.timeline.motion().y>0;
    return false;
}
void ScriptEngine::visitRow(PlayerObject& b,StateEntryActor& a,const ActorCommandInput& input,const GroundStateFrame& f) const {
    auto& r=a.registry28c;
    const auto& row=tables_.row(r[11]+20*r[0]);
    switch(row.type) {
    // 8.1 type prologues: button holds (0x3c..0x3e) branch through row+6.
    case 0x3c:case 0x3d:case 0x3e: {
        const auto& h=input.sampledFeatures;
        const bool ended=actionEnded(b,a.queuedActionA3c);
        const int armedOffset=(a.flags23c&0x1000)?0:1;
        if(row.type==0x3c&&h[24])a.flags248|=0x200;
        if(!h[91]||!h[92])a.flags248&=~0x200u;
        if(row.type==0x3c&&ended&&(a.flags248&0x200))r[2]=uint32_t(row.branch[0]+armedOffset);
        if(row.type==0x3d&&ended&&unsigned(b.timeline.action().id()-0x270)<2)r[2]=uint32_t(row.branch[0]+armedOffset);
        if(row.type==0x3e&&!(a.flags248&0x200)&&(b.timeline.clock().flags108&0x40))r[2]=uint32_t(row.branch[0]+armedOffset);
        break;
    }
    case 0x3f: { // throw victim pinning by the body's record (four latches in the victim body 128..134)
        if(!f.weaponLock)throw std::runtime_error("Script row 0x3f pins the opponent");
        auto& w=*f.weaponLock;auto& ob=w.opponentBody;auto& oa=w.opponent;
        const bool mirror=b.timeline.clock().objectFlags&0x80000;
        const int s=int(int32_t(b.timeline.clock().step));
        using F=ScalarFloat;
        const auto shift=[&](int dx,int dy){
            const auto m=ob.timeline.motion();
            const F x{std::bit_cast<uint32_t>(m.x)},y{std::bit_cast<uint32_t>(m.y)};
            ob.timeline.setPosition(std::bit_cast<float>((dx<0?x.sub(F::integer(-dx)):x.add(F::integer(dx))).bits),
                                    std::bit_cast<float>((dy<0?y.sub(F::integer(-dy)):y.add(F::integer(dy))).bits));
        };
        if(oa.bodyState128==0&&s>=13){shift(mirror?5:-5,5);oa.bodyState128=1;}
        else if(oa.bodyLatch12c==0&&s>=11){shift(mirror?-1:1,-1);oa.bodyLatch12c=1;}
        else if(oa.bodyCounter130==0&&s>=10){shift(mirror?-3:3,-3);oa.bodyCounter130=1;}
        else if(ob.scriptLatch134==0&&s>=9) {
            const auto v=w.objects.anchor(oa.character,8);
            const auto m=b.timeline.motion();
            const F x{std::bit_cast<uint32_t>(m.x)},y{std::bit_cast<uint32_t>(m.y)};
            ob.timeline.setPosition(std::bit_cast<float>((mirror?x.sub(F::integer(v[0])):x.add(F::integer(v[0]))).bits),
                                    std::bit_cast<float>(y.add(F::integer(v[1])).bits));
            ob.scriptLatch134=1;
        }
        GroundStateRuntime::captureBody(ob,oa); // keep the pinned position across the victim's restore
        break;
    }
    case 0x20: // a hit by the own 0x5f projectile marks the body as hit (104:40000) first
        if(f.pools)for(auto t:f.ownObjectTasks)if(t) {
            const auto& o=f.pools->objects.at(f.pools->tasks.at(t-1)[7]-1);
            if(o[0xcc/4]!=2)continue;
            if(o[0xd0/4]==0x5f&&(o[0x104/4]&0x40000)){const auto c=b.timeline.clock();b.setFlags(c.flags104|0x40000,c.flags108);}
        }
        break;
    default:break;
    }
    // 8.2: branch targets use the FRESH row's flags but the visit's fixed row.
    const auto& cur=row;
    int offset=0,unarmed=0;
    if(cur.flags&4){offset=2*int(r[3]);unarmed=!(a.flags23c&0x1000);}
    else if(cur.flags&2)offset=int(r[3]);
    const auto flags104=b.timeline.clock().flags104;
    if(flags104&0x40000) {
        if(row.branch[0]!=-1) {
            if(!(cur.flags&0x20))offset=0;
            r[2]=uint32_t(row.branch[0]+offset+unarmed);
        }
        if(row.type==0x1d&&!(a.flags248&0x100))r[2]=none;
        if(!b.scriptLatch134&&row.type==0x1e) {
            // 16c408(cb, 0x274 / 0x214, 0, 0): an own kind-6 contact effect,
            // then 16e788(o, opp, 0) moves it onto the opponent's body anchor.
            if(!f.weaponLock||!f.pools)throw std::runtime_error("Script contact effect requires the live object pools");
            auto& world=*f.weaponLock;
            const auto handle=world.objects.create(*f.pools,f.ownObjectTasks,f.seat,a.flags23c,b.childParentWords(),0x1396,6,0);
            if(!handle)throw std::runtime_error("Original 16c408 writes through a null object");
            auto& o=f.pools->objects.at(handle-1);
            world.objects.request(o,(a.flags23c&0x100000)?0x274:0x214,false,true);
            o[0x108/4]=((o[0x108/4]|0x2000)&~0x10000u)|0x20000;
            const auto m=world.opponentBody.timeline.motion();
            o[0x40/4]=std::bit_cast<uint32_t>(m.x);o[0x44/4]=std::bit_cast<uint32_t>(m.y);
            const auto anchor=world.objects.bodyAnchor(world.opponent.character);
            o[0xec/4]=ScalarFloat{o[0xec/4]}.add(ScalarFloat::integer(anchor[0])).bits;
            o[0xf0/4]=ScalarFloat{o[0xf0/4]}.add(ScalarFloat::integer(anchor[1])).bits;
            b.scriptLatch134=1;
        }
        if(row.type==6) {
            if(!f.weaponLock)throw std::runtime_error("Script contact event requires the opponent");
            f.weaponLock->opponent.flags244|=0x10;
        }
    }
    if((flags104&0x80000)&&row.branch[1]!=-1) {
        if(!(cur.flags&0x40))offset=0;
        r[2]=uint32_t(row.branch[1]+offset+unarmed);
        if(row.type==0x11){if(a.flags23c&0x10)r[2]=none;} // airborne: no branch
        else if(row.type==0x2b)a.flags248|=0x8000u;
    }
    if(row.branch[2]!=-1) {
        const StageCamera* camera=f.weaponLock?&f.weaponLock->camera:f.battle?&f.battle->camera:nullptr;
        if(!camera)throw std::runtime_error("Script edge branch requires the live camera");
        // 14aad8(actor,(int)(14adf0+2.0),1,0); 14adf0 is 34 except characters 46/47.
        const int m=fighterRadius(a.character)+2; // 36, or 10 / 18 for characters 46 / 47
        const int x=int(b.timeline.motion().x);
        if(b.timeline.clock().objectFlags&0x80000?x<=camera->left+m:x>=camera->right-m) {
            if(!(cur.flags&0x80))offset=0;
            r[2]=uint32_t(row.branch[2]+offset+unarmed);
        }
    }
    if(row.type==5) {
        // 163d34 "steerable drift". Features 62/64 (actor+3bc/3c4) accelerate
        // forward/back, forward winning; without either, vx decays by 0.9 and
        // snaps to zero at |vx| <= 3276.8. Each conversion truncates (cvt.w.s).
        if(flags104&0x40000)b.timeline.stopMotion();
        else {
            auto m=b.timeline.motion();
            using F=ScalarFloat;
            const F limit{0x454ccccdu};
            if(!input.sampledFeatures[62]&&!input.sampledFeatures[64]) {
                m.vx=F::integer(m.vx).mul(F{0x3f666666u}).truncate();m.ax=0;
                const F mag=F::integer(m.vx<0?int32_t(0u-uint32_t(m.vx)):m.vx);
                if(!limit.less(mag))m.vx=0;
            } else {
                m.ax=F::integer(m.ax).add(input.sampledFeatures[62]?limit:F{0xc54ccccdu}).truncate();
                if(F{0x47800000u}.less(F::integer(m.vx)))m.vx=0x10000;
                if(F::integer(m.vx).less(F{0xc7800000u}))m.vx=-0x10000;
            }
            b.timeline.setMotion(m);
        }
    }
    if(row.type==0x24) {
        // 0x24: the first kind-2 own object (140d78(seat, 0, 2)) is caught
        // back when it is thrown object 0x61 within 78 units of the body.
        if(!f.pools||!f.weaponLock)throw std::runtime_error("Script type 0x24 requires the live object pools");
        for(auto task:f.weaponLock->objectTasks) {
            if(!task)continue;
            auto& o=f.pools->objects.at(f.pools->tasks.at(task-1)[7]-1);
            if(o[0xcc/4]!=2)continue;
            const ScalarFloat ox{o[0x40/4]},bx{std::bit_cast<uint32_t>(b.timeline.motion().x)},reach{0x429c0000u}; // 78.0
            if(o[0xd0/4]==0x61&&o[0x24/4]!=0x217&&!bx.less(ox.sub(reach))&&!ox.add(reach).less(bx)) {
                queue(b,a,f,0x220);o[0xd0/4]=0x62;f.weaponLock->objects.request(o,0x221,false,false);
            }
            break;
        }
    }
    if(row.type==0x32) {
        // 0x32: 165580(cb, 8, 0x2e) on each ACT hold marker, which it consumes.
        const auto c=b.timeline.clock();
        if(c.flags104&0x100){selfDrain(a,f,8,0x2e);b.setFlags(b.timeline.clock().flags104&~0x100u,c.flags108);}
    }
    if(row.type==0x11&&!b.scriptLatch134&&(b.timeline.clock().flags104&0x80080000u)) {
        // 16cfc8: 140c68(seat, 0x1396, 6, 16d020) and a forced ACT 0x283.
        if(!f.weaponLock||!f.pools)throw std::runtime_error("Script visit type 0x11 requires the live object pools");
        auto& world=*f.weaponLock;
        const auto h=world.objects.create(*f.pools,f.ownObjectTasks,f.seat,a.flags23c,b.childParentWords(),0x1396,6,0x16d020);
        if(!h)throw std::runtime_error("Original 16cfc8 writes through a null object");
        world.objects.request(f.pools->objects.at(h-1),0x283,false,true);
        b.scriptLatch134=1;
    }
    if(row.type==0x30||row.type==0x31) {
        // "mash": button 0 presses count in body+134; at the hold point 3/4
        // presses take the contact branch, otherwise skip a row directly.
        if(input.sampledFeatures[6])++b.scriptLatch134;
        const auto c=b.timeline.clock();
        if((c.flags108&0x40)&&std::bit_cast<int32_t>(b.scriptLatch134)>=(row.type==0x30?3:4)) {
            if(c.flags104&0x40000)r[2]=row.type==0x30?0x23b:0x23c;
            else ++r[0];
        }
    }
    if(row.type==0x36) {
        const auto& s=input.sampledFeatures;
        if((b.timeline.clock().flags108&0x40)&&(s[6]||s[7]||s[8]))r[2]=r[3]+0x268;
    }
    if(row.type==3||row.type==0x3c||row.type==0x3d||row.type==0x3e) {const auto c=b.timeline.clock();b.setFlags(c.flags104|0x2000,c.flags108);}
}
bool ScriptEngine::step(PlayerObject& b,StateEntryActor& a,const ActorCommandInput& input,const GroundStateFrame& f) const {
    auto& r=a.registry28c;
    const auto& old=tables_.row(r[11]+20*r[0]);
    visitRow(b,a,input,f);
    if(rowComplete(b,a,input,f)) {
        if(old.type==0x2a&&(a.flags244&0x04000000)) { // 14ff80(actor+18c, 1, 0x4d), no row entry
            a.pendingTable=1;a.pendingIndex=0x4d;a.request18c=1;
            return false;
        }
        if(old.type==0x10&&(a.characterBytesF14[11]&7)==7) { // f1f: 1e8298(seat, 0xc7, character)
            if(!f.sound||!f.random)throw std::runtime_error("Script row type 0x10 requires the sound selector");
            f.sound->act(0xc7,int(f.seat),voiceCharacter(a),a.flags23c,3,0,*f.random);
        }
        bool advance=true;
        if(old.type==4) {
            const auto& cur=tables_.row(r[11]+20*r[0]);
            int expect=old.act;
            // 163610 tests the variant flag before the armed pair.
            if(cur.flags&2)expect+=int(r[3]);
            else if(cur.flags&4)expect+=2*int(r[3])+((a.flags23c&0x1000)?0:1);
            if(int(b.timeline.action().id())!=expect){advance=false;r[1]=r[0]-1;}
        }
        if(advance) {
            const auto& cur=tables_.row(r[11]+20*r[0]);
            if(!(cur.flags&1)||r[2]!=none)++r[0];
            else {
                bool recover=false;
                if(old.end==1&&!(b.timeline.motion().y>0)) {
                    stopAtGround(b);
                    queue(b,a,f,(a.flags23c&0x1000)?590:591);
                    a.callbacks260[0]=0x169a50;a.callbacks260[1]=1;a.callbacks260[2]=none;a.callbacks260[5]=0;
                } else if(old.type>=9&&old.type<=11) {
                    a.pendingTable=0;a.pendingIndex=int16_t(0x20+old.type-9);
                } else {
                    if(input.sampledFeatures[0xfc/4])a.flags23c|=8u;else a.flags23c&=~8u;
                    recover=true;
                }
                r.fill(0);r[2]=none; // 163450
                return recover;
            }
        }
    }
    enterRow(b,a,f);
    return false;
}
}
