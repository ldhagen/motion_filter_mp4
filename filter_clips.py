import argparse
import os
import shutil
import cv2
import numpy as np
from ultralytics import YOLO

def iou(boxA, boxB):
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])
    interArea = max(0, xB - xA + 1) * max(0, yB - yA + 1)
    if interArea <= 0: return 0
    boxAArea = (boxA[2] - boxA[0] + 1) * (boxA[3] - boxA[1] + 1)
    boxBArea = (boxB[2] - boxB[0] + 1) * (boxB[3] - boxB[1] + 1)
    return interArea / float(boxAArea + boxBArea - interArea)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--input', required=True, help="Input directory of clips")
    parser.add_argument('-o', '--output', required=True, help="Output directory for kept clips")
    parser.add_argument('--iou-threshold', type=float, default=0.4, help="IOU threshold to consider an object stationary")
    parser.add_argument('--min-motion-frames', type=int, default=5, help="Minimum number of sampled frames with motion to keep clip")
    parser.add_argument('--frame-step', type=int, default=30, help="Check every Nth frame for motion")
    parser.add_argument('--classes', nargs='+', default=['0', '2'], help="YOLOv8 class IDs to detect, or 'all' to detect everything")
    args = parser.parse_args()

    model = YOLO('yolov8n.pt') 
    os.makedirs(args.output, exist_ok=True)
    
    FRAME_STEP = args.frame_step   
    
    # Handle 'all' keyword
    if 'all' in [c.lower() for c in args.classes]:
        DETECT_CLASSES = None
    else:
        DETECT_CLASSES = [int(c) for c in args.classes]
    
    print(f"Filtering clips in {args.input} (Persistence-aware, checking every {FRAME_STEP}th frame)...")
    print(f"Targeting classes: {'all' if DETECT_CLASSES is None else DETECT_CLASSES}")

    kept_count = 0
    skipped_count = 0

    for filename in sorted(os.listdir(args.input)):
        if not filename.endswith('.mp4'):
            continue
            
        filepath = os.path.join(args.input, filename)
        output_path = os.path.join(args.output, filename)

        # Resume support: skip if the file already exists in output
        if os.path.exists(output_path):
            print(f"  [SKIP] {filename} already exists in output directory.")
            continue
            
        cap = cv2.VideoCapture(filepath)
        
        reference_boxes = None
        motion_frames_count = 0
        frame_count = 0
        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret: break
                
            if frame_count % FRAME_STEP == 0:
                # Use a slightly higher confidence (0.4) to filter out weak/ghost detections
                results = model.predict(source=frame, classes=DETECT_CLASSES, conf=0.4, verbose=False)
                current_boxes = results[0].boxes.xyxy.cpu().numpy() if results[0].boxes else []
                
                if reference_boxes is None:
                    if len(current_boxes) > 0:
                        # Establish background in the first frame we see something
                        reference_boxes = current_boxes
                else:
                    frame_has_motion = False
                    
                    # Check if any CURRENT box is 'new' or has 'moved' relative to ALL reference boxes
                    for cb in current_boxes:
                        max_iou = max([iou(cb, rb) for rb in reference_boxes]) if len(reference_boxes) > 0 else 0
                        if max_iou < args.iou_threshold:
                            frame_has_motion = True
                            break
                    
                    # Check if any REFERENCE box disappeared (which implies it moved away)
                    if not frame_has_motion:
                        for rb in reference_boxes:
                            max_iou = max([iou(rb, cb) for cb in current_boxes]) if len(current_boxes) > 0 else 0
                            if max_iou < args.iou_threshold:
                                frame_has_motion = True
                                break
                    
                    if frame_has_motion:
                        motion_frames_count += 1
                                
            if motion_frames_count >= args.min_motion_frames: 
                break
            frame_count += 1
            
        cap.release()
        
        if motion_frames_count >= args.min_motion_frames:
            print(f"  [KEEP] Motion detected in {motion_frames_count} frames: {filename}")
            shutil.copy(filepath, os.path.join(args.output, filename))
            kept_count += 1
        else:
            print(f"  [SKIP] {filename} (stationary or no real motion)")
            skipped_count += 1
            
    print("\nAI Verification Results:")
    print("------------------------")
    print(f"Total Clips Scanned: {kept_count + skipped_count}")
    print(f"Targets Found:       {kept_count} (Keep)")
    print(f"Stationary/Wind:     {skipped_count} (Discarded)")
    if (kept_count + skipped_count) > 0:
        reduction = (skipped_count / (kept_count + skipped_count)) * 100
        print(f"Efficiency:          {reduction:.1f}% reduction in footage.")

if __name__ == "__main__":
    main()
