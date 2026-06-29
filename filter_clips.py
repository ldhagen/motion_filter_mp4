import argparse
import json
import os
import shutil
import cv2
import numpy as np
import torch
from ultralytics import YOLO
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing

# Global variables in worker processes
_model = None
_mask_resized = None

def iou(boxA, boxB):
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])
    interArea = max(0, xB - xA) * max(0, yB - yA)
    if interArea <= 0: return 0
    boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
    boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
    denom = boxAArea + boxBArea - interArea
    if denom == 0: return 0
    return interArea / float(denom)

def init_worker(mask_path):
    global _model, _mask_resized
    # Set PyTorch threads to 1 to avoid thread contention on CPU
    torch.set_num_threads(1)
    _model = YOLO('yolov8n.pt')
    if mask_path and os.path.exists(mask_path):
        _mask_resized = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)

def process_clip(args_tuple):
    filename, input_dir, output_dir, iou_threshold, min_motion_frames, frame_step, classes, conf = args_tuple
    global _model, _mask_resized
    
    filepath = os.path.join(input_dir, filename)
    output_path = os.path.join(output_dir, filename)
    
    cap = cv2.VideoCapture(filepath)
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0: fps = 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    reference_boxes = []
    moving_frames = []
    detected_classes = set()
    local_mask_resized = None
    frame_count = 0
    
    while cap.isOpened():
        if frame_count % frame_step != 0:
            ret = cap.grab()  # skip costly decode for non-sampled frames
            if not ret: break
            frame_count += 1
            continue
        ret, frame = cap.read()
        if not ret: break

        # Apply mask if provided
        if _mask_resized is not None:
            # Resize mask to match frame dimensions (cached after first use)
            if local_mask_resized is None:
                if _mask_resized.shape[:2] != frame.shape[:2]:
                    local_mask_resized = cv2.resize(_mask_resized, (frame.shape[1], frame.shape[0]))
                else:
                    local_mask_resized = _mask_resized
                
            # Apply mask (bitwise AND) to black out ignored areas
            frame_for_detection = cv2.bitwise_and(frame, frame, mask=local_mask_resized)
        else:
            frame_for_detection = frame

        results = _model.predict(source=frame_for_detection, classes=classes, conf=conf, verbose=False)
        current_boxes = results[0].boxes.xyxy.cpu().numpy() if results[0].boxes else []
        
        if len(current_boxes) > 0:
            clses = results[0].boxes.cls.cpu().numpy()
            frame_has_motion = False
            for box, cls_id in zip(current_boxes, clses):
                cb = (box[0], box[1], box[2], box[3], int(cls_id))
                same_class_refs = [rb for rb in reference_boxes if rb[4] == cb[4]]
                max_iou = max([iou(box, rb[:4]) for rb in same_class_refs]) if len(same_class_refs) > 0 else 0
                
                if max_iou >= iou_threshold:
                    # Update reference box to current box to track slight drift
                    for idx, rb in enumerate(reference_boxes):
                        if rb[4] == cb[4] and iou(box, rb[:4]) == max_iou:
                            reference_boxes[idx] = cb
                            break
                else:
                    # New detection at a new position!
                    frame_has_motion = True
                    reference_boxes.append(cb)
            
            if frame_has_motion:
                moving_frames.append(frame_count)
                for c in clses:
                    detected_classes.add(_model.names[int(c)])
            
        frame_count += 1
        
    cap.release()
    
    if len(moving_frames) >= min_motion_frames:
        t_start = moving_frames[0] / fps
        t_end = moving_frames[-1] / fps
        
        # Add 3 seconds padding before and after
        pad_start = max(0.0, t_start - 3.0)
        pad_end = min(total_frames / fps, t_end + 3.0)
        duration = pad_end - pad_start
        
        import subprocess
        temp_out = output_path + ".tmp.mp4"
        slice_cmd = ["ffmpeg", "-y", "-ss", f"{pad_start:.3f}", "-t", f"{duration:.3f}", "-i", filepath, "-c", "copy", "-map", "0", temp_out]
        res = subprocess.run(slice_cmd, capture_output=True)
        if res.returncode == 0 and os.path.exists(temp_out):
            shutil.move(temp_out, output_path)
            return filename, True, sorted(list(detected_classes)), len(moving_frames), pad_start
        else:
            shutil.copy(filepath, output_path)
            return filename, True, sorted(list(detected_classes)), len(moving_frames), 0.0
    else:
        return filename, False, None, len(moving_frames), 0.0

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--input', required=True, help="Input directory of clips")
    parser.add_argument('-o', '--output', required=True, help="Output directory for kept clips")
    parser.add_argument('--iou-threshold', type=float, default=0.4, help="IOU threshold to consider an object stationary")
    parser.add_argument('--min-motion-frames', type=int, default=5, help="Minimum number of sampled frames with motion to keep clip")
    parser.add_argument('--frame-step', type=int, default=30, help="Check every Nth frame for motion")
    parser.add_argument('--classes', nargs='+', default=['0', '2'], help="YOLOv8 class IDs to detect, or 'all' to detect everything")
    parser.add_argument('--conf', type=float, default=0.4, help="Confidence threshold for detection")
    parser.add_argument('--mask', help="Path to a binary image mask (white areas are kept, black ignored)")
    parser.add_argument('--metadata', help="Path to save metadata (mapping filename to classes)")
    parser.add_argument('--jobs', type=int, default=multiprocessing.cpu_count(), help="Number of parallel processes for verification")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)
    
    # Handle 'all' and 'known' keywords
    if 'all' in [c.lower() for c in args.classes]:
        DETECT_CLASSES = None
    elif 'known' in [c.lower() for c in args.classes]:
        DETECT_CLASSES = [0, 1, 2, 3, 5, 7, 15, 16, 17]
    else:
        DETECT_CLASSES = [int(c) for c in args.classes]
    
    print(f"Filtering clips in {args.input} (Persistence-aware, checking every {args.frame_step}th frame)...")
    print(f"Targeting classes: {'all' if DETECT_CLASSES is None else DETECT_CLASSES}")
    print(f"Confidence threshold: {args.conf}")
    print(f"Using {args.jobs} parallel jobs for AI verification")
    
    if args.mask:
        if os.path.exists(args.mask):
            print(f"Loading mask from: {args.mask}")
        else:
            print(f"Warning: Mask file not found at {args.mask}")

    metadata_map = {}
    kept_count = 0
    skipped_count = 0
    skipped_existing = 0

    # Build tasks list
    tasks = []
    for filename in sorted(os.listdir(args.input)):
        if not filename.endswith('.mp4'):
            continue
            
        filepath = os.path.join(args.input, filename)
        output_path = os.path.join(args.output, filename)

        # Resume support: skip if the file already exists in output
        if os.path.exists(output_path):
            print(f"  [SKIP] {filename} already exists in output directory.")
            skipped_existing += 1
            # We also try to populate the metadata_map for existing file
            # By parsing its filename if it contains class suffix
            # E.g. 20250914_123456_DSME_0001_person_car.mp4
            base, ext = os.path.splitext(filename)
            parts = base.split('_')
            try:
                dsme_idx = next(i for i, part in enumerate(parts) if part == "DSME")
                if dsme_idx + 2 < len(parts):
                    classes = parts[dsme_idx+2:]
                    metadata_map[filename] = {
                        "classes": classes,
                        "trim_offset": 0.0
                    }
            except StopIteration:
                pass
            continue
            
        tasks.append((filename, args.input, args.output, args.iou_threshold, args.min_motion_frames, args.frame_step, DETECT_CLASSES, args.conf))

    if tasks:
        if args.jobs > 1:
            with ProcessPoolExecutor(max_workers=args.jobs, initializer=init_worker, initargs=(args.mask,)) as executor:
                futures = {executor.submit(process_clip, t): t[0] for t in tasks}
                for future in as_completed(futures):
                    filename = futures[future]
                    try:
                        fname, kept, classes, motion_count, trim_offset = future.result()
                        if kept:
                            classes_str = ",".join(classes)
                            print(f"  [KEEP] Motion detected in {motion_count} frames: {filename} (Classes: {classes_str})")
                            metadata_map[filename] = {
                                "classes": classes,
                                "trim_offset": trim_offset
                            }
                            kept_count += 1
                        else:
                            print(f"  [SKIP] {filename} (stationary or no real motion)")
                            skipped_count += 1
                    except Exception as e:
                        print(f"Error processing {filename}: {e}")
        else:
            # Sequential execution
            init_worker(args.mask)
            for t in tasks:
                filename = t[0]
                fname, kept, classes, motion_count, trim_offset = process_clip(t)
                if kept:
                    classes_str = ",".join(classes)
                    print(f"  [KEEP] Motion detected in {motion_count} frames: {filename} (Classes: {classes_str})")
                    metadata_map[filename] = {
                        "classes": classes,
                        "trim_offset": trim_offset
                    }
                    kept_count += 1
                else:
                    print(f"  [SKIP] {filename} (stationary or no real motion)")
                    skipped_count += 1

    if args.metadata:
        # Load existing metadata if it exists and merge
        existing_metadata = {}
        if os.path.exists(args.metadata):
            try:
                with open(args.metadata, 'r') as f:
                    existing_metadata = json.load(f)
            except Exception:
                pass
        existing_metadata.update(metadata_map)
        with open(args.metadata, 'w') as f:
            json.dump(existing_metadata, f)

    total_scanned = kept_count + skipped_count
    print("\nAI Verification Results:")
    print("------------------------")
    print(f"Total Clips Scanned: {total_scanned}")
    if skipped_existing > 0:
        print(f"Previously Processed: {skipped_existing} (Skipped)")
    print(f"Targets Found:       {kept_count} (Keep)")
    print(f"Stationary/Wind:     {skipped_count} (Discarded)")
    if total_scanned > 0:
        reduction = (skipped_count / total_scanned) * 100
        print(f"Efficiency:          {reduction:.1f}% reduction in footage.")

if __name__ == "__main__":
    main()
