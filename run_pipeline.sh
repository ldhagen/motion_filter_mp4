#!/bin/bash

# Default values
INPUT_VIDEO=""
WORKSPACE=""
LOG_FILE="pipeline.log"

# Function to show detailed help
show_help() {
    cat << EOF
================================================================================
 VIDEO SCANNING PIPELINE - HELP
================================================================================
Usage: ./run_pipeline.sh -i <input_video.mp4> [-o <output_dir>]

This script automates a 5-stage funnel to extract, verify, and timestamp 
motion events from large video files.

REQUIRED ARGUMENTS:
  -i, --input       Full path to the source MP4 video file.
                    NOTE: Filename MUST contain date/time as: 
                    'name_YYYY_MM_DD_HH_MM...' (e.g. front_2025_02_16_00_00.mp4)

OPTIONAL ARGUMENTS:
  -o, --output      Target directory for final results. 
                    Defaults to: ./scan_results_<video_name>
  -h, --help        Show this full process explanation.

--------------------------------------------------------------------------------
PROCESS STAGES:
--------------------------------------------------------------------------------
STAGE 1: Motion Extraction (DVR-Scan)
  Uses computer vision to perform a high-speed pass over the entire raw video. 
  It identifies ANY motion (shadows, wind, objects) and slices them into 
  short temporary clips.

STAGE 2: AI Filtering (YOLOv8)
  Uses a Neural Network to verify the results. It scans the motion clips 
  specifically for humans and cars. It uses "Persistence Filtering" (IOU math)
  to ensure the object actually moved, dropping clips of parked cars or trees.

STAGE 3: Real-World Renaming
  Calculates the exact calendar date and clock time of each event by 
  anchoring to your filename and adding the recorded scan offsets. 
  Results are renamed to: YYYYMMDD_HHMMSS_DSME_XXXX.mp4

STAGE 4: Visual Timestamp Burn-In
  Uses FFmpeg's drawtext filter to permanently burn the calculated time 
  into the top-left corner of the video in a visible white-on-black box.

STAGE 5: Cleanup
  Aggressively deletes the massive intermediate temporary folders to save 
  disk space, leaving you with only the final verified events.

--------------------------------------------------------------------------------
TIPS FOR NOHUP:
--------------------------------------------------------------------------------
To run this in the background so you can close your session:
  nohup ./run_pipeline.sh -i video.mp4 > my_run.log 2>&1 &

To monitor progress:
  tail -f my_run.log
================================================================================
EOF
}

# Parse Arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        -i|--input) INPUT_VIDEO="$2"; shift ;;
        -o|--output) WORKSPACE="$2"; shift ;;
        -h|--help) show_help; exit 0 ;;
        *) echo "Unknown parameter: $1"; show_help; exit 1 ;;
    esac
    shift
done

# Validation
if [ -z "$INPUT_VIDEO" ]; then
    echo "Error: Input video is required (-i)."
    show_help
    exit 1
fi

if [ ! -f "$INPUT_VIDEO" ]; then
    echo "Error: File $INPUT_VIDEO not found."
    exit 1
fi

# Set default workspace if not provided
BASENAME=$(basename "$INPUT_VIDEO" .mp4)
if [ -z "$WORKSPACE" ]; then
    WORKSPACE="scan_results_${BASENAME}"
fi

# Define internal paths
DIR_MOTION="$WORKSPACE/01_motion_only"
DIR_FINAL="$WORKSPACE/02_humans_cars"
# Local log for this specific run's offsets
PIPE_LOG="$WORKSPACE/offsets.log"

mkdir -p "$DIR_MOTION" "$DIR_FINAL"

echo "========================================================"
echo " STAGE 1: Motion Extraction (DVR-Scan)"
echo "========================================================"
# Slices the massive file into raw motion events. 
# We capture the output to offsets.log so we can rename in Stage 3
dvr-scan -i "$INPUT_VIDEO" -m ffmpeg -fs 2 -df 2 -d "$DIR_MOTION" 2>&1 | tee "$PIPE_LOG"

# Abort early if no motion was found
if [ -z "$(ls -A "$DIR_MOTION"/*.mp4 2>/dev/null)" ]; then
    echo "No motion detected in the entire video. Exiting."
    exit 0
fi

echo ""
echo "========================================================"
echo " STAGE 2: AI Filtering (YOLOv8)"
echo "========================================================"
python filter_clips.py -i "$DIR_MOTION" -o "$DIR_FINAL" --frame-step 30

echo ""
echo "========================================================"
echo " STAGE 3: Filename Timestamps"
echo "========================================================"
# Create the temporary renamer script
cat << 'EOF' > temp_renamer.py
import os
import re
import sys
from datetime import datetime, timedelta

def do_rename(log_file, base_dir, video_filename):
    # Parse the base start time (e.g. front_window_2025_02_16_00_00__...)
    match = re.search(r'(\d{4})_(\d{2})_(\d{2})_(\d{2})_(\d{2})', video_filename)
    if not match:
        print("Warning: Could not parse base date from filename. Skipping rename.")
        return
        
    y, m, d, H, M = map(int, match.groups())
    base_start_time = datetime(y, m, d, H, M, 0)
    
    if not os.path.exists(log_file):
        print(f"Error: log file {log_file} not found.")
        return
        
    with open(log_file, 'r') as f:
        content = f.read()

    # Find all ffmpeg offset lines
    # We look for the base filename pattern inside the log
    escaped_base = re.escape(video_filename.replace('.mp4', ''))
    pattern = re.compile(r'-ss (\d{2}:\d{2}:\d{2}\.\d{3}).*?(' + escaped_base + r'\.DSME_(\d{4})\.mp4)')
    matches = pattern.findall(content)

    rename_map = {}
    for offset_str, full_name, dsme_num in matches:
        h, mn, s = offset_str.split(':')
        offset = timedelta(hours=int(h), minutes=int(mn), seconds=float(s))
        actual_time = base_start_time + offset
        
        new_name = actual_time.strftime("%Y%m%d_%H%M%S") + "_DSME_" + dsme_num + ".mp4"
        rename_map[full_name] = new_name
        
    if not os.path.exists(base_dir): return
    
    success = 0
    for old_name in os.listdir(base_dir):
        if old_name in rename_map:
            os.rename(os.path.join(base_dir, old_name), os.path.join(base_dir, rename_map[old_name]))
            success += 1
    print(f"Renamed {success} files using offsets from {log_file}.")

if __name__ == "__main__":
    do_rename(sys.argv[1], sys.argv[2], sys.argv[3])
EOF

python temp_renamer.py "$PIPE_LOG" "$DIR_FINAL" "$(basename "$INPUT_VIDEO")"
rm temp_renamer.py

echo ""
echo "========================================================"
echo " STAGE 4: Burn Timestamp into Video"
echo "========================================================"
python burn_timestamps.py "$DIR_FINAL"

echo ""
echo "========================================================"
echo " STAGE 5: Cleanup"
echo "========================================================"
if [ -d "$DIR_MOTION" ]; then
    echo "Removing intermediate motion clips in $DIR_MOTION..."
    rm -rf "$DIR_MOTION"
fi

echo ""
echo "========================================================"
echo " DONE! Pipeline complete."
echo " Results available in: $DIR_FINAL"
echo "========================================================"
