# Motion Filter MP4

This project provides a multi-stage pipeline to process large security video files, extracting and highlighting motion events specifically involving humans and cars. It filters out false positives like wind, shadows, and stationary objects.

## Pipeline Overview

1.  **Stage 1: Motion Extraction** (`dvr-scan`)
    Slices the large input video into small clips containing any detected motion.
2.  **Stage 2: AI Filtering** (`filter_clips.py`)
    Uses YOLOv8 to analyze the motion clips. It only keeps clips where humans or cars are detected and moving.
    - **Features:** Persistence checking (requires multiple frames of motion) and IOU thresholding to avoid jitter false positives.
3.  **Stage 3: AI Outlining** (`draw_outlines.py`)
    Uses YOLOv8-seg to draw persistent, color-coded outlines on identified targets in the kept clips.
    - **Optimization:** Uses streaming mode to prevent memory issues on large files.

## Files in this Repository

- `run_pipeline.sh`: The main orchestration script that runs all three stages in sequence.
- `filter_clips.py`: Logic for YOLO-based object filtering.
- `draw_outlines.py`: Script for generating segmentation outlines on targets.
- `batch_outline.sh`: Utility to run the outlining process on a directory of clips.
- `burn_timestamps.py`: Utility to overlay readable timestamps on the video output.
- `rename_results_v3.py`: Handles systematic renaming of processed clips for easier archiving.
- `walk_id.py`: Helper script for directory traversal and identification.
- `yolov8n.pt` & `yolov8n-seg.pt`: Pre-trained YOLOv8 models for detection and segmentation.

## Dependencies

- Python 3.8+
- [dvr-scan](https://github.com/Breakthrough/DVR-Scan)
- [FFmpeg](https://ffmpeg.org/)
- `ultralytics` (YOLOv8)
- `opencv-python`
- `numpy`

## Usage

```bash
./run_pipeline.sh -i <input_video.mp4> -w <workspace_directory>
```

See `run_pipeline.sh --help` for more advanced options.