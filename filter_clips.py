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
    parser.add_argument('--conf', type=float, default=0.4, help="Confidence threshold for detection")
    parser.add_argument('--mask', help="Path to a binary image mask (white areas are kept, black ignored)")
    parser.add_argument('--metadata', help="Path to save metadata (mapping filename to classes)")
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
    print(f"Confidence threshold: {args.conf}")
    
    mask = None
    if args.mask:
        if os.path.exists(args.mask):
            print(f"Loading mask from: {args.mask}")
            mask = cv2.imread(args.mask, cv2.IMREAD_GRAYSCALE)
            if mask is None:
                print(f"Warning: Failed to load mask from {args.mask}")
        else:
            print(f"Warning: Mask file not found at {args.mask}")

    kept_count = 0
    skipped_count = 0
    metadata_map = {}

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
        detected_classes = set()
        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret: break
                
            if frame_count % FRAME_STEP == 0:
                # Apply mask if provided
                if mask is not None:
                    # Resize mask to match frame dimensions if necessary
                    if mask.shape[:2] != frame.shape[:2]:
                        mask_resized = cv2.resize(mask, (frame.shape[1], frame.shape[0]))
                    else:
                        mask_resized = mask
                        
                    # Apply mask (bitwise AND) to black out ignored areas
                    frame_for_detection = cv2.bitwise_and(frame, frame, mask=mask_resized)
                else:
                    frame_for_detection = frame

                results = model.predict(source=frame_for_detection, classes=DETECT_CLASSES, conf=args.conf, verbose=False)
                current_boxes = results[0].boxes.xyxy.cpu().numpy() if results[0].boxes else []
                
                if len(current_boxes) > 0:
                    for c in results[0].boxes.cls:
                        detected_classes.add(model.names[int(c)])

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
            classes_str = ",".join(sorted(list(detected_classes)))
            print(f"  [KEEP] Motion detected in {motion_frames_count} frames: {filename} (Classes: {classes_str})")
            shutil.copy(filepath, os.path.join(args.output, filename))
            metadata_map[filename] = sorted(list(detected_classes))
            kept_count += 1
        else:
            print(f"  [SKIP] {filename} (stationary or no real motion)")
            skipped_count += 1
            
    if args.metadata:
        import json
        with open(args.metadata, 'w') as f:
            json.dump(metadata_map, f)

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
