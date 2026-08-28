import argparse
import os
import math
import shutil
import datetime
from ultralytics import YOLO
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing

# Global worker variable
_model = None
_class_map = None

def init_worker():
    global _model, _class_map
    import cv2
    import torch
    # Limit internal threads to avoid CPU contention
    cv2.setNumThreads(1)
    torch.set_num_threads(1)
    _model = YOLO('yolov8n.pt')
    _class_map = {v: k for k, v in _model.names.items()}

def process_clip(args_tuple):
    filename, input_dir, min_dist = args_tuple
    global _model, _class_map
    
    filepath = os.path.join(input_dir, filename)
    base = os.path.splitext(filename)[0]
    parts = base.split('_')
    
    target_class_ids = []
    for part in reversed(parts):
        if part in _class_map:
            target_class_ids.append(_class_map[part])
        else:
            break
            
    if not target_class_ids:
        return filename, filepath, "VALID_NO_CLASS", 0.0
        
    results = _model.track(source=filepath, persist=True, verbose=False, tracker="bytetrack.yaml", stream=True)
    track_history = {}
    
    for result in results:
        if result.boxes is None or result.boxes.id is None:
            continue
            
        boxes = result.boxes.xyxy.cpu().numpy()
        track_ids = result.boxes.id.cpu().numpy()
        clses = result.boxes.cls.cpu().numpy()
        
        for box, track_id, cls in zip(boxes, track_ids, clses):
            if int(cls) in target_class_ids:
                cx = (box[0] + box[2]) / 2.0
                cy = (box[1] + box[3]) / 2.0
                
                if track_id not in track_history:
                    track_history[track_id] = []
                track_history[track_id].append((cx, cy))
                
    max_displacement = 0.0
    for track_id, points in track_history.items():
        if len(points) < 2:
            continue
        for i in range(len(points)):
            for j in range(i + 1, len(points)):
                dist = math.sqrt((points[i][0] - points[j][0])**2 + (points[i][1] - points[j][1])**2)
                if dist > max_displacement:
                    max_displacement = dist
                    
    if max_displacement >= min_dist:
        return filename, filepath, "VALID_MOVED", max_displacement
    else:
        return filename, filepath, "INVALID_STATIC", max_displacement

def main():
    parser = argparse.ArgumentParser(description="Verify actual object movement using YOLO object tracking.")
    parser.add_argument('-d', '--dir', required=True, help="Directory of clips to verify")
    parser.add_argument('--min-dist', type=float, default=100.0, help="Minimum pixel distance the object must travel to be kept (default: 100)")
    parser.add_argument('--dry-run', action='store_true', help="Print results without moving anything")
    parser.add_argument('-j', '--jobs', type=int, default=multiprocessing.cpu_count(), help="Number of parallel workers")
    args = parser.parse_args()

    # Limit scientific computing threads to prevent spillover in master process
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
    os.environ["NUMEXPR_NUM_THREADS"] = "1"

    log_file_path = os.path.join(args.dir, "movement_verification.log")
    
    def log_print(msg):
        print(msg)
        with open(log_file_path, "a") as log_file:
            log_file.write(msg + "\n")

    log_print(f"\n--- Verification Started: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")
    log_print(f"Target Directory: {args.dir}")
    log_print(f"Minimum Distance: {args.min_dist}px")
    log_print(f"Parallel Workers: {args.jobs}")
    if args.dry_run:
        log_print("Mode: DRY RUN (No files will be moved)")

    files = [f for f in os.listdir(args.dir) if f.endswith('.mp4')]
    log_print(f"Scanning {len(files)} clips...")

    valid_dir = os.path.join(args.dir, "valid_movement")
    invalid_dir = os.path.join(args.dir, "invalid_static")
    
    if not args.dry_run:
        os.makedirs(valid_dir, exist_ok=True)
        os.makedirs(invalid_dir, exist_ok=True)

    invalid_count = 0
    valid_count = 0
    processed_count = 0

    tasks = [(f, args.dir, args.min_dist) for f in files]

    with ProcessPoolExecutor(max_workers=args.jobs, initializer=init_worker) as executor:
        futures = {executor.submit(process_clip, t): t for t in tasks}
        
        for future in as_completed(futures):
            processed_count += 1
            filename, filepath, status, max_disp = future.result()
            
            if status == "VALID_NO_CLASS":
                log_print(f"[{processed_count}/{len(files)}] [VALID] {filename} (No known YOLO classes in filename, keeping by default)")
                valid_count += 1
                if not args.dry_run:
                    shutil.move(filepath, os.path.join(valid_dir, filename))
            elif status == "VALID_MOVED":
                log_print(f"[{processed_count}/{len(files)}] [VALID] {filename} (Moved {max_disp:.1f}px)")
                valid_count += 1
                if not args.dry_run:
                    shutil.move(filepath, os.path.join(valid_dir, filename))
            elif status == "INVALID_STATIC":
                log_print(f"[{processed_count}/{len(files)}] [INVALID] {filename} (Only moved {max_disp:.1f}px - Static Object!)")
                invalid_count += 1
                if not args.dry_run:
                    shutil.move(filepath, os.path.join(invalid_dir, filename))

    log_print("\n===============================")
    log_print(f"Total Scanned: {len(files)}")
    log_print(f"Moved to /valid_movement: {valid_count}")
    log_print(f"Moved to /invalid_static: {invalid_count}")
    log_print("===============================\n")

if __name__ == "__main__":
    main()
