#include "asset_files.hpp"

#include <algorithm>
#include <cstdlib>
#include <mutex>
#include <stdexcept>

namespace ss6 {
namespace {
namespace fs = std::filesystem;

struct Overrides {
    std::mutex mutex;
    bool configured = false;
    std::vector<fs::path> roots;
    std::vector<fs::path> served;
};

Overrides& state() {
    static Overrides overrides;
    return overrides;
}

std::vector<fs::path> checked(std::vector<fs::path> roots) {
    for (const auto& root : roots)
        if (!fs::is_directory(root))
            throw std::runtime_error("Asset override root is not a directory: " + root.string());
    return roots;
}

std::vector<fs::path> rootsFromEnvironment() {
    std::vector<fs::path> roots;
    const char* value = std::getenv("SS6_MODS");
    if (!value) return roots;
#ifdef _WIN32
    constexpr char separator = ';';
#else
    constexpr char separator = ':';
#endif
    std::string list = value;
    size_t begin = 0;
    while (begin <= list.size()) {
        const auto end = std::min(list.find(separator, begin), list.size());
        if (end > begin) roots.emplace_back(list.substr(begin, end - begin));
        begin = end + 1;
    }
    return checked(std::move(roots));
}

// Caller holds the mutex.
void configureFromEnvironment(Overrides& overrides) {
    if (overrides.configured) return;
    overrides.roots = rootsFromEnvironment();
    overrides.configured = true;
}
} // namespace

void setAssetOverrides(std::vector<fs::path> roots) {
    roots = checked(std::move(roots));
    auto& overrides = state();
    std::lock_guard lock(overrides.mutex);
    overrides.roots = std::move(roots);
    overrides.served.clear();
    overrides.configured = true;
}

const std::vector<fs::path>& assetOverrides() {
    auto& overrides = state();
    std::lock_guard lock(overrides.mutex);
    configureFromEnvironment(overrides);
    return overrides.roots;
}

fs::path resolveAsset(const fs::path& requested) {
    auto& overrides = state();
    std::lock_guard lock(overrides.mutex);
    configureFromEnvironment(overrides);
    const auto name = requested.filename();
    if (name.empty()) return requested;
    for (const auto& root : overrides.roots) {
        auto candidate = root / name;
        std::error_code error;
        if (!fs::is_regular_file(candidate, error)) continue;
        if (std::find(overrides.served.begin(), overrides.served.end(), candidate) == overrides.served.end())
            overrides.served.push_back(candidate);
        return candidate;
    }
    return requested;
}

std::vector<fs::path> resolvedOverrides() {
    auto& overrides = state();
    std::lock_guard lock(overrides.mutex);
    return overrides.served;
}

} // namespace ss6
