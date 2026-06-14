# Motion Filter MP4

This project provides a high-performance, multi-stage pipeline to process large security video files. It extracts, verifies, and timestamps motion events specifically involving humans and cars while filtering out false positives.

## Refined Features

- **Parallel Processing:** Uses multi-threaded chunking in Stage 1 to process 100+ hour videos up to 4x faster.
- **Precision Drift Fix:** Automatically corrects for keyframe alignment errors during chunking, ensuring filenames and burned timestamps are 100% accurate to the original footage.
- **Live Dashboard:** Provides real-time progress monitoring for parallel jobs.
- **AI Efficiency Reporting:** Generates a detailed summary of AI filtering performance and footage reduction rates.
- **Static Masking:** Includes a tool to identify and ignore consistently parked vehicles to further reduce false motion triggers.

## Pipeline Overview

1.  **Stage 1: Motion Extraction** (`dvr-scan`)
    Slices the large input video into clips. Supports multi-job parallelism (`-j`).
2.  **Stage 2: AI Filtering** (`filter_clips.py`)
    Uses YOLOv8 to keep only human/car motion. Now with detailed performance reporting.
3.  **Stage 3: Real-World Renaming**
    Calculates precise calendar dates based on filename and drift-corrected offsets.
4.  **Stage 4: Visual Timestamp Burn-In**
    Permanently burns the calculated time into the top-left corner of the video.
5.  **Stage 5: Cleanup**
    Deletes massive intermediate files to reclaim disk space.

## Usage

```bash
./run_pipeline.sh -i <input.mp4> -o <output_dir> -j <num_jobs> -fs 2 -df 2
```

### Optimization Parameters
- `-j <N>`: Run N parallel scan jobs (e.g., `-j 4`).
- `-fs <N>`: Frame skip (default 2). Use higher values for speed, lower for sensitivity.
- `-df <N>`: Downscale factor (default 2). Use 4 for ultra-fast scanning on high-res input.

## New Tools
- `generate_static_mask.py`: Run this on a video to find the coordinates of parked cars that should be ignored during scanning.