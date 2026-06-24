import argparse
import os
from ultralytics import YOLO

def process_video(model, input_video, output_dir, detect_classes):
    """Process a single video file with the given model."""
    # Ensure output_dir is absolute and split it for YOLO
    abs_output_dir = os.path.abspath(output_dir)
    project = os.path.dirname(abs_output_dir)
    name = os.path.basename(abs_output_dir)
    os.makedirs(abs_output_dir, exist_ok=True)

    # Check if the output file already exists (YOLO usually saves as .avi)
    base_filename = os.path.splitext(os.path.basename(input_video))[0]
    output_filename = os.path.join(abs_output_dir, f"{base_filename}.avi")
    if os.path.exists(output_filename):
        print(f"Skipping '{input_video}': Output '{output_filename}' already exists.")
        return

    print(f"Processing '{input_video}'...")

    # Run prediction
    # exist_ok=True prevents Ultralytics from creating new folders like outlined_clips2, outlined_clips3
    results = model.predict(
        source=input_video,
        classes=detect_classes,
        save=True, 
        stream=True,          # Prevent OOM by not accumulating results in RAM
        project=project,      # Base directory
        name=name,            # The specific output folder name
        exist_ok=True
    )

    # We MUST iterate over the generator when stream=True, otherwise it won't run.
    for _ in results:
        pass


def main():
    # Set up the arguments the script will accept
    parser = argparse.ArgumentParser(description="Draw AI outlines on a video for humans and cars.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-i', '--input', help="Path to a single input video file.")
    group.add_argument('-d', '--directory', help="Path to a directory of video files to process.")
    parser.add_argument('-o', '--output', default='outlined_clips', help="Directory to save the output video(s).")
    parser.add_argument('--classes', nargs='+', default=['0', '2'], help="YOLOv8 class IDs to outline, or 'all'")
    
    # Parse the arguments from the command line
    args = parser.parse_args()
    output_dir = args.output
    
    # Handle 'all' and 'known' keywords
    if 'all' in [c.lower() for c in args.classes]:
        detect_classes = None
    elif 'known' in [c.lower() for c in args.classes]:
        detect_classes = [0, 1, 2, 3, 5, 7, 15, 16, 17]
    else:
        detect_classes = [int(c) for c in args.classes]

    # Build list of video files to process
    if args.directory:
        if not os.path.isdir(args.directory):
            print(f"Error: Directory '{args.directory}' does not exist.")
            return
        video_files = sorted([
            os.path.join(args.directory, f)
            for f in os.listdir(args.directory)
            if f.endswith('.mp4')
        ])
        if not video_files:
            print(f"No .mp4 files found in '{args.directory}'.")
            return
        print(f"Found {len(video_files)} clips to process.")
    else:
        if not os.path.exists(args.input):
            print(f"Error: The file '{args.input}' does not exist.")
            return
        video_files = [args.input]

    # Load the heavy AI model once for all files
    print("Loading segmentation model...")
    model = YOLO('yolov8n-seg.pt')
    print(f"Outlining classes: {'all' if detect_classes is None else detect_classes}")

    for video_path in video_files:
        process_video(model, video_path, output_dir, detect_classes)

    print(f"\nDone! Results saved in '{output_dir}'.")

if __name__ == "__main__":
    main()
