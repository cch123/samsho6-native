#!/bin/sh
set -eu
cd "$(dirname "$0")"
cmake --preset release
cmake --build --preset release --target ss6-viewer -j 6
exec work/ss6/build-native/ss6-viewer --assets outputs/ss6-feasibility/native-viewer/assets --mod mods/ink-idle --mode versus "$@"
