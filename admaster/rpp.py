"""Read-only structural preflight; only media paths are rewritten in a derived copy.

Audio edits, FX state and render settings are always changed through ReaScript.
Unsupported state is rejected rather than silently flattened.
"""

import hashlib
import math
import shlex
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .errors import MasterError


@dataclass
class Node:
    tag: str
    header: str
    lines: list = field(default_factory=list)
    children: list = field(default_factory=list)

    def values(self, key):
        return [line.split()[1:] for _, line in self.lines if line.split()[:1] == [key]]

    def number(self, key, default=0, index=0):
        v = self.values(key)
        try:
            value = float(v[0][index]) if v else default
            if not math.isfinite(value):
                raise ValueError("non-finite field")
            return value
        except (ValueError, IndexError) as e:
            raise MasterError("project", f"invalid {key}") from e

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()


def parse(text):
    stack = []
    root = None
    for index, raw in enumerate(text.splitlines()):
        line = raw.strip()
        if line.startswith("<"):
            node = Node(line[1:].split()[0], line)
            if stack:
                stack[-1].children.append(node)
            elif root is not None:
                raise MasterError("project", "multiple project roots")
            else:
                root = node
            stack.append(node)
        elif line == ">":
            if not stack:
                raise MasterError("project", "unbalanced project chunk")
            stack.pop()
        elif stack:
            stack[-1].lines.append((index, line))
        elif line:
            raise MasterError("project", "data outside project chunk")
    if stack or root is None or root.tag != "REAPER_PROJECT":
        raise MasterError("project", "not a balanced REAPER project")
    return root


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def inspect(path):
    path = Path(path).expanduser().resolve()
    if path.suffix.lower() != ".rpp" or not path.is_file():
        raise MasterError("project", "expected an existing .rpp project")
    if path.stat().st_size > 8 * 1024 * 1024:
        raise MasterError("project", "project exceeds the supported ad-read size")
    text = path.read_text(encoding="utf-8-sig")
    root = parse(text)
    tracks = [n for n in root.children if n.tag == "TRACK"]
    if len(tracks) != 1:
        raise MasterError(
            "unsupported_project",
            "requires one dialogue track; isolate an ad-read project first",
        )
    tr = tracks[0]
    if (
        root.number("PLAYRATE", 1) != 1
        or tr.number("MAINSEND", 1) != 1
        or tr.values("AUXRECV")
    ):
        raise MasterError(
            "unsupported_project", "non-unity project rate or custom routing"
        )
    if tr.number("MUTESOLO", 0) != 0 or root.number("MASTERMUTESOLO", 0) != 0:
        raise MasterError("unsupported_project", "muted track/master")
    if root.number("MASTER_VOLUME", 0, 1) != 0:
        raise MasterError("unsupported_project", "master pan requires review")
    if (
        tr.number("VOLPAN", 0, 1) != 0
        or tr.number("IPHASE") != 0
        or tr.number("PLAYOFFS") != 0
    ):
        raise MasterError(
            "unsupported_project",
            "track pan, polarity or playback offset requires review",
        )
    if (
        tr.number("NCHAN", 2) != 2
        or tr.number("FREEMODE") != 0
        or tr.number("ISBUS") != 0
    ):
        raise MasterError(
            "unsupported_project",
            "lanes, folders or multichannel routing require review",
        )
    sources = []
    all_nodes = list(root.walk())
    allowed_chunks = {
        "REAPER_PROJECT",
        "TRACK",
        "ITEM",
        "SOURCE",
        "VST",
        "FXCHAIN",
        "MASTERFXLIST",
        "NOTES",
        "TAKENOTES",
        "PROJBAY",
        "EXTENSIONS",
        "RECORD_CFG",
        "APPLYFX_CFG",
        "RENDER_CFG",
        "METRONOME",
        "TEMPOENVEX",
        "MASTERPLAYSPEEDENV",
    }
    for node in all_nodes:
        if node.tag not in allowed_chunks:
            raise MasterError(
                "unsupported_project",
                f"{node.tag} needs manual review (automation/take FX/etc.)",
            )
        if node.tag in ("TEMPOENVEX", "MASTERPLAYSPEEDENV") and node.number("ACT") != 0:
            raise MasterError("unsupported_project", "active tempo/playrate automation")
        if node.tag == "EXTENSIONS" and (node.children or node.lines):
            raise MasterError(
                "unsupported_project", "extension project state requires manual review"
            )
        if node.tag == "PROJBAY" and node.children:
            raise MasterError(
                "unsupported_project", "project-bay media requires review"
            )
        if node.tag == "VST":
            tokens = shlex.split(node.header[1:])
            if len(tokens) < 3 or Path(tokens[2]).name not in (
                "reaeq.vst.so",
                "reacomp.vst.so",
                "realimit.vst.so",
            ):
                raise MasterError(
                    "unsupported_project",
                    "only stock ReaEQ/ReaComp/ReaLimit source FX supported",
                )
            if node.children or any("PARMENV" in line for _, line in node.lines):
                raise MasterError(
                    "unsupported_project", "FX automation requires review"
                )
        if node.tag == "SOURCE":
            if node.header not in ("<SOURCE WAVE", "<SOURCE FLAC") or node.children:
                raise MasterError(
                    "unsupported_project", "only direct mono WAV/FLAC sources supported"
                )
            files = [(i, text) for i, text in node.lines if text.startswith("FILE ")]
            if len(files) != 1:
                raise MasterError(
                    "missing_media", "source FILE entry missing or ambiguous"
                )
            i, line = files[0]
            tokens = shlex.split(line)
            if len(tokens) != 2 or any(c in tokens[1] for c in '\n\r"'):
                raise MasterError("project", "unsupported source filename")
            source = (path.parent / tokens[1]).resolve()
            if not source.is_file():
                raise MasterError("missing_media", f"missing source: {source.name}")
            sources.append((i, source))
    if len(set(s for _, s in sources)) != 1:
        raise MasterError(
            "unsupported_project", "requires items from one continuous source recording"
        )
    items = [n for n in tr.children if n.tag == "ITEM"]
    if not items or len(items) > 200:
        raise MasterError("unsupported_project", "expected 1–200 dialogue items")
    layout = []
    for item in items:
        if (
            len([n for n in item.children if n.tag == "SOURCE"]) != 1
            or len(item.values("NAME")) > 1
        ):
            raise MasterError("unsupported_project", "alternate takes require review")
        if (
            item.number("PLAYRATE", 1) != 1
            or item.number("PLAYRATE", 0, 2) != 0
            or item.values("SM")
            or item.values("STRETCHMARKER")
        ):
            raise MasterError(
                "unsupported_project",
                "existing pitch/time changes: restore natural source first",
            )
        if (
            item.number("MUTE") != 0
            or item.number("VOLPAN", 0, 1) != 0
            or item.number("CHANMODE") != 0
        ):
            raise MasterError("unsupported_project", "muted/panned/remapped item")
        if item.number("VOLPAN", 1) <= 0 or item.number("VOLPAN", 1) > 4:
            raise MasterError(
                "unsupported_project", "extreme item gain requires review"
            )
        start, length, offset = (
            item.number("POSITION"),
            item.number("LENGTH"),
            item.number("SOFFS"),
        )
        if not 0 < length <= 600 or start < 0 or offset < 0:
            raise MasterError(
                "unsupported_project",
                "invalid item bounds or recording longer than ten minutes",
            )
        layout.append({"position": start, "length": length, "offset": offset})
    layout.sort(key=lambda i: i["position"])
    if layout[0]["position"] > 1e-6:
        raise MasterError(
            "unsupported_project", "first item must begin at project time zero"
        )
    for a, b in zip(layout, layout[1:]):
        overlap = a["position"] + a["length"] - b["position"]
        if overlap < -1e-6 or overlap > 0.1:
            raise MasterError(
                "unsupported_project", "gaps or overlaps over 100 ms require review"
            )
    duration = max(i["position"] + i["length"] for i in layout)
    if duration > 600:
        raise MasterError("unsupported_project", "project exceeds ten-minute limit")
    return {
        "path": path,
        "text": text,
        "sources": sources,
        "items": layout,
        "duration": duration,
        "original_track_gain": tr.number("VOLPAN", 1),
    }


def copy_project(info, output):
    output = Path(output)
    media = output / "media"
    media.mkdir()
    lines = info["text"].splitlines()
    copied = {}
    hashes = {}
    for index, source in info["sources"]:
        if source not in copied:
            digest = sha256(source)
            name = "source-" + digest[:12] + source.suffix.lower()
            shutil.copy2(source, media / name)
            if sha256(media / name) != digest:
                raise MasterError("copy", "source changed while copying")
            copied[source] = "media/" + name
            hashes[name] = digest
        lines[index] = '        FILE "' + copied[source] + '"'
    # Save-relative source rewrite only; REAPER owns all other serialization.
    project = output / "master.rpp"
    project.write_text("\n".join(lines) + "\n")
    shutil.copy2(info["path"], output / "original.rpp.backup")
    return project, hashes
