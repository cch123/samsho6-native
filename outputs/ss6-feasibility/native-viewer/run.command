#!/bin/sh
viewer_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec "$viewer_dir/ss6-viewer" "$@"
