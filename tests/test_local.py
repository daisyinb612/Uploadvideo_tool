import csv
import io
import json
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from unittest.mock import patch

from config import Paths, SERVER_PUBLIC_BASE
from services.jobs import JobManager
from services.media import capture_time, naming_time, video_names
from services.motion import trim_motion
from web import Server


class LocalRules(unittest.TestCase):
    def test_rokid_filename_wins_over_finalization_time(self):
        info = {"original_filename": "vid-20261026-125402-c2.MP4",
                "creation_time": "2099-01-01T00:00:00Z", "time_warning": "ambiguous"}
        self.assertEqual(capture_time(info)[0].isoformat(), "2026-10-26T12:54:02+08:00")

    def test_iphone_compact_offset_and_single_view_naming(self):
        info = {"creation_time": "2026-10-30T10:48:17+0800"}
        self.assertEqual(capture_time(info)[0].isoformat(), "2026-10-30T10:48:17+08:00")
        self.assertEqual(naming_time([None, info])["value"], "20261030_104817")
        self.assertEqual(naming_time([info, None])["value"], "20261030_104817")

    def test_manual_naming_without_video_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = JobManager(Paths(Path(temp)/'uploads', Path(temp)/'outputs'))
            payload = dict(role='teacher', content='hotcoffee', naming_time='20261101_123456')
            preview = manager.preview(payload)
            self.assertEqual(preview['task_name'], '20261101_123456_teacher_hotcoffee')
            self.assertEqual(preview['path'], '/mnt/skill/mess/20261101_123456_teacher_hotcoffee_firstthird.mp4')
            self.assertEqual(preview['video_first_third'], SERVER_PUBLIC_BASE + preview['name'] + '.mp4')
            for invalid in ('', '20260230_123456', '20261101_250000', '../20261101', 123):
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    manager.preview(dict(payload, naming_time=invalid))

    def test_individual_view_filenames_and_collisions(self):
        name = '20261101_123456_teacher_icecoffee_firstthird'
        self.assertEqual(video_names(name)['first'], '20261101_123456_teacher_icecoffee_first.mp4')
        self.assertEqual(video_names(name + '_1')['third'], '20261101_123456_teacher_icecoffee_third_1.mp4')
        with tempfile.TemporaryDirectory() as temp:
            manager = JobManager(Paths(Path(temp)/'uploads', Path(temp)/'outputs'))
            (manager.paths.outputs / video_names(name)['first']).touch()
            self.assertEqual(manager.available_name(name), name + '_1')

    def test_motion_boundary_and_original_columns(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'raw.csv'
            target = Path(temp) / 'out.csv'
            source.write_text('sample_time_iso8601,ax\n2026-10-26T10:00:00Z,0\n'
                              '2026-10-26T10:00:01Z,1\n2026-10-26T10:00:02Z,2\n'
                              '2026-10-26T10:00:03Z,3\n')
            start = capture_time({"creation_time": "2026-10-26T10:00:01Z"})[0].timestamp()
            trim_motion(source, target, start, 2)
            with target.open(encoding='utf-8-sig') as result:
                rows = list(csv.DictReader(result))
            self.assertEqual([r['ax'] for r in rows], ['1', '2'])
            self.assertEqual([r['video_time_s'] for r in rows], ['0.000000', '1.000000'])

    def test_name_collision_checks_entire_artifact_group(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = JobManager(Paths(Path(temp)/'uploads', Path(temp)/'outputs'))
            (manager.paths.outputs/'task_motion.csv').touch()
            (manager.paths.outputs/'task_1.metadata.json').touch()
            self.assertEqual(manager.available_name('task'), 'task_2')


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
class LocalWorkflow(unittest.TestCase):
    def test_upload_cache_export_repeat_and_download(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manager = JobManager(Paths(root/'uploads', root/'outputs'))
            server = Server(('127.0.0.1', 0), manager)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = 'http://127.0.0.1:' + str(server.server_port)

            def request(path, data=None, method=None, headers=None):
                return urllib.request.urlopen(urllib.request.Request(
                    base+path, data=data, method=method, headers=headers or {}))

            def post(path, payload):
                with request(path, json.dumps(payload).encode(), 'POST') as result:
                    return json.load(result)

            def wait(jid):
                for _ in range(200):
                    with request('/api/jobs/'+jid) as result:
                        job = json.load(result)
                    if job['status'] != 'running':
                        self.assertEqual(job['status'], 'done', job)
                        return job
                    time.sleep(.05)
                self.fail('Timed out waiting for export')

            def fixture(path, size, duration, timestamp, pad=None, audio=False):
                cmd = ['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                       f'testsrc2=size={size}:rate=30:duration={duration}']
                if audio:
                    cmd += ['-f', 'lavfi', '-i', f'sine=duration={duration}:frequency=440', '-c:a', 'aac']
                if pad:
                    cmd += ['-vf', pad]
                subprocess.run(cmd+['-c:v', 'libx264', '-metadata', 'creation_time='+timestamp,
                                    '-y', str(path)], check=True)

            try:
                first, third = root/'first.mp4', root/'third.mp4'
                fixture(first, '180x320', 3, '2026-10-26T10:00:00Z', audio=True)
                fixture(third, '320x180', 4, '2026-10-26T10:00:01Z', 'pad=320:260:0:40:black')
                from services.media import probe
                with patch('services.jobs.probe', wraps=probe) as cached_probe:
                    videos = []
                    for file in (first, third):
                        with request('/api/upload', file.read_bytes(), 'PUT') as result:
                            videos.append(json.load(result)['token'])
                    payload = dict(first=videos[0], third=videos[1], role='teacher',
                                   content='icecoffee', align='timestamp', sync_server=False)
                    single = post('/api/naming', dict(first=videos[0], role='teacher', content='icecoffee'))
                    self.assertEqual(single['time']['value'], '20261026_180000')
                    self.assertTrue(single['video_first'].startswith(SERVER_PUBLIC_BASE))
                    for _ in range(3):
                        preview = post('/api/naming', payload)
                    self.assertEqual(cached_probe.call_count, 2)
                    motion = b'sample_time_iso8601,ax\n2026-10-26T10:00:01Z,1\n2026-10-26T10:00:02Z,2\n2026-10-26T10:00:03Z,3\n'
                    with request('/api/motion-upload', motion, 'PUT') as result:
                        payload['motion'] = json.load(result)['token']
                    jid = post('/api/jobs', payload)['id']
                    job = wait(jid)
                    self.assertEqual(job['filename'], preview['name']+'.mp4')
                    self.assertEqual(job['task_name'], '20261026_180001_teacher_icecoffee')
                    self.assertFalse(job['server_synced'])
                    for key in ('video_first', 'video_third', 'video_first_third'):
                        self.assertEqual(job[key], preview[key])
                        self.assertTrue(job[key].startswith(SERVER_PUBLIC_BASE))
                        with request('/videos/' + job[key].rsplit('/', 1)[1], headers={'Range': 'bytes=0-15'}) as result:
                            self.assertEqual(result.status, 206)
                            self.assertEqual(len(result.read()), 16)
                    for key in ('first_path', 'third_path'):
                        self.assertAlmostEqual(probe(Path(job[key]))['duration'], 2, delta=.1)
                    self.assertEqual(cached_probe.call_count, 2)
                    self.assertEqual(job['details']['crops'][1], [320, 180, 0, 40])
                    self.assertEqual(job['details']['starts'], [1.0, 0])
                    with request(job['motion_url']) as result:
                        rows = list(csv.DictReader(io.StringIO(result.read().decode('utf-8-sig'))))
                    self.assertEqual([r['video_time_s'] for r in rows], ['0.000000', '1.000000'])
                    with request(job['url'], headers={'Range': 'bytes=0-15'}) as result:
                        self.assertEqual(result.status, 206)
                        self.assertEqual(len(result.read()), 16)
                    with request('/bundle/'+jid) as result:
                        archive = zipfile.ZipFile(io.BytesIO(result.read()))
                    self.assertEqual(len(archive.namelist()), 5)
                    self.assertIsNone(archive.testzip())
                    metadata = json.loads(Path(job['metadata_path']).read_text())
                    self.assertEqual(metadata['motion']['rows'], 2)
                    self.assertEqual(len(metadata['sources']), 2)
                    second_preview = post('/api/naming', payload)
                    self.assertTrue(second_preview['name'].endswith('_1'))
                    self.assertEqual(second_preview['video_first'], SERVER_PUBLIC_BASE + '20261026_180001_teacher_icecoffee_first_1.mp4')
                    self.assertNotIn('%', second_preview['video_first'])
                    # The same selected uploads remain usable for another local test.
                    payload.update(sync_server=True)
                    with patch.object(manager, 'check_existing', return_value={'existing': False, 'name': second_preview['name']}), \
                         patch('services.jobs.server_password', return_value='test-only'), \
                         patch('services.access_check.verify_video', return_value={'accessible': True}) as access, \
                         patch('services.storage.sync_exports', return_value=['/mnt/skill/mess/test.mp4']) as sync:
                        second = wait(post('/api/jobs', payload)['id'])
                        self.assertTrue(second['server_synced'])
                        self.assertTrue(second['links_verified'])
                        self.assertEqual(access.call_count, 3)
                        self.assertEqual(sync.call_count, 1)
                        self.assertEqual(len(sync.call_args[0][0]), 5)
                        self.assertEqual(sync.call_args[0][1], 'test-only')
                        self.assertNotIn('server_password', second)
                    self.assertEqual(second['filename'], second_preview['name']+'.mp4')
                    payload.update(naming_time='20261101_123456', sync_server=False)
                    manual_preview = post('/api/naming', payload)
                    manual_job = wait(post('/api/jobs', payload)['id'])
                    self.assertEqual(manual_job['filename'], manual_preview['name'] + '.mp4')
                    self.assertEqual(manual_job['task_name'], '20261101_123456_teacher_icecoffee')
                    self.assertEqual(manual_job['details']['starts'], [1.0, 0])
                    self.assertEqual(cached_probe.call_count, 2)
                with request('/') as result:
                    self.assertNotIn('writeFeishu', result.read().decode())
                for asset in ('app.js', 'style.css', 'upload-slot.mjs'):
                    with request('/static/'+asset) as result:
                        self.assertEqual(result.status, 200)
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
