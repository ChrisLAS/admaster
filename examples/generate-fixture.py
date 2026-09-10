#!/usr/bin/env python3
"""Usage: nix develop -c python examples/generate-fixture.py /new/temp/directory"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
from fixtures import generate

if len(sys.argv) != 2:
    raise SystemExit("usage: generate-fixture.py NEW_DIRECTORY")
output = Path(sys.argv[1]).expanduser()
output.mkdir(parents=True, exist_ok=False)
print(generate(output))
