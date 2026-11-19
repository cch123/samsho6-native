#!/usr/bin/env python3
"""Record the published SDL viewer's final versus surface at reproducible pad ticks."""
import argparse
import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import struct
import tempfile
from PIL import Image,ImageChops,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs/ss6-feasibility'
DEFAULT=OUT/'native-viewer/ss6-viewer'
COUNT=90

def masks(crouch):
    # Sixteen lead-in ticks show the target's posture before the jump.
    # Holding down throughout makes the target return to its crouch after hitstun.
    target=32 if crouch else 0
    for i in range(COUNT):
        t=i-15
        ours=144 if t==1 else 256 if t==(34 if crouch else 32) else 0
        yield ours,target

def replay_text(pads):
    segments=[(500,0,0)]
    for a,b in pads:
        n,x,y=segments[-1]
        if (a,b)==(x,y):segments[-1]=(n+1,x,y)
        else:segments.append((1,a,b))
    return ''.join(f'{n} {a} {b}\n' for n,a,b in segments)

def capture(viewer,assets,pads,folder):
    def frame(i):
        script=folder/f'{i}.pad';image=folder/f'{i}.bmp'
        script.write_text(replay_text(pads[:i+1]))
        # --snapshot uses VersusScreen::show and the real 640x480 SDL
        # presentation. --dump would omit the HUD and display compositing.
        subprocess.run([viewer,'--assets',assets,'--mode','versus','--round-time','60',
                        '--match-replay',script,'--snapshot',image],check=True,capture_output=True)
        with Image.open(image) as im:
            assert im.size==(640,480)
            return im.convert('RGB').crop((0,0,640,448))
    with ThreadPoolExecutor(max_workers=4) as workers:return list(workers.map(frame,range(len(pads))))

def inspect(frames,crouch):
    # The two fights must show the actual on-screen 200 -> 191 HP bar change.
    impact=15+(44 if crouch else 42)
    # The priority-20 gauge samples HP before this tick's collision. The
    # original 200-pixel fill first loses its nine pixels on the next tick.
    def health(im):
        return sum(im.getpixel((x,49))==(255,255,32) for x in range(366,566))
    assert [health(frames[i]) for i in (impact-1,impact,impact+1,-1)]==[200,200,191,191]
    # After the impact several different defender/action frames must exist,
    # even when the controller continues to hold the original posture.
    assert len({im.crop((288,224,510,428)).tobytes() for im in frames[impact:impact+16]})>=6

def encode(frames,crouch,path,viewer_sha):
    # GIF viewers commonly clamp 10ms delays. Sample every second 60Hz
    # game tick for 1x, and retain every tick at 1/4x (15fps playback).
    font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial Unicode.ttf',17)
    images=[];delays=[]
    for mode,ticks,fps in [('原速  1×',range(0,len(frames),2),30),('慢放  ¼×',range(len(frames)),15)]:
        for j,tick in enumerate(ticks):
            canvas=Image.new('RGB',(640,480),(24,29,32))
            canvas.paste(frames[tick],(0,0));draw=ImageDraw.Draw(canvas)
            draw.text((15,463),'跳轻斩  ·  '+('蹲姿受击' if crouch else '站姿受击'),font=font,fill=(232,233,225),anchor='lm')
            draw.text((625,463),mode,font=font,fill=(232,233,225),anchor='rm')
            images.append(canvas)
            delays.append(10*(round((j+1)*100/fps)-round(j*100/fps)))
    sheet=Image.new('RGB',(320*8,240*((len(images)+7)//8)))
    for i,im in enumerate(images):sheet.paste(im.resize((320,240),Image.Resampling.NEAREST),((i%8)*320,(i//8)*240))
    palette=sheet.quantize(colors=256)
    samples=[im.quantize(palette=palette,dither=Image.Dither.NONE) for im in images]
    samples[0].save(path,save_all=True,append_images=samples[1:],duration=delays,loop=0,optimize=False,disposal=1,
                    comment=f"ss6-viewer SHA256 {viewer_sha}".encode())
    with Image.open(path) as verify:
        ms=0
        for k in range(verify.n_frames):verify.seek(k);ms+=verify.info['duration']
        assert ms==sum(delays)==7500 and verify.size==(640,480)
        print(path,verify.n_frames,'frames',ms,'ms',path.stat().st_size,'bytes')


def pose_sheet(assets,path,viewer_sha):
    root=ROOT/'work/ss6'
    background=(235,233,224)
    ink=(36,41,40);teal=(22,89,89);muted=(85,89,84);rule=(179,180,168)
    fonts={n:ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial Unicode.ttf',n) for n in (18,21,23,26,34)}
    canvas=Image.new('RGB',(1300,800),background);draw=ImageDraw.Draw(canvas)
    def label(x,y,text,size,color,anchor='lm'):draw.text((x,y),text,font=fonts[size],fill=color,anchor=anchor)
    label(30,38,'跳轻斩命中后的受击姿势',34,ink)
    label(1270,38,'P2  青衣霸王丸',23,teal,'rm')
    draw.line((30,67,1270,67),fill=rule,width=1)
    centers=[130+260*i for i in range(5)]
    for x,t in zip(centers,('命中前','受击姿势 1','受击姿势 2','受击姿势 3','恢复')):
        label(x,100,t,23,ink,'mm')
    with tempfile.TemporaryDirectory() as folder:
        exe=Path(folder)/'poses'
        subprocess.run(['c++','-std=c++20','-O2','-I',ROOT/'src',root/'jump_light_poses.cpp',
                        root/'build-native/libss6-runtime.a','-o',exe],check=True)
        for row,crouch in enumerate((False,True)):
            commands=''.join(f'{l} {r}\n' for l,r in masks(crouch))
            raw=subprocess.run([exe,assets,str(int(crouch))],input=commands.encode(),capture_output=True,check=True).stdout
            span=16+640*448*4
            assert len(raw)==5*span
            baseline=393+310*row
            counts=(9,3,4) if crouch else (5,2,3)
            label(30,baseline-249,('蹲姿' if crouch else '站姿')+'  ·  '+str(sum(counts))+' 个更新',21,teal)
            draw.line((30,baseline,1270,baseline),fill=rule,width=1)
            for i in range(5):
                index,tick,act,step=struct.unpack_from('<4I',raw,i*span)
                assert i==index and (not 0<i<4 or (act,step)==(350 if crouch else 356,i-1))
                im=Image.frombytes('RGBA',(640,448),raw[i*span+16:(i+1)*span]).convert('RGB')
                box=ImageChops.difference(im,Image.new('RGB',im.size,background)).getbbox()
                assert box and box[0]>0 and box[2]<640
                # Every source pose uses a unit camera and a common horizontal
                # actor origin. Align the lowest visible foot pixel to the line
                # without centering on the moving blade or resizing a figure.
                canvas.paste(im.crop(box),(centers[i]+box[0]-320,baseline-(box[3]-box[1])))
                if 0<i<4:label(centers[i],baseline+23,str(counts[i-1])+' 个更新',21,teal,'mm')
    draw.line((30,750,1270,750),fill=rule,width=1)
    label(30,772,'原生实战绘制队列中的 P2 身体层 · 单独展示姿势，已隐去 P1、火花及地面阴影。',18,muted)
    from PIL.PngImagePlugin import PngInfo
    meta=PngInfo();meta.add_text('Source',f'Packaged assets; ss6-viewer SHA256 {viewer_sha}. Isolated queue body, normalized camera, matched ground line.')
    canvas.save(path,pnginfo=meta,optimize=True)
    print(path)

def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--viewer',type=Path,default=DEFAULT);cli.add_argument('--assets',type=Path)
    cli.add_argument('--pose-sheet',action='store_true',help='Write only the isolated P2 hit-pose comparison PNG')
    cli.add_argument('--out',type=Path,default=OUT);args=cli.parse_args()
    viewer=args.viewer.resolve();assets=args.assets or viewer.parent/'assets'
    viewer_sha=hashlib.sha256(viewer.read_bytes()).hexdigest()
    print("ss6-viewer SHA256",viewer_sha)
    if args.pose_sheet:
        pose_sheet(assets,args.out/'jump-light-p2-poses.png',viewer_sha);return
    for crouch,name in [(False,'jump-light-slow.gif'),(True,'jump-light-crouch-slow.gif')]:
        with tempfile.TemporaryDirectory() as td:
            frames=capture(viewer,assets,list(masks(crouch)),Path(td))
            inspect(frames,crouch)
            if hashlib.sha256(viewer.read_bytes()).hexdigest()!=viewer_sha:
                raise RuntimeError("Published viewer changed during recording; rerun both clips")
            encode(frames,crouch,args.out/name,viewer_sha)
if __name__=='__main__':main()
