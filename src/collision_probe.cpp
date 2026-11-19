#include "collision.hpp"
#include <iostream>
#include <stdexcept>
#include <string>

static ss6::CollisionPlayer readPlayer(bool objectFields,bool profile) {
    ss6::CollisionPlayer p;
    unsigned stateFlags,mirrorX,mirrorY,count;
    if(profile)std::cin>>p.judgmentProfile;
    if (objectFields) {
        unsigned descriptor;
        std::cin>>p.objectKind>>p.objectTypeD0>>descriptor;
        p.descriptorFlagsA=uint8_t(descriptor);
    }
    std::cin>>p.owner>>p.objectFlags104>>p.objectFlags108>>p.actorFlags>>p.stateTable>>p.stateIndex>>stateFlags>>p.field1c8
            >>p.x>>p.y>>mirrorX>>mirrorY>>p.judgmentFlags>>count;
    p.stateFlags=uint8_t(stateFlags); p.mirrorX=mirrorX; p.mirrorY=mirrorY;
    if (count>7) throw std::runtime_error("Too many fixture judgments");
    for (unsigned i=0;i<count;++i) {
        ss6::Judgment j{};
        std::cin>>j.index>>j.metadata>>j.auxiliary>>j.x1>>j.y1>>j.x2>>j.y2;
        p.judgments.push_back(j);
    }
    return p;
}
static void side(const ss6::ContactSide& s) {
    const auto& f=s.fields;
    std::cout<<' '<<s.judgmentFlags<<' '<<f.type<<' '<<f.group<<' '<<f.variant<<' '<<f.remainder
             <<' '<<f.bit18<<' '<<f.middle11<<' '<<f.low7<<' '<<unsigned(s.category)<<' '<<unsigned(s.player);
}
int main(int argc,char** argv) {
    try {
        if (argc!=2) throw std::runtime_error("Expected asset directory");
        ss6::CollisionTables tables(argv[1]);
        std::string command;
        while (std::cin>>command) {
            std::vector<ss6::ContactEvent> events;
            if (command=="pair" || command=="pair-object" || command=="pair-profile") {
                unsigned both,sort; std::cin>>both>>sort;
                const auto a=readPlayer(command!="pair",command=="pair-profile"),b=readPlayer(command!="pair",command=="pair-profile");
                ss6::collectContacts(tables,a,b,0,1,events);
                if (both) ss6::collectContacts(tables,b,a,1,0,events);
                if (sort) ss6::orderContacts(events);
                std::cout<<events.size();
                for (const auto& e:events) {
                    std::cout<<' '<<e.route<<' '<<e.centerX<<' '<<e.centerY<<' '<<e.extra<<' '<<e.auxiliary<<' '<<e.width;
                    side(e.a);side(e.b);
                }
            } else if (command=="sort") {
                unsigned count;std::cin>>count;
                if (count>162) throw std::runtime_error("Queue overflow");
                for (unsigned i=0;i<count;++i) {
                    ss6::ContactEvent e{};std::cin>>e.route;e.auxiliary=int32_t(i);events.push_back(e);
                }
                ss6::orderContacts(events);
                for (const auto& e:events) std::cout<<e.auxiliary<<' ';
            } else throw std::runtime_error("Unknown collision probe command");
            if (!std::cin) throw std::runtime_error("Malformed fixture input");
            std::cout<<'\n';
        }
    } catch (const std::exception& e) { std::cerr<<e.what()<<'\n';return 1; }
}
