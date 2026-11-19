#!/bin/sh
project_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec "$project_dir/battle.command" --p1-spirit zan --p2-spirit zan "$@"
