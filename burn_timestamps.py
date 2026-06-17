import os
import subprocess
import sys

FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

def burn_timestamps(directory):
    if not os.path.exists(directory):
        print(f"Error: Directory {directory} not found.")
        return

    files = [f for f in os.listdir(directory) if f.endswith('.mp4') and not f.startswith('temp_')]
    print(f"Found {len(files)} files to process in {directory}")

    success_count = 0
    for idx, filename in enumerate(sorted(files)):
        # Expected format: YYYYMMDD_HHMMSS_DSME_xxxx[_class1_class2].mp4
        parts = os.path.splitext(filename)[0].split('_')
        
        # Check if the file matches our renamed format
        if len(parts) >= 4 and len(parts[0]) == 8 and len(parts[1]) == 6:
            date_str = parts[0]
            time_str = parts[1]
            
            # Extract classes if present (everything after DSME_xxxx)
            # parts[0]=YYYYMMDD, parts[1]=HHMMSS, parts[2]=DSME, parts[3]=xxxx, parts[4:]=classes
            classes = parts[4:]
            classes_text = f" [{', '.join(classes)}]" if classes else ""
            
            # Format to YYYY-MM-DD HH\:MM\:SS (FFmpeg drawtext requires escaping colons)
            formatted_text = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]} {time_str[:2]}\\:{time_str[2:4]}\\:{time_str[4:]}{classes_text}"
            
            input_path = os.path.join(directory, filename)
            temp_path = os.path.join(directory, "temp_" + filename)
            
            print(f"[{idx+1}/{len(files)}] Burning '{formatted_text.replace(r'\\:', ':')}' into {filename}...")
            
            # FFmpeg command to burn text without altering audio, using hardware acceleration if possible
            cmd = [
                "ffmpeg", "-y", "-v", "error",
                "-i", input_path,
                "-vf", f"drawtext=fontfile={FONT}:text='{formatted_text}':fontcolor=white:fontsize=24:box=1:boxcolor=black@0.6:boxborderw=10:x=10:y=10",
                "-c:a", "copy",
                "-preset", "fast", # Speed up the encoding
                temp_path
            ]
            
            result = subprocess.run(cmd)
            if result.returncode == 0:
                os.replace(temp_path, input_path)
                success_count += 1
            else:
                print(f"Error processing {filename}")
        else:
            print(f"[{idx+1}/{len(files)}] Skipping {filename} (Does not match timestamp format)")

    print(f"\nSuccessfully burnt timestamps into {success_count} files.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        target_dir = sys.argv[1]
    else:
        # Default to the current batch if no argument provided
        target_dir = "scan_results_front_window_2025_02_16_00_00__2025_02_22_23_59/02_verified_events"
        
    burn_timestamps(target_dir)
