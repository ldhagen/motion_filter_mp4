# Scanning Work Pipeline

This project processes large security video files to extract and highlight motion events involving humans and cars.

## Pipeline Stages

1.  **Stage 1: Motion Extraction**
    Uses `dvr-scan` to slice the main video into clips containing any motion.
2.  **Stage 2: AI Filtering (`filter_clips.py`)**
    Uses YOLOv8 to identify humans and cars. Clips with only stationary objects are excluded.
    - **Current Settings:** Stricter filtering (IOU threshold 0.4, min 5 motion frames) to avoid jitter/lighting false positives.
3.  **Stage 3: AI Outlining (`draw_outlines.py`)**
    Uses YOLOv8-seg to draw persistent outlines on the identified targets.
    - **Performance Note:** Now uses `stream=True` to prevent OOM on large batches or files.
    - **Resumption:** Skips files if the `.avi` output already exists in the destination folder.

## Scripts
- `run_pipeline.sh`: Automates the 3-stage funnel.
- `filter_clips.py`: AI-based filtering logic.
- `draw_outlines.py`: Heavy segmentation/outlining script.
- `batch_outline.sh`: Helper for processing multiple clips.
