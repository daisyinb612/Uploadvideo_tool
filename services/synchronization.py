"""Cross-check device clocks against multiple audio windows, without extra dependencies."""
import array
import math
import statistics
import subprocess
import sys

from .media import alignment

RATE = 20


def envelope(path):
    result = subprocess.run([
        'ffmpeg', '-v', 'error', '-nostdin', '-i', str(path), '-vn',
        '-ac', '1', '-ar', '8000', '-af', 'highpass=f=150,lowpass=f=3000',
        '-f', 's16le', 'pipe:1',
    ], capture_output=True, check=True)
    pcm = array.array('h')
    pcm.frombytes(result.stdout)
    if sys.byteorder != 'little':
        pcm.byteswap()
    return [math.log1p(math.sqrt(sum(x*x for x in pcm[i:i+400])/400)/32.768)
            for i in range(0, len(pcm)-399, 400)]


def match(query, signal, positions):
    n = len(query)
    mean = sum(query)/n
    centered = [x-mean for x in query]
    energy = sum(x*x for x in centered)
    if energy < .001:
        raise ValueError('音频变化不足以校准')
    sums, squares = [0.0], [0.0]
    for x in signal:
        sums.append(sums[-1]+x)
        squares.append(squares[-1]+x*x)
    scores = []
    for start in positions:
        if start < 0 or start+n > len(signal):
            continue
        variance = squares[start+n]-squares[start]-(sums[start+n]-sums[start])**2/n
        if variance <= .001:
            continue
        dot = sum(x*signal[start+i] for i, x in enumerate(centered))
        scores.append((dot/math.sqrt(energy*variance), start))
    if not scores:
        raise ValueError('没有可匹配的音频片段')
    return sorted(scores, reverse=True)


def audio_alignment(paths, infos):
    signals = [envelope(path) for path in paths]
    first, third = signals
    coarse = [[sum(s[i:i+10])/10 for i in range(0, len(s)-9, 10)] for s in signals]
    window = min(45*RATE, len(first)//4, len(third)//4)
    window = window//10*10
    if window < 8*RATE:
        raise ValueError('视频太短，无法进行多段音频校准')
    offsets = sorted(set(int((len(first)-window)*fraction)//10*10 for fraction in (.1, .45, .8)))
    matches = []
    for offset in offsets:
        query = first[offset:offset+window]
        coarse_scores = match(coarse[0][offset//10:(offset+window)//10], coarse[1],
                              range(len(coarse[1])-window//10+1))
        peaks = []
        for score, index in coarse_scores:
            if all(abs(index-other) > 4 for other in peaks):
                peaks.append(index)
            if len(peaks) == 5:
                break
        candidates = set(i for peak in peaks for i in range(peak*10-20, peak*10+21))
        scores = match(query, third, sorted(candidates))
        best, position = scores[0]
        alternative = max((score for score, index in scores if abs(index-position) > RATE), default=-1)
        if best < .55 or best-alternative < .08:
            raise ValueError('音频匹配不够明确，未自动采用偏移')
        # A sample at first[offset] occurs at third[position].
        matches.append({'first_seconds': offset/RATE, 'third_seconds': position/RATE,
                        'offset_seconds': (position-offset)/RATE, 'score': round(best, 4)})
    offsets = [m['offset_seconds'] for m in matches]
    if len(matches) < 3 or max(offsets)-min(offsets) > .15:
        raise ValueError('各段音频偏移不一致，可能存在剪辑或时钟漂移')
    delta = -statistics.median(offsets)
    starts = [max(0.0, delta), max(0.0, -delta)]
    duration = min(info['duration']-start for info, start in zip(infos, starts))
    if duration <= 0:
        raise ValueError('音频校准后没有共同视频范围')
    return starts, duration, {'method': 'audio', 'windows': matches,
                              'accuracy_note': '三段音频校准，50毫秒采样分辨率；未校正时钟漂移'}


def resolve_alignment(paths, infos, mode):
    if mode == 'already':
        starts, duration = alignment(infos, {'align': mode})
        return starts, duration, {'method': 'already', 'accuracy_note': '用户选择已对齐素材'}
    clock = None
    clock_error = None
    try:
        clock = alignment(infos, {'align': mode})
    except ValueError as exc:
        clock_error = str(exc)
    audio_error = '两路视频需要都有音轨'
    if all(info['audio'] for info in infos):
        try:
            starts, duration, detail = audio_alignment(paths, infos)
            detail['timestamp_starts'] = clock[0] if clock else None
            return starts, duration, detail
        except (ValueError, subprocess.CalledProcessError) as exc:
            audio_error = str(exc)
    if clock is None:
        raise ValueError('无法自动对齐：' + (clock_error or '') + '；' + audio_error)
    starts, duration = clock
    # A clock consuming most of a source often represents recording completion.
    if any(start > info['duration']*.5 for start, info in zip(starts, infos)):
        raise ValueError('时间戳会裁掉超过一半的视频，疑似将完成时间当作起点；' + audio_error +
                         '。请使用原始素材或选择已对齐素材，已停止导出以避免错位')
    return starts, duration, {'method': 'timestamp', 'audio_warning': audio_error,
                              'accuracy_note': '仅按设备时间戳粗对齐，音频未校准'}
