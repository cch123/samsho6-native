#!/bin/sh
project_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec "$project_dir/outputs/ss6-feasibility/native-viewer/ss6-viewer" "$@"
