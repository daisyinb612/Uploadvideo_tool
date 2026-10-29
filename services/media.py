"""Video metadata, capture clocks and crop detection."""
import json
import re
import subprocess
from datetime import datetime, timezone

def probe(path):
    p = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)], capture_output=True, text=True, check=True)
    data = json.loads(p.stdout)
    v = next((s for s in data['streams'] if s['codec_type'] == 'video'))
    tags = [data.get('format', {}).get('tags', {})] + [s.get('tags', {}) for s in data['streams']]
    created = next((t.get('com.apple.quicktime.creationdate') or t.get('creation_time') for t in tags if t.get('com.apple.quicktime.creationdate') or t.get('creation_time')), None)
    rotation = next((abs(float(x.get('rotation', 0))) for x in v.get('side_data_list', []) if x.get('side_data_type') == 'Display Matrix'), 0)
    (w, h) = (v['width'], v['height'])
    if round(rotation) % 180 == 90:
        (w, h) = (h, w)
    format_tags = data.get('format', {}).get('tags', {})
    ambiguous = bool(format_tags.get('com.android.version') and (not format_tags.get('com.apple.quicktime.creationdate')))
    return {'creation_time': created, 'time_warning': 'Android / Rokid 的 creation_time 可能是文件完成时间，不能确认拍摄起点；请使用已对齐素材。' if ambiguous else None, 'width': w, 'height': h, 'duration': float(data['format']['duration']), 'audio': any((s['codec_type'] == 'audio' for s in data['streams'])), 'original_filename': path.name, 'metadata': data}

def capture_time(info):
    from zoneinfo import ZoneInfo
    name = info.get('original_filename', '')
    m = re.fullmatch('vid-(20\\d{6})-(\\d{6})-.+\\.(?:mp4|mov)', name, re.I)
    if m:
        try:
            dt = datetime.strptime(''.join(m.groups()), '%Y%m%d%H%M%S').replace(tzinfo=ZoneInfo('Asia/Shanghai'))
            return (dt, 'Rokid 原始文件名（北京时间，秒级）')
        except ValueError:
            pass
    if not info.get('time_warning') and info.get('creation_time'):
        try:
            dt = datetime.fromisoformat(info['creation_time'].replace('Z', '+00:00'))
            if dt.tzinfo is not None:
                return (dt, '拍摄元数据')
        except ValueError:
            pass
    raise ValueError('未找到可靠的拍摄起点：请保留 Rokid 原始 vid-日期-时间 文件名或 iPhone 拍摄元数据')

def naming_time(infos):
    from zoneinfo import ZoneInfo
    for idx in (1, 0):
        try:
            (dt, source) = capture_time(infos[idx])
            dt = dt.astimezone(ZoneInfo('Asia/Shanghai'))
            return {'value': dt.strftime('%Y%m%d_%H%M%S'), 'display': dt.strftime('%Y-%m-%d %H:%M:%S') + '（北京时间）', 'source': ('第三' if idx else '第一') + '视角：' + source}
        except ValueError:
            pass
    raise ValueError('视频没有可用拍摄日期时间，请保留原始文件名和拍摄信息')

def alignment(infos, payload):
    mode = payload.get('align', 'already')
    if mode == 'timestamp':
        times = [capture_time(i)[0].timestamp() for i in infos]
        delta = times[1] - times[0]
    elif mode == 'already':
        delta = 0
    else:
        raise ValueError('未知对齐方式')
    starts = [max(0, delta), max(0, -delta)]
    duration = min((i['duration'] - t for (i, t) in zip(infos, starts)))
    if duration <= 0:
        raise ValueError('两个视频没有共同时间范围，请检查拍摄时间或偏移')
    return (starts, duration)

def absolute_start(infos, starts):
    for idx in (1, 0):
        try:
            return capture_time(infos[idx])[0].timestamp() + starts[idx]
        except ValueError:
            pass
    raise ValueError('Motion 裁切需要可靠的绝对拍摄起点')

def build_name(infos, role, content):
    for (label, value) in [('角色', role), ('内容', content)]:
        if not isinstance(value, str) or not re.fullmatch('[\\w-]{1,40}', value):
            raise ValueError(label + '仅支持文字、数字、下划线和短横线（最多40字）')
    return naming_time(infos)['value'] + '_' + role + '_' + content + '_firstthird'

def detect(path, info):
    boxes = []
    for f in (0.1, 0.35, 0.65, 0.9):
        p = subprocess.run(['ffmpeg', '-hide_banner', '-ss', str(info['duration'] * f), '-i', str(path), '-t', '1.5', '-vf', 'cropdetect=limit=20:round=2:reset=0', '-an', '-f', 'null', '-'], capture_output=True, text=True, check=True)
        hits = re.findall('crop=(\\d+):(\\d+):(\\d+):(\\d+)', p.stderr)
        if hits:
            boxes.append(tuple(map(int, hits[-1])))
    if len(boxes) < 4:
        return (info['width'] // 2 * 2, info['height'] // 2 * 2, 0, 0)
    x = min((b[2] for b in boxes)) // 2 * 2
    y = min((b[3] for b in boxes)) // 2 * 2
    right = max((b[2] + b[0] for b in boxes))
    bottom = max((b[3] + b[1] for b in boxes))
    w = (right - x) // 2 * 2
    h = (bottom - y) // 2 * 2
    if w < info['width'] * 0.65 or h < info['height'] * 0.5:
        return (info['width'] // 2 * 2, info['height'] // 2 * 2, 0, 0)
    return (w, h, x, y)
