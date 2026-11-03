import tempfile
import unittest
from pathlib import Path
from config import Paths
from services.jobs import JobManager
from services.roles import COFFEE_ROLES, normalize_role


class CoffeeRoles(unittest.TestCase):
    def test_labels_and_names_always_generate_the_same_english_filename(self):
        self.assertEqual(len(COFFEE_ROLES), 11)
        self.assertEqual(len({r['value'] for r in COFFEE_ROLES}), 11)
        with tempfile.TemporaryDirectory() as temp:
            manager = JobManager(Paths(Path(temp)/'uploads',Path(temp)/'exports'))
            for role in COFFEE_ROLES:
                with self.subTest(role=role['value']):
                    expected=f"coffee_20261102_120000_{role['value']}_icecoffee_first.mp4"
                    for value in (role['value'], role['name'], role['value']+' · '+role['name']):
                        preview=manager.preview(dict(project='coffee', mode='first', role=value,
                            content='icecoffee',naming_time='20261102_120000'))
                        self.assertEqual(preview['name']+'.mp4',expected)
                        self.assertTrue(preview['video_first'].endswith(expected))
                        self.assertTrue(expected.isascii())

    def test_coffee_rejects_unknown_roles_and_keeps_other_projects_customizable(self):
        with self.assertRaises(ValueError):normalize_role('coffee','student')
        self.assertEqual(normalize_role('other','custom-person'),'custom-person')
        self.assertEqual(normalize_role('coffee','丁筱夏'),'student10_dingxiaoxia')
