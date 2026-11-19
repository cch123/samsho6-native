"""Independent original-function effect playback and preview rasterization.

The caller supplies native fixture birth events. This is not a complete
original battle/scheduler oracle. Quad generation executes original code up
to114ae8; texture filtering/coverage below is the inspection preview policy.
"""
import math,struct
from pathlib import Path
from mips_probe import Probe
ROOT=Path(__file__).resolve().parents[2]
ASSETS=ROOT/'work/ss6/extracted/resources'
def bits(v):return struct.unpack('<I',struct.pack('<f',v))[0]
def scalar(v):return struct.unpack('<f',struct.pack('<I',v))[0]
class OriginalEffects:
 def __init__(self):
  self.p=Probe((ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes(),finite_model=True)
  for bank,name in [(1,'01HitFlash.bin'),(5,'Display.bin'),(6,'Display2.bin'),(7,'Display3.bin')]:
   data=(ASSETS/name).read_bytes();base=0x4a4810+(bank-1)*0x3da0
   self.p.memory[base:base+len(data)]=data
  self.objects=[];self.draws=[];self.previous=None;self.vertex_checks=0
  self.palette=(ASSETS/'effect_pal_data.bin').read_bytes()
  self.textures={i:(ASSETS/n).read_bytes() for i,n in [(1,'effect01.tex'),(12,'hanabi1.tex'),(13,'hanabi2.tex'),(14,'moji_e.tex'),
   (15,'moji1.tex'),(16,'moji2.tex'),(17,'moji3.tex'),(20,'ougi1.tex'),(21,'ougi2.tex'),(22,'sakura.tex')]}
 def spawn(self,bank,action,flags,x,y,z):
  o=0x1d00000+len(self.objects)*0x200
  assert o<0x1e00000
  for f,v in [(12,x),(13,y),(14,z),(15,1)]:self.p.floats[f]=bits(v)
  self.p.run(0x123330,[o,bank,action,flags]);self.objects.append(o)
 def tick(self,row):
  self.draws=[]
  if self.previous is not None:
   assert row[0]==self.previous[0]+1
   for o in self.objects:
    self.p.write(0x4a2250,0,4);self.p.run(0x1235f8,[o])
    if self.p.read(0x4a2250,4):self.draws.append(bytes(self.p.memory[0x479250:0x479250+0x138]))
   if self.previous[57]!=5 and row[57]==5:
    final=row[96] and row[1]!=2
    for action in ([12,13,14] if row[1]==2 else [4,5,6,7,8,24,25,26] if final else [0,1,2,3]):self.spawn(7,action,0x100000,320,240,-50)
   for i in range(2):
    if row[47+i*6]>self.previous[47+i*6]:self.spawn(1,18,0x8000000|(0x80000 if i else 0),row[7+i*11],0,0)
  self.previous=row
  return list(self.draws)
 def paint(self,canvas,draws,camera):
  p=self.p;p.floats[12:15]=[bits(v) for v in camera];p.run(0x122ed8)
  for data in sorted(draws,key=lambda d:bool(struct.unpack_from('<I',d,0x38)[0]&0x100000)):
   o=0x1e00000;p.memory[o:o+len(data)]=data
   rec=p.run(0x1233a0,[o])[0];asset=p.read(rec+4,2);pal=p.read(rec+6,2)
   p.write(0x4c3510+asset*4,14,4)
   # This slice executes all trigonometry and projection callees unchanged.
   # It stops at the renderer entry; no GS call is skipped then resumed.
   p.run(0x123840,[o],stop_before=(0x114ae8,),limit=10000)
   sp=p.registers[29];vertices=[struct.unpack_from('<5fI',p.memory,sp+i*24) for i in range(4)]
   assert all(v[5]==0xffffffff for v in vertices)
   self.vertex_checks+=1
   if p.read(rec,2)&8 and p.read(rec+0x22,2):
    self.paint_rotated(canvas,vertices,self.textures[asset],pal,rec)
    continue
   x0,y0,_,u0,v0,_=vertices[0];x1,y1,_,u1,v1,_=vertices[3]
   left,top=40+x0*.5,y0*.5-68;w,h=(x1-x0)*.5,(y1-y0)*.5
   tex=self.textures[asset]
   if w<=0 or h<=0:continue
   for y in range(max(0,math.ceil(top-.5)),min(160,math.ceil(top+h-.5))):
    for x in range(max(0,math.ceil(left-.5)),min(400,math.ceil(left+w-.5))):
     # Preview nearest sampling reflects the selected discrete texel. At
     # an exact boundary this differs from flooring a reversed UV; neither
     # policy is claimed to reproduce GS filtering/subpixel coverage.
     tw,th=round(abs(u1-u0)*512),round(abs(v1-v0)*512)
     u=int((x+.5-left)*tw/w);v=int((y+.5-top)*th/h)
     if u1<u0:u=tw-1-u
     if v1<v0:v=th-1-v
     u+=round(min(u0,u1)*512);v+=round(min(v0,v1)*512)
     assert 0<=u<512 and 0<=v<512
     pixel=v*512+u;index=(tex[pixel//2]>>((pixel&1)*4))&15
     if not index:continue
     c=struct.unpack_from('<I',self.palette,(pal*16+index)*4)[0]
     if c>>24:
      assert c>>24==128
      pos=(y*400+x)*4
      canvas[pos:pos+4]=bytes([c&255,(c>>8)&255,(c>>16)&255,255])
 def paint_rotated(self,canvas,vertices,tex,pal,rec):
  xy=[(40+v[0]*.5,v[1]*.5-68) for v in vertices]
  xmin,xmax=min(v[0] for v in xy),max(v[0] for v in xy)
  ymin,ymax=min(v[1] for v in xy),max(v[1] for v in xy)
  u0,v0,tw,th=struct.unpack_from('<4h',self.p.memory,rec+8)
  flipx=vertices[2][3]<vertices[0][3];flipy=vertices[1][4]<vertices[0][4]
  if not tw or not th:return
  # Float vertices are binary rationals. Integer edge functions give this
  # independent oracle exact coverage and exact nearest-texel boundaries.
  unit=max(c.as_integer_ratio()[1] for point in xy for c in point)
  unit=max(unit,2)
  integral=[tuple(int(c*unit) for c in point) for point in xy]
  def cross(a,b):return a[0]*b[1]-a[1]*b[0]
  def sub(a,b):return a[0]-b[0],a[1]-b[1]
  for y in range(max(0,math.ceil(ymin-.5)),min(160,math.ceil(ymax-.5))):
   for x in range(max(0,math.ceil(xmin-.5)),min(400,math.ceil(xmax-.5))):
    for ids in [(0,1,2),(2,1,3)]:
     a,b,c=[integral[i] for i in ids];area=cross(sub(b,a),sub(c,a))
     if not area:continue
     at=((2*x+1)*unit//2,(2*y+1)*unit//2)
     wa=cross(sub(b,at),sub(c,at));wb=cross(sub(c,at),sub(a,at));wc=cross(sub(a,at),sub(b,at))
     if area<0:area,wa,wb,wc=-area,-wa,-wb,-wc
     if min(wa,wb,wc)<0:continue
     s=sum(weight*bool(i&2) for weight,i in zip([wa,wb,wc],ids))
     t=sum(weight*bool(i&1) for weight,i in zip([wa,wb,wc],ids))
     u,v=s*tw//area,t*th//area
     if not(0<=u<tw and 0<=v<th):continue
     if flipx:u=tw-1-u
     if flipy:v=th-1-v
     pixel=(v0+v)*512+u0+u;index=(tex[pixel//2]>>((pixel&1)*4))&15
     color=struct.unpack_from('<I',self.palette,(pal*16+index)*4)[0]
     if color>>24:
      assert color>>24==128
      at=(y*400+x)*4;canvas[at:at+4]=bytes([color&255,(color>>8)&255,(color>>16)&255,255])
     break
