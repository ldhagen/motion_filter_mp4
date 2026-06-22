import cv2
import numpy as np
from ultralytics import YOLO
import argparse
import sys

def iou(boxA, boxB):
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])
    interArea = max(0, xB - xA) * max(0, yB - yA)
    boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
    boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
    denom = boxAArea + boxBArea - interArea
    if denom == 0: return 0
    return interArea / float(denom)

def main():
    parser = argparse.ArgumentParser(description="Find static cars in a video and output exclusion regions.")
    parser.add_argument("-i", "--input", required=True, help="Input video file")
    parser.add_argument("-n", "--samples", type=int, default=5, help="Number of frames to sample")
    args = parser.parse_args()

    model = YOLO('yolov8n.pt')
    cap = cv2.VideoCapture(args.input)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    if total_frames <= 0:
        print("Error: Could not read video duration.")
        sys.exit(1)

    print(f"Analyzing {args.input} ({width}x{height}, {total_frames} frames)...")
    interval = total_frames // (args.samples + 1)
    all_detections = []

    for i in range(1, args.samples + 1):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i * interval)
        ret, frame = cap.read()
        if not ret: continue
        
        results = model(frame, classes=[2, 3, 5, 7], verbose=False) # car, motorcycle, bus, truck
        frame_boxes = []
        for r in results:
            for box in r.boxes:
                frame_boxes.append(box.xyxy[0].cpu().numpy())
        all_detections.append(frame_boxes)
    
    cap.release()

    if not all_detections:
        print("No potential static objects detected.")
        return

    # Find boxes that appear in ALL samples with high IOU
    static_boxes = []
    if len(all_detections) < 2:
        print("Not enough samples to determine persistence.")
        return

    first_frame_boxes = all_detections[0]
    for box in first_frame_boxes:
        is_static = True
        for next_frame_boxes in all_detections[1:]:
            found_match = False
            for other_box in next_frame_boxes:
                if iou(box, other_box) > 0.85: # High threshold for stationary
                    found_match = True
                    break
            if not found_match:
                is_static = False
                break
        if is_static:
            static_boxes.append(box)

    if not static_boxes:
        print("No static objects found.")
        return

    print(f"Found {len(static_boxes)} static objects.")
    
    # Generate -a regions for dvr-scan. 
    # Since dvr-scan doesn't have "exclude", we use the Region Editor logic 
    # but automated. For simplicity, we can output the list of boxes 
    # and let the user decide, OR we can generate a mask image if dvr-scan 
    # supported it. 
    # 
    # NEW STRATEGY: Instead of complex inclusive regions, we can just 
    # use these coordinates to further filter in Stage 2.
    # But the user wanted to SPEED UP Stage 1.
    
    for i, box in enumerate(static_boxes):
        x1, y1, x2, y2 = map(int, box)
        print(f"STATIC_BOX:{x1},{y1},{x2},{y2}")

if __name__ == "__main__":
    main()
