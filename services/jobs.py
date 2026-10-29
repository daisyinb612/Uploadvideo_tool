"""In-memory upload metadata and single-job orchestration. No persistent job store."""
import os
import tempfile
import threading
import uuid
from pathlib import Path

from config import SERVER_DIR
from .media import build_name, capture_time, naming_time, probe
from .processing import render


class BusyError(ValueError):
    pass


class JobManager:
    def __init__(self, paths):
        self.paths = paths
        paths.prepare()
        self.jobs = {}
        self.uploads = {}
        self.lock = threading.Lock()

    def register(self, token, path, filename, kind):
        info = None
        if kind == "video":
            info = probe(path)
            info["original_filename"] = filename
            try:
                dt, source = capture_time(info)
                # Expose the selected clock without changing raw metadata semantics.
                info["capture_time"] = dt.isoformat()
                info["capture_source"] = source
            except ValueError:
                pass
        self.uploads[token] = {"path": path, "kind": kind, "info": info}
        if kind == "motion":
            return {"token": token, "time_column": "sample_time_iso8601"}
        return {"token": token, "info": info}

    def upload(self, token, kind):
        record = self.uploads.get(token)
        if not record or record["kind"] != kind or not record["path"].is_file():
            raise ValueError("上传文件不存在或已失效，请重新选择")
        return record

    def available_name(self, base):
        name = base
        number = 0
        while any((self.paths.outputs / (name + suffix)).exists()
                  for suffix in (".mp4", "_motion.csv", ".metadata.json")) or any(
                      job.get("reserved_name") == name and job["status"] == "running"
                      for job in self.jobs.values()):
            number += 1
            name = f"{base}（{number}）"
        return name

    def preview(self, payload):
        infos = [self.upload(payload.get(key), "video")["info"] for key in ("first", "third")]
        name = self.available_name(build_name(infos, payload.get("role"), payload.get("content")))
        return {
            "time": naming_time(infos), "name": name,
            "path": str(SERVER_DIR / (name + ".mp4")),
            "motion_path": str(SERVER_DIR / (name + "_motion.csv")),
        }

    def create(self, payload):
        records = [self.upload(payload.get(key), "video") for key in ("first", "third")]
        motion = self.upload(payload["motion"], "motion") if payload.get("motion") else None
        infos = [record["info"] for record in records]
        base = build_name(infos, payload.get("role"), payload.get("content"))
        if payload.get("align") not in ("timestamp", "already"):
            raise ValueError("请选择有效的对齐方式")
        if payload.get("sync_server") and not payload.get("server_password"):
            raise ValueError("请填写服务器密码")
        if not self.lock.acquire(blocking=False):
            raise BusyError("已有视频正在处理，请完成后重试")
        try:
            name = self.available_name(base)
            jid = uuid.uuid4().hex
            self.jobs[jid] = {"status": "running", "stage": "准备处理", "progress": 0,
                              "reserved_name": name}
            # Freeze selected files/settings for this job. Password is never stored in job state.
            settings = {"name": name, "align": payload["align"],
                        "sync_server": bool(payload.get("sync_server")),
                        "server_password": payload.get("server_password", "")}
            threading.Thread(target=self.run, args=(jid, records, motion, settings), daemon=True).start()
            return {"id": jid}
        except Exception:
            self.lock.release()
            raise

    def run(self, jid, records, motion, settings):
        job = self.jobs[jid]

        def report(stage, progress, details=None):
            job.update(stage=stage, progress=progress)
            if details is not None:
                job["details"] = details

        try:
            # All exports are prepared together; failure cannot leave half a published set.
            with tempfile.TemporaryDirectory(prefix=".processing-", dir=self.paths.outputs) as work:
                artifacts, motion_info = render(
                    [record["path"] for record in records],
                    [record["info"] for record in records],
                    motion["path"] if motion else None,
                    Path(work), settings["name"], settings["align"], report,
                )
                published = {}
                try:
                    for kind, path in artifacts.items():
                        target = self.paths.outputs / path.name
                        os.link(path, target)
                        published[kind] = target
                except Exception:
                    for target in published.values():
                        target.unlink(missing_ok=True)
                    raise
            video = published["video"]
            job.update(url="/outputs/" + jid, output=str(video), path=str(video),
                       filename=video.name, metadata_path=str(published["metadata"]),
                       metadata_url="/metadata/" + jid)
            if "motion" in published:
                job.update(motion_url="/motion/" + jid, motion_path=str(published["motion"]),
                           motion_filename=published["motion"].name, motion_info=motion_info)
            if settings["sync_server"]:
                report("同步到服务器", 99)
                try:
                    from .storage import sync_exports
                    job["server_paths"] = sync_exports(list(published.values()), settings["server_password"])
                except Exception as exc:
                    job["sync_error"] = str(exc)
            job.update(status="done", progress=100,
                       stage="本地已完成，服务器同步失败" if job.get("sync_error") else "已完成")
        except Exception as exc:
            job.update(status="error", stage="处理失败", error=str(exc))
        finally:
            settings.pop("server_password", None)
            self.lock.release()
