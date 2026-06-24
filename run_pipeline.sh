#!/bin/bash

# Save original command line arguments before they are shifted
INVOCATION="$0 $@"

# Default values
INPUT_VIDEO=""
WORKSPACE=""
LOG_FILE="pipeline.log"
JOBS=1
FS_VAL=2
DF_VAL=2
CLASSES="0 2"
CONF=0.4
THRESHOLD_VAL="0.15"
MIN_LEN_VAL="0.1s"
BG_SUB_VAL="MOG2"

# Function to show detailed help
show_help() {
    cat << EOF
================================================================================
 VIDEO SCANNING PIPELINE - HELP
================================================================================
Usage: ./run_pipeline.sh -i <input_video.mp4> [-o <output_dir>] [-j <jobs>] [--fs <frame_skip>] [--df <downscale>] [--classes "0 2"] [--conf 0.4]

This script automates a 5-stage funnel to extract, verify, and timestamp 
motion events from large video files.

REQUIRED ARGUMENTS:
  -i, --input       Full path to the source MP4 video file.
                    NOTE: Filename MUST contain date/time as: 
                    'name_YYYY_MM_DD_HH_MM...' (e.g. front_2025_02_16_00_00.mp4)

OPTIONAL ARGUMENTS:
  -o, --output      Target directory for final results. 
                    Defaults to: ./scan_results_<video_name>
  -j, --jobs        Number of parallel dvr-scan jobs (default: 1).
  --fs              Frame skip for dvr-scan (default: 2, processes every 3rd frame).
                    Use 4 for much faster scanning of human/car motion.
  --df              Downscale factor for dvr-scan (default: 2).
                    Use 4 for significantly faster scanning at lower resolution.
  --classes         YOLOv8 class IDs to detect (default: "0 2" for person/car).
                    Use "all" to detect every object type known to YOLO.
                    Example: --classes "all" or --classes "0 2 16"
  --conf            Confidence threshold for AI filtering (default: 0.4).
                    Increase (e.g. 0.6) to reduce false positives from shadows.
  --threshold       Threshold representing amount of motion in a frame to trigger (default: 0.15).
                    Increase (e.g. 0.25) to reduce false positives from wind/shadows.
  --min-len         Minimum event length of motion to trigger event (default: 0.1s).
                    Increase (e.g. 1.5s) to filter out transient/false motion.
  --bg-subtractor   Background subtractor type: MOG2 or CNT (default: MOG2).
                    CNT is optimized for speed/parallelism.
  -h, --help        Show this full process explanation.

--------------------------------------------------------------------------------
PROCESS STAGES:
--------------------------------------------------------------------------------
STAGE 1: Motion Extraction (DVR-Scan)
  Uses computer vision to perform a high-speed pass over the entire raw video. 
  It identifies ANY motion (shadows, wind, objects) and slices them into 
  short temporary clips. Now supports multi-threaded chunking.

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
================================================================================
EOF
}

# Parse Arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        -i|--input) INPUT_VIDEO="$2"; shift ;;
        -o|--output) WORKSPACE="$2"; shift ;;
        -j|--jobs) JOBS="$2"; shift ;;
        --fs) FS_VAL="$2"; shift ;;
        --df) DF_VAL="$2"; shift ;;
        --classes) CLASSES="$2"; shift ;;
        --conf) CONF="$2"; shift ;;
        --mask) MASK_FILE="$2"; shift ;;
        --threshold) THRESHOLD_VAL="$2"; shift ;;
        --min-len) MIN_LEN_VAL="$2"; shift ;;
        --bg-subtractor) BG_SUB_VAL="$2"; shift ;;
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
DIR_FINAL="$WORKSPACE/02_verified_events"
PIPE_LOG="$WORKSPACE/offsets.log"
STATUS_LOG="$WORKSPACE/status.log"
REGION_FILE="$WORKSPACE/mask_regions.txt"

mkdir -p "$DIR_MOTION" "$DIR_FINAL"

if [ -n "$MASK_FILE" ]; then
    echo "Extracting region polygons from mask file: $MASK_FILE"
    python3 - <<EOF
import cv2
import sys
mask = cv2.imread("$MASK_FILE", cv2.IMREAD_GRAYSCALE)
if mask is None:
    sys.exit(0)
_, mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
with open("$REGION_FILE", "w") as f:
    for contour in contours:
        if len(contour) >= 3:
            pts = contour.reshape(-1, 2)
            f.write(" ".join([f"{x} {y}" for x, y in pts]) + "\n")
EOF
fi

# Log the calling command line details
echo "Command Line: $INVOCATION"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] $INVOCATION" >> "$WORKSPACE/run_command.log"

# Log the parsed arguments explicitly
{
    echo "Parsed Parameters:"
    echo "  Input Video: $INPUT_VIDEO"
    echo "  Workspace:   $WORKSPACE"
    echo "  Jobs:        $JOBS"
    echo "  Frame Skip:  $FS_VAL"
    echo "  Downscale:   $DF_VAL"
    echo "  Classes:     $CLASSES"
    echo "  Confidence:  $CONF"
    echo "  Mask File:   ${MASK_FILE:-None}"
    echo "  Threshold:   $THRESHOLD_VAL"
    echo "  Min Len:     $MIN_LEN_VAL"
    echo "  BG Sub:      $BG_SUB_VAL"
    echo "--------------------------------------------------------"
} | tee -a "$WORKSPACE/run_command.log"

echo "========================================================"
echo " STAGE 1: Motion Extraction (DVR-Scan)"
echo " Started: $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================================"

if [ "$JOBS" -le 1 ]; then
    if [ -s "$REGION_FILE" ]; then
        dvr-scan -i "$INPUT_VIDEO" -m ffmpeg -fs "$FS_VAL" -df "$DF_VAL" -d "$DIR_MOTION" -R "$REGION_FILE" -t "$THRESHOLD_VAL" -l "$MIN_LEN_VAL" -b "$BG_SUB_VAL" 2>&1 | tee "$PIPE_LOG"
    else
        dvr-scan -i "$INPUT_VIDEO" -m ffmpeg -fs "$FS_VAL" -df "$DF_VAL" -d "$DIR_MOTION" -t "$THRESHOLD_VAL" -l "$MIN_LEN_VAL" -b "$BG_SUB_VAL" 2>&1 | tee "$PIPE_LOG"
    fi
else
    echo "Parallel Mode: $JOBS jobs"
    echo "Tracking progress in: $STATUS_LOG"
    python3 - <<EOF
import subprocess
import os
import shutil
import re
import time
from datetime import timedelta
from concurrent.futures import ProcessPoolExecutor

input_video = "$INPUT_VIDEO"
workspace = "$WORKSPACE"
jobs = int("$JOBS")
fs = "$FS_VAL"
df = "$DF_VAL"
dir_motion = "$DIR_MOTION"
pipe_log = "$PIPE_LOG"
status_log = "$STATUS_LOG"
region_file = "$REGION_FILE"
threshold = "$THRESHOLD_VAL"
min_len = "$MIN_LEN_VAL"
bg_sub = "$BG_SUB_VAL"
orig_base = os.path.splitext(os.path.basename(input_video))[0]

def get_duration(video):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video]
    return float(subprocess.check_output(cmd).decode().strip())

def get_actual_start_offset(video, part_file):
    # Determine the actual time in the original video where the part_file starts
    # By analyzing the first packet of the chunk
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time", "-of", "csv=p=0", part_file]
    try:
        output = subprocess.check_output(cmd + ["-read_intervals", "%+1"], stderr=subprocess.STDOUT).decode().split('\n')[0]
        return float(output) if output else 0.0
    except Exception:
        return 0.0

duration = get_duration(input_video)
chunk_size = duration / jobs

def run_job(i):
    start_req = i * chunk_size
    part_dir = os.path.join(workspace, f"part_{i}")
    os.makedirs(part_dir, exist_ok=True)
    part_log = os.path.join(part_dir, "offsets.log")
    part_video = os.path.join(part_dir, f"part_{i}.mp4")
    
    # Split using fast seeking and stream copy
    split_cmd = ["ffmpeg", "-y", "-ss", str(start_req), "-t", str(chunk_size), "-i", input_video, "-c", "copy", "-map", "0", "-copyts", "-start_at_zero", part_video]
    subprocess.run(split_cmd, capture_output=True)
    
    if not os.path.exists(part_video):
        return i, start_req, False

    # Get the actual timestamp where ffmpeg landed (corrected for keyframe)
    # With -copyts and -start_at_zero, the first frame's pts_time in the new file 
    # should reflect its position in the old file IF handled correctly. 
    # However, dvr-scan usually resets time to 0. 
    # So we calculate the 'drift' relative to the original.
    
    scan_cmd = ["dvr-scan", "-i", part_video, "-m", "ffmpeg", "-fs", fs, "-df", df, "-d", part_dir, "-t", threshold, "-l", min_len, "-b", bg_sub]
    if os.path.exists(region_file) and os.path.getsize(region_file) > 0:
        scan_cmd.extend(["-R", region_file])
    
    with open(part_log, "w") as f:
        subprocess.run(scan_cmd, stdout=f, stderr=subprocess.STDOUT)
    
    if os.path.exists(part_video):
        os.remove(part_video)
    
    return i, start_req, True

print(f"Dividing {duration:.2f}s into {jobs} chunks...")
with ProcessPoolExecutor(max_workers=jobs) as executor:
    futures = []
    for i in range(jobs):
        futures.append(executor.submit(run_job, i))
        time.sleep(2)  # Staggered start to prevent dvr-scan log contention
    
    while not all(f.done() for f in futures):
        summary = []
        for i in range(jobs):
            p_log = os.path.join(workspace, f"part_{i}", "offsets.log")
            if os.path.exists(p_log):
                with open(p_log, "r") as f:
                    content = f.read()
                    last_prog = re.findall(r"Progress:.*?(\d+%)", content)
                    if last_prog:
                        summary.append(f"Job {i}: {last_prog[-1]}")
                    else:
                        summary.append(f"Job {i}: Scanning...")
            else:
                summary.append(f"Job {i}: Initializing...")
        
        status_text = " | ".join(summary)
        print(f"\r{status_text}", end="", flush=True)
        with open(status_log, "w") as f:
            f.write(status_text + "\n")
        time.sleep(5)
    print("\nAll scan jobs complete.")

results = [f.result() for f in futures]

print("Merging results and correcting timestamps...")
with open(pipe_log, "w") as master:
    for i, start, success in results:
        if not success: continue
        part_dir = os.path.join(workspace, f"part_{i}")
        part_log = os.path.join(part_dir, "offsets.log")
        part_base = f"part_{i}"
        
        if os.path.exists(part_log):
            with open(part_log, "r") as f:
                content = f.read()
                
                def adjust_offset(match):
                    time_str = match.group(1)
                    h, m, s = time_str.split(':')
                    offset = timedelta(hours=int(h), minutes=int(m), seconds=float(s))
                    # Anchor back to original absolute time
                    new_time = offset + timedelta(seconds=start)
                    
                    total = new_time.total_seconds()
                    hrs = int(total // 3600)
                    mns = int((total % 3600) // 60)
                    scs = int(total % 60)
                    mms = int((total * 1000) % 1000)
                    return f"-ss {hrs:02}:{mns:02}:{scs:02}.{mms:03}"

                content = re.sub(r"-ss (\d{2}:\d{2}:\d{2}\.\d{3})", adjust_offset, content)
                content = content.replace(part_base, orig_base)
                def prefix_dsme(match):
                    return f"{orig_base}.DSME_{i:02d}{match.group(1)}.mp4"
                content = re.sub(re.escape(orig_base) + r"\.DSME_(\d{4})\.mp4", prefix_dsme, content)
                master.write(content)
        
        for f in os.listdir(part_dir):
            if f.endswith(".mp4") and f.startswith(part_base):
                new_f = f.replace(part_base, orig_base).replace(".DSME_", f".DSME_{i:02d}")
                shutil.move(os.path.join(part_dir, f), os.path.join(dir_motion, new_f))
        shutil.rmtree(part_dir)
EOF
fi

# Abort early if no motion was found
if [ -z "$(ls -A "$DIR_MOTION"/*.mp4 2>/dev/null)" ]; then
    echo "No motion detected in the entire video. Exiting."
    exit 0
fi

echo ""
echo "========================================================"
echo " STAGE 2: AI Filtering (YOLOv8)"
echo " Started: $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================================"
FILTER_CMD=(python filter_clips.py -i "$DIR_MOTION" -o "$DIR_FINAL" --frame-step 30 --classes $CLASSES --conf "$CONF" --metadata "$WORKSPACE/classes.json" --jobs "$JOBS")
if [ -n "$MASK_FILE" ]; then
    FILTER_CMD+=(--mask "$MASK_FILE")
fi
echo "Executing: ${FILTER_CMD[*]}"
"${FILTER_CMD[@]}"

echo ""
echo "========================================================"
echo " STAGE 3: Filename Timestamps"
echo " Started: $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================================"
cat << 'EOF' > temp_renamer.py
import os
import re
import sys
import json
from datetime import datetime, timedelta

def do_rename(log_file, base_dir, video_filename, metadata_file):
    # Try YYYYMMDD_HHMMSS first (standard for many cams)
    match = re.search(r'(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})', video_filename)
    if match:
        y, m, d, H, M, S = map(int, match.groups())
        base_start_time = datetime(y, m, d, H, M, S)
    else:
        # Fallback to YYYY_MM_DD_HH_MM
        match = re.search(r'(\d{4})_(\d{2})_(\d{2})_(\d{2})_(\d{2})', video_filename)
        if not match: 
            print(f"Warning: Could not parse start time from {video_filename}")
            return
        y, m, d, H, M = map(int, match.groups())
        base_start_time = datetime(y, m, d, H, M, 0)
    
    metadata = {}
    if os.path.exists(metadata_file):
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)

    if not os.path.exists(log_file): return
    with open(log_file, 'r') as f:
        content = f.read()

    escaped_base = re.escape(os.path.splitext(video_filename)[0])
    pattern = re.compile(r'-ss (\d{2}:\d{2}:\d{2}\.\d{3}).*?(' + escaped_base + r'\.DSME_(\d+)\.mp4)')
    matches = pattern.findall(content)

    rename_map = {}
    for offset_str, full_name, dsme_num in matches:
        h, mn, s = offset_str.split(':')
        offset = timedelta(hours=int(h), minutes=int(mn), seconds=float(s))
        actual_time = base_start_time + offset
        
        classes_suffix = ""
        if full_name in metadata:
            classes_suffix = "_" + "_".join(metadata[full_name])
            
        new_name = actual_time.strftime("%Y%m%d_%H%M%S") + "_DSME_" + dsme_num + classes_suffix + ".mp4"
        rename_map[full_name] = new_name
        
    if not os.path.exists(base_dir): return
    success = 0
    for old_name in os.listdir(base_dir):
        if old_name in rename_map:
            os.rename(os.path.join(base_dir, old_name), os.path.join(base_dir, rename_map[old_name]))
            success += 1
    print(f"Renamed {success} files using offsets.")

if __name__ == "__main__":
    do_rename(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
EOF

python temp_renamer.py "$PIPE_LOG" "$DIR_FINAL" "$(basename "$INPUT_VIDEO")" "$WORKSPACE/classes.json"
rm temp_renamer.py

echo ""
echo "========================================================"
echo " STAGE 4: Burn Timestamp into Video"
echo " Started: $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================================"
BURN_CMD=(python burn_timestamps.py "$DIR_FINAL")
if [ -n "$MASK_FILE" ]; then
    BURN_CMD+=(--mask "$MASK_FILE")
fi
echo "Executing: ${BURN_CMD[*]}"
"${BURN_CMD[@]}"

echo ""
echo "========================================================"
echo " STAGE 5: Cleanup"
echo " Started: $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================================"
if [ -d "$DIR_MOTION" ]; then
    echo "Removing intermediate motion clips in $DIR_MOTION..."
    rm -rf "$DIR_MOTION"
fi
rm -rf "$WORKSPACE"/part_* 2>/dev/null

echo ""
echo "========================================================"
echo " DONE! Pipeline complete."
echo " Finished: $(date '+%Y-%m-%d %H:%M:%S')"
echo " Results available in: $DIR_FINAL"
echo "========================================================"
