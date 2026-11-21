#!/usr/bin/env python3
"""Compare the ranking scene 1e8850 to the Japanese callbacks for any ranking table.

Both entry paths: the title attract loop (factory tables, 582450 = -1) and the
arcade Game Over (1c5150 inserts the score and sets 582450). Every visit of the
priority-20 callback 1e8b38 is run in Probe on the display rows the original
copies at entry; its GS queue is decoded and compared with the native
MenuDrawList record by record, and both are rasterised to 640x480 frames.
"""
import hashlib,json,random,struct,subprocess,sys,tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np
from PIL import Image
from extract_console_ranking_art import setup,unpack4,RANK,PACKETS,GLYPH
from character_tiles_oracle import ROOT,ASSETS
from extract_collision_tables import SOURCE_HASH
from validate_console_ranking_art import original_clear

OUT=ROOT/'outputs/ss6-feasibility'
BACKGROUND=OUT/'combat-stage00-jump.png'
TABLE=0x43d0f0;TABLE_SIZE=0x118;PULSE=0x585294;HIGHLIGHT=0x582450
ALPHABET=b'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!?./-_ '
LENGTHS=(1,540,60,360,60,360,65,2,240,60,19*72+361,2,3)
SAMPLE={0:[0],1:[0,480,539],2:[0,1,17,29,57,59],3:[0,4,26,47,49,60,83,105,119,120,180,239,240,267,300,333,359],
        4:[0,1,15,29,47,59],5:[0,59,60,359],6:[0,1,24,41,63,64],7:[1],8:[0,25,59,60,61,76,88,100,119,139,179,180,181,203,225,239],
        9:[0,1,21,50,59],10:[0,1,25,50,51,71,72,73,144,200,380,550,711,950,1100,1250,1367,1368,1370,1440,1600,1668,1690,1727,1728],
        11:[1],12:[0,1,21]}   # the ticks of validate_console_ranking_art.py
DRIVER=r'''
#include "arcade_ranking.hpp"
#include "arcade_run.hpp"
#include "console_ranking_art.hpp"
#include "game_random.hpp"
#include "system_data.hpp"
#include <cstdio>
#include <fstream>
#include <iostream>
#include <memory>
#include <vector>
using namespace ss6;
static std::vector<uint8_t> hex(const std::string& s) {
    std::vector<uint8_t> out;
    for(size_t i=0;i+1<s.size();i+=2)out.push_back(uint8_t(std::stoi(s.substr(i,2),nullptr,16)));
    return out;
}
int main(int,char** argv) {
    const std::filesystem::path assets=argv[1];
    MenuCanvas canvas(assets);ArcadeRankingArt art(assets);ConsoleRankingArt replay(assets);
    SystemData system(assets);GameRandom random;
    std::ifstream tables(assets/"arcade_run.bin",std::ios::binary);
    std::vector<uint8_t> blob((std::istreambuf_iterator<char>(tables)),{});
    auto runTables=std::make_unique<ArcadeTables>(blob);
    ArcadeRun run(*runTables,system,random);
    std::vector<uint8_t> base(640*480*4);
    if(!std::ifstream(argv[2],std::ios::binary).read(reinterpret_cast<char*>(base.data()),base.size()))return 2;
    ArcadeRanking scene;bool alternate=true;
    const auto emit=[&](const MenuDrawList& list,unsigned phase) {
        std::printf("%zu\n",list.records.size());
        for(const auto& r:list.records)
            std::printf("%d %d %d %d %d %d %08x %a %a %a %a %a %a %a %a %a\n",int(r.kind),int(r.font),r.slot,r.glyph,r.blend,
                        r.additive,r.colour,r.z,r.x,r.y,r.w,r.h,r.u,r.v,r.uw,r.vh);
        std::fflush(stdout);
        auto pixels=base;
        if(phase>6)for(size_t i=0;i<pixels.size();i+=4){pixels[i]=pixels[i+1]=pixels[i+2]=0;pixels[i+3]=255;}
        art.rasterise(canvas,list,pixels);
        std::fwrite(pixels.data(),1,pixels.size(),stdout);std::fflush(stdout);
    };
    const auto rows=[&] {
        for(const auto& r:scene.table.rows) {
            std::printf("%d %d %d %d ",r.index,r.value,r.spirit,r.character);
            for(auto b:r.name)std::printf("%02x",b);
            std::printf("\n");
        }
        std::fflush(stdout);
    };
    std::string cmd;
    while(std::cin>>cmd) {
        if(cmd=="T") {  // table hex, overseas, 582450
            std::string data;int overseas,highlight;std::cin>>data>>overseas>>highlight;
            const auto bytes=hex(data);
            std::copy(bytes.begin(),bytes.end(),system.image().begin()+SystemData::ranking);
            system.setting(2)=uint8_t(overseas);
            scene.enter(art,system,random,highlight);alternate=true;
            rows();
        } else if(cmd=="F") {  // stateless draw of one visit
            unsigned phase,tick,first;int counter,direction,highlight;
            std::cin>>phase>>tick>>first>>counter>>direction>>highlight;
            MenuDrawList list;list.beginFrame();
            art.draw(canvas,list,{phase,tick,first},scene.table,highlight,{counter,direction});
            emit(list,phase);
        } else if(cmd=="V") {  // n visits of the scene object, the last one reported
            unsigned n;std::cin>>n;
            for(unsigned i=0;i<n;++i)scene.tick(false,alternate);
            const auto& f=scene.control.draw;
            std::printf("%u %u %u %d %d %d %d\n",f.phase,f.tick,f.firstRow,scene.drawPulse.counter,scene.drawPulse.direction,
                        scene.pulse.counter,scene.pulse.direction);
            MenuDrawList list;list.beginFrame();scene.draw(art,canvas,list);
            emit(list,f.phase);
        } else if(cmd=="C") {  // the factory replay of ConsoleRankingArt
            unsigned phase,tick,first;std::cin>>phase>>tick>>first;
            auto pixels=base;replay.paint({phase,tick,first},pixels);
            std::fwrite(pixels.data(),1,pixels.size(),stdout);std::fflush(stdout);
        } else if(cmd=="R") {  // 1c5150 through ArcadeRun, then the scene entry
            std::string data,name;unsigned seat;int score,character,spirit;
            std::cin>>data>>seat>>score>>character>>spirit>>name;
            const auto bytes=hex(data);
            std::copy(bytes.begin(),bytes.end(),system.image().begin()+SystemData::ranking);
            run.rankingHighlight=-1;run.game.score=score;
            run.players[seat].character=character;run.players[seat].spirit=spirit;
            const auto text=hex(name);
            const int placed=run.recordScore(seat,std::string(text.begin(),text.end()).c_str());
            scene.enter(art,system,random,run.rankingHighlight);
            std::printf("%d %d ",placed,run.rankingHighlight);
            for(size_t i=0;i<0x118;++i)std::printf("%02x",system.image()[SystemData::ranking+i]);
            std::printf("\n");rows();
            scene.leave(run);std::printf("%d\n",run.rankingHighlight);std::fflush(stdout);
        }
    }
}
'''

def signed(v):return v-(1<<32) if v>=1<<31 else v

class Oracle:
    def __init__(self):
        self.p=p=setup();self.clear=original_clear(p);self.instructions=0;self.packets=0
        raw=(ASSETS/'rank_obj.tex').read_bytes()
        self.indices={0x29:np.frombuffer((ASSETS/'map_main.tex').read_bytes(),np.uint8).reshape(1024,1024),
                      8:np.frombuffer(raw,np.uint8,512*512).reshape(512,512)}
        for slot,name in [(0x1e,'cloud_l'),(0x2b,'cloud_r'),(0x0a,'face')]:
            self.indices[slot]=unpack4((ASSETS/(name+'.tex')).read_bytes(),512)
        self.rankPal=np.frombuffer(raw,np.uint8,1024,512*512).reshape(8,4,8,4)[:,[0,2,1,3]].reshape(256,4)
        data=(ASSETS/'arcade_ranking.bin').read_bytes()
        self.faces=np.frombuffer(data,np.uint8,52*64,len(data)-52*64).reshape(52,16,4)
    def run(self,*args,**kw):
        result=self.p.run(*args,**kw);self.instructions+=result[1];return result
    def load(self,table,overseas,highlight):
        p=self.p
        p.memory[TABLE:TABLE+TABLE_SIZE]=table;p.write(0x43d052,overseas,1)
        self.run(0x315f38,[RANK,0,0x264]);p.put(21,RANK)
        self.run(0x1e88c0,limit=50000,stop_before=(0x1e898c,))
        p.write(HIGHLIGHT,highlight&0xffffffff,4);p.write(PULSE,0,4);p.write(PULSE+4,0,4)
        p.write(0x3d3aa0,0xffffffff,4)  # 1e9140 lifts the 113028 reveal limit before any text
        return self.rows()
    def rows(self):
        p=self.p;out=[]
        for i in range(25):
            a=RANK+0x18*i
            out.append([signed(p.read(a+4*k,4)) for k in range(4)]+[bytes(p.memory[a+16:a+24]).hex()])
        return out
    def pulse(self):return [self.p.read(PULSE,4),self.p.read(PULSE+4,4)]
    def frame(self,phase,tick,first,base,pulse=None):
        p=self.p;self.run(0x114e80)
        for a in (0x345178,0x345180,0x378e08,0x3ec73c,0x439a40):p.write(a,0,4)
        # 111890 -> 113aa8 releases every CLUT cache use mark once per frame.
        p.memory[0x439aa8:0x439aa8+0x60]=bytes(0x60)
        if pulse is not None:p.write(PULSE,pulse[0],4);p.write(PULSE+4,pulse[1],4)
        for a,v in ((0x258,phase),(0x260,tick),(0x25c,first)):p.write(RANK+a,v,4)
        slots={};last=0
        def watch(pc):
            nonlocal last
            if pc==0x1149d0:last=p.registers[6]&255
            if pc==0x108464:slots[p.read(0x345178,4)-1]=last
        if phase==7:
            p.write(0x1fff008,0x1ffff00,8);self.run(0x1e9174,observe=watch,limit=25000)
        else:
            if phase==11:p.write(0x582214,1,4)  # a scene change is already queued
            self.run(0x1e8b38,observe=watch,limit=400000,stop_before=(0x115a00,) if phase==6 and tick==64 else ())
        state=[p.read(RANK+a,4) for a in (0x258,0x260,0x25c)]
        self.run(0x116588,limit=500000)
        colours=lambda addr,n:np.frombuffer(p.memory,np.uint8,n*4,addr).reshape(n,4)
        prims=[];draws=[]
        for i in range(p.read(0x345178,4)):
            a=PACKETS+128*i;typ,col,tex,uv,xy,uv1,xy1=struct.unpack_from('<7Q',p.memory,a)
            kind,tag=typ&0xfff,typ>>12;col&=0xffffffff
            c=np.array([col>>(8*j)&255 for j in range(4)],np.int32)
            if kind==0xff3:
                v0,v3=p.read(a+16,8),p.read(a+64,8)
                (x,y),(r,b)=[(((q&65535)-0x6c00)/16,(((q>>16)&65535)-0x7900)/8) for q in (v0,v3)]
                z=v0>>32;prims.append(('flat',x,y,r,b,col,float(z),tag))
                draws.append((z,x,y,r,b,c,None,tag));continue
            if kind==0xff2:
                s=slots[i];q0=struct.unpack_from('<5fI',p.memory,uv);q1=struct.unpack_from('<5fI',p.memory,uv+72)
                x,y,z,u,v,_=q0;r,b,_,ur,vb,_=q1
                bank=(tex>>37&16383)-0x3081
                if s==8:pal=self.rankPal
                elif s==0x29:pal=colours(0x1232880,256)
                else:pal=colours(0x11e7980+64*bank,16)
                prims.append(('quad',s,x,y,r,b,u,v,ur,vb,col,z,tag,pal.copy() if s==0x0a else None))
                texture=self.indices[s]
            else:
                assert kind==0xff1 and (tex>>37)&16383==0x3080,hex(typ)
                (x,y),(r,b)=[(((q&65535)-p.read(0x32ce14,4))/16,(((q>>16)&65535)-p.read(0x32ce18,4))/16) for q in (xy,xy1)]
                z=(xy>>32)&0x7fffffff;u,v=(uv&65535)//16,((uv>>16)&65535)//16
                prims.append(('glyph',x,y,r,b,u,v,col,float(z),tag))
                ur,vb=u+(r-x),v+(b-y);texture=unpack4(p.memory[GLYPH:GLYPH+512*256],512);pal=colours(0x348a48,16)
            draws.append((z,x,y,r,b,c,(texture,pal,u,v,ur,vb),tag))
        self.packets+=len(draws)
        dst=base.copy() if phase<=6 else np.full_like(base,self.clear);dst[:,:,3]=255
        for _,x,y,r,b,color,src,tag in sorted(draws,key=lambda q:q[0]):
            x0,y0=max(0,int(x)),max(0,int(y));x1,y1=min(640,int(r)),min(480,int(b))
            if x1<=x0 or y1<=y0:continue
            rgb=dst[y0:y1,x0:x1,:3];existing=rgb.astype(np.int32)
            if src is None:shaded=color[:3];alpha=color[3]
            else:
                index,pal,u,v,ur,vb=src
                us=np.floor(u+(np.arange(x0,x1)+.5-x)*(ur-u)/(r-x)).astype(int).clip(0,index.shape[1]-1)
                vs=np.floor(v+(np.arange(y0,y1)+.5-y)*(vb-v)/(b-y)).astype(int).clip(0,index.shape[0]-1)
                texels=pal[index[vs[:,None],us]].astype(np.int32)*color//128
                shaded=np.minimum(texels[:,:,:3],255);alpha=texels[:,:,3:]
            # Tag 2ff2 is the additive preset 348bc0 (Cd + Cs) latched by a zero colour.
            if tag==2:rgb[:]=np.minimum(existing+shaded,255)
            else:rgb[:]=np.clip(existing+((shaded-existing)*alpha//128),0,255)
        return prims,dst,state

class Native:
    def __init__(self,exe,base):
        self.proc=subprocess.Popen([exe,ASSETS,base],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
    def send(self,line):self.proc.stdin.write((line+'\n').encode());self.proc.stdin.flush()
    def line(self):return self.proc.stdout.readline().decode().split()
    def rows(self):return [[int(v) for v in self.line()[:4]] for _ in range(25)]
    def records(self):
        out=[]
        for _ in range(int(self.line()[0])):
            f=self.line()
            out.append([int(v) for v in f[:6]]+[int(f[6],16)]+[float.fromhex(v) for v in f[7:]])
        return out
    def frame(self):return np.frombuffer(self.proc.stdout.read(640*480*4),np.uint8).reshape(480,640,4)
    def close(self):self.proc.stdin.close();assert self.proc.wait()==0

def native_rows(native):
    out=[]
    for _ in range(25):
        f=native.line();out.append([int(v) for v in f[:4]]+[f[4]])
    return out

def compare(case,prims,records,faces):
    assert len(prims)==len(records),(case,len(prims),len(records))
    for i,(o,n) in enumerate(zip(prims,records)):
        kind,font,slot,glyph,blend,additive,colour,z,x,y,w,h,u,v,uw,vh=n
        where=(case,i,o[:12],n)
        if o[0]=='flat':
            assert kind==0 and (x,y,x+w,y+h)==o[1:5] and colour==o[5] and z==o[6] and not additive,where
        elif o[0]=='quad':
            _,s,ox,oy,r,b,ou,ov,ur,vb,col,oz,tag,pal=o
            assert kind==2 and slot==s and colour==col and additive==(tag==2) and z==oz,where
            assert (x,y,x+w,y+h,u,v,u+uw,v+vh)==(ox,oy,r,b,ou,ov,ur,vb),where
            if s==0x0a:assert np.array_equal(pal,faces[glyph]),(where,'face CLUT')
        else:
            _,ox,oy,r,b,ou,ov,col,oz,tag=o
            assert kind==4 and font==3 and (x,y,x+w,y+h,u,v)==(ox,oy,r,b,ou,ov) and colour==col and z==oz,where

def same_frame(case,a,b):
    if np.array_equal(a,b):return
    mask=np.any(a!=b,axis=2);y,x=map(int,np.argwhere(mask)[0])
    raise AssertionError((case,int(mask.sum()),x,y,a[y,x].tolist(),b[y,x].tolist()))

def factory_table():
    out=bytearray()
    for i in range(5):out+=struct.pack('<IBBH',5-i,i,5,0)
    names=[b'HAO',b'NAK',b'RIM',b'HAN',b'GAL',b'KYO',b'UKY',b'GEN',b'BAS',b'SHI',b'GAI',b'AMA',b'JUB',b'ZAN',b'CHA',b'TAM',b'KAZ',b'SOG',b'RAS',b'RER']
    for i in range(20):out+=struct.pack('<IB4sBH',200000-10000*i,i,names[i],5,0)
    return bytes(out)

def random_table(rng):
    out=bytearray()
    for i in range(5):
        value=rng.choice([rng.randrange(1000),rng.randrange(1<<24),0,999])
        out+=struct.pack('<IBBH',value,rng.randrange(49),rng.randrange(10),rng.randrange(65536))
    scores=sorted((rng.choice([rng.randrange(10**7),rng.randrange(10**9),rng.randrange(1000)]) for _ in range(20)),reverse=True)
    for i in range(20):
        name=bytes(rng.choice(ALPHABET) for _ in range(rng.randrange(1,4))).ljust(4,b'\0')
        out+=struct.pack('<IB4sBH',scores[i],rng.randrange(49),name,rng.randrange(10),rng.randrange(65536))
    return bytes(out)

def natural_first(phase,tick):return max(0,19-max(0,tick-1)//72) if phase==10 else 0

def worker(job):
    kind,seed,exe,base_path=job
    base=np.asarray(Image.open(BACKGROUND).convert('RGBA'))
    oracle=Oracle();native=Native(exe,base_path);rng=random.Random(seed)
    faces=oracle.faces;report=dict(kind=kind,seed=seed,frames=0,visits=0,records=0)
    def check(case,phase,prims,image,records,frame):
        compare(case,prims,records,faces);same_frame(case,image,frame)
        report['frames']+=1;report['records']+=len(records)
    if kind in ('factory','random'):
        if kind=='factory':table,overseas,highlights=factory_table(),0,[-1]
        else:table,overseas=random_table(rng),rng.randrange(2);highlights=[-1,rng.randrange(20),rng.randrange(20)]
        for highlight in highlights:
            want=oracle.load(table,overseas,highlight)
            native.send(f'T {table.hex()} {overseas} {highlight}')
            got=native_rows(native);assert got==want,(kind,seed,[(a,b) for a,b in zip(got,want) if a!=b][:2])
            cases=[(ph,t) for ph,ticks in SAMPLE.items() for t in ticks] if kind=='factory' or highlight==-1 else \
                  [(10,t) for t in sorted(rng.sample(range(LENGTHS[10]),40))]+[(3,rng.randrange(360)),(9,rng.randrange(60))]
            for phase,tick in cases:
                first=natural_first(phase,tick);pulse=[rng.randrange(61),rng.randrange(2)]
                prims,image,_=oracle.frame(phase,tick,first,base,pulse)
                native.send(f'F {phase} {tick} {first} {pulse[0]} {pulse[1]} {highlight}')
                records=native.records();frame=native.frame()
                check((kind,seed,highlight,phase,tick),phase,prims,image,records,frame)
                if kind=='factory':
                    native.send(f'C {phase} {tick} {first}');same_frame(('replay',phase,tick),native.frame(),frame)
                    report['replay_frames']=report.get('replay_frames',0)+1
    elif kind=='session':
        # Every visit of the scene object from entry (or from phase 8) until
        # phase 12; the oracle keeps its own 585294/585298 between visits.
        table=random_table(rng);overseas=seed%2;highlight=[0,19,3,11][seed%4]
        want=oracle.load(table,overseas,highlight)
        native.send(f'T {table.hex()} {overseas} {highlight}')
        assert native_rows(native)==want
        skip=0 if seed<2 else 1447  # visits of phases 0..7
        native.send(f'V {skip+1}');previous=None;idle=0;report['pulse_steps']=0
        while idle<2:
            if previous is not None:native.send('V 1')
            phase,tick,first,dc,dd,pc,pd=map(int,native.line())
            records=native.records();frame=native.frame()
            if previous is None:assert (phase,tick)==((0,0) if skip==0 else (8,0)),(phase,tick)
            elif previous[0] not in (6,7,11):
                expect=previous if phase!=10 or tick else previous[:2]
                assert expect==([phase,tick,first] if phase!=10 or tick else [phase,tick]),(previous,phase,tick,first)
            assert oracle.pulse()==[dc,dd],(phase,tick,oracle.pulse(),dc,dd)
            prims,image,state=oracle.frame(phase,tick,first,base)
            assert oracle.pulse()==[pc,pd],(phase,tick,oracle.pulse(),pc,pd)
            check(('session',seed,phase,tick),phase,prims,image,records,frame)
            previous=state;report['visits']+=1;report['pulse_steps']+=[dc,dd]!=[pc,pd]
            idle+=phase==12
        report['pulse_end']=oracle.pulse()
    elif kind=='entry':
        # Game Over path: 1c5150 (via ArcadeRun::recordScore), the display
        # copy with 582450, and the destructor's 1c5270.
        p=oracle.p;report['insertions']=0;report['placed']=0
        for n in range(24):
            table=random_table(rng)
            seat=rng.randrange(2);character=rng.randrange(49);spirit=rng.randrange(10)
            scores=[struct.unpack_from('<I',table,0x28+12*i)[0] for i in range(20)]
            score=rng.choice([scores[rng.randrange(20)]+rng.randrange(-2,3),rng.randrange(10**8),0,scores[19]])
            score=max(0,min(score,2**31-1))
            name=bytes(rng.choice(ALPHABET[:-1]) for _ in range(rng.randrange(1,4)))
            p.memory[TABLE:TABLE+TABLE_SIZE]=table;p.write(HIGHLIGHT,0xffffffff,4)
            p.write(0x4c3898,score,4)
            record=0x456890+0x30*seat;p.write(record,character,1);p.write(record+8,spirit,1)
            p.memory[0x1fe0000:0x1fe0008]=name.ljust(8,b'\0')
            oracle.run(0x1c5150,[seat,0x1fe0000],limit=100000)
            after=bytes(p.memory[TABLE:TABLE+TABLE_SIZE]);highlight=signed(p.read(HIGHLIGHT,4))
            want=oracle.load(after,0,highlight)
            native.send(f'R {table.hex()} {seat} {score} {character} {spirit} {name.hex()}')
            placed,mark,image=native.line();got=native_rows(native);left=int(native.line()[0])
            assert int(mark)==highlight==int(placed),(n,placed,mark,highlight)
            image=bytes.fromhex(image)
            # 1c5150 builds the entry on its stack with strcpy: the padding and
            # the bytes after the name's NUL are not written by the native port.
            for i in range(25):
                o=0x28+12*(i-5) if i>=5 else 8*i
                if i<5:assert image[o:o+6]==after[o:o+6],(n,i)
                else:
                    nm=after[o+5:o+9].split(b'\0')[0]
                    assert image[o:o+5]==after[o:o+5] and image[o+9]==after[o+9] and image[o+5:o+9].split(b'\0')[0]==nm,(n,i)
            assert got==want,(n,[(a,b) for a,b in zip(got,want) if a!=b][:2])
            if highlight>=0:
                # Two visits of phase 10 with the inserted row on screen.
                f=min(max(highlight-rng.randrange(6),0),19)
                for _ in range(2):
                    tick=72*(19-f)+rng.randrange(1,73);first=natural_first(10,tick);pulse=[rng.randrange(61),rng.randrange(2)]
                    prims,frame,_=oracle.frame(10,tick,first,base,pulse)
                    native.send(f'F 10 {tick} {first} {pulse[0]} {pulse[1]} {highlight}')
                    check(('entry',n,tick),10,prims,frame,native.records(),native.frame())
            oracle.run(0x1c5270)
            assert left==signed(p.read(HIGHLIGHT,4))==-1
            report['insertions']+=1;report['placed']+=highlight>=0
    native.close()
    report['instructions']=oracle.instructions;report['packets']=oracle.packets
    return report

def main():
    assert hashlib.sha256((ASSETS.parent/'SLPS_255.59').read_bytes()).hexdigest()==SOURCE_HASH
    base=np.asarray(Image.open(BACKGROUND).convert('RGBA'));assert base.shape==(480,640,4)
    with tempfile.TemporaryDirectory() as tmp:
        tmp=Path(tmp);cpp=tmp/'ranking.cpp';cpp.write_text(DRIVER);exe=tmp/'ranking'
        src=ROOT/'src'
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',src,cpp]+
                       [src/f for f in ('arcade_ranking.cpp','console_attract_ranking.cpp','console_ranking_art.cpp','menu_canvas.cpp',
                                         'console_menu.cpp','system_data.cpp','arcade_run.cpp','game_random.cpp','scalar_float.cpp')]+
                       ['-o',exe],check=True)
        template=tmp/'base.rgba';template.write_bytes(base.tobytes())
        jobs=[('factory',0),('entry',1)]+[('session',s) for s in range(4)]+[('random',100+s) for s in range(int(sys.argv[1]) if len(sys.argv)>1 else 16)]
        with ProcessPoolExecutor(max_workers=6) as pool:
            reports=list(pool.map(worker,[(k,s,str(exe),str(template)) for k,s in jobs]))
    total=lambda key:sum(r.get(key,0) for r in reports)
    report=dict(status='passed',japanese_elf_sha256=SOURCE_HASH,
                asset_sha256=hashlib.sha256((ASSETS/'arcade_ranking.bin').read_bytes()).hexdigest(),
                exact_640x480_frames=total('frames'),session_visits=total('visits'),gs_packets=total('packets'),
                native_records=total('records'),factory_replay_frames=total('replay_frames'),
                score_insertions=total('insertions'),insertions_placed=total('placed'),
                probe_instructions=total('instructions'),runs=reports,
                scope='Original 1e8b38 phase callbacks (1e9174 tail for phase 7 after the optical loads) with their real '
                      '117a00/113f98/113be0/1145c0/113028/122ab8/115d40 callees on display rows produced by the original '
                      '1e88c0 copy; 1c5150 and 1c5270 whole. GS submission is suppressed (3ec73c) and the queue decoded; '
                      'frames are composed with the per-frame CLUT cache release of 113aa8. The demonstration battle under '
                      'phases 0..6 is a supplied combat image; phase 6 stops before the 115a00/148528 teardown.')
    (OUT/'arcade_ranking_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f"passed: {report['exact_640x480_frames']} frames ({report['session_visits']} consecutive visits), "
          f"{report['gs_packets']} packets, {report['score_insertions']} insertions, {report['probe_instructions']} instructions")

if __name__=='__main__':main()
