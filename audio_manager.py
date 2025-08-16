import os
import shutil
from pathlib import Path
from loguru import logger
from database import get_session, File
from sqlmodel import select
from config import AUDIO_FOLDER_SIZE_LIMIT
import time


def get_folder_size(folder_path: str) -> int:
    """Get the total size of a folder in bytes."""
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(folder_path):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            if os.path.exists(filepath):
                total_size += os.path.getsize(filepath)
    return total_size


def get_audio_files_info(folder_path: str) -> list:
    """Get information about all audio files in the folder."""
    files_info = []
    for filename in os.listdir(folder_path):
        if filename.endswith('.mp3'):
            filepath = os.path.join(folder_path, filename)
            if os.path.exists(filepath):
                stat = os.stat(filepath)
                video_id = filename[:-4]  # Remove .mp3 extension
                files_info.append({
                    'filepath': filepath,
                    'filename': filename,
                    'video_id': video_id,
                    'size': stat.st_size,
                    'modified_time': stat.st_mtime
                })
    return files_info


def get_files_usage_count(files_info: list) -> dict:
    """Get usage count for each file from the database."""
    with get_session() as session:
        # Get all files from database
        statement = select(File)
        db_files = session.exec(statement).all()
        
        # Create a dictionary mapping video_id to uses_count
        usage_dict = {file.video_id: file.uses_count for file in db_files}
        
        # Add usage count to files_info
        for file_info in files_info:
            file_info['uses_count'] = usage_dict.get(file_info['video_id'], 0)
        
        return usage_dict


def delete_oldest_lowest_usage_files(folder_path: str, target_size: int):
    """Delete oldest files with lowest usage count until folder size is below target."""
    # Get current folder size
    current_size = get_folder_size(folder_path)
    
    # If already below target size, nothing to do
    if current_size <= target_size:
        return
    
    # Get information about all audio files
    files_info = get_audio_files_info(folder_path)
    
    # Get usage count for each file
    get_files_usage_count(files_info)
    
    # Sort files by usage count (ascending) and then by modification time (ascending)
    # This will prioritize deleting files with lowest usage count, and among those with the same usage count,
    # it will delete the oldest ones
    files_info.sort(key=lambda x: (x['uses_count'], x['modified_time']))
    
    # Delete files until we're below target size
    deleted_size = 0
    deleted_files = []
    
    for file_info in files_info:
        if current_size - deleted_size <= target_size:
            break
            
        try:
            os.remove(file_info['filepath'])
            deleted_size += file_info['size']
            deleted_files.append(file_info['filename'])
            logger.info(f"Deleted file: {file_info['filename']} (size: {file_info['size']} bytes, uses: {file_info['uses_count']})")
        except Exception as e:
            logger.error(f"Failed to delete file {file_info['filename']}: {str(e)}")
    
    logger.info(f"Deleted {len(deleted_files)} files, freed {deleted_size} bytes")
    return deleted_files


def auto_delete_audio_files(max_size_mb: int = 1000):
    """
    Automatically delete oldest files with lowest usage count when folder size exceeds limit.
    
    Args:
        max_size_mb: Maximum size of audio folder in MB (default: 1000 MB)
    """
    folder_path = "audio"
    
    # Check if folder exists
    if not os.path.exists(folder_path):
        logger.info("Audio folder does not exist")
        return
    
    # Convert max_size to bytes
    max_size_bytes = max_size_mb * 1024 * 1024
    
    # Get current folder size
    current_size = get_folder_size(folder_path)
    current_size_mb = current_size / (1024 * 1024)
    
    logger.info(f"Audio folder size: {current_size_mb:.2f} MB (limit: {max_size_mb} MB)")
    
    # If folder size exceeds limit, delete files
    if current_size > max_size_bytes:
        logger.info("Audio folder size exceeds limit, deleting oldest files with lowest usage count...")
        deleted_files = delete_oldest_lowest_usage_files(folder_path, max_size_bytes)
        new_size = get_folder_size(folder_path)
        new_size_mb = new_size / (1024 * 1024)
        logger.info(f"New audio folder size: {new_size_mb:.2f} MB")
        return deleted_files
    else:
        logger.info("Audio folder size is within limit")
        return []


# Function to be called periodically or when needed
def cleanup_audio_folder():
    """Main function to clean up the audio folder based on configuration."""
    try:
        # Use AUDIO_FOLDER_SIZE_LIMIT from config as max size in MB
        max_size_mb = AUDIO_FOLDER_SIZE_LIMIT
        deleted_files = auto_delete_audio_files(max_size_mb)
        return deleted_files
    except Exception as e:
        logger.error(f"Error during audio folder cleanup: {str(e)}")
        return []
