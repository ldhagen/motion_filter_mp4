import argparse
import os
from ultralytics import YOLO

def main():
    # Set up the arguments the script will accept
    parser = argparse.ArgumentParser(description="Draw AI outlines on a video for humans and cars.")
    parser.add_argument('-i', '--input', required=True, help="Path to the input video file.")
    parser.add_argument('-o', '--output', default='outlined_clips', help="Directory to save the output video.")
    parser.add_argument('--classes', nargs='+', default=['0', '2'], help="YOLOv8 class IDs to outline, or 'all'")
    
    # Parse the arguments from the command line
    args = parser.parse_args()
    input_video = args.input
    output_dir = args.output
    
    # Handle 'all' keyword
    if 'all' in [c.lower() for c in args.classes]:
        detect_classes = None
    else:
        detect_classes = [int(c) for c in args.classes]

    # Check if the input file actually exists before loading the heavy AI model
    if not os.path.exists(input_video):
        print(f"Error: The file '{input_video}' does not exist.")
        return

    print("Loading segmentation model...")
    model = YOLO('yolov8n-seg.pt')

    print(f"Scanning '{input_video}' and saving to '{output_dir}'...")
    print(f"Outlining classes: {'all' if detect_classes is None else detect_classes}")

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

    print(f"Done! Your video has been saved inside the '{output_dir}' folder.")

if __name__ == "__main__":
    main()
