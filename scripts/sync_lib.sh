#!/bin/sh
# Copy the library into the component so it installs as one folder (HACS/manual copy).
# Run after changing anything under vklass/src/vklass.
set -e
cd "$(dirname "$0")/.."
dest=custom_components/vklass/vklass_api
rm -rf "$dest"
cp -R vklass/src/vklass "$dest"
find "$dest" -name __pycache__ -prune -exec rm -rf {} +
echo "synced library -> $dest"
