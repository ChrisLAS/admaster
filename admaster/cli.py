import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

from . import __version__, audio, rpp, timing
from .errors import MasterError
from .profile import ROOT, load_profile
from .reaper import Reaper


def parser():
    p = argparse.ArgumentParser(
        prog="admaster",
        description="Master a WAV/FLAC or edited REAPER ad read at its original speed.",
    )
    p.add_argument("project", nargs="?", type=Path)
    p.add_argument(
        "--duration",
        metavar="SECONDS",
        help="requested runtime; accepts up to 1 second under",
    )
    p.add_argument(
        "--exact-duration",
        action="store_true",
        help="require --duration to within one sample",
    )
    p.add_argument("--profile", type=Path)
    p.add_argument("--output", type=Path, help="new job directory (must not exist)")
    p.add_argument(
        "--analyze-only",
        action="store_true",
        help="read-only unprocessed timeline analysis",
    )
    p.add_argument(
        "--no-edit",
        action="store_true",
        help="preserve timing; still apply the mastering profile",
    )
    p.add_argument(
        "--no-render",
        action="store_true",
        help="prepare project, without a finished master",
    )
    p.add_argument(
        "--doctor",
        action="store_true",
        help="check dependencies and stock plugins in isolated REAPER",
    )
    p.add_argument(
        "--validate-render",
        type=Path,
        metavar="WAV",
        help="validate an existing render without modifying it",
    )
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--version", action="version", version=__version__)
    return p


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def fixture(path):
    sr = 44100
    t = np.arange(sr) / sr
    audio.sf.write(
        path / "source.wav", 0.05 * np.sin(2 * np.pi * 180 * t), sr, subtype="PCM_24"
    )
    (path / "test.rpp").write_text(
        '<REAPER_PROJECT 0.1 7 1\n  <TRACK\n    NAME Test\n    NCHAN 2\n    MAINSEND 1\n    <ITEM\n      POSITION 0\n      LENGTH 1\n      VOLPAN 1 0 1 -1\n      PLAYRATE 1 0 0 -1\n      <SOURCE WAVE\n        FILE "source.wav"\n      >\n    >\n  >\n>\n'
    )
    return path / "test.rpp"


def doctor(args, profile):
    required = ("reaper", "ffmpeg", "ffprobe", "xvfb-run", "xauth")
    missing = [name for name in required if not shutil.which(name)]
    if missing:
        raise MasterError(
            "dependency",
            "missing commands: "
            + ", ".join(missing)
            + "; use scripts/bootstrap or nix develop",
        )
    if args.project:
        rpp.inspect(args.project)
    with tempfile.TemporaryDirectory(prefix="admaster-doctor-") as tmp:
        directory = Path(tmp)
        project = fixture(directory)
        with Reaper(directory / "logs", args.verbose, timeout=90) as reaper:
            job = {
                "profile": profile,
                "gain_db": profile["gain"]["initial_db"],
                "plugin_state": (ROOT / "reaper/presets/realimit-reference.b64")
                .read_text()
                .strip(),
            }
            result = reaper.script(project, job, ["apply-profile"])
    return {
        "status": "ready",
        "reaper_version": result["reaper_version"],
        "plugins": [p["name"] for p in result["plugins"]],
        "writable_runtime": True,
        "project_accessible": bool(args.project),
        "nix_environment": bool(os.environ.get("ADMASTER_ROOT")),
    }


def process(args, profile):
    info = rpp.inspect(args.project, preserve_gaps=args.no_edit or args.analyze_only)
    source = info["sources"][0][1]
    source_meta = audio.probe(source)

    if source_meta["duration"] > 600:
        raise MasterError("unsupported_project", "source exceeds ten-minute limit")
    for item in info["items"]:
        if item["offset"] + item["length"] > source_meta["duration"] + 1e-5:
            raise MasterError(
                "missing_media", "item extends beyond available source media"
            )
    temp = None
    if args.analyze_only:
        temp = tempfile.TemporaryDirectory(prefix="admaster-analysis-")
        output = Path(temp.name) / "job"
    else:
        output = (
            (args.output or info["path"].with_name(info["path"].stem + "-admaster"))
            .expanduser()
            .resolve()
        )
    try:
        output.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise MasterError(
            "output_exists",
            "job directory exists; choose a new --output (nothing overwritten)",
        ) from None
    try:
        work = output / "work"
        work.mkdir()
        project, hashes = rpp.copy_project(info, output)
        profile_src = (args.profile or ROOT / "profiles/ad-read.toml").expanduser()
        shutil.copy2(profile_src, output / "profile.toml")
        dry = work / "dry.wav"
        job = {
            "profile": profile,
            "edit": not (args.no_edit or args.analyze_only),
            "render_path": str(dry),
            "plugin_state": (ROOT / "reaper/presets/realimit-reference.b64")
            .read_text()
            .strip(),
        }
        with Reaper(work, args.verbose) as reaper:
            prepared = reaper.script(project, job, ["prepare"])
            reaper.render(project, dry)
            x, sr = audio.read(dry)
            if args.analyze_only:
                measures = audio.loudness(dry)
                return {
                    "status": "analyzed",
                    "original_duration": info["duration"],
                    "timeline": "unprocessed; original item gains/fades retained, track/master FX and gains bypassed",
                    "source": source_meta,
                    "items": len(prepared["items"]),
                    **measures,
                    "auditory_review": "not_performed",
                }
            plan = timing.plan(
                x,
                sr,
                prepared["items"],
                profile,
                args.duration,
                args.no_edit,
                args.exact_duration,
            )
            write_json(work / "plan.json", plan)
            gain = profile["gain"]["initial_db"]
            render = output / "master.wav"
            job.update({"plan": plan, "gain_db": gain, "render_path": str(render)})
            inventory = reaper.script(
                project, job, ["tighten-runtime", "apply-profile", "render-master"]
            )
            write_json(work / "inventory.json", inventory)
            base = {
                "requested_duration": float(args.duration) if args.duration else None,
                "duration_allowance_seconds": (
                    timing.DURATION_ALLOWANCE_SECONDS
                    if args.duration and not args.exact_duration
                    else 0
                ),
                "duration_shortfall_seconds": (
                    max(0, float(args.duration) - plan["target_frames"] / sr)
                    if args.duration
                    else None
                ),
                "original_duration": info["duration"],
                "duration": plan["target_frames"] / sr,
                "adjustment_seconds": plan["target_frames"] / sr - info["duration"],
                "recovered_tail_seconds": prepared["recovered_tail_seconds"],
                "pause_cuts": len(plan["cuts"]),
                "stretch_percent": 0.0,
                "project": str(project),
                "auditory_review": "not_performed",
                "channel_policy": info["channel_policy"],
                "input": str(info["path"]),
            }
            if args.no_render:
                result = {
                    **base,
                    "status": "prepared",
                    "render": None,
                    "validation": {"complete": False},
                }
                write_json(output / "report.json", result)
                return result
            history = []
            for attempt in range(int(profile["gain"]["max_passes"])):
                reaper.render(project, render)
                validation = audio.validate(
                    render,
                    profile,
                    plan["target_frames"],
                    work / f"loudness-{attempt + 1}.log",
                    [i["position"] for i in inventory["items"][1:]],
                )
                history.append({"gain_db": gain, **validation})
                write_json(work / "gain-passes.json", history)
                write_json(work / "validation.json", validation)
                if any(error != "loudness" for error in validation["errors"]):
                    break
                if "loudness" not in validation["errors"]:
                    break
                if attempt + 1 == profile["gain"]["max_passes"]:
                    break
                next_gain = audio.next_gain(history, profile)
                render.rename(work / f"pass-{attempt + 1}.wav")
                gain = next_gain
                job["gain_db"] = gain
                inventory = reaper.script(project, job, ["render-master"])
            write_json(work / "gain-passes.json", history)
            write_json(work / "validation.json", validation)
            if not validation["valid"]:
                raise MasterError(
                    "validation", "render failed: " + ", ".join(validation["errors"])
                )
            final = validation
            prelimit = work / "prelimit-minus24db.wav"
            diagnostic = dict(job, prelimit=True, render_path=str(prelimit))
            reaper.script(project, diagnostic, ["render-master"])
            reaper.render(project, prelimit)
            inventory = reaper.script(project, job, ["render-master"])
            limiter = audio.limiter_activity(render, prelimit, profile)
            write_json(work / "limiter-activity.json", limiter)
            write_json(work / "inventory.json", inventory)
            if not limiter["valid"]:
                raise MasterError(
                    "limiter_load",
                    "limiter is working too hard; source dynamics need review",
                )
            if rpp.sha256(info["path"]) != info["input_sha256"]:
                raise MasterError(
                    "source_changed",
                    "original project changed during the job; compare the backup",
                )
            for name, digest in hashes.items():
                if (
                    rpp.sha256(output / "media" / name) != digest
                    or rpp.sha256(source) != digest
                ):
                    raise MasterError("source_changed", "source changed during the job")
            for name, digest in info.get("derived_hashes", {}).items():
                if rpp.sha256(output / "media" / name) != digest:
                    raise MasterError(
                        "source_changed", "derived mono media changed during the job"
                    )
            result = {
                **base,
                **{
                    k: v
                    for k, v in final.items()
                    if k not in ("boundaries", "valid", "errors")
                },
                "status": "complete",
                "render": str(render),
                "gain_db": gain,
                "validation": {"complete": True, "errors": []},
                "profile": profile["name"],
                "reaper_version": inventory["reaper_version"],
                "limiter": limiter,
                "source_hashes": hashes,
                "derived_media_hashes": info.get("derived_hashes", {}),
                "render_sha256": rpp.sha256(render),
            }
            if args.duration:
                result["duration_shortfall_seconds"] = max(
                    0, float(args.duration) - result["duration"]
                )
            write_json(output / "report.json", result)
            return result
    except Exception as e:
        if not args.analyze_only:
            write_json(
                output / "report.json",
                {
                    "status": "failed",
                    "code": getattr(e, "code", "internal"),
                    "message": str(e),
                    "work": str(output / "work"),
                    "auditory_review": "not_performed",
                },
            )
        raise
    finally:
        if temp:
            temp.cleanup()


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        profile = load_profile(args.profile)
        if args.exact_duration and (
            not args.duration or args.doctor or args.analyze_only
        ):
            raise MasterError(
                "arguments",
                "--exact-duration requires --duration in a job or render validation",
            )
        modes = sum((args.doctor, args.analyze_only, bool(args.validate_render)))
        if args.doctor and (
            args.duration or args.output or args.no_edit or args.no_render
        ):
            raise MasterError("arguments", "doctor does not accept job-edit options")
        if args.validate_render and (
            args.project or args.output or args.no_edit or args.no_render
        ):
            raise MasterError(
                "arguments", "validate-render does not accept project-edit options"
            )
        if modes > 1:
            raise MasterError(
                "arguments", "doctor, analysis and validation modes are exclusive"
            )
        if args.analyze_only and (args.no_edit or args.no_render or args.output):
            raise MasterError(
                "arguments",
                "analyze-only cannot be combined with editing/output options",
            )
        if args.duration:
            timing.duration_frames(args.duration, profile["render"]["sample_rate"])
        if args.doctor:
            result = doctor(args, profile)
        elif args.validate_render:
            target = (
                timing.duration_frames(args.duration, profile["render"]["sample_rate"])
                if args.duration
                else None
            )
            result = audio.validate(
                args.validate_render,
                profile,
                target,
                shortfall_frames=(
                    timing.DURATION_ALLOWANCE_SECONDS * profile["render"]["sample_rate"]
                    if target is not None and not args.exact_duration
                    else 0
                ),
            )
            result["requested_duration"] = (
                float(args.duration) if args.duration else None
            )
            result["duration_allowance_seconds"] = (
                timing.DURATION_ALLOWANCE_SECONDS
                if args.duration and not args.exact_duration
                else 0
            )
            result["duration_shortfall_seconds"] = (
                max(0, float(args.duration) - result["duration"])
                if args.duration
                else None
            )
            result["status"] = "validated" if result["valid"] else "failed"
            if args.json:
                print(json.dumps(result, allow_nan=False))
            else:
                print(
                    "Render validation "
                    + (
                        "passed"
                        if result["valid"]
                        else "failed: " + ", ".join(result["errors"])
                    )
                )
            return 0 if result["valid"] else 2
        else:
            if args.project is None:
                raise MasterError(
                    "arguments",
                    "provide project.rpp, --doctor, or --validate-render WAV",
                )
            result = process(args, profile)
        if args.json:
            print(json.dumps(result, allow_nan=False))
        elif result["status"] == "complete":
            print(
                f"Ad master complete\n\nDuration:   {result['duration']:.3f} s\nLoudness:   {result['lufs']:.2f} LUFS\nTrue peak:  {result['true_peak_db']:.2f} dBTP\nAdjustment: {result['adjustment_seconds']:+.3f} s\nStretch:    0.0%\nRender:     {result['render']}\nListening:  pending"
            )
            if args.duration:
                print(
                    f"Requested:  {result['requested_duration']:.3f} s\n"
                    f"Shortfall:  {result['duration_shortfall_seconds']:.3f} s"
                )
        elif result["status"] == "ready":
            print(
                "Admaster ready: REAPER "
                + result["reaper_version"]
                + ", stock plugins and dependencies verified"
            )
        elif result["status"] == "prepared":
            print("Project prepared (not rendered or validated): " + result["project"])
        else:
            print(json.dumps(result, indent=2))
        return 0
    except Exception as e:
        result = {
            "status": "failed",
            "code": getattr(e, "code", "internal"),
            "message": str(e),
            "needs_intervention": True,
        }
        if args.json:
            print(json.dumps(result))
        else:
            print(f"admaster: {result['code']}: {e}", file=sys.stderr)
        if args.verbose:
            import traceback

            traceback.print_exc(file=sys.stderr)
        return 2
