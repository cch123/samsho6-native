#include "edited_palettes.hpp"
#include <algorithm>

namespace ss6 {
EditedPalettes::EditedPalettes(const std::filesystem::path& assets):tables(assets),assets_(assets) {
    const SystemData factory(assets);
    const auto block=factory.image().subspan(SystemData::editData,tableSize);
    defaults_.assign(block.begin(),block.end());
    runtime={defaults_,defaults_}; // 115498 at boot
}
void EditedPalettes::restoreDefaults(unsigned side) {runtime.at(side)=defaults_;}
void EditedPalettes::loadVersusCards(const SystemData& live) {
    bool card=true;
    SystemData stored(assets_);
    if(live.file.empty())std::copy(live.image().begin(),live.image().end(),stored.image().begin());
    else card=stored.load(live.file);
    if(!card){restoreDefaults(0);restoreDefaults(1);return;}
    const auto block=std::span<const uint8_t>(stored.image()).subspan(SystemData::editData,tableSize);
    runtime[0].assign(block.begin(),block.end());
    runtime[1]=runtime[0];
}
}
