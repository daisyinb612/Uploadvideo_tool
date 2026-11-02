import random
import unittest
from unittest.mock import patch

from services.synchronization import audio_alignment, resolve_alignment


class AudioSynchronization(unittest.TestCase):
    def signals(self):
        rng = random.Random(41)
        # Nonperiodic activity shared across microphones with slightly different gain.
        signal = [rng.random() for _ in range(2400)]
        return signal, [x*1.2+.05 for x in signal[56:]]

    def test_three_windows_recover_direction_and_subsecond_offset(self):
        first, third = self.signals()
        infos = [{'duration': len(s)/20, 'audio': True} for s in (first, third)]
        with patch('services.synchronization.envelope', side_effect=[first, third]):
            starts, duration, detail = audio_alignment(['first', 'third'], infos)
        self.assertEqual(starts, [2.8, 0.0])
        self.assertAlmostEqual(duration, 117.2)
        self.assertEqual(len(detail['windows']), 3)
        self.assertTrue(all(w['score'] > .99 for w in detail['windows']))
        with patch('services.synchronization.envelope', side_effect=[third, first]):
            reverse, _, _ = audio_alignment(['third', 'first'], list(reversed(infos)))
        self.assertEqual(reverse, [0.0, 2.8])

    def test_unrelated_or_silent_audio_is_not_accepted(self):
        rng = random.Random(42)
        a = [rng.random() for _ in range(2400)]
        b = [rng.random() for _ in range(2400)]
        infos = [{'duration': 120, 'audio': True}]*2
        for signals in ([a, b], [[0.0]*2400, [0.0]*2400]):
            with patch('services.synchronization.envelope', side_effect=signals):
                with self.assertRaises(ValueError):
                    audio_alignment(['a', 'b'], infos)

    def test_completion_timestamp_cannot_silently_trim_ten_minutes(self):
        infos = [dict(duration=600, audio=False, creation_time='2026-10-30T02:21:17Z'),
                 dict(duration=712, audio=False, creation_time='2026-10-30T02:11:18Z')]
        with self.assertRaisesRegex(ValueError, '超过一半'):
            resolve_alignment(['a', 'b'], infos, 'timestamp')
        starts, duration, detail = resolve_alignment(['a', 'b'], infos, 'already')
        self.assertEqual(starts, [0, 0])
        self.assertEqual(duration, 600)
        self.assertEqual(detail['method'], 'already')
