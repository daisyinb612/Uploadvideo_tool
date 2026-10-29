"""Local paths and the existing optional SSH destination."""
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
SERVER_DIR = Path("/mnt/skill/mess")
SERVER_HOST = "maxuejiao@172.23.40.162"
SERVER_HOME = "/home/maxuejiao"
SERVER_UID = 1004
SERVER_GID = 1004


@dataclass(frozen=True)
class Paths:
    uploads: Path = ROOT / "uploads"
    outputs: Path = ROOT / "outputs"

    def prepare(self):
        self.uploads.mkdir(parents=True, exist_ok=True)
        self.outputs.mkdir(parents=True, exist_ok=True)
