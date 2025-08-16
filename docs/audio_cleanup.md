# Audio Folder Auto-Cleanup

## Overview

This feature automatically deletes the oldest audio files with the lowest usage count when the audio folder size exceeds a specified limit. This helps manage disk space while preserving frequently used files.

## How It Works

1. **Monitoring**: The system monitors the size of the `audio/` folder where downloaded MP3 files are stored.

2. **Size Check**: When a new file is downloaded, the system checks if the total folder size exceeds the configured limit.

3. **File Analysis**: If the limit is exceeded, the system:
   - Retrieves all MP3 files in the audio folder
   - Gets usage count information for each file from the database
   - Sorts files by usage count (ascending) and then by modification time (ascending)

4. **Deletion Strategy**: The system deletes files in this order:
   - First, files with the lowest usage count
   - Among files with the same usage count, the oldest files (by modification time) are deleted first

5. **Target Size**: Deletion continues until the folder size is below the configured limit.

## Configuration

The feature is configured through environment variables:

- `AUDIO_FOLDER_SIZE_LIMIT`: Maximum size of the audio folder in MB (default: 1000 MB)

## Implementation Details

### Key Functions

- `get_folder_size()`: Calculates the total size of the audio folder
- `get_audio_files_info()`: Retrieves information about all MP3 files in the folder
- `get_files_usage_count()`: Gets usage count for each file from the database
- `delete_oldest_lowest_usage_files()`: Deletes files based on the prioritization strategy
- `auto_delete_audio_files()`: Main function that orchestrates the cleanup process
- `cleanup_audio_folder()`: Wrapper function that uses configuration values

### Integration Points

The cleanup function is automatically called after each successful file download in:
- `tl_handlers.py` (Telethon implementation)
- `aiogram_handlers.py` (Aiogram implementation)

## Usage Count Tracking

File usage counts are tracked in the database through the `add_use()` function, which is called each time a file is downloaded or sent to a user.

## Testing

A test script (`test_audio_manager_simple.py`) is provided to verify the functionality without requiring a database connection.
