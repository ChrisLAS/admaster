import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf
from fixtures import generate

from admaster import audio, rpp
from admaster.errors import MasterError
from admaster.profile import load_profile


class ValidationTests(unittest.TestCase):
    def test_duration_allowance_is_one_sided_and_opt_in_for_internal_qc(self):
        sr = 44100
        target = 2 * sr
        for delta, allowance, accepted in [
            (-sr - 1, sr, False),
            (-sr, sr, True),
            (-sr // 2, sr, True),
            (0, sr, True),
            (1, sr, True),
            (2, sr, False),
            (-sr // 2, 0, False),
            (-1, 0, True),
        ]:
            with self.subTest(delta=delta, allowance=allowance):
                x = np.full((target + delta, 1), 0.1)
                x[-1] = 0
                with (
                    patch("admaster.audio.read", return_value=(x, sr)),
                    patch(
                        "admaster.audio.probe",
                        return_value={"codec": "pcm_s24le", "bits": 24},
                    ),
                    patch(
                        "admaster.audio.loudness",
                        return_value={"lufs": -19, "true_peak_db": -2, "lra": 3},
                    ),
                ):
                    result = audio.validate(
                        "unused.wav", load_profile(), target, shortfall_frames=allowance
                    )
                self.assertEqual(result["valid"], accepted)
                self.assertEqual(result["errors"], [] if accepted else ["duration"])

    def test_project_seam_limits_and_issue_1(self):
        layouts = [
            ([(0, 1), (1 + delta, 1)], accepted)
            for delta, accepted in [
                (-0.100001, False),
                (-0.1, True),
                (0, True),
                (0.002813749, True),
                (0.1, True),
                (0.100001, False),
            ]
        ]
        layouts.append(
            (
                [
                    (0, 3.801101598),
                    (3.778172701, 1.518290831),
                    (5.289291610, 4.921659812),
                    (10.213765171, 4.865198369),
                    (15.121995065, 8.199240876),
                    (23.303402355, 33.539917462),
                    (56.86, 1.883813099),
                    (58.802199242, 0.630653617),
                ],
                True,
            )
        )
        with tempfile.TemporaryDirectory() as d:
            path = generate(d)
            for layout, accepted in layouts:
                with self.subTest(layout=layout):
                    items = "".join(
                        f"<ITEM\nPOSITION {p}\nLENGTH {length}\n"
                        '<SOURCE WAVE\nFILE "source.wav"\n>\n>\n'
                        for p, length in layout
                    )
                    path.write_text("<REAPER_PROJECT\n<TRACK\n" + items + ">\n>\n")
                    if accepted:
                        self.assertEqual(len(rpp.inspect(path)["items"]), len(layout))
                    else:
                        with self.assertRaises(MasterError) as error:
                            rpp.inspect(path)
                        self.assertEqual(error.exception.code, "unsupported_project")

    def test_probe_and_threshold_failures(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "bad.wav"
            x = np.zeros((4800, 2))
            x[:2400] = 0.2
            x[0] = 1
            sf.write(path, x, 48000, subtype="PCM_24")
            self.assertEqual(audio.probe(path)["sample_rate"], 48000)
            with patch(
                "admaster.audio.loudness",
                return_value={"lufs": -15, "true_peak_db": -0.5, "lra": 3},
            ):
                result = audio.validate(path, load_profile(), 100)
            self.assertFalse(result["valid"])
            self.assertTrue(
                {
                    "duration",
                    "loudness",
                    "true_peak",
                    "sample_rate",
                    "channels",
                    "clipping",
                }
                <= set(result["errors"])
            )

    def test_suspicious_silence(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "silent.wav"
            sf.write(path, np.zeros(44100), 44100, subtype="PCM_24")
            with self.assertRaises(MasterError):
                audio.loudness(path)

    def test_project_missing_source_and_automation(self):
        with tempfile.TemporaryDirectory() as d:
            path = generate(d)
            original = path.read_text()
            self.assertEqual(len(rpp.inspect(path)["items"]), 1)
            path.write_text(original.replace("source.wav", "missing.wav"))
            with self.assertRaises(MasterError) as e:
                rpp.inspect(path)
            self.assertEqual(e.exception.code, "missing_media")
            path.write_text(original.replace(" <ITEM", " <VOLENV2\n ACT 1\n >\n <ITEM"))
            with self.assertRaises(MasterError) as e:
                rpp.inspect(path)
            self.assertEqual(e.exception.code, "unsupported_project")
            path.write_text(
                original.replace(" NAME Dialogue", " NAME Dialogue\n HWOUT 4 0 1")
            )
            with self.assertRaises(MasterError) as e:
                rpp.inspect(path)
            self.assertEqual(e.exception.code, "unsupported_project")

    def test_invalid_rates_and_nonfinite_fields(self):
        with tempfile.TemporaryDirectory() as d:
            path = generate(d)
            original = path.read_text()
            for change in [
                original.replace("PLAYRATE 1", "PLAYRATE 1.0235"),
                original.replace("LENGTH 20", "LENGTH nan"),
            ]:
                path.write_text(change)
                with self.assertRaises(MasterError):
                    rpp.inspect(path)

    def test_invalid_boolean_profile(self):
        from admaster.profile import ROOT

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "profile.toml"
            path.write_text(
                (ROOT / "profiles/ad-read.toml")
                .read_text()
                .replace("true_peak = true", "true_peak = false")
            )
            with self.assertRaises(MasterError):
                load_profile(path)

    def test_limiter_workload(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            sr = 44100
            t = np.arange(sr) / sr
            x = 0.2 * np.sin(2 * np.pi * 200 * t)
            sf.write(root / "pre.wav", x * 10 ** (-24 / 20), sr, subtype="PCM_24")
            sf.write(root / "master.wav", x * 0.25, sr, subtype="PCM_24")
            result = audio.limiter_activity(
                root / "master.wav", root / "pre.wav", load_profile()
            )
            self.assertFalse(result["valid"])
            self.assertGreater(result["maximum_reduction_db"], 10)


if __name__ == "__main__":
    unittest.main()
