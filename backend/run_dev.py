"""
Development server startup script for Windows network drives.
This script works around multiprocessing issues on network drives.
"""
import sys
import os
import multiprocessing

# Force multiprocessing to use 'spawn' method explicitly for Windows
if sys.platform == 'win32':
    multiprocessing.set_start_method('spawn', force=True)

if __name__ == "__main__":
    import uvicorn
    
    # Run uvicorn with settings optimized for network drives
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        reload_delay=0.5,  # Add slight delay to avoid rapid reloads
        log_level="info"
    )

