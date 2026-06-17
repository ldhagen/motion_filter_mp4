# Motion Filter MP4

This project provides a high-performance, multi-stage pipeline to process large security video files. It extracts, verifies, and timestamps motion events involving various objects (humans, cars, etc.) while filtering out false positives.

## Refined Features

- **Parallel Processing:** Uses multi-threaded chunking in Stage 1 to process 100+ hour videos up to 4x faster. Includes a staggered job start to prevent log file contention and ensure high reliability.
- **Precision Drift Fix:** Automatically corrects for keyframe alignment errors during chunking, ensuring filenames and burned timestamps are 100% accurate to the original footage.
- **Object Labeling:** Detected object classes (e.g., person, car) are automatically appended to filenames and visually burned into the video overlay.
- **Adjustable AI Confidence:** Fine-tune detection sensitivity with the `--conf` parameter to balance between catching every event and reducing false positives from shadows.
- **Flexible Object Detection:** Support for specific YOLO classes or a "detect all" mode.
- **Live Dashboard:** Provides real-time progress monitoring for parallel jobs.
- **AI Efficiency Reporting:** Generates a detailed summary of AI filtering performance and footage reduction rates.
- **Static Masking:** Includes a tool to identify and ignore consistently parked vehicles to further reduce false motion triggers.
- **AI Outlining (Optional):** Segmentation-based highlighting for identified targets.

## Pipeline Overview

1.  **Stage 1: Motion Extraction** (`dvr-scan`)
    Slices the large input video into clips. Supports multi-job parallelism (`-j`).
2.  **Stage 2: AI Filtering** (`filter_clips.py`)
    Uses YOLOv8 to keep only moving targets. Supports persistence filtering to ignore stationary objects. Includes object class detection and labeling.
3.  **Stage 3: Filename Timestamps & Labeling**
    Calculates precise calendar dates and appends detected object classes to the filename.
4.  **Stage 4: Visual Timestamp & Label Burn-In**
    Permanently burns the calculated time and object labels into the top-left corner of the video.
5.  **Stage 5: Cleanup**
    Deletes massive intermediate files to reclaim disk space.

## Usage

```bash
./run_pipeline.sh -i <input.mp4> -o <output_dir> -j <num_jobs> --conf 0.4 --classes "0 2"
```

### Parameters
- `-i, --input`: Source video file (filename must contain `YYYY_MM_DD_HH_MM`).
- `-o, --output`: Target directory for results.
- `-j, --jobs`: Number of parallel scan jobs (e.g., `-j 4`).
- `--conf <N>`: AI confidence threshold (default 0.4). Increase (e.g., 0.6) to reduce false positives from shadows.
- `--fs <N>`: Frame skip (default 2). Use higher values for speed, lower for sensitivity.
- `--df <N>`: Downscale factor (default 2). Use 4 for ultra-fast scanning on high-res input.
- `--classes`: YOLOv8 class IDs to detect. 
    - Default: `"0 2"` (Person and Car).
    - Detect Everything: `--classes all`.

### Long-Running Background Execution
For large video files, it is recommended to run the pipeline in the background using `nohup`:

```bash
nohup ./run_pipeline.sh -i "path/to/video_2025_11_09_00_00.mp4" -j 4 --conf 0.5 --classes "all" > run.log 2>&1 &
```
You can then monitor progress by checking `run.log` or the `status.log` inside the workspace directory.

## Individual Tools
- `filter_clips.py`: AI-based verification and labeling logic.
- `burn_timestamps.py`: Batch burn timestamps and object labels into video files.
- `draw_outlines.py`: Segmentation tool to draw outlines on targets. Supports `--classes all`.
- `generate_static_mask.py`: Identify coordinates of parked cars to be ignored during scanning.
- `batch_outline.sh`: Process an entire directory through `draw_outlines.py`.
