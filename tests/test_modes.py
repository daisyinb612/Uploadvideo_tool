import json
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from config import Paths
from services.jobs import JobManager


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
class UploadModes(unittest.TestCase):
    def test_all_modes_export_only_selected_views(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manager = JobManager(Paths(root/'incoming', root/'exports'))
            for key in ('first', 'third'):
                path = root/(key+'.mp4')
                subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',
                    'testsrc2=size=160x120:rate=30:duration=2','-c:v','libx264',
                    '-metadata','creation_time=2026-11-02T02:00:00Z','-y',str(path)],check=True)
                manager.register(key,path,key+'.mp4','video')
            motion = root/'motion.csv'
            motion.write_text('sample_time_iso8601,x\n2026-11-02T02:00:00Z,1\n2026-11-02T02:00:01Z,2\n2026-11-02T02:00:02Z,3\n')
            manager.register('motion',motion,'motion.csv','motion')
            for mode in ('first','third','both','both_motion'):
                with self.subTest(mode=mode):
                    payload = dict(mode=mode, project='coffee', role='teacher', content=mode,
                        naming_time='20261102_100000', align='timestamp',sync_server=False)
                    for key in ((mode,) if mode in ('first','third') else ('first','third')):
                        payload[key] = key
                    if mode == 'both_motion': payload['motion'] = 'motion'
                    preview = manager.preview(payload)
                    jid = manager.create(payload)['id']
                    for _ in range(300):
                        job = manager.jobs[jid]
                        if job['status'] != 'running': break
                        time.sleep(.05)
                    self.assertEqual(job['status'],'done',job)
                    self.assertEqual(job['filename'],preview['name']+'.mp4')
                    self.assertTrue(job['filename'].startswith('coffee_20261102_100000_'))
                    for view in ('first','third'):
                        self.assertEqual(bool(job['video_'+view]),mode != ('third' if view=='first' else 'first'))
                    self.assertEqual(bool(job['video_first_third']),mode in ('both','both_motion'))
                    self.assertEqual(bool(job.get('motion_url')),mode=='both_motion')
                    metadata=json.loads(Path(job['metadata_path']).read_text())
                    self.assertEqual(len(metadata['sources']),1 if mode in ('first','third') else 2)
                    self.assertAlmostEqual(job['details']['duration'],2,delta=.1)
            with self.assertRaisesRegex(ValueError,'Motion'):
                manager.create(dict(payload,motion=None))
            with self.assertRaises(ValueError):
                manager.preview(dict(payload,project='../coffee'))
