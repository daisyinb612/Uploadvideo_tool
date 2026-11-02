"""Render aligned individual views, composite video and synchronized Motion data."""
import json
import subprocess
from datetime import datetime, timezone

from .media import absolute_start, capture_time, detect, probe, video_names
from .motion import trim_motion
from .synchronization import resolve_alignment


def render(paths, infos, motion_source, workdir, name, mode, report):
    """Write all artifacts inside an isolated workdir before publishing them."""
    report("对齐时间范围", 1)
    starts, duration, sync = resolve_alignment(paths, infos, mode)
    artifacts = {}
    motion_info = None
    if motion_source:
        motion_path = workdir / (name + "_motion.csv")
        motion_info = trim_motion(
            motion_source, motion_path, absolute_start(infos, starts), duration
        )
        artifacts["motion"] = motion_path

    report("检测黑边", 2)
    crops = [detect(path, info) for path, info in zip(paths, infos)]
    height = min(720, *(crop[1] for crop in crops)) // 2 * 2
    widths = [max(2, round(crop[0] / crop[1] * height / 2) * 2) for crop in crops]
    details = {
        "crops": crops,
        "size": f"{sum(widths)} × {height}",
        "duration": duration,
        "starts": starts,
        "alignment": mode,
        "synchronization": sync,
    }
    report("合成导出", 5, details)
    filters = []
    for index, (crop, width) in enumerate(zip(crops, widths)):
        w, h, x, y = crop
        filters.append(
            f"[{index}:v]crop={w}:{h}:{x}:{y},scale={width}:{height},"
            f"setsar=1,fps=30,setpts=PTS-STARTPTS,split=2[v{index}][solo{index}]"
        )
    filters.append("[v0][v1]hstack=inputs=2:shortest=1[v]")
    audio = next((i for i in (0, 1) if infos[i]["audio"]), None)
    metadata = {
        "schema_version": 1,
        "sources": [
            {"view": view, "filename": info["original_filename"], "probe": info["metadata"]}
            for view, info in zip(("first", "third"), infos)
        ],
        "processing": {
            "alignment_mode": mode,
            "start_offsets_seconds": starts,
            "duration_seconds": duration,
            "crop_rectangles": crops,
            "output_dimensions": [sum(widths), height],
            "fps": 30,
            "audio_source": audio,
            "time_sources": [
                "音频校准" if sync["method"] == "audio" else
                (capture_time(info)[1] if mode == "timestamp" else "已对齐素材")
                for info in infos
            ],
            "alignment_accuracy_note": sync["accuracy_note"],
            "synchronization": sync,
            "note": "Video and selected audio are re-encoded; auxiliary tracks are not copied.",
        },
    }
    if motion_info:
        metadata["motion"] = motion_info

    output = workdir / (name + ".mp4")
    command = [
        "ffmpeg", "-v", "error", "-nostdin",
        "-ss", str(starts[0]), "-i", str(paths[0]),
        "-ss", str(starts[1]), "-i", str(paths[1]),
        "-filter_complex", ";".join(filters), "-map", "[v]",
    ]
    if audio is not None:
        command += [
            "-map", f"{audio}:a:0", "-af", "asetpts=PTS-STARTPTS",
            "-c:a", "aac", "-b:a", "160k",
        ]
    source_tags = [
        {"view": view, "filename": info["original_filename"],
         "tags": info["metadata"].get("format", {}).get("tags", {})}
        for view, info in zip(("first", "third"), infos)
    ]
    command += [
        "-map_metadata", "-1",
        "-metadata", "viewpair_sources=" + json.dumps(source_tags, ensure_ascii=False),
        "-metadata", "viewpair_processing=" + json.dumps(metadata["processing"]),
    ]
    common = None
    if mode == "timestamp":
        try:
            common = datetime.fromtimestamp(absolute_start(infos, starts), timezone.utc).isoformat()
        except ValueError:
            pass  # Audio can align files without inventing an absolute clock.
    if common:
        command += ["-metadata", "creation_time=" + common,
                    "-metadata", "com.apple.quicktime.creationdate=" + common]
    for view, info in zip(("first", "third"), infos):
        if info.get("creation_time"):
            command += ["-metadata", f"viewpair_{view}_original_creation_time=" + info["creation_time"]]
    command += [
        "-t", str(duration), "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart+use_metadata_tags",
        "-progress", "pipe:1", "-n", str(output),
    ]
    # Reuse the same decoded/cropped frames for all three outputs.
    for index, view in enumerate(("first", "third")):
        individual = workdir / video_names(name)[view]
        command += ["-map", f"[solo{index}]"]
        if infos[index]["audio"]:
            command += ["-map", f"{index}:a:0", "-af", "asetpts=PTS-STARTPTS",
                        "-c:a", "aac", "-b:a", "160k"]
        command += [
            "-map_metadata", "-1",
            "-metadata", "viewpair_source=" + json.dumps(metadata["sources"][index], ensure_ascii=False),
            "-metadata", "viewpair_processing=" + json.dumps(metadata["processing"]),
        ]
        if common:
            command += ["-metadata", "creation_time=" + common,
                        "-metadata", "com.apple.quicktime.creationdate=" + common]
        command += ["-t", str(duration), "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart+use_metadata_tags", str(individual)]
        artifacts[view] = individual
    log = workdir / "ffmpeg.log"
    with log.open("w") as errors:
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors, text=True) as process:
            for line in process.stdout:
                if line.startswith("out_time_us="):
                    try:
                        progress = min(98, 5 + int(float(line.split("=")[1]) / 1e6 / duration * 93))
                        report("合成导出", progress)
                    except ValueError:
                        pass
            if process.wait():
                raise RuntimeError(log.read_text()[-1500:])
    for video in (output, artifacts["first"], artifacts["third"]):
        probe(video)
    metadata_path = workdir / (name + ".metadata.json")
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2))
    artifacts.update(video=output, metadata=metadata_path)
    return artifacts, motion_info
