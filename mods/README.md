# mods

Each subdirectory is one asset override set. Start the game with
`--mod mods/<name>` (repeatable; earlier directories win) or list directories
in `SS6_MODS`. See [docs/modding.md](../docs/modding.md).

This preview branch also tracks the generated Haohmaru ink illustrations in
`mods/ink-idle`. The launcher reconstructs derivative weapon and effect layers
from the user's local assets and caches the assembled pack under `work/ss6`.
