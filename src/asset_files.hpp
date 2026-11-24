#pragma once
// Asset override search path ("mods").
//
// Every loader opens its files through resolveAsset(). With no override roots
// the requested path is returned unchanged, so the factory data set behaves
// exactly as before. With override roots, a file of the same name found in a
// root replaces the factory file; roots are searched in the given order.
//
// Lookup is by file name only: the factory asset directory is flat, and a mod
// directory mirrors it. Loaders keep their own size and layout checks, so an
// override must still satisfy the format the loader expects.
#include <filesystem>
#include <string>
#include <vector>

namespace ss6 {

// Replaces the override roots. Non-directories are rejected with
// std::runtime_error so a mistyped --mod does not silently load factory data.
void setAssetOverrides(std::vector<std::filesystem::path> roots);

// Current roots. Before the first setAssetOverrides() call these come from the
// SS6_MODS environment variable (':'-separated, ';' on Windows).
const std::vector<std::filesystem::path>& assetOverrides();

// The file a loader should open for `requested`.
std::filesystem::path resolveAsset(const std::filesystem::path& requested);

// Files served from an override root so far, for diagnostics ("which of my
// replacements did the game actually read?").
std::vector<std::filesystem::path> resolvedOverrides();

} // namespace ss6
