#!/bin/sh
project_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec "$project_dir/battle.command" --p1-spirit zero --p2-spirit zero "$@"
