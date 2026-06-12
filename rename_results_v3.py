import os
from datetime import datetime, timedelta

# Configuration
LOG_FILE = "pipeline.log"
BASE_DIR = "scan_results_front_window_2025_02_16_00_00__2025_02_22_23_59/02_humans_cars"
BASE_START_TIME = datetime(2025, 2, 16, 0, 0, 0)

def rename_clips():
    if not os.path.exists(LOG_FILE):
        print(f"Error: Log file {LOG_FILE} not found.")
        return

    rename_map = {}

    print("Parsing log file...")
    with open(LOG_FILE, 'r') as f:
        content = f.read()
        
        # We need to handle the fact that the log file says:
        # scan_results_front_window.../01_motion_only/front_window...DSME_0001.mp4
        # BUT the files are now in:
        # scan_results_front_window.../02_humans_cars/front_window...DSME_0001.mp4
        
        import re
        # This matches the timestamp and the filename at the very end of the line
        pattern = re.compile(r'-ss (\d{2}:\d{2}:\d{2}\.\d{3}).*?(front_window_2025_02_16_00_00__2025_02_22_23_59\.DSME_(\d{4})\.mp4)')
        matches = pattern.findall(content)
        
        for offset_str, full_name, dsme_num in matches:
            h, m, s = offset_str.split(':')
            offset = timedelta(hours=int(h), minutes=int(m), seconds=float(s))
            actual_time = BASE_START_TIME + offset
            
            # Key = the full filename in 02_humans_cars
            # Value = the new timestamp-prefixed name
            new_name = actual_time.strftime("%Y%m%d_%H%M%S") + "_DSME_" + dsme_num + ".mp4"
            rename_map[full_name] = new_name

    print(f"Found {len(rename_map)} total mappings in log.")

    if not os.path.exists(BASE_DIR):
        print(f"Error: Directory {BASE_DIR} not found.")
        return

    files_in_dir = os.listdir(BASE_DIR)
    print(f"Directory contains {len(files_in_dir)} files.")
    
    success_count = 0
    for old_name in files_in_dir:
        if old_name in rename_map:
            new_name = rename_map[old_name]
            old_path = os.path.join(BASE_DIR, old_name)
            new_path = os.path.join(BASE_DIR, new_name)
            
            try:
                os.rename(old_path, new_path)
                success_count += 1
            except Exception as e:
                print(f"Failed to rename {old_name}: {e}")
        else:
            if "DSME" in old_name and success_count < 5:
                print(f"No mapping found for: {old_name}")

    print(f"Successfully renamed {success_count} files.")

if __name__ == "__main__":
    rename_clips()
