#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
target_triple="${TAURI_ENV_TARGET_TRIPLE:-$(rustc -vV | sed -n 's/^host: //p')}"
target_path="$root_dir/desktop/src-tauri/binaries/bridle-sidecar-$target_triple"

case "$target_triple" in
  *-linux-gnu) ;;
  *)
    echo "Linux sidecar build requires a *-linux-gnu Rust target, got: $target_triple" >&2
    exit 2
    ;;
esac

if [[ "${BRIDLE_REUSE_SIDECAR:-0}" == "1" && -x "$target_path" ]]; then
  echo "Reusing existing sidecar: $target_path"
  exit 0
fi

cd "$root_dir"
export PYTHONDONTWRITEBYTECODE=1
export PYINSTALLER_CONFIG_DIR="${PYINSTALLER_CONFIG_DIR:-/tmp/bridle-pyinstaller-cache}"
uv run --extra packaging pyinstaller \
  --noconfirm \
  --clean \
  --onefile \
  --collect-data litellm \
  --collect-all tiktoken \
  --name bridle-sidecar \
  --specpath /tmp/bridle-pyinstaller-spec \
  --workpath /tmp/bridle-pyinstaller-build \
  bridle/app/sidecar_entry.py
mkdir -p desktop/src-tauri/binaries
cp dist/bridle-sidecar "$target_path"
