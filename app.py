#!/usr/bin/env python3
"""Start the local ViewPair tool."""
import argparse
import shutil
from pathlib import Path

from config import Paths
from services.jobs import JobManager
from web import Server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--output-dir", type=Path, default=Paths().outputs)
    args = parser.parse_args()
    for binary in ("ffmpeg", "ffprobe"):
        if not shutil.which(binary):
            parser.error(f"请先安装 {binary}")
    paths = Paths(outputs=args.output_dir.resolve())
    manager = JobManager(paths)
    server = Server(("127.0.0.1", args.port), manager)
    print(f"Local: http://127.0.0.1:{args.port}  Output: {paths.outputs}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
