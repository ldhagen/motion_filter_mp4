#!/bin/bash
# ==============================================================================
#  PORTABLE MOTION CLIPS ARCHIVER & CLEANUP SCRIPT WITH PERMANENT LOGGING
# ==============================================================================
#  Usage:
#  ./archive_clips.sh -i <raw_source_video.mp4> [-w <workspace_dir>] [-a <archive_base_dir>]
# ==============================================================================

set -euo pipefail

show_help() {
    echo "================================================================================"
    echo " MOTION CLIPS ARCHIVER & CLEANUP"
    echo "================================================================================"
    echo "Usage: $0 -i <raw_source_video.mp4> [-w <workspace_dir>] [-a <archive_base_dir>]"
    echo ""
    echo "Arguments:"
    echo "  -i, --input       Full path to the original raw week-long video file."
    echo "                    (e.g., /media/ldhagen/.../front_window_2025_05_04_00_00...mp4)"
    echo "  -w, --workspace   The folder containing the scan results."
    echo "                    Defaults to: ./scan_results_<video_name_without_ext>"
    echo "  -a, --archive     The base path for permanent archival (required)."
    echo "  -h, --help        Show this help message."
    echo "================================================================================"
}

INPUT_VIDEO=""
WORKSPACE_DIR=""
ARCHIVE_BASE=""

# Parse arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        -i|--input) INPUT_VIDEO="$2"; shift ;;
        -w|--workspace) WORKSPACE_DIR="$2"; shift ;;
        -a|--archive) ARCHIVE_BASE="$2"; shift ;;
        -h|--help) show_help; exit 0 ;;
        *) echo "Unknown parameter: $1"; show_help; exit 1 ;;
    esac
    shift
done

# Validate required inputs
if [ -z "$INPUT_VIDEO" ]; then
    echo "Error: Missing required input video argument (-i/--input)."
    show_help
    exit 1
fi

if [ -z "$ARCHIVE_BASE" ]; then
    echo "Error: Missing required archive base argument (-a/--archive)."
    show_help
    exit 1
fi

if [ ! -f "$INPUT_VIDEO" ]; then
    echo "Error: Raw source video file does not exist: $INPUT_VIDEO"
    exit 1
fi

# Ensure archive directory exists
mkdir -p "$ARCHIVE_BASE"
LOG_FILE="$ARCHIVE_BASE/archive_history.log"

# Logging helper
log_msg() {
    local TIMESTAMP
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$TIMESTAMP] $1" | tee -a "$LOG_FILE"
}

# Auto-calculate workspace directory if not provided
VIDEO_BASENAME=$(basename "$INPUT_VIDEO")
VIDEO_NAME_NO_EXT="${VIDEO_BASENAME%.*}"
if [ -z "$WORKSPACE_DIR" ]; then
    WORKSPACE_DIR="./scan_results_${VIDEO_NAME_NO_EXT}"
fi

# Check if workspace was moved from RAM to persistent storage by the pipeline
if [[ "$WORKSPACE_DIR" == /dev/shm/* ]]; then
    PERSISTENT_WORKSPACE="./persistent_$(basename "$WORKSPACE_DIR")"
    if [ -d "$PERSISTENT_WORKSPACE" ]; then
        log_msg "RAM workspace was moved to persistent storage. Updating target to: $PERSISTENT_WORKSPACE"
        WORKSPACE_DIR="$PERSISTENT_WORKSPACE"
    fi
fi

# Check workspace directory presence
if [ ! -d "$WORKSPACE_DIR" ]; then
    log_msg "[ERROR] Workspace directory does not exist: $WORKSPACE_DIR"
    exit 1
fi

# Auto-parse camera name from raw source video filename
# Assumes format camera_name_YYYY_MM_DD... or camera_name_YYYYMMDD...
CAMERA_NAME=$(echo "$VIDEO_BASENAME" | sed -E 's/_([0-9]{4})[0-9]*_.*//')
if [ "$CAMERA_NAME" == "$VIDEO_BASENAME" ]; then
    # Fallback if filename pattern doesn't match
    CAMERA_NAME="unknown_camera"
fi


log_msg "========================================================"
log_msg " STARTING PORTABLE ARCHIVAL PROCESS"
log_msg "========================================================"
log_msg "Raw Source:    $INPUT_VIDEO"
log_msg "Workspace:     $WORKSPACE_DIR"
log_msg "Camera Name:   $CAMERA_NAME"
log_msg "Archive Base:  $ARCHIVE_BASE"
log_msg "Log File:      $LOG_FILE"
log_msg "--------------------------------------------------------"

VALID_RUN=true
COPY_COUNT=0

# Loop through all daily folders in the workspace
for day_dir in "$WORKSPACE_DIR"/202*; do
    [ -d "$day_dir" ] || continue
    
    DAY_NAME=$(basename "$day_dir")
    VERIFIED_DIR="$day_dir/02_verified_events"
    
    if [ ! -d "$VERIFIED_DIR" ]; then
        log_msg "No verified events directory found for $DAY_NAME, skipping..."
        continue
    fi
    
    log_msg "Processing $DAY_NAME..."
    
    # Process each MP4 event clip in 02_verified_events
    for clip in "$VERIFIED_DIR"/*.mp4; do
        [ -f "$clip" ] || continue
        
        CLIP_NAME=$(basename "$clip")
        YEAR="${CLIP_NAME:0:4}"
        MONTH="${CLIP_NAME:4:2}"
        
        TARGET_DIR="$ARCHIVE_BASE/$CAMERA_NAME/$YEAR/$MONTH"
        mkdir -p "$TARGET_DIR"
        
        log_msg "  - Archiving: $CLIP_NAME"
        
        # 1. Run ffprobe to check if it's a valid, readable video file
        if ! ffprobe -v error -show_entries format=duration "$clip" >/dev/null; then
            log_msg "    [ERROR] File is corrupted or unreadable: $clip"
            VALID_RUN=false
            continue
        fi
        
        # 2. Copy file to the archive target
        cp "$clip" "$TARGET_DIR/$CLIP_NAME"
        
        # 3. Verify copy integrity using cmp
        if cmp --silent "$clip" "$TARGET_DIR/$CLIP_NAME"; then
            log_msg "    [OK] Copy verified."
            COPY_COUNT=$((COPY_COUNT + 1))
        else
            log_msg "    [ERROR] Copy integrity check failed for: $CLIP_NAME"
            VALID_RUN=false
        fi
    done
done

log_msg "--------------------------------------------------------"
if [ "$VALID_RUN" = true ]; then
    if [ "$COPY_COUNT" -gt 0 ]; then
        log_msg "Success! $COPY_COUNT event clips successfully archived & verified."
    else
        log_msg "Success! No event clips found to archive."
    fi
    
    # 4. Safe Delete Raw Source Video
    if [ -f "$INPUT_VIDEO" ]; then
        log_msg "Deleting original raw source video: $INPUT_VIDEO..."
        rm "$INPUT_VIDEO"
        log_msg "Raw source video deleted successfully."
    fi
    
    # 5. Clean up temporary daily directories
    log_msg "Cleaning up local workspace results folder..."
    rm -rf "$WORKSPACE_DIR"
    log_msg "Workspace cleaned up."
    
    # 6. Delete run.log
    if [ -f "run.log" ]; then
        log_msg "Deleting run.log..."
        rm "run.log"
        log_msg "run.log deleted successfully."
    fi
    
    log_msg "========================================================"
    log_msg " ARCHIVE COMPLETE!"
    log_msg "========================================================"
else
    log_msg "========================================================"
    log_msg " WARNING: Archival had errors."
    log_msg " No files have been deleted. Please check logs."
    log_msg "========================================================"
    exit 1
fi
