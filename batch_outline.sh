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

python draw_outlines.py -d "$IN_DIR" -o "$OUT_DIR"

echo ""
echo "Finished outlining all clips in $IN_DIR."

