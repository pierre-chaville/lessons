"""Simple script to run the worker for testing purposes"""
import sys
import os

# Add the backend directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    print("=" * 60)
    print("Starting Task Worker (Test Mode)")
    print("=" * 60)
    print("Press Ctrl+C to stop the worker")
    print()
    
    from worker import main
    main()

