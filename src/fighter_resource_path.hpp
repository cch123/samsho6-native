#pragma once
#include <filesystem>
#include <string>
#include <string_view>

namespace ss6 {
// The Japanese archive uses two decimal digits for each resource bank.
// A seat number selects a bank at load time and is never part of the filename.
inline std::filesystem::path fighterResourcePath(const std::filesystem::path& assets,
                                                std::string_view kind,unsigned resource) {
    return assets/(std::string(kind)+"_"+(resource<10?"0":"")+std::to_string(resource)+".bin");
}
}
