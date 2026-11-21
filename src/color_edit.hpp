#pragma once
#include "system_data.hpp"
#include <array>
#include <cstdint>
#include <filesystem>
#include <span>
#include <vector>

namespace ss6 {
// color_edit.bin (extract_color_edit.py): the tables read by 13be78,
// 20eae0, 115d40, 13c880, 13bfd0 and 13c4f8.
struct ColorEditTables {
    explicit ColorEditTables(const std::filesystem::path& assets);
    struct Preview {int32_t id;std::array<std::array<int32_t,2>,4> part;}; // {action, 1-based record}
    std::array<uint8_t,52> auxBank{};       // 4ca9a8, ff = no auxiliary bank
    std::array<uint8_t,0x35> order{};       // 59cd20: 49 list ids, then the four EX ids
    int32_t auxBias=0;                      // 4caaac
    std::array<uint32_t,24> cacheSlots{};   // 5dd5c8: physical CLUT row of each cache entry
    std::array<Preview,51> preview{};       // 4ca278
    std::array<int32_t,51> weaponY{};       // 4ca9e0
    std::array<float,27> scalars{};         // 5e1d10
    int aux(int character) const {const auto v=auxBank.at(size_t(character));return v==0xff?-1:int(v);} // 13be78
    bool partExists(int character,int part) const;                                                     // 13c880
};

// 115d40: where the sixteen colours of (palette key, bank) come from.
// key = character*5 + colour | owner bits 10000 (seat 0) / 20000 (seat 1)
// | 40000 (per-seat runtime copy 3ec740 / 3f28c0) | 80000 (network buffer).
struct EditPaletteSource {
    enum class Table {PalAll,SaveImage,RuntimeP1,RuntimeP2,NetworkP1,NetworkP2};
    Table table=Table::PalAll;
    uint32_t group=0;      // index of the 32-byte colour group inside the table
    uint32_t identity=0;   // cache tag 439a48
    int bank=0;            // bank after the auxiliary-bank remap
};
EditPaletteSource resolveEditPaletteSource(const ColorEditTables&,uint32_t key,int bank);
// 129db0 as src/character_select.cpp stores it (0x40000 + button + owner),
// completed with the fighter: the key the draw path hands to 115d40.
// button 0..4 = pad bits 400, 200, 2, 4, 400000; edited = SELECT (80000) held.
uint32_t selectedPaletteKey(unsigned side,unsigned character,unsigned button,bool edited);

// The 24-entry palette cache as the editor uses it.
class EditPaletteCache {
public:
    virtual ~EditPaletteCache()=default;
    virtual void reset()=0;                                         // 1159d0
    virtual int resolve(uint32_t key,int bank)=0;                   // 115d40: CLUT row or -1
    virtual void poke(int row,unsigned entry,uint16_t colour)=0;    // 43ab70[row*16 + entry]
};
// Self-contained cache over the save image and the pal_all arena. No frame
// ages the reference words here; a renderer-owned cache replaces this class.
class StandaloneEditPaletteCache final:public EditPaletteCache {
public:
    StandaloneEditPaletteCache(const ColorEditTables& tables,SystemData& data,std::span<uint8_t> palAll);
    void reset() override;
    int resolve(uint32_t key,int bank) override;
    void poke(int row,unsigned entry,uint16_t colour) override;
    std::array<uint32_t,24> identity{},reference{},busy{};
    std::array<uint16_t,32*16> colours{};
private:
    const ColorEditTables& tables_;
    SystemData& data_;
    std::span<uint8_t> palAll_;
};

// 13bfd0 / 13c4f8: placement of the two preview objects. hidden means object
// flag 2; x and y are meaningful only when the function reached them.
struct EditPreviewPose {
    bool hidden=true,flip=false;   // flip: bit 31 of object+38 (Gaira's "other" part)
    float x=0,y=0;
    int action=-1,record=0;        // record is zero-based (object+28)
    uint32_t paletteKey=0;
};
// visible is the task's argument ANDed with ColorEdit::spriteLoaded (124a184);
// character is the fighter loaded by 13bed0 (object+14), part/colour/x0/pose
// come from ColorEdit::Preview.
EditPreviewPose colorEditSprite(const ColorEditTables&,int character,bool visible,int part,int colour,int x0);
EditPreviewPose colorEditCheckPose(const ColorEditTables&,int character,bool visible,int colour,int pose,int x0);

struct ColorEditPad {uint32_t held=0,pressed=0,repeat=0;}; // 118128 record of the controlling seat

// Requests the original issues through callees outside this module, in call order.
struct ColorEditEvent {
    enum Kind {
        Sound,          // 1e7b70(-1, a)
        CacheReset,     // 1159d0
        CameraInit,     // 13f8a8
        SpriteUnload,   // 13be98
        SpriteLoad,     // 13bed0(a = character)
        PortraitSet,    // 11d668(object 0, a = character, 190, 0, 290000)
        ObjectPlace,    // 11d570(object a, 0xb, b, c, 210000)
        ObjectAction,   // 11d908(object a, b = action, 1, 0)
        FrameKind,      // 182318(frame, a)
        FrameOpen,      // 182648
        FrameClose,     // 1826b0
        HeaderHide,     // 17f4b0(frame+1c); frame+14 = 0
        Help,           // 1827c0(frame, a = id, b = sub)
        SecondHint,     // 1827d8(frame, a)
        SecondHintShow, // 1827f0
        SecondHintHide, // 182828
        KeyHint,        // 181c10(frame+ac, a ? 5e1da0 : 5e1d90)
        AutoSave,       // 10f158
        SceneSwitch     // 1252f0(1, 0, 13b188, 127940): white fade to the title scene
    };
    Kind kind;int a=0,b=0,c=0;
};

// Scene 13b160 / task 13b1c8.
class ColorEdit {
public:
    // 17f308..17f4b0
    struct Slide {
        int x=0,y=0,remaining=0,duration=1,startX=0,startY=0,targetX=0,targetY=0,state=1,outX=0,outY=0,inX=0,inY=0;
        void configure(int ox,int oy,int ix,int iy,int frames);
        void in();
        void out();
        int tick();                      // 2 moving, 1 settled in, 0 settled out
        bool settled() const {return remaining<1;}
    private:
        void start(int tx,int ty);
    };
    // 20dff8..20e528
    struct List {
        uint32_t flags=5,disabled=0;
        int min=0,max=1,step=1,cursor=0,page=0;
        void range(int lo,int hi,int stride,int pageSize);
        void set(int value);
        void flag(unsigned bit,bool on) {flags=on?flags|(1u<<bit):flags&~(1u<<bit);}
        bool rowDisabled(int row) const {return (flags&0x800)&&row>=0&&row<32&&(disabled>>row&1);}
        int update(const ColorEditPad& pad,std::vector<ColorEditEvent>& events);
    };
    // Common head of the seven widgets: +c visible rows, +10 scroll,
    // +14 visible, +18 active, +1c slide, +50 list.
    struct Panel {
        int visibleRows=1,scroll=0,visible=0,active=0;
        Slide slide;
        List list;
        void rows(int count,int shown);  // 20e5d8
        int update(const ColorEditPad& pad,std::vector<ColorEditEvent>& events,int scrollEvent=-1);
    };
    struct Preview {
        int portraitVisible=0,colour=0;                     // 13bf00(object 0, visible, colour)
        int spriteVisible=0,part=0,x0=0;                    // 13bfd0(object 1, visible, part, colour, x0)
        int poseVisible=0,pose=0;                           // 13c4f8(object 2, visible, part, colour, pose, x0)
    };

    ColorEdit(const ColorEditTables& tables,SystemData& data,std::span<const uint8_t> palAll,EditPaletteCache& cache);
    // One task visit. Returns the requests of this visit; the first visit
    // also carries the requests of the task prologue.
    const std::vector<ColorEditEvent>& tick(const ColorEditPad& pad);

    int state() const {return cur_;}             // -2 after the exit request
    int nextState() const {return next_;}
    bool finished() const {return cur_==-2;}
    int character() const;                       // 20ee20
    int colour() const {return colourMenu.list.cursor;}
    int part() const {return partId[size_t(partPanel.list.cursor)];} // 20bf58
    uint32_t sliderWord() const;                 // 20f9f0
    uint32_t paletteKey() const {return uint32_t(character()*5+colour())|0x10000;}

    // Draw state. Row labels: characterIds through 4d4bb0, the five
    // colour rows and the two copy rows are fixed strings.
    Panel characterMenu,colourMenu,copyMenu,partPanel,swatchPanel,sliderPanel,dialog;
    std::array<int16_t,0x37> characterIds{};     // 1373830
    int partCharacter=0,partRows=0;              // P+6c, P+70
    std::array<int,5> partId{};                  // P+74, filled by 13c720
    std::array<uint32_t,15> swatch{};            // R+6c: ff000000 | bits 10-14 << 19 | bits 5-9 << 11 | bits 0-4 << 3
    List valueList;                              // S+6c
    std::array<uint8_t,3> field{0xf8,0xf8,0xf8},backup{}; // S+88 (bits 10-14, 5-9, 0-4), S+8b
    uint32_t clipboard=0x00f8f8f8;               // S+90
    int highlight=0;                             // S+94: 0, 1 copy row, 2 paste row
    int portrait=0;                              // task sp+1d38
    int portraitEnabled=0,spriteLoaded=0;        // 124a180, 124a184
    int loadedCharacter=0;                       // last 13bed0 argument
    Preview preview;

    // 13ca58 / 13cbd8 / 13c928, usable without the scene.
    void write(uint32_t word,int character,int part,int index,int colour);
    void restore(int character,int part,int colour);
    void loadSwatches(int character,int part,int colour);
private:
    void entry(int state,int ch);
    void update(int state,int ch,bool select,const std::array<int,7>& ev);
    void buildParts(int ch);                     // 13c720
    void loadSlider(uint32_t word);              // 20f998
    int sliderUpdate(const ColorEditPad& pad);   // 20fa40
    void partHelp(int ch);
    void emit(ColorEditEvent::Kind kind,int a=0,int b=0,int c=0) {events_.push_back({kind,a,b,c});}

    const ColorEditTables& tables_;
    SystemData& data_;
    std::span<const uint8_t> palAll_;
    EditPaletteCache& cache_;
    std::vector<ColorEditEvent> events_;
    int cur_=-1,next_=0;
    bool first_=true;
};
}
