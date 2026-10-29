"""Local HTTP transport; media and task logic live in services/."""
import csv
import json
import mimetypes
import shutil
import tempfile
import uuid
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

from config import SERVER_DIR, STATIC_DIR
from services.jobs import BusyError


class Server(ThreadingHTTPServer):
    def __init__(self, address, manager):
        self.manager = manager
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    @property
    def manager(self):
        return self.server.manager

    def json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def allowed(self):
        origin = self.headers.get("Origin")
        return not origin or origin == "http://" + self.headers.get("Host", "")

    def do_PUT(self):
        if not self.allowed():
            return self.json({"error": "不允许跨站上传"}, 403)
        if self.path not in ("/api/upload", "/api/motion-upload"):
            return self.send_error(404)
        path = None
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                raise ValueError("请选择非空文件")
            kind = "motion" if self.path == "/api/motion-upload" else "video"
            token = uuid.uuid4().hex
            path = self.manager.paths.uploads / (token + (".csv" if kind == "motion" else ".mp4"))
            with path.open("xb") as output:
                while length:
                    chunk = self.rfile.read(min(1024 * 1024, length))
                    if not chunk:
                        raise ValueError("上传中断")
                    output.write(chunk)
                    length -= len(chunk)
            if kind == "motion":
                with path.open(encoding="utf-8-sig", newline="") as source:
                    reader = csv.DictReader(source)
                    if not reader.fieldnames or "sample_time_iso8601" not in reader.fieldnames:
                        raise ValueError("CSV 需要 sample_time_iso8601 时间列")
                    if not next(reader, None):
                        raise ValueError("CSV 没有数据")
            filename = Path(unquote(self.headers.get("X-Filename", "video.mp4"))).name
            return self.json(self.manager.register(token, path, filename, kind))
        except Exception as exc:
            if path:
                path.unlink(missing_ok=True)
            return self.json({"error": str(exc)}, 400)

    def do_POST(self):
        if not self.allowed():
            return self.json({"error": "不允许跨站请求"}, 403)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 10000:
                raise ValueError("请求大小无效")
            payload = json.loads(self.rfile.read(length))
            if self.path == "/api/naming":
                return self.json(self.manager.preview(payload))
            if self.path == "/api/jobs":
                return self.json(self.manager.create(payload))
            return self.send_error(404)
        except BusyError as exc:
            return self.json({"error": str(exc)}, 409)
        except Exception as exc:
            return self.json({"error": str(exc)}, 400)

    def serve_file(self, path, content_type=None, ranged=False):
        if not path.is_file():
            return self.send_error(404)
        size = path.stat().st_size
        start, end, status = 0, size - 1, 200
        if ranged and self.headers.get("Range"):
            import re
            match = re.fullmatch(r"bytes=(\d+)-(\d*)", self.headers["Range"])
            if not match:
                return self.send_error(416)
            start = int(match[1])
            end = min(end, int(match[2])) if match[2] else end
            if start > end:
                return self.send_error(416)
            status = 206
        self.send_response(status)
        self.send_header("Content-Type", content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(end - start + 1))
        if ranged:
            self.send_header("Accept-Ranges", "bytes")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        try:
            with path.open("rb") as source:
                source.seek(start)
                remaining = end - start + 1
                while remaining:
                    chunk = source.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def bundle(self, job):
        with tempfile.TemporaryFile() as archive:
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as bundle:
                for key in ("output", "motion_path", "metadata_path"):
                    if job.get(key):
                        path = Path(job[key])
                        bundle.write(path, arcname=path.name)
            size = archive.tell()
            archive.seek(0)
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Length", str(size))
            name = Path(job["filename"]).stem + ".zip"
            self.send_header("Content-Disposition", "attachment; filename=export.zip; filename*=UTF-8''" + quote(name))
            self.end_headers()
            try:
                shutil.copyfileobj(archive, self.wfile, length=1024 * 1024)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/config":
            return self.json({"output": str(SERVER_DIR), "local_output": str(self.manager.paths.outputs)})
        if path.startswith("/api/jobs/"):
            job = self.manager.jobs.get(path.rsplit("/", 1)[1])
            return self.json(job or {"error": "任务不存在"}, 200 if job else 404)
        if path == "/":
            return self.serve_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
        assets = {"/static/style.css": "style.css", "/static/app.js": "app.js",
                  "/static/upload-slot.mjs": "upload-slot.mjs"}
        if path in assets:
            return self.serve_file(STATIC_DIR / assets[path])
        routes = {"outputs": ("output", "video/mp4"), "motion": ("motion_path", "text/csv; charset=utf-8"),
                  "metadata": ("metadata_path", "application/json; charset=utf-8")}
        parts = path.strip("/").split("/")
        if len(parts) != 2:
            return self.send_error(404)
        route, jid = parts
        job = self.manager.jobs.get(jid, {})
        if job.get("status") != "done":
            return self.send_error(404)
        if route == "bundle":
            return self.bundle(job)
        if route not in routes or not job.get(routes[route][0]):
            return self.send_error(404)
        key, content_type = routes[route]
        return self.serve_file(Path(job[key]), content_type, ranged=route == "outputs")
