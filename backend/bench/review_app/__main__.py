"""python -m bench.review_app [--port 8765] [--no-browser]"""

from __future__ import annotations

import argparse
import threading
import webbrowser

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m bench.review_app", description="Browse the bench results.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser")
    parser.add_argument("--reload", action="store_true", help="reload the server when the code changes")
    args = parser.parse_args()

    url = f"http://{args.host}:{args.port}/"
    print(f"Bench review app: {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        threading.Timer(1.5, webbrowser.open, (url,)).start()
    uvicorn.run("bench.review_app.api:app", host=args.host, port=args.port, reload=args.reload,
                reload_dirs=["bench"] if args.reload else None, log_level="warning")


if __name__ == "__main__":
    main()
