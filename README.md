# Motion Filter Pipeline (Highly Optimized)

This project is a high-performance, multi-threaded video processing pipeline designed to extract, verify, and archive human and vehicle motion events from massive, multi-day security camera archives.

## 🚀 The Ultimate Optimized Workflow
Processing 24 hours of 1080p security footage typically takes standard computers 5-10 hours. By pushing the hardware to its mathematical limits, this pipeline has been optimized to complete in **under 2 hours per day** (or ~8 hours for a full 7-day archive) with zero SSD bottlenecking.

### 1. The RAM Disk & Parallel Decoding
Instead of grinding the SSD, the master 7-day archive is sliced into 24 one-hour chunks that are written **directly into your system's RAM** (`/dev/shm`). 
The pipeline then spins up 8 parallel Python workers that read from RAM at lightspeed, mathematically decompressing the H.264 video and applying `MOG2` background subtraction simultaneously.

### 2. Geometric Masking & Shadow Rejection
By passing a solid mask (e.g., `front_solid_bottom_80.png`) that paints the top portion of the camera view black (covering the trees, sky, and distant roads), we achieved massive wins in speed and accuracy. 
Additionally, shadow-rejection logic was introduced to prevent parked cars from being falsely verified by bounding box jitter.

### 3. Persistent Memory Management
Because 7 days of video cannot fit in a 14GB RAM disk, the pipeline runs **one day at a time** (`--daily`). Once a 24-hour segment finishes, it automatically copies the verified clips to a physical SSD (`./persistent_<workspace>`) and completely wipes the RAM disk clean for the next day.

---

## 🛠️ Pipeline Stages

1. **Motion Extraction (`dvr-scan`)**: Reads directly from RAM, ignores masked pixels, and extracts short clips of active motion.
2. **AI Filtering (`filter_clips.py`)**: Uses Neural Networks (`YOLOv8`) to verify the clips. It measures bounding box displacement to ensure objects physically moved.
3. **Real-World Renaming**: Calculates the exact calendar date and clock time of each event by anchoring to your filename and adding the scan offsets. 
4. **Visual Burn-in (`FFmpeg`)**: Burns the calculated timestamp and AI label directly into the corner of the MP4.
5. **Auto-Archival (`archive_clips.sh`)**: Verifies file integrity, neatly sorts the final clips into a permanent `Camera/Year/Month` folder structure, and automatically deletes the massive raw source video to free up disk space.
6. **(Optional) Secondary Movement Verification (`verify_movement.py`)**: A multi-threaded post-processor that scans your final archives. It uses `Bytetrack` to trace the precise pixel path of multiple objects (cars, people, dogs). If a parked car jittered in the shadows and traveled less than 100 pixels, it is automatically safely isolated to an `invalid_static` folder.

---

## 💻 Usage & Mass Processing

You can process an entire directory of multi-day archives completely unattended. The script will automatically log its progress to `pipeline_history.csv` and skip any videos it has already completed.

### The Master Command
```bash
nohup ./run_pipeline.sh -d /home/ldhagen/FrigateArchiveXfers -a /home/ldhagen/FrigateArchives -o /dev/shm/newcam_scan -j 8 --fs 8 --df 2 --conf 0.4 --classes known --threshold 1.0 --min-displacement 60 --min-len 0.1s --bg-subtractor MOG2 --mask front_solid_bottom_80.png --daily > mass_run.log 2>&1 &
```

### Key Arguments:
* `-d /path/to/vids`: Directory containing massive raw videos to automatically chew through.
* `-a /path/to/archive`: Triggers auto-archival to your permanent folders and deletes the raw file on success.
* `-o /dev/shm/workspace`: Forces all heavy lifting to happen in RAM.
* `-j 8`: Number of parallel processing workers (matches CPU cores).
* `--mask`: Black-and-white image to blind the AI to trees/wind.
* `--threshold`: Motion sensitivity. (Raise to 1.0 or 1.5 to aggressively ignore cloud shadows).
* `--min-displacement`: Minimum pixels an object must travel to be kept (e.g. 60px to ignore shadow jitter on parked cars).
* `--force`: Bypasses the `pipeline_history.csv` memory if you want to intentionally re-run a video.

---

## 🔍 Stage 6: Movement Verification
If you still have parked cars slipping through due to shadows, run the multi-threaded verification script on your archive folder:
```bash
nohup python3 -u verify_movement.py -d /home/ldhagen/FrigateArchives/front_window/2025/02 --min-dist 100 -j 8 > verify_run.log 2>&1 &
```
* **Output:** Creates `valid_movement` and `invalid_static` subdirectories in the target folder and sorts the MP4s based on whether the objects physically traveled across the screen.

## 📊 Logging & History
* **`pipeline_history.csv`**: Tracks exact processing times of master raw videos. The pipeline reads this file to instantly skip videos it has already processed.
* **`archive_history.log`**: A permanent, running ledger inside your `FrigateArchives` folder detailing every single clip the system has successfully captured and saved over its lifetime.
