import json
import math
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

from .errors import MasterError


def execute(args, timeout=180):
    try:
        p = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise MasterError("dependency", f"{args[0]} failed: {e}") from e
    if p.returncode:
        raise MasterError("audio", f"{args[0]} failed: {p.stderr[-1500:]}")
    return p


def probe(path):
    p = execute(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ]
    )
    try:
        data = json.loads(p.stdout)
        audio = [s for s in data["streams"] if s["codec_type"] == "audio"]
        if len(audio) != 1:
            raise MasterError("audio", "expected exactly one audio stream")
        stream = audio[0]
        return {
            "sample_rate": int(stream["sample_rate"]),
            "channels": int(stream["channels"]),
            "duration": float(stream.get("duration", data["format"]["duration"])),
            "codec": stream["codec_name"],
            "bits": int(
                stream.get("bits_per_raw_sample") or stream.get("bits_per_sample") or 0
            ),
        }
    except (KeyError, ValueError, TypeError) as e:
        raise MasterError("audio", "invalid ffprobe output") from e


def read(path):
    try:
        meta = sf.info(path)
        if meta.duration > 601 or meta.channels > 2 or meta.samplerate > 192000:
            raise MasterError("audio", "audio exceeds supported size/channel limits")
        x, sr = sf.read(path, dtype="float64", always_2d=True)
    except (OSError, RuntimeError) as e:
        raise MasterError("audio", f"unreadable audio: {e}") from e
    if not x.size or not np.isfinite(x).all():
        raise MasterError("audio", "empty/non-finite audio")
    return x, sr


def db(v):
    return float(20 * np.log10(max(abs(float(v)), 1e-15)))


def runs(mask):
    edges = np.diff(np.r_[False, mask, False].astype(np.int8))
    return list(
        zip(np.flatnonzero(edges == 1).tolist(), np.flatnonzero(edges == -1).tolist())
    )


def features(x, sr, quiet_db=-50):
    peak = np.max(np.abs(x), axis=1)
    w = max(1, round(sr * 0.01))
    blocks = peak[: len(peak) // w * w].reshape(-1, w)
    rms = np.sqrt(np.mean(blocks**2, axis=1)) if len(blocks) else peak
    quiet = peak <= 10 ** (quiet_db / 20)
    return {
        "quiet_runs": runs(quiet),
        "quiet_fraction": float(np.mean(quiet)),
        "speech_p95_db": db(np.percentile(rms, 95)),
        "sample_peak_db": db(np.max(peak)),
        "clipped_samples": int(np.count_nonzero(peak >= 1 - 2**-23)),
        "longest_clip_seconds": max(
            (b - a for a, b in runs(peak >= 1 - 2**-23)), default=0
        )
        / sr,
    }


def loudness(path, log=None):
    p = execute(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-af",
            "loudnorm=I=-19:TP=-1:LRA=7:print_format=json",
            "-f",
            "null",
            "-",
        ]
    )
    if log:
        Path(log).write_text(p.stderr)
    try:
        start = p.stderr.rindex("{")
        end = p.stderr.index("}", start) + 1
        d = json.loads(p.stderr[start:end])
        result = {
            k: float(d[n])
            for k, n in [
                ("lufs", "input_i"),
                ("true_peak_db", "input_tp"),
                ("lra", "input_lra"),
            ]
        }
        if not all(math.isfinite(v) for v in result.values()):
            raise ValueError("silence/non-finite loudness")
        return result
    except (ValueError, KeyError) as e:
        raise MasterError(
            "measurement", "could not measure finite program loudness"
        ) from e


def validate(
    path, profile, target_frames=None, log=None, boundaries=(), *, shortfall_frames=0
):
    x, sr = read(path)
    meta = probe(path)
    r = profile["render"]
    q = profile["quality"]
    m = loudness(path, log)
    f = features(x, sr, profile["timing"]["quiet_db"])
    errors = []
    if sr != r["sample_rate"]:
        errors.append("sample_rate")
    if x.shape[1] != r["channels"]:
        errors.append("channels")
    if meta["codec"] != "pcm_s24le" or meta["bits"] != 24:
        errors.append("format")
    if (
        target_frames is not None
        and not -max(shortfall_frames, r["duration_tolerance_samples"])
        <= len(x) - target_frames
        <= r["duration_tolerance_samples"]
    ):
        errors.append("duration")
    if abs(m["lufs"] - r["lufs"]) > r["lufs_tolerance"]:
        errors.append("loudness")
    if m["true_peak_db"] > r["true_peak_max_db"] + 0.01:
        errors.append("true_peak")
    if f["clipped_samples"]:
        errors.append("clipping")
    if f["quiet_fraction"] > q["maximum_silence_fraction"]:
        errors.append("excessive_silence")
    boundary_stats = []
    for t in boundaries:
        n = round(t * sr)
        z = x[max(0, n - round(0.01 * sr)) : min(len(x), n + round(0.01 * sr))]
        step = db(np.max(np.abs(np.diff(z, axis=0)))) if len(z) > 1 else -300
        boundary_stats.append({"time": t, "maximum_step_db": step})
        if step > q["maximum_boundary_step_db"]:
            errors.append("boundary_step")
    if db(np.max(np.abs(x[-1]))) > -45:
        errors.append("abrupt_ending")
    return {
        **m,
        "duration": len(x) / sr,
        "frames": len(x),
        "sample_rate": sr,
        "channels": x.shape[1],
        "bits": meta["bits"],
        "clipped_samples": f["clipped_samples"],
        "silence_fraction": f["quiet_fraction"],
        "boundaries": boundary_stats,
        "valid": not errors,
        "errors": sorted(set(errors)),
    }


def next_gain(history, profile):
    """Measured post-FX/pre-limiter search; never change dynamics or QC limits."""
    target = profile["render"]["lufs"]
    g = profile["gain"]
    current = history[-1]
    if not all(math.isfinite(p[k]) for p in history for k in ("gain_db", "lufs")):
        raise MasterError("measurement", "non-finite gain search measurement")
    if len(history) >= 3:
        best_before = min(abs(p["lufs"] - target) for p in history[:-2])
        best_now = min(abs(p["lufs"] - target) for p in history)
        if best_before - best_now < 0.05:
            raise MasterError("loudness_stalled", "measured loudness stopped improving")
    slope = 1.0
    if len(history) >= 2:
        previous = history[-2]
        delta = current["gain_db"] - previous["gain_db"]
        if abs(delta) > 1e-6:
            measured = (current["lufs"] - previous["lufs"]) / delta
            if 0.1 <= measured <= 2:
                slope = measured
    correction = (target - current["lufs"]) / slope
    limit = g["max_correction_db"]
    candidate = current["gain_db"] + max(-limit, min(limit, correction))
    below = [p["gain_db"] for p in history if p["lufs"] < target]
    above = [p["gain_db"] for p in history if p["lufs"] > target]
    if below and above:
        low, high = max(below), min(above)
        if low >= high:
            raise MasterError(
                "loudness_stalled", "non-monotonic measured gain response"
            )
        if not low < candidate < high:
            candidate = (low + high) / 2
        candidate = current["gain_db"] + max(
            -limit, min(limit, candidate - current["gain_db"])
        )
    if not g["minimum_db"] <= candidate <= g["maximum_db"]:
        raise MasterError(
            "gain_limit",
            "loudness needs gain outside the source-adjustment safety range",
        )
    return candidate


def limiter_activity(master, prelimit, profile):
    x, sr = read(prelimit)
    y, ys = read(master)
    if sr != ys or x.shape != y.shape or np.max(np.abs(x)) >= 1 - 2**-23:
        raise MasterError("limiter_qc", "invalid pre-limiter diagnostic render")
    x *= 10 ** (24 / 20)  # matches the diagnostic-only -24 dB master attenuation
    w = round(sr * 0.01)
    count = len(x) // w * w
    a = np.sqrt(np.mean(x[:count].reshape(-1, w, x.shape[1]) ** 2, axis=(1, 2)))
    b = np.sqrt(np.mean(y[:count].reshape(-1, w, y.shape[1]) ** 2, axis=(1, 2)))
    active = a > 10 ** (-40 / 20)
    if not np.any(active):
        raise MasterError("limiter_qc", "no active audio")
    reduction = 20 * np.log10((a[active] + 1e-12) / (b[active] + 1e-12))
    peak = max(0, float(np.max(reduction)))
    heavy = float(np.mean(reduction > 3))
    return {
        "maximum_reduction_db": peak,
        "active_fraction_over_3db": heavy,
        "valid": peak <= profile["quality"]["maximum_limiter_reduction_db"]
        and heavy <= profile["quality"]["maximum_heavy_limiting_fraction"],
    }
