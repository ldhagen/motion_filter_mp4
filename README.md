# Motion Filter MP4

This project provides a high-performance, multi-stage pipeline to process large security video files. It extracts, verifies, and timestamps motion events involving various objects (humans, cars, etc.) while filtering out false positives.

## Refined Features

- **Displacement-Based Motion Detection:** Uses frame-to-frame bounding box center displacement to distinguish real motion from detection jitter, shadows, and lighting changes. Only objects moving >30 pixels between consecutive samples are flagged.
- **Event Clustering:** Groups nearby motion frames into discrete events separated by configurable time gaps (default 10s). Each event produces a separate short clip instead of one massive file.
- **Parallel Processing:** Uses multi-threaded chunking in Stage 1 to process 100+ hour videos up to 4x faster. Includes a staggered job start to prevent log file contention and ensure high reliability.
- **Precision Drift Fix:** Automatically corrects for keyframe alignment errors during chunking, ensuring filenames and burned timestamps are 100% accurate to the original footage.
- **Object Labeling:** Detected object classes (e.g., person, car) are automatically appended to filenames and visually burned into the video overlay.
- **Adjustable AI Confidence:** Fine-tune detection sensitivity with the `--conf` parameter to balance between catching every event and reducing false positives from shadows.
- **Shadow & Static Area Masking:** Pass a custom binary image mask (`--mask`) to completely ignore specific areas of the camera view (like waving trees or intense shadow zones) during AI detection.
- **Detailed Pipeline Logging:** The process now outputs exact start and end timestamps for the full run and every individual stage.
- **Flexible Object Detection:** Support for specific YOLO classes or a "detect all" mode.
- **Live Dashboard:** Provides real-time progress monitoring for parallel jobs.
- **AI Efficiency Reporting:** Generates a detailed summary of AI filtering performance and footage reduction rates.
- **AI Outlining (Optional):** Segmentation-based highlighting for identified targets.

## Pipeline Overview

1.  **Stage 1: Motion Extraction** (`dvr-scan`)
    Slices the large input video into clips. Supports multi-job parallelism (`-j`).
2.  **Stage 2: AI Filtering** (`filter_clips.py`)
    Uses YOLOv8 with **displacement-based tracking** to keep only actively moving targets. Compares each detection's center position against the previous frame — real motion means significant displacement (>30px), not just a new detection. First appearances of objects are skipped (not flagged as motion). Motion frames are clustered into discrete events, each producing a tightly trimmed output clip.
3.  **Stage 3: Filename Timestamps & Labeling**
    Calculates precise calendar dates and appends detected object classes to the filename. Supports event-suffixed filenames from multi-event clips.
4.  **Stage 4: Visual Timestamp, Label & Mask Burn-In**
    Permanently burns the calculated time, object labels, and a **visual outline of your mask** (if provided) into the top-left corner of the video.
5.  **Stage 5: Cleanup**
    Deletes massive intermediate files to reclaim disk space.

## Motion Detection Algorithm

The AI filter (`filter_clips.py`) uses a displacement-based approach rather than IOU reference box accumulation:

### How It Works
1. For each sampled frame (every 30th frame = ~1 sample/second at 30fps):
   - Run YOLOv8 object detection
   - For each detected object, compute its bounding box center `(cx, cy)`
   - Find the nearest same-class detection from the **previous** sampled frame
   - If center displacement > `--min-displacement` (default 30px) → **real motion**
   - If no previous detection exists → skip (first appearance, not motion)
2. Cluster consecutive motion frames into **events** separated by `--event-gap` (default 10s)
3. Discard events with fewer than `--min-event-frames` (default 2) motion frames
4. Output each valid event as a separate trimmed clip with 3-second padding

### Why Displacement > IOU
| Scenario | IOU Approach | Displacement Approach |
|----------|-------------|----------------------|
| Parked car, stable | ✅ Correctly ignored | ✅ Correctly ignored |
| Parked car, shadow shift | ❌ Flagged as motion | ✅ Ignored (< 30px shift) |
| First detection of any object | ❌ Always flagged as motion | ✅ Skipped |
| Car driving through scene | ✅ Detected | ✅ Detected (100-500px/sec) |
| Person walking | ✅ Detected | ✅ Detected (30-100px/sec) |
| Long clip trim accuracy | ❌ First→last = hours | ✅ Per-event = seconds |

## Usage

```bash
./run_pipeline.sh -i <input.mp4> -o <output_dir> -j <num_jobs> --conf 0.4 --classes "0 2" --mask "shadow_mask.png"
```

### Parameters
- `-i, --input`: Source video file (filename must contain `YYYY_MM_DD_HH_MM`).
- `-o, --output`: Target directory for results.
- `-j, --jobs`: Number of parallel scan jobs (e.g., `-j 4`).
- `--conf <N>`: AI confidence threshold (default 0.4). Increase (e.g., 0.6) to reduce false positives from shadows.
- `--mask <file.png>`: Path to a binary image mask (white = keep, black = ignore) to block out specific camera zones.
- `--fs <N>`: Frame skip (default 2). Use higher values for speed, lower for sensitivity.
- `--df <N>`: Downscale factor (default 2). Use 4 for ultra-fast scanning on high-res input.
- `--classes`: YOLOv8 class IDs to detect. 
    - Default: `"0 2"` (Person and Car).
    - Detect Everything: `--classes all`.
    - Detect Known Outdoor/Security Objects: `--classes known` (Person, Bicycle, Car, Motorcycle, Bus, Truck, Cat, Dog, Horse).
    - Custom: `--classes "0 2 16"`.

### Filter-Specific Parameters (Stage 2)
These can be passed to `filter_clips.py` directly for standalone use:
- `--min-displacement <px>`: Minimum pixel displacement between frames to count as motion (default: 30).
- `--min-event-frames <N>`: Minimum motion frames per event to keep it (default: 2).
- `--event-gap <seconds>`: Seconds of no motion before starting a new event (default: 10).

## How to Create a Mask

Creating a mask (`--mask shadow_mask.png`) tells the AI which areas of the video to analyze and which to ignore. This is highly effective for eliminating false positives caused by moving shadows, blowing trees, or busy background streets.

The mask must be a **binary image**:
*   **White (Keep):** The AI will look for motion and objects here.
*   **Black (Ignore):** The AI will completely ignore these areas.

### Step-by-Step Instructions:
1. **Get a Reference Frame:** Open your raw `.mp4` video in a media player (like VLC). Pause the video at a clear frame and take a screenshot. Save this as your reference image.
2. **Open an Image Editor:** Open the screenshot in an image editor (Photoshop, GIMP, MS Paint, or Photopea).
3. **Paint the Mask:**
   * Create a new layer (if supported) over your screenshot.
   * Fill the entire canvas with **pure solid white**.
   * Select a paintbrush or shape tool, pick **pure solid black**, and paint over any areas you want the AI to ignore (e.g., the area where a tree casts heavy shadows).
4. **Save the Mask:** If you used layers, hide or delete the original screenshot layer. You should be left with an image that is only black shapes on a pure white background. Save it as a `.png` file (e.g., `shadow_mask.png`) in your project folder.
5. **Run the Pipeline:** Use the `--mask` argument. The script will automatically resize the mask to fit the video, ignore the black zones, and trace a red outline around your white "active" zones in the final output videos so you can verify it worked!

### Long-Running Background Execution
For large video files, it is recommended to run the pipeline in the background using `nohup`:

```bash
nohup ./run_pipeline.sh -i "path/to/video_2025_11_09_00_00.mp4" -j 4 --conf 0.5 --classes "all" --mask "my_mask.png" > run.log 2>&1 &
```
You can then monitor progress by checking `run.log` or the `status.log` inside the workspace directory.

## Individual Tools
- `filter_clips.py`: AI-based verification using displacement-based motion tracking, masking, and event clustering.
- `burn_timestamps.py`: Batch burn timestamps, object labels, and mask outlines into video files.
- `draw_outlines.py`: Segmentation tool to draw outlines on targets. Supports `--classes all`.
- `generate_static_mask.py`: Identify coordinates of parked cars to be ignored during scanning.
- `batch_outline.sh`: Process an entire directory through `draw_outlines.py`.