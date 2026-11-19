#include "character_tiles.hpp"
#include <iostream>
#include <bit>
#include <fstream>
#include <cmath>
#include <algorithm>
#include <stdexcept>
uint32_t word(){uint32_t v;if(!(std::cin>>v))throw std::runtime_error("Incomplete tile fixture");return v;}
uint64_t hash(const auto& range){uint64_t h=14695981039346656037ull;for(auto x:range){h^=uint32_t(x);h*=1099511628211ull;}return h;}
void emit(auto v){std::cout<<+v<<' ';}

void savePreview(const std::string& path,const ss6::CharacterTileState& state,const ss6::CharacterPaletteBank& palettes,
                 const std::vector<ss6::CharacterTileQuad>& quads) {
 constexpr int width=640,height=448;std::vector<uint8_t> image(width*height*3);
 for(int y=0;y<height;++y)for(int x=0;x<width;++x)for(int c=0;c<3;++c)image[(y*width+x)*3+c]=uint8_t(26+c*5+((x/16+y/16)%2)*5);
 for(const auto& q:quads) {
  if(q.blendMode||q.additive>1)throw std::runtime_error("Inspection raster blend outside admitted preview");
  const auto f=[&](unsigned i){return double(std::bit_cast<float>(q.vertices[i]));};
  const double x0=f(0),y0=f(1),ax=f(6)-x0,ay=f(7)-y0,bx=f(12)-x0,by=f(13)-y0,det=ax*by-ay*bx;
  if(det==0)continue;
  const int left=std::max(0,int(std::floor(std::min({f(0),f(6),f(12),f(18)})))),right=std::min(width,int(std::ceil(std::max({f(0),f(6),f(12),f(18)}))));
  const int top=std::max(0,int(std::floor(std::min({f(1),f(7),f(13),f(19)})))),bottom=std::min(height,int(std::ceil(std::max({f(1),f(7),f(13),f(19)}))));
  for(int y=top;y<bottom;++y)for(int x=left;x<right;++x) {
   const double dx=x+.5-x0,dy=y+.5-y0,a=(dx*by-dy*bx)/det,b=(ax*dy-ay*dx)/det;
   if(a<0||a>=1||b<0||b>=1)continue;
   const auto u=f(3)+a*(f(9)-f(3))+b*(f(15)-f(3)),v=f(4)+a*(f(10)-f(4))+b*(f(16)-f(4));
   const int tx=std::clamp(int(u*512),0,511),ty=std::clamp(int(v*512),0,511);
   const auto texel=(state.atlas[ty*256+tx/2]>>((tx%2)*4))&15;
   const auto color=palettes.rgba.at((q.paletteArgument&255)*16+texel),mod=q.vertices[5];
   if(!(color>>24))continue;
   const unsigned alpha=((color>>24)*(mod>>24))/128;
   for(unsigned c=0;c<3;++c) {
    const int src=std::min(255,int(((color>>(c*8))&255)*((mod>>(c*8))&255)/128)),at=(y*width+x)*3+c,dst=image[at];
    image[at]=uint8_t(std::clamp(q.additive?dst+src:dst+(((src-dst)*int(alpha))>>7),0,255));
   }
  }
 }
 //Nearest sampling is a diagnostic preview, not a PS2 GS pixel comparison.
 std::ofstream out(path,std::ios::binary);out<<"P6\n"<<width<<' '<<height<<"\n255\n";out.write(reinterpret_cast<const char*>(image.data()),image.size());
 if(!out)throw std::runtime_error("Could not save tile preview");
}
int main(int argc,char** argv){try {
 if(argc!=2)throw std::runtime_error("Expected assets");
 ss6::CharacterTiles tiles(argv[1],{0,0,51});ss6::EffectPalettes cache{};cache[0].fill(0xffffffff);
 ss6::CharacterDraws prepare(argv[1],{0,0,51});ss6::CharacterDrawState drawState;
 ss6::CharacterTileState state;std::array<uint16_t,1024> tones{};std::vector<ss6::CharacterTileQuad> quads;
 std::string op;while(std::cin>>op) {
  if(op=="begin"){auto seed=word();state.groups=word();state.depthCounter=word();for(unsigned i=0;i<state.atlas.size();++i)state.atlas[i]=uint8_t(i*17+seed);quads.clear();}
  else if(op=="cache"){auto row=word(),index=word();cache.at(row).at(index)=word();}
  else if(op=="render"){state.disabled=word();state.tintFlags=word();state.tintColor=word();state.tintAmount=word();}
  else if(op=="raw16"){auto i=word();tiles.palettes.raw16.at(i)=uint16_t(word());}
  else if(op=="raw32"){auto i=word();tiles.palettes.raw32.at(i)=word();}
  else if(op=="format"){auto i=word();tiles.palettes.format.at(i)=word();}
  else if(op=="tone"){auto i=word();tones.at(i)=uint16_t(word());}
  else if(op=="colorize"){auto f=word(),c=word(),a=word();tiles.palettes.colorize(f,c,a,tones);}
  else if(op=="object") {
   ss6::ObjectDrawQueue::Record o;for(auto& v:o)v=word();ss6::StageCamera camera;
   camera.projectionX=std::bit_cast<float>(word());camera.projectionY=std::bit_cast<float>(word());camera.depth=std::bit_cast<float>(word());camera.depthOffset=std::bit_cast<float>(word());camera.verticalOffset=std::bit_cast<float>(word());
   ss6::CharacterDrawContext c{camera,{word(),word()},std::bit_cast<int32_t>(word()),std::bit_cast<int32_t>(word())};
   tiles.submitObject(prepare,drawState,o,c,cache,state,quads);
  }
  else if(op=="sprite") {
   ss6::CharacterSprite s;s.slot=word();s.palette=word();s.image=word();s.flags=word();s.shadow=word();s.x.bits=word();s.y.bits=word();s.z.bits=word();s.scaleX.bits=word();s.scaleY.bits=word();
   s.mode=word();s.color=word();s.contextFlags=word();s.contextColor=word();s.additive=word();s.depthOffset.bits=word();tiles.submit(s,cache,state,quads);
  }else if(op=="save") {std::string path;std::cin>>path;savePreview(path,state,tiles.palettes,quads);}
  else if(op=="snapshot") {
   emit(state.groups);emit(state.depthCounter);emit(state.primitiveColor);emit(state.blendMode);
   for(auto& row:cache)emit(hash(row));emit(hash(tiles.palettes.raw16));emit(hash(tiles.palettes.raw32));emit(hash(tiles.palettes.format));emit(hash(tiles.palettes.rgba));emit(hash(tiles.palettes.source()));emit(hash(state.atlas));emit(quads.size());
   for(const auto& q:quads){for(auto v:q.vertices)emit(v);emit(q.paletteArgument);emit(q.blendMode);emit(q.additive);}std::cout<<'\n';
  }else throw std::runtime_error("Unknown tile operation");
 }
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
