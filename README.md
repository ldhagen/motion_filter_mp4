# Motion Filter MP4

This project provides a high-performance, multi-stage pipeline to process large security video files. It extracts, verifies, and timestamps motion events specifically involving humans and cars (or any object known to YOLO) while filtering out false positives.

## Refined Features

- **Parallel Processing:** Uses multi-threaded chunking in Stage 1 to process 100+ hour videos up to 4x faster.
- **Precision Drift Fix:** Automatically corrects for keyframe alignment errors during chunking, ensuring filenames and burned timestamps are 100% accurate to the original footage.
- **Flexible Object Detection:** Support for specific YOLO classes or a "detect all" mode.
- **Live Dashboard:** Provides real-time progress monitoring for parallel jobs.
- **AI Efficiency Reporting:** Generates a detailed summary of AI filtering performance and footage reduction rates.
- **Static Masking:** Includes a tool to identify and ignore consistently parked vehicles to further reduce false motion triggers.
- **AI Outlining (Optional):** Segmentation-based highlighting for identified targets.

## Pipeline Overview

1.  **Stage 1: Motion Extraction** (`dvr-scan`)
    Slices the large input video into clips. Supports multi-job parallelism (`-j`).
2.  **Stage 2: AI Filtering** (`filter_clips.py`)
    Uses YOLOv8 to keep only moving targets. Supports persistence filtering to ignore stationary objects.
3.  **Stage 3: Filename Timestamps**
    Calculates precise calendar dates based on filename and drift-corrected offsets.
4.  **Stage 4: Visual Timestamp Burn-In**
    Permanently burns the calculated time into the top-left corner of the video.
5.  **Stage 5: Cleanup**
    Deletes massive intermediate files to reclaim disk space.

## Usage

```bash
./run_pipeline.sh -i <input.mp4> -o <output_dir> -j <num_jobs> -fs 2 -df 2 --classes "0 2"
```

### Parameters
- `-i, --input`: Source video file (filename must contain `YYYY_MM_DD_HH_MM`).
- `-o, --output`: Target directory for results.
- `-j, --jobs`: Number of parallel scan jobs (e.g., `-j 4`).
- `-fs <N>`: Frame skip (default 2). Use higher values for speed, lower for sensitivity.
- `-df <N>`: Downscale factor (default 2). Use 4 for ultra-fast scanning on high-res input.
- `--classes`: YOLOv8 class IDs to detect. 
    - Default: `"0 2"` (Person and Car).
    - Detect Everything: `--classes all`.
    - Custom: `--classes "0 2 16"` (Person, Car, Dog).

## Individual Tools
- `filter_clips.py`: AI-based verification logic.
- `draw_outlines.py`: Segmentation tool to draw outlines on targets. Supports `--classes all`.
- `generate_static_mask.py`: Identify coordinates of parked cars to be ignored during scanning.
- `burn_timestamps.py`: Batch burn timestamps into video files.
- `batch_outline.sh`: Process an entire directory through `draw_outlines.py`.
