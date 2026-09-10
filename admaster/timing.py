import math
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from .audio import features
from .errors import MasterError

DURATION_ALLOWANCE_SECONDS = 1


def duration_frames(seconds, sr):
    try:
        value = Decimal(str(seconds))
        if not value.is_finite() or not 0 < value <= 600:
            raise ValueError()
        frames = int((value * sr).to_integral_value(rounding=ROUND_HALF_UP))
        if frames < 1:
            raise ValueError()
        return frames
    except (InvalidOperation, ValueError):
        raise MasterError(
            "duration", "duration must be finite, positive, and at most 600 seconds"
        ) from None


def plan(x, sr, items, profile, seconds=None, no_edit=False, exact_duration=False):
    t = profile["timing"]
    q = profile["quality"]
    f = features(x, sr, t["quiet_db"])
    original = len(x)
    target = duration_frames(seconds, sr) if seconds is not None else original
    if (
        seconds is not None
        and not exact_duration
        and 0 <= target - original <= DURATION_ALLOWANCE_SECONDS * sr
    ):
        target = original
    if (
        f["clipped_samples"]
        or f["longest_clip_seconds"] > q["maximum_peak_plateau_seconds"]
    ):
        raise MasterError(
            "source_clipping",
            "source contains full-scale samples; repair before mastering",
        )
    if f["speech_p95_db"] - t["quiet_db"] < q["minimum_speech_to_cut_threshold_db"]:
        raise MasterError(
            "source_level",
            "speech is too close to the automatic cut threshold; needs level/noise review",
        )
    if f["quiet_fraction"] > q["maximum_silence_fraction"]:
        raise MasterError(
            "source_silence", "source is mostly quiet; inspect the performance"
        )
    if no_edit:
        if abs(original - target) > 1:
            raise MasterError(
                "duration_no_edit", "--no-edit cannot alter the current runtime"
            )
        return {
            "head_frames": 0,
            "tail_frames": 0,
            "cuts": [],
            "target_frames": target,
            "rate": 1.0,
            "removed_frames": 0,
        }
    if target > original + 1:
        raise MasterError(
            "duration_too_long",
            "read is shorter than the requested duration window; refusing to pad or slow speech",
        )
    need = max(0, original - target)
    edge_limit = round(t["maximum_edge_trim_seconds"] * sr)
    head = tail = 0
    if f["quiet_runs"] and f["quiet_runs"][0][0] == 0:
        head = max(
            0,
            min(
                edge_limit,
                f["quiet_runs"][0][1] - round(t["head_room_seconds"] * sr),
                round((items[0]["length"] - 0.1) * sr),
            ),
        )
    if f["quiet_runs"] and f["quiet_runs"][-1][1] == original:
        tail = max(
            0,
            min(
                edge_limit,
                original - f["quiet_runs"][-1][0] - round(t["tail_room_seconds"] * sr),
                round((items[-1]["length"] - 0.1) * sr),
            ),
        )
    if seconds is None:
        target = original - head - tail
        need = head + tail
    head = min(head, need)
    tail = min(tail, need - head)
    remaining = need - head - tail
    if need / original > t["maximum_total_reduction_fraction"]:
        raise MasterError(
            "timing_limit", "requested reduction exceeds the profile safety limit"
        )
    candidates = []
    for a, b in f["quiet_runs"]:
        if a == 0 or b == original or (b - a) / sr < t["minimum_gap_seconds"]:
            continue
        # Do not cut across an existing edit, fade, or empty arrangement space.
        containing = [
            i
            for i in items
            if a / sr > i["position"] + 0.02
            and b / sr < i["position"] + i["length"] - 0.02
        ]
        if len(containing) != 1:
            continue
        capacity = min(
            math.floor((b - a) * t["maximum_gap_reduction_fraction"]),
            b - a - round(t["minimum_retained_gap_seconds"] * sr),
        )
        if capacity > 0:
            candidates.append({"a": a, "b": b, "capacity": capacity})
    max_cuts = max(1, math.floor(original / sr / 60 * t["maximum_cuts_per_minute"]))
    # Longest gaps get priority; stop once enough capacity exists.
    chosen = []
    capacity = 0
    for c in sorted(candidates, key=lambda c: c["capacity"], reverse=True):
        if capacity >= remaining:
            break
        if len(chosen) >= max_cuts:
            break
        chosen.append(c)
        capacity += c["capacity"]
    if remaining > capacity:
        available = (need - remaining + capacity) / sr
        raise MasterError(
            "timing_capacity",
            f"need {need / sr:.3f}s reduction, only {available:.3f}s of safe pause edits; no stretching allowed",
        )
    cuts = []
    used = 0
    chosen.sort(key=lambda c: c["a"])
    allocations = [math.floor(remaining * c["capacity"] / capacity) for c in chosen]
    remainder = remaining - sum(allocations)
    for i, c in enumerate(chosen):
        extra = min(remainder, c["capacity"] - allocations[i])
        allocations[i] += extra
        remainder -= extra
    for c, remove in zip(chosen, allocations):
        if remove <= 0:
            continue
        if remove > c["capacity"]:
            raise MasterError("timing_capacity", "rounding exhausted pause capacity")
        center = (c["a"] + c["b"]) / 2
        cuts.append(
            {
                "start": (center - remove / 2) / sr,
                "end": (center + remove / 2) / sr,
                "removed_frames": remove,
                "quiet_start": c["a"] / sr,
                "quiet_end": c["b"] / sr,
                "retained_seconds": (c["b"] - c["a"] - remove) / sr,
            }
        )
        used += remove
    assert head + tail + used == need
    return {
        "head_frames": head,
        "tail_frames": tail,
        "cuts": cuts,
        "target_frames": target,
        "rate": 1.0,
        "removed_frames": need,
    }
