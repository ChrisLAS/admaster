import json
import os
import signal
import subprocess
import tempfile
from pathlib import Path

from .errors import MasterError
from .profile import ROOT


def lua(value):
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (float, int)):
        return repr(value)
    if isinstance(value, str):
        return (
            '"'
            + value.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
            + '"'
        )
    if isinstance(value, dict):
        return (
            "{"
            + ",".join("[" + lua(str(k)) + "]=" + lua(v) for k, v in value.items())
            + "}"
        )
    return "{" + ",".join(lua(v) for v in value) + "}"


class Reaper:
    def __init__(self, work, verbose=False, timeout=180):
        self.work = Path(work)
        self.work.mkdir(exist_ok=True)
        self.verbose = verbose
        self.timeout = timeout
        self.temp = tempfile.TemporaryDirectory(prefix="admaster-reaper-")
        self.resource = Path(self.temp.name)
        self.ini = self.resource / "reaper.ini"
        self.ini.write_text(
            "[reaper]\nversion=7.79\naudiomode=0\nnewprojdo=0\nloadlastproj=0\nshowlastundo=0\nsaveundostatesproj=0\nmaxrecentprojects=0\n"
        )
        license_path = Path(
            os.environ.get(
                "REAPER_LICENSE_FILE",
                Path.home() / ".config/REAPER/reaper-reginfo2.ini",
            )
        ).expanduser()
        if license_path.is_file():
            (self.resource / "reaper-reginfo2.ini").symlink_to(license_path.resolve())
        self.sequence = 0

    def close(self):
        self.temp.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def run(self, args, tag):
        env = os.environ.copy()
        env.pop("WAYLAND_DISPLAY", None)
        env.pop("DISPLAY", None)
        env.update(
            {
                "HOME": str(self.resource),
                "XDG_CONFIG_HOME": str(self.resource / "config"),
                "GDK_BACKEND": "x11",
                "QT_QPA_PLATFORM": "xcb",
            }
        )
        # Private per-job REAPER profile and virtual display. Never attach to a live session.
        command = [
            "xvfb-run",
            "-a",
            "-s",
            "-screen 0 1024x768x24 -nolisten tcp",
            "reaper",
            "-newinst",
            "-cfgfile",
            str(self.ini),
            "-nosplash",
            "-ignoreerrors",
            *map(str, args),
        ]
        log = self.work / (tag + ".log")
        with log.open("w") as f:
            try:
                p = subprocess.Popen(
                    command,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    env=env,
                    cwd=self.work.parent,
                    start_new_session=True,
                )
                try:
                    code = p.wait(timeout=self.timeout)
                except (subprocess.TimeoutExpired, KeyboardInterrupt) as interrupted:
                    os.killpg(p.pid, signal.SIGTERM)
                    try:
                        p.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(p.pid, signal.SIGKILL)
                        p.wait()
                    if isinstance(interrupted, KeyboardInterrupt):
                        raise MasterError(
                            "interrupted",
                            "job interrupted; owned REAPER process stopped",
                        ) from None
                    raise MasterError(
                        "reaper_timeout",
                        f"REAPER timed out; inspect {log}. License/dialog/plugin initialization may need attention.",
                    )
            except OSError as e:
                raise MasterError("dependency", str(e)) from e
        if self.verbose:
            import sys

            print(log.read_text()[-3000:], file=sys.stderr)
        if code:
            raise MasterError("reaper", f"REAPER exited {code}; inspect {log}")

    def script(self, project, job, phases):
        self.sequence += 1
        tag = f"{self.sequence:02d}-" + ("-".join(phases))
        config = self.work / (tag + ".lua")
        result = self.work / (tag + ".json")
        job_file = self.work / (tag + "-job.lua")
        job_file.write_text("return " + lua(job) + "\n")
        script = (
            "local job=dofile("
            + lua(str(job_file))
            + ")\nlocal C=dofile("
            + lua(str(ROOT / "reaper/lib/core.lua"))
            + ")\n"
        )
        script += "local function main()\n local inventory\n"
        for phase in phases:
            script += (
                " inventory=dofile("
                + lua(str(ROOT / "reaper" / (phase + ".lua")))
                + ")(job,C)\n"
            )
        script += " return inventory\nend\n"
        script += (
            "local ok,value=xpcall(main,debug.traceback)\nC.write("
            + lua(str(result))
            + ", {ok=ok, result=ok and value or nil, error=not ok and value or nil})\n"
        )
        # Only the derived project can be saved, including a failed partial stage.
        script += "reaper.Main_SaveProject(0,false)\nreaper.Main_OnCommand(40004,0)\n"
        config.write_text(script)
        self.run([project, config], tag)
        if not result.is_file():
            raise MasterError(
                "reaper_protocol",
                f"REAPER did not execute automation; inspect {self.work / (tag + '.log')}",
            )
        data = json.loads(result.read_text())
        if not data.get("ok"):
            raise MasterError(
                "reaper_script", str(data.get("error", "unknown ReaScript failure"))
            )
        return data["result"]

    def render(self, project, path):
        if Path(path).exists():
            raise MasterError("output_exists", f"refusing to overwrite render: {path}")
        self.sequence += 1
        self.run(["-renderproject", project], f"{self.sequence:02d}-render")
        if not Path(path).is_file() or Path(path).stat().st_size < 100:
            raise MasterError(
                "render_missing", "REAPER did not produce the requested render"
            )
