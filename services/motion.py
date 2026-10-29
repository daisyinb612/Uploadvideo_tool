"""Trim sensor samples against the video absolute timeline."""
import csv
from datetime import datetime, timezone

def trim_motion(source, destination, start, duration):
    count = 0
    previous = None
    first = None
    last = None
    try:
        with source.open(encoding='utf-8-sig', newline='') as inp, destination.open('x', encoding='utf-8-sig', newline='') as out:
            reader = csv.DictReader(inp)
            if not reader.fieldnames or 'sample_time_iso8601' not in reader.fieldnames:
                raise ValueError('Motion CSV 需要 sample_time_iso8601 绝对时间列')
            if 'video_time_s' in reader.fieldnames:
                raise ValueError('Motion CSV 已有 video_time_s 列，请上传原始数据')
            writer = csv.DictWriter(out, fieldnames=reader.fieldnames + ['video_time_s'])
            writer.writeheader()
            for (line, row) in enumerate(reader, 2):
                try:
                    dt = datetime.fromisoformat(row['sample_time_iso8601'].replace('Z', '+00:00'))
                    if dt.tzinfo is None:
                        raise ValueError('无时区')
                    timestamp = dt.timestamp()
                except Exception:
                    raise ValueError(f'Motion 第 {line} 行时间无效或缺少时区')
                if previous is not None and timestamp < previous:
                    raise ValueError('Motion 时间列必须递增，不能混入多段会话')
                previous = timestamp
                first = timestamp if first is None else first
                last = timestamp
                if start <= timestamp < start + duration:
                    row['video_time_s'] = f'{timestamp - start:.6f}'
                    writer.writerow(row)
                    count += 1
        if not count:
            raise ValueError('Motion 与视频时间范围不重叠')
        return {'rows': count, 'start_iso': datetime.fromtimestamp(start, timezone.utc).isoformat(), 'end_iso_exclusive': datetime.fromtimestamp(start + duration, timezone.utc).isoformat(), 'coverage_complete': first <= start and last >= start + duration - 0.1}
    except Exception:
        destination.unlink(missing_ok=True)
        raise
