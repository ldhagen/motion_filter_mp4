#!/usr/bin/env python3
"""
This module is designed to walk a directory tree starting at the passed 
location and identify specifically formatted filenames which contain DTG.
These filenames are tested for specific length, prefix string, and suffix string
and then added to a dictionary by converted DTG. The result is persisted as a
pickle file with the name provided by the second argument passed.

Additional functions include copying the files from the dictionary sequentially
using str.zfill padding to ensure they stay sortable in their chronological
order.
"""

import os
import sys
import pickle
from datetime import datetime as dt
import shutil
import argparse

# Constants
DEFAULT_START = '.'
FILENAME_LENGTH_CONST = 29
FILENAME_PREFIX_CONST = 'ldh'
FILENAME_SUFFIX_CONST = '.jpg'
FILENAME_DTG_FORMAT_CONST = '%a_%d_%b_%y_%H_%M_%S' 

def walk_id(start_dir=DEFAULT_START, out_pickle_name=None):
    """
    Walks directory tree looking for constants above, confirms, 
    converts to DTG, populates dict, and persists as pickle file.
    """
    if out_pickle_name is None:
        dtg = dt.now().strftime('%Y%m%d_%H%M%S')
        out_pickle_name = f'./DTGscan_{dtg}.pkl'

    found_dict = {}
    
    try:
        start_dev = os.stat(start_dir).st_dev
    except OSError as e:
        print(f"Error accessing start directory {start_dir}: {e}")
        return

    print(f"Starting scan in: {os.path.abspath(start_dir)}")
    dir_count = 0
    file_count = 0
    
    for root, dirs, files in os.walk(start_dir):
        dir_count += 1
        # Stay on the same filesystem to avoid mounted drives
        def is_same_dev(d):
            try:
                return os.stat(os.path.join(root, d)).st_dev == start_dev
            except OSError:
                return False
        
        dirs[:] = [d for d in dirs if is_same_dev(d)]

        for file in files:
            file_count += 1
            if file.endswith(FILENAME_SUFFIX_CONST):
                if len(file) == FILENAME_LENGTH_CONST:
                    if file.startswith(FILENAME_PREFIX_CONST):
                        try:
                            # Extract DTG part and parse it
                            dtg_str = file[len(FILENAME_PREFIX_CONST):-len(FILENAME_SUFFIX_CONST)]
                            dvalue = dt.strptime(dtg_str, FILENAME_DTG_FORMAT_CONST)
                            found_dict[dvalue] = os.path.join(root, file)
                        except ValueError:
                            # Skip files that don't match the DTG format
                            continue
        
        if dir_count % 10 == 0:
            print(f"Scanned {dir_count} directories, {file_count} files. Matches found: {len(found_dict)}", end='\r')

    print(f"\nScan complete. Found {len(found_dict)} matches in {file_count} files across {dir_count} directories.")
    
    with open(out_pickle_name, 'wb') as ofile:
        pickle.dump(found_dict, ofile)
    print(f"Results saved to {out_pickle_name}")

def copy_files(pkl_dict_path, target_dir, spacing=3600):
    """
    Opens the passed pickled dictionary and copies the listed
    files in sequence spaced as passed.
    """
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)

    with open(pkl_dict_path, 'rb') as ifile:
        passed_dict = pickle.load(ifile)

    if not passed_dict:
        print("No files found in the dictionary.")
        return

    sorted_keys = sorted(passed_dict.keys())
    current_time = sorted_keys[0]
    seq_count = 0

    for dt_key in sorted_keys:
        if (dt_key - current_time).total_seconds() >= spacing or seq_count == 0:
            print(f"Processing: {dt_key}")
            prefix = str(seq_count).zfill(8)
            source_path = passed_dict[dt_key]
            filename = os.path.basename(source_path)
            out_target = os.path.join(target_dir, f"{prefix}_{filename}")
            
            print(f"Copying to: {out_target}")
            shutil.copy2(source_path, out_target)
            
            current_time = dt_key 
            seq_count += 1

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Walk directory tree and identify DTG formatted filenames.")
    parser.add_argument('start_dir', nargs='?', default=DEFAULT_START, 
                        help=f'The root directory to start the search (default: {DEFAULT_START})')
    parser.add_argument('output_pickle', nargs='?', default=None, 
                        help='The name of the output pickle file (default: DTGscan_YYYYMMDD_HHMMSS.pkl)')
    args = parser.parse_args()
    
    walk_id(args.start_dir, args.output_pickle)
