"""Check real HTTPS video content after remote storage succeeds."""
from urllib.request import Request, urlopen


def verify_video(url, expected_size=None):
    with urlopen(Request(url, headers={'Range': 'bytes=0-31'}), timeout=20) as response:
        data = response.read(32)
        content_type = response.headers.get('Content-Type', '')
        if response.status not in (200, 206) or 'video/' not in content_type or b'ftyp' not in data:
            raise ValueError('链接未返回有效 MP4 视频')
        size = response.headers.get('Content-Range', '').rsplit('/', 1)[-1]
        if response.status == 200:
            size = response.headers.get('Content-Length', '')
        if expected_size is not None and (not size.isdigit() or int(size) != expected_size):
            raise ValueError('公网视频大小与本次导出不一致')
    return {'url': url, 'accessible': True}


if __name__ == '__main__':
    import sys
    try:
        print(verify_video(sys.argv[1]))
    except Exception as exc:
        print('访问校验失败：', exc)
        sys.exit(1)
