#include "asset_files.hpp"
#include "audio_routing.hpp"
#include "practice_art.hpp"
#include "native_match.hpp"
#include "arcade_presentation.hpp"
#include "gallery_art.hpp"
#if SS6_HAVE_PAUSE_ART
#include "pause_art.hpp"
#endif
#include <algorithm>
#include <cstdlib>
#include <fstream>
#include <iterator>

// Scene wiring of SPIRITS EDIT (13ad40), COLOR EDIT (13b160), GALLERY
// (1d22f8, 13ed98, 13e090, 182968) and the OPTION page KEY CONFIGURATION
// (13cdb0). The logic and art modules are validated separately; this file
// orders their calls as the original tasks do and routes their requests.
namespace ss6 {
namespace {
constexpr std::array<uint32_t,8> physicalButtons{0x400,0x200,2,4,0x400000,0x800000,0x100000,0x200000};
// 118128 word of the software controller (see resultPad in native_match.cpp).
uint32_t physicalPad(uint32_t logical) {
    uint32_t bits=logical&0xf8;
    if(logical&PadSelect)bits|=0x80000;
    for(unsigned i=0;i<physicalButtons.size();++i)if(logical&(PadLight<<i))bits|=physicalButtons[i];
    return bits;
}
}

struct NativeMatch::MenuScenes {
    MenuScene scene=MenuScene::None;
    unsigned seat=0;
    // 1252f0 request in flight: the scene entered at the midpoint (0 = none, Title = mode menu).
    uint32_t pending=0;
    std::unique_ptr<EditArt> editArt;
    std::unique_ptr<EditFrame> frame;
    EditPen pen;
    MenuChrome chrome;                       // page frame counters of the running scene (1ce478)
    // COLOR EDIT
    std::unique_ptr<ColorEditTables> colorTables;
    std::vector<uint8_t> palAll;             // resident pal_all.bin (408a40)
    std::unique_ptr<EditPaletteBank> bank;
    std::unique_ptr<ColorEdit> color;
    std::array<EditPreviewObject,3> preview{};
    // The two fighter preview objects (13bfd0 sprite, 13c4f8 check pose) drawn with the edited colours.
    struct PreviewBody {int character=-1,action=-1,record=-1;std::unique_ptr<PlayerObject> body;};
    std::array<PreviewBody,2> previewBodies;
    std::unique_ptr<ActionBank> previewBank;int previewBankCharacter=-1;
    std::unique_ptr<NativeScene> previewScene;int previewSceneCharacter=-1;
    ObjectDrawQueue previewQueue;
    // GALLERY
    std::unique_ptr<GalleryData> galleryData;
    std::unique_ptr<GalleryArt> galleryArt;
    GalleryTopMenu top;
    std::unique_ptr<IllustrationViewer> pictures;
    std::unique_ptr<SoundTest> sound;
    std::unique_ptr<EndingViewer> ending;
    bool reselect=false;                     // 182ce0: 182a98 returned, the selection starts again
    std::unique_ptr<GalleryEndingPlayer> endingPlayer; // 182a98 for the chosen character
    bool endingPlaying=false;
    std::array<int,2> banks{51,52};          // sample banks of groups 0 and 1 (1e79c8)
    int musicAge=-1;                         // visits since an accepted 214060 request
    // KEY CONFIGURATION
#if SS6_HAVE_PAUSE_ART
    std::unique_ptr<PauseArt> pauseArt;
    PauseWindowContext context;
#endif
    KeyConfigWindow keys;
};

struct NativeMatch::BattleOverlay {
#if SS6_HAVE_PAUSE_ART
    std::unique_ptr<GalleryArt> library;
    std::unique_ptr<PauseArt> pause;
    PauseEdgePulse pulse;                   // 582f60/582f64 survive between pauses
#endif
    std::unique_ptr<EditArt> edit;
    std::unique_ptr<PracticeArtTables> practiceTables;
    std::unique_ptr<EditFrame> practiceFrame;  // help window 12d3870 (1822a0)
    EditPen pen;
    MenuBackdrop backdrop;                  // untouched by the battle-mode windows
    MenuChrome chrome;
    MenuDrawList edits,windows;             // EditArt pass (practice), PauseArt pass (pause family)
    bool active=false;
};
NativeMatch::BattleOverlay& NativeMatch::battleOverlay() {
    if(!overlay_)overlay_=std::make_shared<BattleOverlay>();
    auto& o=*overlay_;
    if(!menuCanvas_)menuCanvas_=std::make_unique<MenuCanvas>(assets_);
#if SS6_HAVE_PAUSE_ART
    if(!o.library){o.library=std::make_unique<GalleryArt>(*menuCanvas_,assets_);o.pause=std::make_unique<PauseArt>(*menuCanvas_,*o.library,assets_);}
#endif
    if(!o.edit){o.edit=std::make_unique<EditArt>(assets_,*menuCanvas_);o.pen.colour=o.edit->assets().initialTextColour;}
    return o;
}
void NativeMatch::drawPauseOverlay() {
    auto& o=battleOverlay();
    o.windows.beginFrame();o.windows.asciiDepth=-200.f;o.edits.records.clear();
    o.active=pause_&&pause_->active;
    if(!o.active)return;
#if SS6_HAVE_PAUSE_ART
    menuCanvas_->setBrightness(system_->brightness());o.pause->setBrightness(system_->brightness());
    auto& list=o.windows;
    const PauseWindowContext context{unsigned(battle_.gameMode),pause_->ownerSeat(pauseGame_),SkillUnlocks(*system_)};
    auto random=battle_.random; // the battle-mode windows leave the backdrop and its RNG untouched
    if(pause_->windowTask[0]==PauseMenu::Woken)
        o.pause->drawKeyConfig(list,*keyAssets_,keyConfig_,*system_,context,o.backdrop,random,o.chrome);
    else if(pause_->windowTask[1]==PauseMenu::Woken&&skillList_)
        o.pause->drawSkillList(list,*skillList_,PauseWindowContext{context.gameMode,skillList_->seat,context.unlocks},o.backdrop,random,o.chrome);
    else o.pause->drawPauseMenu(list,*pauseAssets_,pauseDraw_,pause_->chrome,pauseGame_.submode==5,o.pulse);
#endif
}
void NativeMatch::drawPracticeOverlay() {
    auto& o=battleOverlay();
    const auto& p=*practiceBattle_;
    o.active=true;
    o.edits.beginFrame();o.edits.asciiDepth=-200.f;o.edits.resetCursor();
    o.windows.beginFrame();o.windows.asciiDepth=-200.f;
    if(!o.practiceTables)o.practiceTables=std::make_unique<PracticeArtTables>(assets_);
    EditArt::Context c{o.edits,o.pen,0,system_->option(0x7e)!=0};
    drawPracticeDisplays(*o.edit,*o.practiceTables,c,*practice_,p.damage,p.keys,
                         {fighters_[0].sampling.replayIndex,fighters_[1].sampling.replayIndex},p.tables);
    if(!o.practiceFrame)return;
    drawPracticeWindow(*o.edit,*o.practiceTables,c,p.window,*practice_,*o.practiceFrame,p.tables,[&]{
#if SS6_HAVE_PAUSE_ART
        // 212478 / 20ef38 / 210298 sit between the menu and the dialog. They
        // use the window library of PauseArt, composed in a second pass.
        const PauseWindowContext context{unsigned(battle_.gameMode),unsigned(practice_->localSeat()),SkillUnlocks(*system_)};
        auto random=battle_.random;
        if(p.keyConfigOpen&&keyAssets_)o.pause->drawKeyConfig(o.windows,*keyAssets_,keyConfig_,*system_,context,o.backdrop,random,o.chrome);
        if(p.skillListOpen&&skillList_)o.pause->drawSkillList(o.windows,*skillList_,context,o.backdrop,random,o.chrome);
#endif
    });
}
void NativeMatch::practiceFrame(int step) {
    auto& o=battleOverlay();
    const auto& p=*practiceBattle_;
    if(step==0) {
        if(!editWidgets_)editWidgets_=std::make_unique<EditWidgetAssets>(assets_);
        o.practiceFrame=std::make_unique<EditFrame>(o.edit->assets(),*editWidgets_,unsigned(practice_->localSeat()));
    }
    if(!o.practiceFrame)return;
    if(step==1)o.practiceFrame->tick();
    else applyPracticeHelp(*o.practiceFrame,p.help,p.tables);
}
bool NativeMatch::composeBattleOverlay(std::span<uint8_t> rgba) const {
    if(!overlay_||!overlay_->active)return false;
    if(rgba.size()!=640*480*4)throw std::invalid_argument("Expected a 640x480 RGBA frame");
    const auto& o=*overlay_;
    if(!o.edits.records.empty())o.edit->rasterise(o.edits,rgba);
#if SS6_HAVE_PAUSE_ART
    if(!o.windows.records.empty())o.pause->rasterise(o.windows,rgba);
#endif
    return true;
}
NativeMatch::MenuScenes& NativeMatch::menus() {
    if(!menus_)menus_=std::make_shared<MenuScenes>();
    if(!menuCanvas_)menuCanvas_=std::make_unique<MenuCanvas>(assets_);
    return *menus_;
}
NativeMatch::MenuScene NativeMatch::menuScene() const {
    if(menus_&&menus_->scene!=MenuScene::None)return menus_->scene;
    return option_?MenuScene::Option:MenuScene::None;
}
const ColorEdit* NativeMatch::colorEdit() const {return menus_?menus_->color.get():nullptr;}
std::span<const EditPreviewObject> NativeMatch::colorEditPreview() const {
    if(!menus_||menus_->scene!=MenuScene::ColorEdit)return {};
    return menus_->preview;
}
int NativeMatch::galleryRow() const {return menus_?menus_->top.row:0;}
int NativeMatch::galleryCursor() const {
    if(!menus_)return -1;
    switch(menus_->scene) {
    case MenuScene::Illustrations:return menus_->pictures->list.selector.current;
    case MenuScene::SoundTest:return menus_->sound->lists[size_t(std::clamp(menus_->sound->state,0,2))].selector.current;
    case MenuScene::EndingSelect:return menus_->ending->list.selector.current;
    default:return -1;
    }
}
const KeyConfigWindow* NativeMatch::optionKeyConfig() const {
    return menus_&&menus_->scene==MenuScene::KeyConfig?&menus_->keys:nullptr;
}
void NativeMatch::paintColorEditPreview(std::span<uint8_t> rgba) const {
    // 13f8a8 sets the camera 122e98(320, 150, -400) / 122eb8(-160, -200). The objects are ordinary
    // fighter bodies of resource slot 1 (13bed0 loads the fighter there), restarted by 11d908 when
    // the action changes and animated every visit; +20 is the palette key (fighter*5+colour) | 10000,
    // whose colours 115d40 reads from the edit block of the save image the editor writes into.
    // Object 0 (11d668(object, character, 400, 0, 290000), kind 8) is not drawn: it plays resource 99's
    // action 3 from slot 0 but shows the highlighted fighter (+14 / +1c = character, character * 5);
    // the kind-8 branch of the draw path is not ported.
    // Validation only: validate_menu_scenes.py compares the menu raster without the objects.
    if(std::getenv("SS6_MENU_NO_PREVIEW"))return;
    auto& m=*menus_;
    std::vector<AuxiliaryObject> poses;
    const auto submit=[&](PlayerObject& body) {
        auto pose=body.childParentWords();
        pose[0x24/4]=body.timeline.action().id();
        pose[0x28/4]=body.timeline.clock().step;
        pose[0x104/4]=body.timeline.clock().flags104;
        pose[0x8c/4]=body.color8c;
        poses.push_back(pose);
    };
    for(unsigned k=0;k<2;++k) {
        const auto& v=m.preview[k+1];
        auto& live=m.previewBodies[k];
        if(v.hidden||v.action<0){live={};continue;}
        if(m.previewBankCharacter!=v.character) {
            m.previewBank=std::make_unique<ActionBank>(assets_,true,unsigned(v.character));m.previewBankCharacter=v.character;
            for(auto& b:m.previewBodies)b={};
        }
        if(!live.body||live.character!=v.character||live.action!=v.action||live.record!=v.record) {
            live.character=v.character;live.action=v.action;live.record=v.record;
            try {live.body=std::make_unique<PlayerObject>(*m.previewBank,unsigned(v.action));}
            catch(const std::exception&) {live.body.reset();continue;}
            live.body->timeline.setRecordStep(uint32_t(v.record));
        } else live.body->animate(256);
        auto& body=*live.body;
        body.timeline.setPosition(v.x,v.y);
        const auto& c=body.timeline.clock();
        body.timeline.setObjectFlags(v.flip?(c.objectFlags|0x80000000u):(c.objectFlags&~0x80000000u),c.flags104,c.flags108);
        body.resourceSlot0c=1;body.field20=v.paletteKey;
        submit(body);
    }
    if(poses.empty())return;
    if(!m.previewScene||m.previewSceneCharacter!=m.previewBankCharacter) {
        m.previewScene=std::make_unique<NativeScene>(assets_,std::array<unsigned,3>{0,unsigned(std::max(m.previewBankCharacter,0)),51});
        m.previewSceneCharacter=m.previewBankCharacter;
    }
    m.previewScene->bindEdited(m.colorTables.get(),system_.get());
    m.previewScene->resetPalettes();
    m.previewQueue.beginFrame();
    for(const auto& o:poses)m.previewQueue.submit(o,GaugeState{});
    m.previewQueue.sort();
    StageCamera camera;
    camera.projectionX=320.f;camera.projectionY=150.f;camera.depth=-400.f;camera.verticalOffset=-200.f;
    std::array<uint16_t,1024> tones{};
    m.previewScene->paint(m.previewQueue,{camera,{},-2,0},EffectPalettes{},tones,rgba,{});
}
void NativeMatch::rasteriseMenu(std::span<uint8_t> rgba) const {
    if(rgba.size()!=640*480*4)throw std::invalid_argument("Expected a 640x480 RGBA frame");
    for(size_t i=0;i<rgba.size();i+=4){rgba[i]=rgba[i+1]=rgba[i+2]=0;rgba[i+3]=255;}
    if(!menuCanvas_)return;
    switch(menuScene()) {
    case MenuScene::Option:menuCanvas_->rasterise(menuList_,rgba);break;
    case MenuScene::SpiritsEdit:menus_->editArt->rasterise(menuList_,rgba);break;
    case MenuScene::ColorEdit:menus_->editArt->rasterise(menuList_,rgba);paintColorEditPreview(rgba);break;
    case MenuScene::EndingSelect:
        if(menus_->endingPlaying){menus_->endingPlayer->paint(rgba);break;}
        menus_->galleryArt->rasterise(menuList_,rgba);break;
    case MenuScene::GalleryTop:case MenuScene::Illustrations:case MenuScene::SoundTest:
        menus_->galleryArt->rasterise(menuList_,rgba);break;
    case MenuScene::KeyConfig:
#if SS6_HAVE_PAUSE_ART
        menus_->pauseArt->rasterise(menuList_,rgba);
#else
        menuCanvas_->rasterise(menuList_,rgba);
#endif
        break;
    case MenuScene::None:break;
    }
    for(size_t i=3;i<rgba.size();i+=4)rgba[i]=255;
}
void NativeMatch::menuFade() {
    // 1252f0: 117288/117318 scale the vertex colours and 116588 the CLUTs
    // while 3ebf18 bit 1 is set. The request made by the mode menu is still
    // falling when the new scene draws its first frames.
    bool enabled=sceneFade_.active();
    int level=sceneFade_.level();
    if(!enabled&&titleFadeTick_){enabled=true;level=selectWhiteLevel();}
    menuCanvas_->setBrightness(system_->brightness());
    menuCanvas_->setFade(enabled,level,0xffffffffu);
    if(!menus_)return;
    if(menus_->editArt)menus_->editArt->setFade(enabled,level,0xffffffffu);
    if(menus_->galleryArt)menus_->galleryArt->setFade(enabled,level,0xffffffffu);
#if SS6_HAVE_PAUSE_ART
    if(menus_->pauseArt)menus_->pauseArt->setBrightness(system_->brightness());
#endif
}
void NativeMatch::applyKeyMasks() {
    // 177310 tests pad word & mask for fighter button k. The fight samples
    // the logical pad word, whose bits PadLight << i stand for the physical
    // buttons square, triangle, circle, cross, R1, R2, L1, L2; mask bits
    // without a logical counterpart (1 and 100) cannot be pressed natively.
    for(unsigned seat=0;seat<2;++seat)for(unsigned slot=0;slot<8;++slot) {
        const uint32_t mask=keyMask(*system_,seat,slot);
        uint32_t logical=0;
        for(unsigned i=0;i<physicalButtons.size();++i)if(mask&physicalButtons[i])logical|=PadLight<<i;
        mappings_[seat].normal[slot]=logical;
    }
}

// ---------------------------------------------------------------------
// SPIRITS EDIT (task 13ada0)
void NativeMatch::enterSpiritsEdit(unsigned seat) {
    auto& m=menus();
    if(!spiritsAssets_)spiritsAssets_=std::make_unique<SpiritsEditAssets>(assets_);
    if(!editWidgets_)editWidgets_=std::make_unique<EditWidgetAssets>(assets_);
    if(!m.editArt)m.editArt=std::make_unique<EditArt>(assets_,*menuCanvas_);
    menuEntrySeed_=battle_.random.librarySeed;
    editSeat_=m.seat=seat;editLeaving_=false;
    // 1822a0 runs 1ce478 for this mode word: 1802 library draws, of which the
    // logic module takes the variant draw alone (see enterGalleryBackdrop).
    const uint64_t seed=battle_.random.librarySeed;
    spiritsEdit_.emplace(*system_,*spiritsAssets_,*editWidgets_,battle_.random);
    enterGalleryBackdrop(menuBackdrop_,spiritsEdit_->chrome,battle_.random,seed);
    m.frame=std::make_unique<EditFrame>(m.editArt->assets(),*editWidgets_,seat);
    m.pen=EditPen();m.pen.colour=m.editArt->assets().initialTextColour;
    menuList_=MenuDrawList();
    m.scene=MenuScene::SpiritsEdit;
}
void NativeMatch::tickSpiritsEdit(const std::array<NormalizedPadSample,2>& pads) {
    auto& m=menus();
    if(titleFadeTick_ && ++titleFadeTick_>=27)titleFadeTick_=0;
    const auto menuPads=menuRepeat_.sample({physicalPad(pads[0].held),physicalPad(pads[1].held)},
                                           {physicalPad(pads[0].pressed),physicalPad(pads[1].pressed)});
    m.frame->tick();
    const auto result=spiritsEdit_->tick(menuPads[editSeat_]);
    m.frame->follow(*spiritsEdit_);
    for(int id:result.sounds)sounds_.sample(-1,id);
    menuFade();
    menuList_.beginFrame();
    drawSpiritsEdit(*m.editArt,menuList_,m.pen,*spiritsEdit_,*m.frame,editSeat_,system_->option(0x7e)!=0);
    // 10f158 writes the card only while AUTO SAVE is on.
    if(result.autoSave && system_->autoSave())system_->saveFile();
    if(result.exitToTitle && !sceneFade_.active()){editLeaving_=true;sceneFade_.begin(true);}
    if(sceneFade_.tick() && editLeaving_) {
        editLeaving_=false;spiritsEdit_.reset();m.scene=MenuScene::None;returnToModeMenu();
    }
}

// ---------------------------------------------------------------------
// COLOR EDIT (task 13b1c8)
void NativeMatch::enterColorEdit(unsigned seat) {
    auto& m=menus();
    if(!editWidgets_)editWidgets_=std::make_unique<EditWidgetAssets>(assets_);
    if(!m.editArt)m.editArt=std::make_unique<EditArt>(assets_,*menuCanvas_);
    if(!m.colorTables) {
        m.colorTables=std::make_unique<ColorEditTables>(assets_);
        std::ifstream file(resolveAsset(assets_/"pal_all.bin"),std::ios::binary);
        m.palAll.assign(std::istreambuf_iterator<char>(file),std::istreambuf_iterator<char>());
    }
    menuEntrySeed_=battle_.random.librarySeed;
    editSeat_=m.seat=seat;editLeaving_=false;
    // 1822a0 -> 1ce478: the page background state is drawn although the
    // layouts of this scene show the still picture (1ce628).
    m.chrome=MenuChrome();
    m.chrome.enter(menuBackdrop_.enter(battle_.random));
    // The editor resolves its keys (owner bit 10000) on the save image through the cache of 115d40.
    m.bank=std::make_unique<EditPaletteBank>(*m.colorTables,*system_,m.palAll);
    m.color=std::make_unique<ColorEdit>(*m.colorTables,*system_,m.palAll,*m.bank);
    m.frame=std::make_unique<EditFrame>(m.editArt->assets(),*editWidgets_,seat);
    m.pen=EditPen();m.pen.colour=m.editArt->assets().initialTextColour;
    m.preview={};
    menuList_=MenuDrawList();
    m.scene=MenuScene::ColorEdit;
}
void NativeMatch::tickColorEdit(const std::array<MenuPad,2>& pads,const std::array<uint32_t,2>& held) {
    auto& m=*menus_;
    const unsigned seat=m.seat;
    m.bank->beginFrame();   // 113aa8
    m.frame->tick();
    bool leave=false;
    for(const auto& e:m.color->tick({held[seat],pads[seat].pressed,pads[seat].repeat})) {
        m.frame->apply(e);
        switch(e.kind) {
        case ColorEditEvent::Sound:sounds_.sample(-1,e.a);break;
        // 10f158 writes the card only while AUTO SAVE is on.
        case ColorEditEvent::AutoSave:if(system_->autoSave())system_->saveFile();break;
        case ColorEditEvent::SceneSwitch:leave=true;break;
        default:break;
        }
    }
    menuFade();
    menuList_.beginFrame();
    m.preview=drawColorEdit(*m.editArt,menuList_,m.pen,*m.color,*m.colorTables,*m.frame,*editWidgets_,seat,
                            system_->option(0x7e)!=0);
    if(leave && !sceneFade_.active()){editLeaving_=true;sceneFade_.begin(true);}
    if(sceneFade_.tick() && editLeaving_) {
        editLeaving_=false;m.color.reset();m.bank.reset();m.scene=MenuScene::None;returnToModeMenu();
    }
}

// ---------------------------------------------------------------------
// GALLERY (1d22f8 and its three sub-scenes)
void NativeMatch::enterGallery(unsigned seat) {
    auto& m=menus();
    if(!widgetData_)widgetData_=std::make_unique<MenuWidgetData>(assets_);
    if(!m.galleryData)m.galleryData=std::make_unique<GalleryData>(assets_);
    if(!m.galleryArt)m.galleryArt=std::make_unique<GalleryArt>(*menuCanvas_,assets_);
    menuEntrySeed_=battle_.random.librarySeed;
    m.seat=seat;m.pending=0;
    m.galleryArt->gameMode=battle_.gameMode;
    m.galleryArt->extraIcons=system_->option(0x7e)!=0;
    m.top.reset();          // 1d2610 at the mode-menu confirm
    m.banks={51,int(lineup_[1].character)};   // as enterTitleAudio bound them
    m.musicAge=-1;
    menuList_=MenuDrawList();
    enterGalleryScene(uint32_t(GalleryScene::TopMenu));
}
void NativeMatch::enterGalleryScene(uint32_t scene) {
    auto& m=*menus_;
    auto& random=battle_.random;
    const uint64_t seed=random.librarySeed;
    switch(GalleryScene(scene)) {
    case GalleryScene::TopMenu:
        m.top.enter(*m.galleryData,m.chrome,random);
        m.scene=MenuScene::GalleryTop;break;
    case GalleryScene::Illustrations:
        m.galleryArt->forget();   // 17ed90
        m.pictures=std::make_unique<IllustrationViewer>();
        m.pictures->enter(unsigned(m.top.operatingSeat),*system_,*widgetData_,*m.galleryData,m.chrome,random);
        m.scene=MenuScene::Illustrations;break;
    case GalleryScene::SoundTest:
        m.sound=std::make_unique<SoundTest>();
        m.sound->enter(unsigned(m.top.operatingSeat),*system_,*widgetData_,*m.galleryData,m.chrome,random);
        m.scene=MenuScene::SoundTest;break;
    case GalleryScene::Ending: {
        m.ending=std::make_unique<EndingViewer>();
        // 182968 -> 120110: 1e79c8(0, 0x31), the ending scripts' sound bank 49 into group 1.
        sounds_.loadBank(0,0x31);
        m.ending->enterScene(*m.galleryData,m.chrome,random);
        enterGalleryBackdrop(menuBackdrop_,m.chrome,random,seed);
        // 182ce0 enters the selection 13f4a8 on its first visit.
        const uint64_t second=random.librarySeed;
        m.ending->beginSelection(unsigned(m.top.operatingSeat),*system_,*widgetData_,m.chrome,random);
        enterGalleryBackdrop(menuBackdrop_,m.chrome,random,second);
        m.reselect=false;
        m.scene=MenuScene::EndingSelect;return;
    }
    default:throw std::runtime_error("Unknown gallery scene");
    }
    enterGalleryBackdrop(menuBackdrop_,m.chrome,random,seed);
}
void NativeMatch::galleryEvents(const std::vector<GalleryEvent>& events) {
    auto& m=*menus_;
    const auto packaged=[&](const char* stem,int id) {
        if(id==0)return true;   // Haohmaru's groups are resident in combat_sound_bank.bin
        if(id<0||id>99)return false;
        return std::filesystem::exists(assets_/(std::string(stem)+(id<10?"0":"")+std::to_string(id)+".bin"));
    };
    for(const auto& e:events) switch(e.kind) {
    case GalleryEvent::Tone:case GalleryEvent::BankTone:
        // 1e7ba0 has the body of 1e7b70: group a, tone b.
        if(e.a<0||packaged("vs_sounds_",m.banks[size_t(e.a)&1]))sounds_.sample(std::clamp(e.a,-1,1),e.b);
        break;
    case GalleryEvent::LoadBank:
        // 1e79c8(a, b) -> 212dd8: one group's bank (its voices too below 0x31).
        m.banks[size_t(e.a)&1]=e.b;
        sounds_.loadBank(e.a,e.b);
        break;
    case GalleryEvent::BattleSound:
        // 1e8298: the fighter command path with mode word d/e, which lifts the gate of commands 170..197.
        if(packaged("vs_sounds_",e.c)&&packaged("vs_voice_",e.c))
            sounds_.act(e.b,e.a,e.c,0,battle_.gameMode,0,battle_.random);
        break;
    case GalleryEvent::Voice:sounds_.voice(e.a,e.b,e.c);break;
    case GalleryEvent::Music:
        // 214060(track, flag): the soundtrack byte in force (c), the repeat flag (b)
        // and the fade-out on the next stop.
        sounds_.requestMusic(1,e.c!=0,e.a,e.b);m.musicAge=0;
        break;
    case GalleryEvent::MusicStop:sounds_.stopMusic();m.musicAge=-1;break;
    case GalleryEvent::EffectsStop:sounds_.stopGroup(2);break;
    case GalleryEvent::Scene:
        if(!sceneFade_.active()){m.pending=uint32_t(e.b);sceneFade_.begin(true);}
        break;
    case GalleryEvent::EndingChosen:
        // 182ce0: 4ef0c8 = 0; 182a98(c).
        try {
            if(!m.endingPlayer)m.endingPlayer=std::make_unique<GalleryEndingPlayer>(assets_);
            m.endingPlayer->begin(e.a,system_->setting(2)!=0);
            m.endingPlaying=true;
        } catch(const std::exception&) {m.reselect=true;} // the ending assets are not packaged
        break;
    // The narration language bank (213180/213238) is not routed: the mixer plays the factory language.
    default:break;
    }
}
void NativeMatch::tickGallery(const std::array<MenuPad,2>& pads,const std::array<uint32_t,2>& held) {
    auto& m=*menus_;
    auto& art=*m.galleryArt;
    auto& random=battle_.random;
    const auto widgetPad=[&](unsigned i){return WidgetPad{held[i],pads[i].pressed,pads[i].repeat};};
    menuFade();
    switch(m.scene) {
    case MenuScene::GalleryTop: {
        menuList_.beginFrame();
        // 1ce660 draws the bands and the legend before it advances the counters.
        const MenuChrome before=m.chrome;
        m.top.tick(*m.galleryData,m.chrome,pads);
        art.seat=unsigned(m.top.operatingSeat);
        art.drawGalleryTop(menuList_,menuBackdrop_,random,before,m.top,*m.galleryData);
        galleryEvents(m.top.events);
        break;
    }
    case MenuScene::Illustrations:
        menuList_.beginFrame();
        m.pictures->tick(widgetPad(m.pictures->seat));
        art.drawIllustrationViewer(menuList_,menuBackdrop_,random,m.chrome,*m.pictures);
        galleryEvents(m.pictures->events);
        break;
    case MenuScene::SoundTest:
        menuList_.beginFrame();
        // 213d70: the stream word is set by the driver once the request plays
        // (five service steps and twelve load ticks in CombatMusic).
        if(m.musicAge>=0&&m.musicAge<18)++m.musicAge;
        m.sound->tick(widgetPad(m.sound->seat),m.musicAge>=18);
        art.drawSoundTest(menuList_,menuBackdrop_,random,m.chrome,*m.sound,*m.galleryData);
        galleryEvents(m.sound->events);
        break;
    case MenuScene::EndingSelect:
        if(m.endingPlaying) {
            std::vector<ArcadeSceneSound> requests;
            const bool done=m.endingPlayer->tick(pads[m.ending->seat].pressed,requests);
            // The scripts' 1e7c00 / 1e7b70 / 1e7ad0 and their objects' 1e8298 (mode word d / e).
            selectEndingSounds(sounds_,*system_,requests,battle_.gameMode,battle_.random);
            if(!done)break;
            // 182a98 returned: this visit continues into 182858 and 13f4a8 without a yield.
            m.endingPlaying=false;m.reselect=true;
        }
        if(m.reselect) {
            // 182ce0 starts the next selection with the last choice preselected.
            const uint64_t seed=random.librarySeed;
            m.ending->beginSelection(unsigned(m.top.operatingSeat),*system_,*widgetData_,m.chrome,random);
            enterGalleryBackdrop(menuBackdrop_,m.chrome,random,seed);
            m.reselect=false;
        }
        m.ending->tick(widgetPad(m.ending->seat));
        // 13f4a8 returns the choice before its draw: the previous frame stays.
        if(!m.ending->chosen) {
            menuList_.beginFrame();
            art.drawEndingSelect(menuList_,menuBackdrop_,random,m.chrome,*m.ending);
        }
        galleryEvents(m.ending->events);
        break;
    default:break;
    }
    if(!sceneFade_.tick()||!m.pending)return;
    const uint32_t next=m.pending;m.pending=0;
    m.pictures.reset();m.sound.reset();m.ending.reset();
    if(GalleryScene(next)==GalleryScene::Title) {
        // 1d2508: 124d50 clears the game data before the title scene.
        m.scene=MenuScene::None;returnToModeMenu();
    } else enterGalleryScene(next);
}

// ---------------------------------------------------------------------
// OPTION -> KEY CONFIGURATION (coroutine 13ce08 in a menu mode)
void NativeMatch::enterKeyConfig() {
    auto& m=menus();
    if(!widgetData_)widgetData_=std::make_unique<MenuWidgetData>(assets_);
    if(!keyAssets_)keyAssets_=std::make_unique<KeyConfigAssets>(assets_);
    if(!m.galleryArt)m.galleryArt=std::make_unique<GalleryArt>(*menuCanvas_,assets_);
    menuEntrySeed_=battle_.random.librarySeed;
    const unsigned mode=unsigned(battle_.gameMode);
    m.seat=KeyConfigWindow::operatingSeat(mode,0,0);   // 178f90: mode word 11 / 12
    m.keys=KeyConfigWindow{};
    m.keys.start(*widgetData_,m.seat);
    // 1822a0 runs 1ce478 in a menu mode.
    m.chrome=MenuChrome();
    m.chrome.enter(menuBackdrop_.enter(battle_.random));
#if SS6_HAVE_PAUSE_ART
    if(!m.pauseArt)m.pauseArt=std::make_unique<PauseArt>(*menuCanvas_,*m.galleryArt,assets_);
    m.context.gameMode=mode;m.context.seat=m.seat;
#endif
    m.pending=0;
    menuList_=MenuDrawList();
    m.scene=MenuScene::KeyConfig;
}
void NativeMatch::tickKeyConfig(const std::array<MenuPad,2>& pads,const std::array<uint32_t,2>& held) {
    auto& m=*menus_;
    const auto widgetPad=[&](unsigned i){return WidgetPad{held[i],pads[i].pressed,pads[i].repeat};};
    std::vector<int> tones;
    const auto result=m.keys.tick({widgetPad(0),widgetPad(1)},*system_,*keyAssets_,true,tones);
    for(int id:tones)sounds_.sample(-1,id);
    applyKeyMasks();
    menuFade();
    menuList_.beginFrame();
#if SS6_HAVE_PAUSE_ART
    m.context.unlocks=SkillUnlocks(*system_);
    m.pauseArt->drawKeyConfig(menuList_,*keyAssets_,m.keys,*system_,m.context,menuBackdrop_,battle_.random,m.chrome);
#else
    menuCanvas_->background(menuList_,menuBackdrop_,battle_.random,m.chrome);
    menuCanvas_->ascii(menuList_,"KEY CONFIGURATION",0x44,0x58,0xffffffffu);
#endif
    // 1252f0(1, 0, 13cdc8, 1cfa10): back to the OPTION top page.
    if(result.optionScene && !sceneFade_.active()){m.pending=1;sceneFade_.begin(true);}
    if(sceneFade_.tick() && m.pending) {
        m.pending=0;m.scene=MenuScene::None;
        enterOption(OptionScene::Top);
    }
}

bool NativeMatch::tickMenuScene(const std::array<NormalizedPadSample,2>& pads) {
    if(!menus_||menus_->scene==MenuScene::None)return false;
    if(menus_->scene==MenuScene::SpiritsEdit){tickSpiritsEdit(pads);return true;}
    if(titleFadeTick_ && ++titleFadeTick_>=27)titleFadeTick_=0;
    const std::array<uint32_t,2> held{physicalPad(pads[0].held),physicalPad(pads[1].held)};
    const auto menuPads=menuRepeat_.sample(held,{physicalPad(pads[0].pressed),physicalPad(pads[1].pressed)});
    switch(menus_->scene) {
    case MenuScene::ColorEdit:tickColorEdit(menuPads,held);break;
    case MenuScene::KeyConfig:tickKeyConfig(menuPads,held);break;
    default:tickGallery(menuPads,held);break;
    }
    return true;
}
}
