"""Local paths and the existing optional SSH destination."""
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
SERVER_DIR = Path("/mnt/skill/mess")
SERVER_PUBLIC_BASE = "https://innojudge.ecnu.edu.cn/skill/public/18006/"
SERVER_HOST = "maxuejiao@172.23.40.162"
SERVER_HOME = "/home/maxuejiao"
SERVER_UID = 1004
SERVER_GID = 1004


def server_password():
    """Read a backend-only secret; never send it through the web API."""
    value = os.environ.get('VIEWPAIR_SERVER_PASSWORD')
    if value:
        return value
    local = ROOT / '.env.local'
    if local.is_file():
        for line in local.read_text().splitlines():
            key, separator, value = line.partition('=')
            if separator and key.strip() == 'VIEWPAIR_SERVER_PASSWORD':
                return value.strip()
    return ''


@dataclass(frozen=True)
class Paths:
    uploads: Path
    outputs: Path

    def prepare(self):
        self.uploads.mkdir(parents=True, exist_ok=True)
        self.outputs.mkdir(parents=True, exist_ok=True)
