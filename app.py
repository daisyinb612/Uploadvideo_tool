#!/usr/bin/env python3
"""Start the local ViewPair tool."""
import argparse
import shutil
import tempfile
from pathlib import Path

from config import Paths, SERVER_DIR
from services.jobs import JobManager
from web import Server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    for binary in ("ffmpeg", "ffprobe"):
        if not shutil.which(binary):
            parser.error(f"请先安装 {binary}")
    with tempfile.TemporaryDirectory(prefix="viewpair-session-") as temporary:
        root = Path(temporary)
        paths = Paths(uploads=root / "incoming", outputs=root / "exports")
        manager = JobManager(paths)
        server = Server(("127.0.0.1", args.port), manager)
        print(f"Local: http://127.0.0.1:{args.port}  Server destination: {SERVER_DIR}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


if __name__ == "__main__":
    main()
