import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

from admaster import rpp
from admaster.errors import MasterError


class InputTests(unittest.TestCase):
    def test_direct_disguised_container_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "voice.wav"
            sf.write(source, np.zeros(100), 44100, format="AIFF", subtype="PCM_24")
            with self.assertRaises(MasterError) as error:
                rpp.inspect(source)
            self.assertIn("WAV/FLAC", str(error.exception))

    def test_edited_project_metadata_and_spacing(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            sf.write(root / "voice.flac", np.zeros((44100, 2)), 44100, subtype="PCM_24")
            item = (
                "<ITEM\nPOSITION {position}\nLENGTH .2\nSOFFS {offset}\n"
                "FADEIN 1 .01 0\nFADEOUT 1 .02 0\n"
                '<SOURCE FLAC\nFILE "voice.flac"\n>\n'
                "<EXT\nORIGINAL_FILENAME /old/path.flac\n>\n>\n"
            )
            project = root / "edited.RPP"
            text = (
                "<REAPER_PROJECT\n<TRACK\n"
                + item.format(position=0, offset=0)
                + item.format(position=0.5, offset=0.6)
                + ">\n>\n"
            )
            project.write_text(text)
            info = rpp.inspect(project, preserve_gaps=True)
            output = root / "job"
            output.mkdir()
            derived, _ = rpp.copy_project(info, output)
            self.assertEqual(
                rpp.inspect(derived, preserve_gaps=True)["items"], info["items"]
            )
            self.assertIn("FADEOUT 1 .02 0", derived.read_text())
            self.assertEqual(project.read_text(), text)
            with self.assertRaises(MasterError):
                rpp.inspect(project)
            project.write_text(
                text.replace("ORIGINAL_FILENAME /old/path.flac", "UNKNOWN 1")
            )
            with self.assertRaises(MasterError):
                rpp.inspect(project, preserve_gaps=True)

    def test_distinct_stereo_rejected_for_wav_and_flac(self):
        with tempfile.TemporaryDirectory() as d:
            for suffix in ("wav", "flac"):
                source = Path(d) / ("voice." + suffix)
                sf.write(
                    source,
                    np.column_stack((np.zeros(100), np.ones(100) * 0.1)),
                    44100,
                    subtype="PCM_24",
                )
                with self.assertRaises(MasterError) as error:
                    rpp.inspect(source)
                self.assertIn("distinct stereo", str(error.exception))

    def test_direct_identical_stereo_is_portable_mono(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            x = np.sin(np.arange(4410) * 0.1) * 0.1
            source = root / "voice.wav"
            sf.write(source, np.column_stack((x, x)), 44100, subtype="PCM_24")
            before = source.read_bytes()
            info = rpp.inspect(source)
            output = root / "job"
            output.mkdir()
            project, hashes = rpp.copy_project(info, output)
            derived = rpp.inspect(project)
            data, sr = sf.read(derived["sources"][0][1], always_2d=True)
            self.assertEqual(data.shape, (4410, 1))
            np.testing.assert_array_equal(data[:, 0], sf.read(source)[0][:, 0])
            self.assertEqual(info["channel_policy"], "identical_stereo_to_mono")
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(len(hashes), 1)


if __name__ == "__main__":
    unittest.main()
