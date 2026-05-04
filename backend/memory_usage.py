"""Helpers to inspect process memory usage in MB."""

from __future__ import annotations

import os
from typing import Optional


def get_rss_memory_mb() -> Optional[float]:
    """Return the current process RSS in MB when available."""
    # Linux containers (Render) expose this file and it reflects current RSS.
    status_path = "/proc/self/status"
    try:
        if os.path.exists(status_path):
            with open(status_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        # Example: "VmRSS:\t  123456 kB"
                        rss_kb = int(line.split()[1])
                        return rss_kb / 1024.0
    except Exception:
        pass

    # Optional fallback for environments without /proc.
    try:
        import psutil  # type: ignore

        return psutil.Process(os.getpid()).memory_info().rss / (1024.0 * 1024.0)
    except Exception:
        return None


def format_memory_mb(value: Optional[float]) -> str:
    """Format memory value for logs."""
    if value is None:
        return "n/a"
    return f"{value:.2f} MB"
