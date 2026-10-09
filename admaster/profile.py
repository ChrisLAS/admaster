import copy
import math
import os
import tomllib
from pathlib import Path

from .errors import MasterError

ROOT = Path(os.environ.get("ADMASTER_ROOT", Path(__file__).resolve().parent.parent))


def load_profile(path=None):
    default = ROOT / "profiles/ad-read.toml"
    try:
        with default.open("rb") as f:
            schema = tomllib.load(f)
        with Path(path or default).expanduser().open("rb") as f:
            value = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise MasterError("profile", str(e)) from e

    def check(v, spec, prefix=""):
        if not isinstance(v, dict) or set(v) != set(spec):
            raise MasterError(
                "profile", f"{prefix or 'profile'}: keys must match standard profile"
            )
        for key, expected in spec.items():
            actual = v[key]
            name = prefix + key
            if isinstance(expected, dict):
                check(actual, expected, name + ".")
            elif isinstance(expected, bool):
                if not isinstance(actual, bool):
                    raise MasterError("profile", f"{name}: expected boolean")
            elif isinstance(expected, str):
                if not isinstance(actual, str) or not actual:
                    raise MasterError("profile", f"{name}: expected nonempty string")
            elif (
                isinstance(actual, bool)
                or not isinstance(actual, (int, float))
                or not math.isfinite(actual)
            ):
                raise MasterError("profile", f"{name}: expected finite number")

    check(value, schema)

    def bound(section, key, low, high):
        v = value[section][key]
        if not low <= v <= high:
            raise MasterError("profile", f"{section}.{key} outside [{low}, {high}]")

    if value["version"] != 1:
        raise MasterError("profile", "unsupported profile version")
    r = value["render"]
    if (
        r["sample_rate"] not in (44100, 48000)
        or r["channels"] not in (1, 2)
        or r["bits"] != 24
    ):
        raise MasterError(
            "profile", "supported outputs: 44.1/48 kHz, mono/stereo, 24-bit WAV"
        )
    for key, low, high in [
        ("lufs", -24, -14),
        ("lufs_tolerance", 0.05, 1),
        ("true_peak_db", -6, -1),
        ("true_peak_max_db", -6, -0.9),
        ("duration_tolerance_samples", 0, 1),
    ]:
        bound("render", key, low, high)
    if r["true_peak_db"] > r["true_peak_max_db"]:
        raise MasterError(
            "profile", "limiter ceiling must not exceed validation ceiling"
        )
    if value["timing"]["max_stretch_percent"] != 0:
        raise MasterError(
            "profile",
            "time stretching is deliberately unsupported; edit pauses or escalate",
        )
    for key, low, high in [
        ("quiet_db", -65, -45),
        ("minimum_gap_seconds", 0.25, 2),
        ("minimum_retained_gap_seconds", 0.18, 1),
        ("maximum_gap_reduction_fraction", 0.1, 0.65),
        ("crossfade_seconds", 0.003, 0.02),
        ("head_room_seconds", 0.025, 0.2),
        ("tail_room_seconds", 0.08, 0.5),
        ("maximum_edge_trim_seconds", 0, 5),
        ("maximum_total_reduction_fraction", 0.01, 0.15),
        ("maximum_cuts_per_minute", 1, 30),
        ("recover_tail_seconds", 0, 0.2),
        ("recover_tail_source_margin_seconds", 0, 0.5),
        ("fade_in_seconds", 0.001, 0.02),
        ("fade_out_seconds", 0.01, 0.08),
    ]:
        bound("timing", key, low, high)
    if (
        value["timing"]["minimum_retained_gap_seconds"]
        >= value["timing"]["minimum_gap_seconds"]
    ):
        raise MasterError("profile", "retained gap must be shorter than eligible gap")
    for key in ("highpass_hz", "body_hz", "presence_hz"):
        bound("eq", key, 20, 16000)
    for key in ("body_db", "presence_db"):
        bound("eq", key, -4, 4)
    for key in ("body_bandwidth_octaves", "presence_bandwidth_octaves"):
        bound("eq", key, 0.2, 3)
    for key, low, high in [
        ("threshold_db", -40, -10),
        ("ratio", 1, 4),
        ("attack_ms", 1, 50),
        ("release_ms", 30, 500),
        ("rms_ms", 0, 20),
        ("knee_db", 0, 12),
        ("detector_highpass_hz", 0, 200),
    ]:
        bound("compressor", key, low, high)
    bound("limiter", "release_normalized", 0, 1)
    if not value["limiter"]["true_peak"]:
        raise MasterError("profile", "true-peak limiting must remain enabled")
    for key in ("initial_db", "minimum_db", "maximum_db"):
        bound("gain", key, -18, 24)
    g = value["gain"]
    if not g["minimum_db"] <= g["initial_db"] <= g["maximum_db"]:
        raise MasterError("profile", "initial gain outside limits")
    bound("gain", "max_correction_db", 0.1, 6)
    bound("gain", "max_passes", 1, 8)
    if int(g["max_passes"]) != g["max_passes"]:
        raise MasterError("profile", "max_passes must be integer")
    bound("quality", "minimum_speech_to_cut_threshold_db", 20, 40)
    bound("quality", "maximum_silence_fraction", 0.1, 0.8)
    bound("quality", "maximum_peak_plateau_seconds", 0.001, 0.05)
    bound("quality", "maximum_boundary_step_db", -60, -25)
    bound("quality", "maximum_limiter_reduction_db", 3, 8)
    bound("quality", "maximum_heavy_limiting_fraction", 0.001, 0.05)
    return copy.deepcopy(value)
