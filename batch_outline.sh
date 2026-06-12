#!/bin/bash

# Usage: ./batch_outline.sh <input_dir> <output_dir>

IN_DIR="${1:-test_improved_filter}"
OUT_DIR="${2:-test_improved_outlines}"

mkdir -p "$OUT_DIR"

echo "========================================================"
echo " Starting Batch AI Outlining"
echo " Input:  $IN_DIR"
echo " Output: $OUT_DIR"
echo "========================================================"

for clip in "$IN_DIR"/*.mp4; do
    if [ ! -f "$clip" ]; then continue; fi
    filename=$(basename "$clip")
    echo "--- Processing: $filename ---"
    python draw_outlines.py -i "$clip" -o "$OUT_DIR"
done

echo ""
echo "Finished outlining all clips in $IN_DIR."
