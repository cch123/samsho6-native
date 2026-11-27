#!/bin/sh
set -eu
cd "$(dirname "$0")"
cmake --preset release
cmake --build --preset release --target ss6-viewer -j 6
assets=outputs/ss6-feasibility/native-viewer/assets
cache=work/ss6/ink-parts
python3 tools/assets/ss6ink_parts.py "$assets" mods/ink-idle/haohmaru_actions.ink "$cache"
exec work/ss6/build-native/ss6-viewer --assets "$assets" --mod "$cache" --mod mods/ink-idle --mode versus "$@"
