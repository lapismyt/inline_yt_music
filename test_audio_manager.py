#!/usr/bin/env python3
"""
Test script for the audio manager functionality.
This script tests the auto-deletion of oldest files with lowest usage count.
"""

import os
import sys
import time
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from audio_manager import cleanup_audio_folder, auto_delete_audio_files
from database import get_session, File
from sqlmodel import select


def create_test_files():
    """Create some test files in the audio folder for testing."""
    audio_folder = "audio"
    os.makedirs(audio_folder, exist_ok=True)
    
    # Create some test files
    test_files = [
        "test1.mp3",
        "test2.mp3",
        "test3.mp3"
    ]
    
    for filename in test_files:
        filepath = os.path.join(audio_folder, filename)
        # Create a small test file
        with open(filepath, "w") as f:
            f.write("test content")
        print(f"Created test file: {filepath}")


def create_test_database_entries():
    """Create some test entries in the database."""
    with get_session() as session:
        # Create test files with different usage counts
        test_files = [
            {"video_id": "test1", "uses_count": 1},
            {"video_id": "test2", "uses_count": 5},
            {"video_id": "test3", "uses_count": 2}
        ]
        
        for file_data in test_files:
            # Check if file already exists
            statement = select(File).where(File.video_id == file_data["video_id"])
            existing_file = session.exec(statement).first()
            
            if not existing_file:
                file = File(
                    video_id=file_data["video_id"],
                    uses_count=file_data["uses_count"],
                    downloaded=True
                )
                session.add(file)
        
        session.commit()
        print("Created test database entries")


def test_audio_manager():
    """Test the audio manager functionality."""
    print("Testing audio manager functionality...")
    
    # Create test files and database entries
    create_test_files()
    create_test_database_entries()
    
    # Test the cleanup function
    print("\nTesting cleanup_audio_folder()...")
    deleted_files = cleanup_audio_folder()
    print(f"Deleted files: {deleted_files}")
    
    # Test with a very small size limit to force deletion
    print("\nTesting auto_delete_audio_files() with small limit...")
    deleted_files = auto_delete_audio_files(max_size_mb=0.001)  # 1KB limit
    print(f"Deleted files: {deleted_files}")


if __name__ == "__main__":
    test_audio_manager()
