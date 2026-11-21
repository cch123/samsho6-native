#pragma once
#include "edit_widgets.hpp"
#include "game_random.hpp"
#include <optional>
#include <span>

namespace ss6 {
// A custom ("祭") spirit: byte c is the global option index chosen for
// category c of the 47-entry table 4d6e30.
using SpiritDescriptor=std::array<uint8_t,16>;

struct SpiritsEditAssets {
    explicit SpiritsEditAssets(const std::filesystem::path& assets); // spirits_edit.bin
    struct Option {uint8_t category=0;int8_t cost=0;std::string romaji,japanese;};
    struct Category {std::string romaji,japanese;};
    std::array<Option,47> options;
    std::array<Category,16> categories;
    std::array<std::string,8> slotNames;        // 4ca250
    std::string panelTitle,emptyRow,optionTitle,pointFormat;
    // Out-of-table indices cost 0 here; the original reads past the table.
    int cost(unsigned option) const {return option<options.size()?options[option].cost:0;}
    int first(unsigned category) const;         // first option of a category
    int count(unsigned category) const;
};

// The eight records of 4d7068 live in the save image at +633c.
std::span<uint8_t,16> spiritSlot(SystemData& data,unsigned slot);
SpiritDescriptor readSpiritSlot(const SystemData& data,unsigned slot);                   // 1527c8
SpiritDescriptor defaultSpirit(const SpiritsEditAssets& assets);                         // 152898
void restoreDefaultSpirits(SystemData& data,const SpiritsEditAssets& assets);            // 152658
int spiritPointsUsed(const SpiritsEditAssets& assets,const SpiritDescriptor& d);         // 152908
// 152948: slots 0..5 have 50 points, slots 6 and 7 have 300.
int spiritPointsLeft(const SpiritsEditAssets& assets,const SpiritDescriptor& d,int slot);
inline int spiritSlotCount(const SystemData& data) {return data.option(0x95)?8:6;}       // byte 43d0ed

// 152988: (group, icon) pairs of the summary panel and of character select.
struct SpiritIcon {int16_t group,icon;};
std::vector<SpiritIcon> spiritIcons(const SpiritDescriptor& d);

// 152f08 unpacks the peers' tables to 12d2308 + player*80.
struct NetworkSpirits {std::array<std::array<SpiritDescriptor,8>,2> players{};};
// 152758(player, slot): sub-mode word 4c38a8 == 6 selects the network copy,
// any other value the saved table. Slot >= 8 yields no descriptor.
std::optional<SpiritDescriptor> spiritDescriptor(const SystemData& data,int subMode,unsigned player,unsigned slot,
                                                 const NetworkSpirits* network=nullptr);
// 14f4e0(cfg = actor+10c {system, player, character, slot}): only system 6
// has a descriptor. The result is the value of InputSystemConfig::descriptor.
std::optional<SpiritDescriptor> actorSpiritDescriptor(const SystemData& data,int subMode,int system,unsigned player,
                                                      unsigned slot,const NetworkSpirits* network=nullptr);
// Descriptor byte of one category, or -1 where 14f4e0 returns NULL.
int actorSpiritOption(const SystemData& data,int subMode,int system,unsigned player,unsigned slot,
                      unsigned category,const NetworkSpirits* network=nullptr);

// 20cd00: list panel with a label, a value text and a cost per row.
struct SpiritPanel {
    int width=0x80,height=0;
    std::string title;
    int visibleRows=1,scroll=0,visible=0,active=0;
    EditSlide slide;
    EditListCursor list;
    int nameChars=0,valueChars=0;               // widest label / value in bytes
    std::array<int,32> cost{};
    std::array<std::string,32> label,value;
    void construct(const SpiritsEditAssets& assets);
    void setRows(int count,int visibleCount,const SpiritsEditAssets& assets);  // 20cd68
    void setRow(unsigned row,const std::string& left,const std::string& right,int points); // 20ce48
};

// 20d6f8: category list (focus 0) and option list (focus 1) of one slot.
struct SpiritEditor {
    SpiritEditor(SystemData& data,const SpiritsEditAssets& assets);
    SpiritPanel categories,options;
    int slot=0,focus=0;
    std::array<int,16> first{};
    SpiritDescriptor descriptor{};
    // 20dfa8 help request: id f + category for the category list, id
    // 10 + category with the option row as sub index for the option list.
    int helpId=-1,helpSub=0;
    unsigned helpRevision=0;
    void load(int slotIndex);          // 20d7a0
    int update(const MenuPad& pad,std::vector<int>& sounds); // 20d818
    void show();                       // 20db00
    void hide();                       // 20db50
    void setActive(bool on);           // 20db90
private:
    void refresh();                    // 20dbc8
    void buildOptions(int category);   // 20dcd8
    void commit();                     // 20df58
    void help();                       // 20dfa8
    SystemData* data_;
    const SpiritsEditAssets* assets_;
};

struct SpiritsEditResult {
    std::vector<int> sounds;           // 1e7b70(-1, id) requests in order
    // Set on the visit that issues 10f158 and 1252f0(1, 0, 13ad60, 127940):
    // white fade to the title scene. autoSave mirrors 10f158's gate on the
    // image's first word; the card write itself belongs to the caller.
    bool exitToTitle=false,autoSave=false;
};

// Task 13ada0 ("customThreadGauge"), one tick per scheduler visit.
class SpiritsEdit {
public:
    // The frame constructor 1822a0 runs the page background setup 1ce478 for
    // this mode word (17ea48), which draws the C library generator once.
    SpiritsEdit(SystemData& data,const SpiritsEditAssets& assets,const EditWidgetAssets& widgets,GameRandom& random);
    // 178f90: mode word f is opened by seat 0, mode word 10 by seat 1.
    static unsigned controllingSeat(int modeWord) {return modeWord==0x10;}
    SpiritsEditResult tick(const MenuPad& pad);
    // 7 slot list, 8 editor, -1 closing, -2 scene switch requested.
    int state=-1,next=7;
    bool frameOpen=false;              // 182648 / 1826b0
    MenuChrome chrome;                 // background variant; 1ce660 is not run by this task
    int helpId=-1,helpSub=0;           // last 1821f8 request of either owner
    const std::string& helpText() const {return widgets_->help(helpId,helpSub);}
    EditListMenu slots;
    SpiritEditor editor;
    EditSlide summary;                 // 17eac8 panel origin
    std::vector<SpiritIcon> summaryIcons() const;  // icons of the highlighted slot
private:
    SystemData* data_;
    const EditWidgetAssets* widgets_;
    unsigned helpSeen_=0;
};
}
