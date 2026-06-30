import argparse
import json
import math
import os
import shutil
import subprocess
import cv2
import numpy as np
import torch
from ultralytics import YOLO
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing

# Global variables in worker processes
_model = None
_mask_resized = None


def init_worker(mask_path):
    """Initialize YOLO model and mask in each worker process."""
    global _model, _mask_resized
    torch.set_num_threads(1)
    _model = YOLO('yolov8n.pt')
    if mask_path and os.path.exists(mask_path):
        _mask_resized = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)


def process_clip(args_tuple):
    """Analyze a clip for active object motion using frame-to-frame displacement.

    Instead of accumulating reference boxes (which fails on long clips),
    this compares each detection's center position against the previous
    frame's detections of the same class.  Real motion = significant
    displacement (default >30 px).  First appearances are skipped
    (no prior frame to compare against).

    Motion frames are clustered into discrete events separated by time
    gaps.  Each event produces a separate trimmed output clip.
    """
    (filename, input_dir, output_dir, min_displacement, min_event_frames,
     frame_step, classes, conf, event_gap_sec) = args_tuple
    global _model, _mask_resized

    filepath = os.path.join(input_dir, filename)

    cap = cv2.VideoCapture(filepath)
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    prev_detections = {}   # class_id -> list of (cx, cy)
    motion_frames = []
    detected_classes = set()
    local_mask_resized = None
    frame_count = 0

    while cap.isOpened():
        if frame_count % frame_step != 0:
            ret = cap.grab()  # skip costly decode for non-sampled frames
            if not ret:
                break
            frame_count += 1
            continue
        ret, frame = cap.read()
        if not ret:
            break

        # Apply mask if provided
        if _mask_resized is not None:
            if local_mask_resized is None:
                if _mask_resized.shape[:2] != frame.shape[:2]:
                    local_mask_resized = cv2.resize(
                        _mask_resized, (frame.shape[1], frame.shape[0]))
                else:
                    local_mask_resized = _mask_resized
            frame_for_detection = cv2.bitwise_and(
                frame, frame, mask=local_mask_resized)
        else:
            frame_for_detection = frame

        results = _model.predict(
            source=frame_for_detection, classes=classes,
            conf=conf, verbose=False)
        current_boxes = (results[0].boxes.xyxy.cpu().numpy()
                         if results[0].boxes else [])

        curr_detections = {}   # class_id -> list of (cx, cy)
        frame_has_motion = False

        if len(current_boxes) > 0:
            clses = results[0].boxes.cls.cpu().numpy()
            for box, cls_id in zip(current_boxes, clses):
                cls = int(cls_id)
                cx = (box[0] + box[2]) / 2.0
                cy = (box[1] + box[3]) / 2.0

                if cls not in curr_detections:
                    curr_detections[cls] = []
                curr_detections[cls].append((cx, cy))

                # Only flag motion if we have a PREVIOUS frame to compare
                if cls in prev_detections and prev_detections[cls]:
                    min_dist = min(
                        math.sqrt((cx - pcx) ** 2 + (cy - pcy) ** 2)
                        for pcx, pcy in prev_detections[cls]
                    )
                    if min_dist > min_displacement:
                        frame_has_motion = True
                        detected_classes.add(_model.names[cls])

        if frame_has_motion:
            motion_frames.append(frame_count)

        prev_detections = curr_detections
        frame_count += 1

    cap.release()

    if not motion_frames:
        return filename, []

    # ---- Cluster motion frames into discrete events ----
    event_gap_frames = event_gap_sec * fps
    events = []
    current_event = [motion_frames[0]]
    for mf in motion_frames[1:]:
        if (mf - current_event[-1]) > event_gap_frames:
            events.append(current_event)
            current_event = [mf]
        else:
            current_event.append(mf)
    events.append(current_event)

    # Require minimum motion frames per event
    valid_events = [e for e in events if len(e) >= min_event_frames]

    if not valid_events:
        return filename, []

    # ---- Output each event as a separate trimmed clip ----
    output_results = []
    for idx, event in enumerate(valid_events):
        t_start = event[0] / fps
        t_end = event[-1] / fps
        pad_start = max(0.0, t_start - 3.0)
        pad_end = min(total_frames / fps, t_end + 3.0)
        duration = pad_end - pad_start
        event_duration = t_end - t_start

        # Name: original if single event, _evt### if multiple
        if len(valid_events) == 1:
            out_name = filename
        else:
            base, ext = os.path.splitext(filename)
            out_name = f"{base}_evt{idx + 1:03d}{ext}"

        output_path = os.path.join(output_dir, out_name)
        temp_out = output_path + ".tmp.mp4"

        slice_cmd = [
            "ffmpeg", "-y",
            "-ss", f"{pad_start:.3f}",
            "-t", f"{duration:.3f}",
            "-i", filepath,
            "-c", "copy", "-map", "0",
            temp_out
        ]
        res = subprocess.run(slice_cmd, capture_output=True)

        if res.returncode == 0 and os.path.exists(temp_out):
            shutil.move(temp_out, output_path)
            output_results.append({
                "output_name": out_name,
                "source": filename,
                "classes": sorted(list(detected_classes)),
                "trim_offset": pad_start,
                "motion_frames": len(event),
                "event_duration": round(event_duration, 1),
                "clip_duration": round(duration, 1),
            })
        else:
            # Clean up failed temp file
            if os.path.exists(temp_out):
                os.remove(temp_out)

    return filename, output_results


def main():
    parser = argparse.ArgumentParser(
        description="AI-filter motion clips using displacement-based tracking")
    parser.add_argument('-i', '--input', required=True,
                        help="Input directory of motion clips")
    parser.add_argument('-o', '--output', required=True,
                        help="Output directory for verified events")
    parser.add_argument('--min-displacement', type=float, default=30.0,
                        help="Min pixel displacement between frames to count "
                             "as motion (default: 30)")
    parser.add_argument('--min-event-frames', type=int, default=2,
                        help="Min motion frames per event to keep (default: 2)")
    parser.add_argument('--event-gap', type=float, default=10.0,
                        help="Seconds of no motion before starting a new "
                             "event (default: 10)")
    parser.add_argument('--frame-step', type=int, default=30,
                        help="Check every Nth frame (default: 30)")
    parser.add_argument('--classes', nargs='+', default=['0', '2'],
                        help="YOLO class IDs, 'all', or 'known'")
    parser.add_argument('--conf', type=float, default=0.4,
                        help="YOLO confidence threshold (default: 0.4)")
    parser.add_argument('--mask',
                        help="Path to binary mask image")
    parser.add_argument('--metadata',
                        help="Path to save metadata JSON")
    parser.add_argument('--jobs', type=int,
                        default=multiprocessing.cpu_count(),
                        help="Parallel worker processes")
    # Backward-compatible (ignored) parameters from old version
    parser.add_argument('--iou-threshold', type=float, default=0.4,
                        help=argparse.SUPPRESS)
    parser.add_argument('--min-motion-frames', type=int, default=5,
                        help=argparse.SUPPRESS)
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    # Handle class keywords
    if 'all' in [c.lower() for c in args.classes]:
        DETECT_CLASSES = None
    elif 'known' in [c.lower() for c in args.classes]:
        DETECT_CLASSES = [0, 1, 2, 3, 5, 7, 15, 16, 17]
    else:
        DETECT_CLASSES = [int(c) for c in args.classes]

    print(f"Filtering clips in {args.input} "
          f"(Displacement-based motion detection)...")
    print(f"  Min displacement: {args.min_displacement}px")
    print(f"  Min event frames: {args.min_event_frames}")
    print(f"  Event gap:        {args.event_gap}s")
    print(f"  Frame step:       {args.frame_step}")
    print(f"  Classes:          "
          f"{'all' if DETECT_CLASSES is None else DETECT_CLASSES}")
    print(f"  Confidence:       {args.conf}")
    print(f"  Parallel jobs:    {args.jobs}")

    if args.mask:
        if os.path.exists(args.mask):
            print(f"  Mask:             {args.mask}")
        else:
            print(f"  Warning: Mask not found at {args.mask}")

    metadata_map = {}
    clips_with_motion = 0
    event_count = 0
    skipped_count = 0
    skipped_existing = 0

    # Build task list
    tasks = []
    for filename in sorted(os.listdir(args.input)):
        if not filename.endswith('.mp4'):
            continue

        output_path = os.path.join(args.output, filename)

        # Resume support: skip already processed files
        if os.path.exists(output_path):
            print(f"  [SKIP] {filename} already in output")
            skipped_existing += 1
            continue

        tasks.append((
            filename, args.input, args.output,
            args.min_displacement, args.min_event_frames,
            args.frame_step, DETECT_CLASSES, args.conf,
            args.event_gap
        ))

    def handle_result(src_filename, results):
        nonlocal clips_with_motion, event_count, skipped_count
        if results:
            clips_with_motion += 1
            for r in results:
                classes_str = ", ".join(r["classes"])
                print(f"  [KEEP] {r['output_name']}  "
                      f"({r['motion_frames']} motion frames, "
                      f"event {r['event_duration']}s -> "
                      f"clip {r['clip_duration']}s)  "
                      f"[{classes_str}]")
                metadata_map[r["output_name"]] = {
                    "source": r["source"],
                    "classes": r["classes"],
                    "trim_offset": r["trim_offset"],
                }
                event_count += 1
        else:
            print(f"  [SKIP] {src_filename} (no active motion)")
            skipped_count += 1

    if tasks:
        if args.jobs > 1:
            with ProcessPoolExecutor(
                max_workers=args.jobs,
                initializer=init_worker,
                initargs=(args.mask,)
            ) as executor:
                futures = {
                    executor.submit(process_clip, t): t[0] for t in tasks
                }
                for future in as_completed(futures):
                    src_filename = futures[future]
                    try:
                        fname, results = future.result()
                        handle_result(fname, results)
                    except Exception as e:
                        print(f"  [ERROR] {src_filename}: {e}")
        else:
            init_worker(args.mask)
            for t in tasks:
                fname, results = process_clip(t)
                handle_result(fname, results)

    # Save metadata
    if args.metadata:
        existing_metadata = {}
        if os.path.exists(args.metadata):
            try:
                with open(args.metadata, 'r') as f:
                    existing_metadata = json.load(f)
            except Exception:
                pass
        existing_metadata.update(metadata_map)
        with open(args.metadata, 'w') as f:
            json.dump(existing_metadata, f, indent=2)

    total_scanned = clips_with_motion + skipped_count
    print(f"\nAI Verification Results:")
    print(f"------------------------")
    print(f"Total Clips Scanned:  {total_scanned}")
    if skipped_existing > 0:
        print(f"Previously Processed: {skipped_existing}")
    print(f"Clips with Motion:    {clips_with_motion}")
    print(f"Events Extracted:     {event_count}")
    print(f"No Active Motion:     {skipped_count} (Discarded)")
    if total_scanned > 0:
        reduction = (skipped_count / total_scanned) * 100
        print(f"Efficiency:           {reduction:.1f}% reduction")


if __name__ == "__main__":
    main()
