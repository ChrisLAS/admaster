"""Deterministic non-speech test signal; not an audio-quality listening reference."""

from pathlib import Path

import numpy as np
import soundfile as sf


def generate(directory):
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    sr = 44100
    rng = np.random.default_rng(7)
    wave = []
    for _ in range(8):
        t = np.arange(sr * 2) / sr
        envelope = np.minimum(1, t * 30) * np.minimum(1, (2 - t) * 30)
        voiced = (
            0.10 * np.sin(2 * np.pi * 140 * t)
            + 0.05 * np.sin(2 * np.pi * 280 * t)
            + 0.015 * rng.normal(size=len(t))
        ) * envelope
        wave.extend([voiced, rng.normal(0, 1e-5, size=sr // 2)])
    sf.write(root / "source.wav", np.concatenate(wave), sr, subtype="PCM_24")
    (root / "source.rpp").write_text(
        '<REAPER_PROJECT 0.1 7 1\n <TRACK\n NAME Dialogue\n NCHAN 2\n MAINSEND 1\n <ITEM\n POSITION 0\n LENGTH 20\n VOLPAN 1 0 1 -1\n PLAYRATE 1 0 0 -1\n <SOURCE WAVE\n FILE "source.wav"\n >\n >\n >\n>\n'
    )
    return root / "source.rpp"
