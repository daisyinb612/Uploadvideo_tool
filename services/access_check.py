"""Check real HTTPS video content after remote storage succeeds."""
from urllib.request import Request, urlopen, build_opener, ProxyHandler, HTTPSHandler
from urllib.parse import urlparse
from urllib.error import URLError, HTTPError
import time
import socket
from http.client import HTTPSConnection


def ipv4_connection(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None):
    last_error = None
    for family, kind, protocol, _, target in socket.getaddrinfo(address[0], address[1], socket.AF_INET, socket.SOCK_STREAM):
        connection = socket.socket(family, kind, protocol)
        try:
            if timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:
                connection.settimeout(timeout)
            if source_address:
                connection.bind(source_address)
            connection.connect(target)
            return connection
        except OSError as exc:
            connection.close()
            last_error = exc
    raise last_error or OSError('服务器没有可用的 IPv4 地址')


class PlatformHTTPSConnection(HTTPSConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = ipv4_connection


class PlatformHTTPSHandler(HTTPSHandler):
    def https_open(self, request):
        return self.do_open(PlatformHTTPSConnection, request, context=self._context)


def open_public(request, timeout=25):
    """Use the verified direct VPN route for our server, retaining TLS verification."""
    target = request.full_url if isinstance(request, Request) else request
    direct = urlparse(target).hostname == 'innojudge.ecnu.edu.cn'
    opener = build_opener(ProxyHandler({}), PlatformHTTPSHandler()).open if direct else urlopen
    for attempt in range(2):
        try:
            return opener(request, timeout=timeout)
        except HTTPError:
            raise  # A missing file is not a transient handshake failure.
        except (URLError, TimeoutError, OSError) as exc:
            if attempt:
                raise ValueError('服务器 HTTPS 连接失败（已直连重试），请检查 VPN 路由；' + str(exc)) from exc
            time.sleep(.5)


def verify_video(url, expected_size=None):
    with open_public(Request(url, headers={'Range': 'bytes=0-31'})) as response:
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


def verify_motion(url, expected_size=None):
    with open_public(Request(url, headers={'Range': 'bytes=0-4095'})) as response:
        data = response.readline(4096).decode('utf-8-sig')
        if response.status not in (200, 206) or 'sample_time_iso8601' not in data.splitlines()[0]:
            raise ValueError('链接未返回有效 Motion CSV')
        size = response.headers.get('Content-Range', '').rsplit('/', 1)[-1]
        if response.status == 200:
            size = response.headers.get('Content-Length', '')
        if expected_size is not None and (not size.isdigit() or int(size) != expected_size):
            raise ValueError('公网 Motion 大小与本次导出不一致')
    return {'url': url, 'accessible': True}
