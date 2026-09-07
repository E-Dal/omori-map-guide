#!/bin/bash
# Download a region's map PNGs from goats.dev.
# Skips files that already exist locally and any IDs that 404.
#
# Usage: ./scripts/02_download_goats_pngs.sh <region>
#        e.g. ./scripts/02_download_goats_pngs.sh junkyard

set -e
cd "$(dirname "$0")/.."

REGION="${1:-faraway}"
META="data/${REGION}_maps.json"
if [ ! -f "$META" ]; then
  echo "Missing $META. Run: node scripts/01_extract_adjacency.js $REGION"
  exit 1
fi

OUT_DIR="data/raw_pngs"
mkdir -p "$OUT_DIR"

# Map IDs from region's metadata file
IDS=$(node -e "
const fs=require('fs');
const meta=JSON.parse(fs.readFileSync('$META','utf8'));
console.log(Object.keys(meta).join(' '));
")
echo "Downloading $REGION PNGs ($(echo $IDS | wc -w | tr -d ' ') maps)..."

ok=0; skip=0; miss=0; fail=0
for id in $IDS; do
  out="$OUT_DIR/map${id}.png"
  if [ -f "$out" ]; then
    skip=$((skip+1))
    continue
  fi
  url="https://goats.dev/omori/map/img/map${id}.png"
  # Say who is knocking, and knock slowly. Existing files are skipped above, so
  # a re-run costs nothing, but a first run asks for several hundred images from
  # someone else's server — the one thing about this that could reasonably
  # annoy them. A UA that names the project also gives them somebody to contact
  # instead of just a stranger hammering the host.
  UA="omori-map-guide (fan atlas; https://github.com/goats-credit-see-README)"
  sleep 0.4
  # HEAD first to skip 404s quickly
  status=$(curl -sLI -A "$UA" "$url" -o /dev/null -w "%{http_code}")
  case "$status" in
    200)
      curl -sL -A "$UA" "$url" -o "$out"
      bytes=$(stat -f%z "$out" 2>/dev/null || stat -c%s "$out")
      printf "  OK Map%-3s  %s bytes\n" "$id" "$bytes"
      ok=$((ok+1))
      ;;
    404)
      printf "  -- Map%-3s  not on goats.dev\n" "$id"
      miss=$((miss+1))
      ;;
    *)
      printf "  !! Map%-3s  HTTP %s\n" "$id" "$status"
      fail=$((fail+1))
      ;;
  esac
done

echo ""
echo "Done.  ok=$ok  skip=$skip  missing=$miss  fail=$fail"
echo "Output: $OUT_DIR/"
