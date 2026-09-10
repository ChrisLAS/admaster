import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

from admaster.errors import MasterError
from admaster.profile import load_profile
from admaster.reaper import lua
from admaster.rpp import parse
from admaster.timing import duration_frames, plan


class CoreTests(unittest.TestCase):
    def test_profile(self):
        p = load_profile()
        self.assertEqual(p["timing"]["max_stretch_percent"], 0)
        self.assertEqual(p["compressor"]["ratio"], 2)

    def test_invalid_profile(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "profile.toml"
            f.write_text("version = 1\n")
            with self.assertRaises(MasterError):
                load_profile(f)

    def test_duration(self):
        self.assertEqual(duration_frames("90.000", 44100), 3969000)
        self.assertEqual(duration_frames("0.00003125", 48000), 2)
        for value in ["nan", "inf", "-1", "0", "601", "oops"]:
            with self.assertRaises(MasterError):
                duration_frames(value, 44100)

    def test_parse_rejects_unbalanced(self):
        with self.assertRaises(MasterError):
            parse("<REAPER_PROJECT\n<TRACK\n>")

    def test_lua_escaping(self):
        self.assertIn('\\"', lua('quote"; os.execute("bad")'))
        self.assertEqual(lua({"rate": 1}), '{["rate"]=1}')

    def test_plan_preserves_copy_and_exact_samples(self):
        sr = 44100
        t = np.arange(sr) / sr
        voiced = 0.2 * np.sin(2 * np.pi * 180 * t)
        x = np.concatenate([voiced, np.zeros(sr), voiced, np.zeros(sr), voiced])[
            :, None
        ]
        p = load_profile()
        p["timing"]["maximum_total_reduction_fraction"] = 0.15
        p["timing"]["maximum_cuts_per_minute"] = 30
        result = plan(x, sr, [{"position": 0, "length": 5}], p, "4.5")
        self.assertEqual(result["target_frames"], 198450)
        self.assertEqual(result["removed_frames"], 22050)
        self.assertEqual(result["rate"], 1)
        for cut in result["cuts"]:
            self.assertLess(
                np.max(abs(x[round(cut["start"] * sr) : round(cut["end"] * sr)])), 1e-9
            )

    def test_impossible_timing(self):
        x = np.ones((44100 * 4, 1)) * 0.1
        with self.assertRaises(MasterError):
            plan(x, 44100, [{"position": 0, "length": 4}], load_profile(), "3.9")

    def test_no_edit(self):
        x = np.ones((44100 * 4, 1)) * 0.1
        with self.assertRaises(MasterError):
            plan(x, 44100, [{"position": 0, "length": 4}], load_profile(), "3.9", True)

    def test_slightly_short_reads_preserve_timing(self):
        sr = 1000
        for seconds in (60, 90):
            for shortfall in (0, 0.567, 1):
                for no_edit in (False, True):
                    with self.subTest(
                        seconds=seconds, shortfall=shortfall, no_edit=no_edit
                    ):
                        frames = round((seconds - shortfall) * sr)
                        x = np.full((frames, 1), 0.1)
                        items = [{"position": 0, "length": frames / sr}]
                        result = plan(x, sr, items, load_profile(), seconds, no_edit)
                        self.assertEqual(result["target_frames"], frames)
                        self.assertEqual(result["removed_frames"], 0)
                        self.assertEqual(result["cuts"], [])
                        self.assertEqual(result["rate"], 1)

    def test_short_read_limits_and_exact_duration(self):
        sr = 1000
        for seconds in (60, 90):
            for shortfall, exact in ((1.001, False), (0.567, True)):
                for no_edit in (False, True):
                    with self.subTest(
                        seconds=seconds,
                        shortfall=shortfall,
                        exact=exact,
                        no_edit=no_edit,
                    ):
                        frames = round((seconds - shortfall) * sr)
                        with self.assertRaises(MasterError) as error:
                            plan(
                                np.full((frames, 1), 0.1),
                                sr,
                                [{"position": 0, "length": frames / sr}],
                                load_profile(),
                                seconds,
                                no_edit,
                                exact,
                            )
                        self.assertEqual(
                            error.exception.code,
                            "duration_no_edit" if no_edit else "duration_too_long",
                        )

    def test_cli_json_failure(self):
        p = subprocess.run(
            [sys.executable, "-m", "admaster", "missing.rpp", "--json"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(p.returncode, 2)
        self.assertEqual(json.loads(p.stdout)["status"], "failed")
        self.assertEqual(p.stderr, "")


if __name__ == "__main__":
    unittest.main()
