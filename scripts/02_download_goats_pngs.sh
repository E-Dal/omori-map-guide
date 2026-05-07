#!/bin/bash
# Download all Faraway map PNGs from goats.dev.
# Skips files that already exist locally and any IDs that 404.
#
# Usage: ./scripts/02_download_goats_pngs.sh

set -e
cd "$(dirname "$0")/.."

OUT_DIR="data/raw_pngs"
mkdir -p "$OUT_DIR"

# Faraway map IDs (extracted by 01_extract_faraway_adjacency.js)
IDS=$(node -e "
const fs=require('fs');
const meta=JSON.parse(fs.readFileSync('data/faraway_maps.json','utf8'));
console.log(Object.keys(meta).join(' '));
")

ok=0; skip=0; miss=0; fail=0
for id in $IDS; do
  out="$OUT_DIR/map${id}.png"
  if [ -f "$out" ]; then
    skip=$((skip+1))
    continue
  fi
  url="https://goats.dev/omori/map/img/map${id}.png"
  # HEAD first to skip 404s quickly
  status=$(curl -sLI "$url" -o /dev/null -w "%{http_code}")
  case "$status" in
    200)
      curl -sL "$url" -o "$out"
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
