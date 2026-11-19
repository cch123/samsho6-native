#include "motion.hpp"
#include "judgment.hpp"
#include <bit>
#include <iostream>
#include <stdexcept>
#include <string>

// A line protocol keeps differential fixtures cheap to batch. This executable
// is a native test interface and contains no original instruction interpreter.
int main() {
    try {
        std::string mode;
        while (std::cin>>mode) {
            if (mode=="command" || mode=="integrate") {
                ss6::MotionState s;
                std::cin>>s.dx>>s.vx>>s.ax>>s.dy>>s.vy>>s.ay;
                if (mode=="command") {
                    ss6::MotionCommand c; int reverse,suppress;
                    std::cin>>c.kind;
                    for (auto& v:c.values) std::cin>>v;
                    std::cin>>reverse>>suppress;
                    ss6::enterMotion(s,c,reverse,suppress);
                } else {
                    uint32_t delta; std::cin>>delta;
                    ss6::advanceMotion(s,delta,false);
                }
                std::cout<<s.dx<<' '<<s.vx<<' '<<s.ax<<' '<<s.dy<<' '<<s.vy<<' '<<s.ay<<'\n';
            } else if (mode=="rect") {
                ss6::Judgment j{}; float x,y; int mx,my;
                std::cin>>j.x1>>j.y1>>j.x2>>j.y2>>x>>y>>mx>>my;
                const auto r=ss6::worldRect(j,x,y,mx,my);
                std::cout<<r.left<<' '<<r.right<<' '<<r.bottom<<' '<<r.top<<'\n';
            } else if (mode=="intersect") {
                ss6::Rect a,b; ss6::Intersection out{false,123,456,789};
                std::cin>>a.left>>a.right>>a.bottom>>a.top>>b.left>>b.right>>b.bottom>>b.top;
                ss6::intersect(a,b,out);
                std::cout<<out.touches<<' '<<out.width<<' '<<out.centerX<<' '<<out.centerY<<'\n';
            } else throw std::runtime_error("Unknown probe command");
            if (!std::cin) throw std::runtime_error("Malformed probe input");
        }
    } catch (const std::exception& e) { std::cerr<<e.what()<<'\n'; return 1; }
}
