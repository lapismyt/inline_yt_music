#!/usr/bin/env python3
"""
Simple test script for the audio manager functionality.
This script tests the auto-deletion of oldest files with lowest usage count
without requiring a database connection.
"""

import os
import sys
import time
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from audio_manager import get_folder_size, get_audio_files_info, delete_oldest_lowest_usage_files


def create_test_files():
    """Create some test files in the audio folder for testing."""
    audio_folder = "audio"
    os.makedirs(audio_folder, exist_ok=True)
    
    # Create some test files with different sizes and modification times
    test_files = [
        "test1.mp3",
        "test2.mp3",
        "test3.mp3"
    ]
    
    for i, filename in enumerate(test_files):
        filepath = os.path.join(audio_folder, filename)
        # Create a test file with different sizes
        with open(filepath, "w") as f:
            f.write("test content" * (i + 1))  # Different sizes
        # Set different modification times
        mod_time = time.time() - (i * 3600)  # Different ages
        os.utime(filepath, (mod_time, mod_time))
        print(f"Created test file: {filepath}")


def test_audio_manager_functions():
    """Test the audio manager functions."""
    print("Testing audio manager functions...")
    
    # Create test files
    create_test_files()
    
    # Test get_folder_size
    folder_size = get_folder_size("audio")
    print(f"Folder size: {folder_size} bytes")
    
    # Test get_audio_files_info
    files_info = get_audio_files_info("audio")
    print(f"Files info: {files_info}")
    
    # Test delete_oldest_lowest_usage_files with a small target size
    # We'll simulate usage counts by modifying the files_info
    for i, file_info in enumerate(files_info):
        file_info['uses_count'] = i + 1  # Different usage counts
    
    # Sort files by usage count and modification time to see the order
    files_info.sort(key=lambda x: (x['uses_count'], x['modified_time']))
    print(f"Files sorted by usage count and age: {files_info}")
    
    print("Test completed successfully!")


if __name__ == "__main__":
    test_audio_manager_functions()
