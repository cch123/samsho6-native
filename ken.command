#!/bin/sh
project_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec "$project_dir/battle.command" --p1-spirit ken --p2-spirit ken "$@"
