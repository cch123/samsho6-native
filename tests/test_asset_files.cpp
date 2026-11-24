// Override search path: factory fallback, precedence, user-data isolation.
#include "asset_files.hpp"

#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>

namespace fs = std::filesystem;

namespace {
int failures = 0;

void expect(bool condition, const char* what) {
    if (condition) return;
    std::fprintf(stderr, "FAILED: %s\n", what);
    ++failures;
}

void write(const fs::path& file, const std::string& text) {
    fs::create_directories(file.parent_path());
    std::ofstream(file, std::ios::binary) << text;
}

std::string read(const fs::path& file) {
    std::ifstream in(ss6::resolveAsset(file), std::ios::binary);
    return {std::istreambuf_iterator<char>(in), {}};
}
} // namespace

int main() {
    const auto root = fs::temp_directory_path() / ("ss6-asset-files-" + std::to_string(std::rand()));
    fs::remove_all(root);
    const auto base = root / "base", first = root / "first", second = root / "second";
    write(base / "a.bin", "base-a");
    write(base / "b.bin", "base-b");
    write(first / "a.bin", "first-a");
    write(second / "a.bin", "second-a");
    write(second / "b.bin", "second-b");

    ss6::setAssetOverrides({});
    expect(read(base / "a.bin") == "base-a", "no roots: factory file is used");
    expect(ss6::resolvedOverrides().empty(), "no roots: nothing reported as overridden");

    ss6::setAssetOverrides({first, second});
    expect(read(base / "a.bin") == "first-a", "earlier root wins");
    expect(read(base / "b.bin") == "second-b", "later root supplies files the earlier one lacks");
    expect(ss6::resolveAsset(base / "missing.bin") == base / "missing.bin",
           "unknown file keeps the requested path so the loader reports it");
    expect(ss6::resolvedOverrides().size() == 2, "each served override is reported once");
    read(base / "a.bin");
    expect(ss6::resolvedOverrides().size() == 2, "repeat reads are not reported twice");

    // A directory with an asset's name must not shadow the factory file.
    fs::create_directories(first / "b.bin");
    expect(read(base / "b.bin") == "second-b", "directories are not treated as overrides");

    bool rejected = false;
    try {
        ss6::setAssetOverrides({root / "absent"});
    } catch (const std::runtime_error&) {
        rejected = true;
    }
    expect(rejected, "a root that is not a directory is rejected");
    expect(ss6::assetOverrides().size() == 2, "a rejected configuration leaves the previous roots");

    ss6::setAssetOverrides({});
    fs::remove_all(root);
    if (failures) return 1;
    std::puts("asset_files: all checks passed");
    return 0;
}
