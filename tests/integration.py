"""Executable clean-HOME, synthetic-only integration test. No private audio."""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

BIN = os.environ.get("ADMASTER_TEST_BIN", "admaster")


def run(*args, expected=0):
    p = subprocess.run(
        [BIN, *map(str, args), "--json"], capture_output=True, text=True, timeout=240
    )
    assert p.returncode == expected, (p.returncode, p.stdout, p.stderr)
    return json.loads(p.stdout)


def main():
    with tempfile.TemporaryDirectory(prefix="admaster-test-") as d:
        root = Path(d)
        sr = 44100
        from fixtures import generate

        generate(root)
        before = (root / "source.rpp").read_bytes()
        doctor = run("--doctor")
        assert doctor["status"] == "ready"
        result = run(
            root / "source.rpp", "--duration", "19", "--output", root / "result"
        )
        assert (
            result["status"] == "complete"
            and result["frames"] == 19 * sr
            and result["stretch_percent"] == 0
        )
        assert (root / "source.rpp").read_bytes() == before
        check = run("--validate-render", root / "result/master.wav", "--duration", "19")
        assert check["valid"]
        inventory = json.loads((root / "result/work/inventory.json").read_text())
        assert inventory["plugins"][-1]["true_peak"] is True
        assert inventory["hardware_outputs"] == [0]
        params = {p["name"]: p["value"] for p in inventory["plugins"][1]["parameters"]}
        assert params["RMS size"] == "5.0" and params["Ratio"] == "2.00"
        assert result["limiter"]["valid"]
        shutil.copytree(root / "result", root / "portable")
        moved = run(root / "portable/master.rpp", "--analyze-only")
        assert (
            moved["status"] == "analyzed"
            and abs(moved["original_duration"] - 19) < 1e-6
        )
        prepared = run(
            root / "portable/master.rpp",
            "--no-edit",
            "--duration",
            "20",
            "--no-render",
            "--output",
            root / "prepared",
        )
        assert (
            prepared["status"] == "prepared" and not prepared["validation"]["complete"]
        )
        assert not (root / "prepared/master.wav").exists()
        assert prepared["duration"] == 19
        assert prepared["requested_duration"] == 20
        assert prepared["duration_shortfall_seconds"] == 1

        gapped = root / "gapped.rpp"
        gapped.write_text(
            "<REAPER_PROJECT\n<TRACK\n"
            "<ITEM\nPOSITION 0\nLENGTH 2.2\n"
            '<SOURCE WAVE\nFILE "source.wav"\n>\n>\n'
            "<ITEM\nPOSITION 2.25\nLENGTH 17.75\nSOFFS 2.25\n"
            '<SOURCE WAVE\nFILE "source.wav"\n>\n>\n>\n>\n'
        )
        assert run(gapped, "--analyze-only")["status"] == "analyzed"
        short = run(gapped, "--duration", "21", "--output", root / "short")
        assert short["status"] == "complete" and short["validation"]["complete"]
        assert short["frames"] == 20 * sr and short["stretch_percent"] == 0
        assert short["requested_duration"] == 21
        assert short["duration_shortfall_seconds"] == 1
        assert short["pause_cuts"] == 0
        short_inventory = json.loads((root / "short/work/inventory.json").read_text())
        assert abs(short_inventory["items"][1]["position"] - 2.25) < 1e-8
        assert run("--validate-render", root / "short/master.wav", "--duration", "21")[
            "valid"
        ]
        exact = run(
            "--validate-render",
            root / "short/master.wav",
            "--duration",
            "21",
            "--exact-duration",
            expected=2,
        )
        assert "duration" in exact["errors"]
        failure = run(
            root / "source.rpp",
            "--no-edit",
            "--duration",
            "19",
            "--output",
            root / "noedit-conflict",
            expected=2,
        )
        assert failure["code"] == "duration_no_edit"

        failure = run(
            root / "source.rpp",
            "--duration",
            "10",
            "--output",
            root / "impossible",
            expected=2,
        )
        assert failure["code"] in ("timing_limit", "timing_capacity")
        failure = run(root / "source.rpp", "--output", root / "result", expected=2)
        assert failure["code"] == "output_exists"
        failure = run(
            "--validate-render",
            root / "result/master.wav",
            "--duration",
            "18",
            expected=2,
        )
        assert "duration" in failure["errors"]
        print(
            "PASS: isolated REAPER, plugins, exact and slightly short renders, gapped timeline, loudness, media preservation, failure handling"
        )


if __name__ == "__main__":
    main()
