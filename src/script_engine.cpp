#include "script_engine.hpp"
#include "ground_state.hpp"
#include "battle_round.hpp"
#include "knockout.hpp"
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
void face(PlayerObject& b,StateEntryActor& a,const GroundStateFrame& f) {
    GroundStateRuntime::captureBody(b,a);
    a.opponentX=f.opponentX;a.faceOpponent();GroundStateRuntime::restoreBody(b,a);
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
    battle.timers.lock=lock;battle.gauges.focus46a948=int32_t(b.ownerCC);
    for(auto& tone:std::span(battle.gauges.paletteTones).subspan(512))tone|=4;
    a.flags23c|=0x08000000u;f.weaponLock->opponent.flags23c&=~0x08000000u;
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
    if(a.character==23)throw UnportedFighterState(a.character,a.stateTable(),a.stateIndex());
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
void ScriptEngine::entryEvent(PlayerObject&,StateEntryActor& a,const GroundStateFrame& f,uint8_t type) const {
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
    case 21:a.flags23c|=0x400000u;return;
    case 22:a.flags23c&=~0x400000u;return;
    case 33:case 34:
        // Mina's volley and shoulder object need the live object pools.
        if(f.scriptEvent){f.scriptEvent(type);return;}
        throw UnportedFighterState(a.character,a.stateTable(),a.stateIndex());
    default:
        // Spawning, teleport and character-specific entry events are ported
        // by their characters; an unknown event must not be skipped.
        throw UnportedFighterState(a.character,a.stateTable(),a.stateIndex());
    }
}
bool ScriptEngine::rowComplete(PlayerObject& b,StateEntryActor& a,const GroundStateFrame&) const {
    auto& r=a.registry28c;
    const auto& row=tables_.row(r[11]+20*r[0]);
    if(r[2]!=none)return true;
    if(row.type==0x1b||(a.character==22&&(a.flags23c&0x100000)&&row.end==4))
        throw UnportedFighterState(a.character,a.stateTable(),a.stateIndex());
    const float y=b.timeline.motion().y;
    const bool ended=actionEnded(b,a.queuedActionA3c);
    bool wait=true;
    switch(row.end) {
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
    default:throw UnportedFighterState(a.character,a.stateTable(),a.stateIndex());
    }
    if(wait)consumeHold(b,a);
    r[6]=b.timeline.motion().y>0;
    return false;
}
void ScriptEngine::visitRow(PlayerObject& b,StateEntryActor& a,const GroundStateFrame& f) const {
    auto& r=a.registry28c;
    const auto& row=tables_.row(r[11]+20*r[0]);
    switch(row.type) {
    case 0x3c:case 0x3d:case 0x3e:case 0x3f:case 0x20:case 0x11:case 0x24:case 0x05:case 0x30:case 0x31:
    case 0x32:case 0x36:case 0x1d:case 0x1e:case 0x2b:
        throw UnportedFighterState(a.character,a.stateTable(),a.stateIndex());
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
        if(row.type==6) {
            if(!f.weaponLock)throw std::runtime_error("Script contact event requires the opponent");
            f.weaponLock->opponent.flags244|=0x10;
        }
    }
    if((flags104&0x80000)&&row.branch[1]!=-1) {
        if(!(cur.flags&0x40))offset=0;
        r[2]=uint32_t(row.branch[1]+offset+unarmed);
    }
    if(row.branch[2]!=-1) {
        const StageCamera* camera=f.weaponLock?&f.weaponLock->camera:f.battle?&f.battle->camera:nullptr;
        if(!camera)throw std::runtime_error("Script edge branch requires the live camera");
        // 14aad8(actor,(int)(14adf0+2.0),1,0); 14adf0 is 34 except characters 46/47.
        if(a.character==46||a.character==47)throw UnportedFighterState(a.character,a.stateTable(),a.stateIndex());
        const int x=int(b.timeline.motion().x);
        if(b.timeline.clock().objectFlags&0x80000?x<=camera->left+36:x>=camera->right-36) {
            if(!(cur.flags&0x80))offset=0;
            r[2]=uint32_t(row.branch[2]+offset+unarmed);
        }
    }
    if(row.type==3) {const auto c=b.timeline.clock();b.setFlags(c.flags104|0x2000,c.flags108);}
}
bool ScriptEngine::step(PlayerObject& b,StateEntryActor& a,const ActorCommandInput& input,const GroundStateFrame& f) const {
    auto& r=a.registry28c;
    const auto& old=tables_.row(r[11]+20*r[0]);
    visitRow(b,a,f);
    if(rowComplete(b,a,f)) {
        if(old.type==0x2a||old.type==0x10)throw UnportedFighterState(a.character,a.stateTable(),a.stateIndex());
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
