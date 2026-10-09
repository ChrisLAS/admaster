import unittest

from admaster import audio
from admaster.errors import MasterError
from admaster.profile import load_profile


class GainTests(unittest.TestCase):
    def test_uses_measured_limiter_response_not_unity_slope(self):
        history = [
            {"gain_db": 11.92, "lufs": -15.37},
            {"gain_db": 8.29, "lufs": -16.78},
        ]
        gain = audio.next_gain(history, load_profile())
        expected = 8.29 + (-19 + 16.78) / ((-16.78 + 15.37) / (8.29 - 11.92))
        self.assertAlmostEqual(gain, expected)
        self.assertLess(abs(gain - 8.29), 6)

    def test_stalled_response_stops(self):
        with self.assertRaises(MasterError) as error:
            audio.next_gain(
                [{"gain_db": g, "lufs": -15} for g in (12, 8, 4)], load_profile()
            )
        self.assertEqual(error.exception.code, "loudness_stalled")

    def test_gain_bounds_not_relaxed(self):
        with self.assertRaises(MasterError) as error:
            audio.next_gain([{"gain_db": 18, "lufs": -30}], load_profile())
        self.assertEqual(error.exception.code, "gain_limit")

    def test_bracketed_step_stays_inside_measured_bracket(self):
        history = [{"gain_db": 12, "lufs": -15}, {"gain_db": 6, "lufs": -22}]
        self.assertTrue(6 < audio.next_gain(history, load_profile()) < 12)


if __name__ == "__main__":
    unittest.main()
