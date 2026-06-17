# Scanning Work Pipeline

This project processes large security video files to extract and highlight motion events involving various objects (humans, cars, etc.).

## Pipeline Stages

1.  **Stage 1: Motion Extraction**
    Uses `dvr-scan` to slice the main video into clips containing any motion.
2.  **Stage 2: AI Filtering (`filter_clips.py`)**
    Uses YOLOv8 to identify and verify motion events. Clips with only stationary objects are excluded.
    - **Current Settings:** Adjustable confidence (default 0.4), IOU threshold 0.4, min 5 motion frames to avoid jitter/lighting false positives.
    - **Labeling:** Detected object classes are appended to filenames and burned into the video.
3.  **Stage 3: Filename Timestamps & Labeling**
    Calculates real-world timestamps and appends detected object classes to the filename.
4.  **Stage 4: Visual Timestamp & Label Burn-In (`burn_timestamps.py`)**
    Uses FFmpeg to burn the calculated time and object labels into the video.
5.  **Cleanup**
    Removes intermediate files to save space.

## Scripts
- `run_pipeline.sh`: Automates the multi-stage funnel.
- `filter_clips.py`: AI-based filtering and object verification logic.
- `burn_timestamps.py`: Burns timestamps and object labels into MP4 files.
- `draw_outlines.py`: Heavy segmentation/outlining script (Optional/Stage 3 in some variants).
- `batch_outline.sh`: Helper for processing multiple clips.
