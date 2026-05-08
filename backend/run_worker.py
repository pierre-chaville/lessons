"""Entrypoint to run the task worker as a standalone process."""
import sys
import os

# Add the backend directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    print("Starting standalone task worker process...")
    print("Press Ctrl+C to stop the worker.")
    from worker import main

    main()
