"""Shared pytest configuration — adds backend root to sys.path for all tests."""
import sys
from pathlib import Path

backend_root = str(Path(__file__).resolve().parent.parent)
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)
