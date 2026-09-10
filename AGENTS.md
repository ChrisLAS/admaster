# admaster

Canonical private ad-read workflow for Nix Linux. The profile comes from an
approved REAPER master; normal jobs need orchestration, not new EQ decisions.

## Run a job

```sh
./scripts/bootstrap --json              # once on a new host; Nix + REAPER/plugin check
./bin/admaster /path/to/project.rpp --duration 90 --json
```

Or enter `nix develop`, then use `admaster project.rpp --duration 90 --json`.
Works identically from Codex CLI, OpenCode, Hermes, or a shell. No LLM/API keys.
Use an absolute input path and an optional **new** `--output /path/to/job` directory.
Never store recordings inside this repository or commit job directories.

## Operating contract

- Supported: one mono dialogue track, one continuous WAV/FLAC source, existing
  splits/crossfades, unity playback rates. Stock ReaEQ/ReaComp/ReaLimit source FX
  are supported. Active automation, alternate takes, complex routing, other FX,
  stereo sources, and source overruns stop for review.
- The tool preserves originals and copies media into a portable derived job.
  It runs isolated REAPER on Xvfb; it never controls the user's live REAPER session.
- Standard profile: `profiles/ad-read.toml`. **Original speed only.** Even 2.35%
  pitch-preserving compression sounded robotic in the reference. Do not introduce
  stretching to make a duration fit. `timing_capacity` means pause edits cannot
  safely meet the request; explain the available reduction and obtain a revised
  target or an explicitly reviewed manual edit.
- Use `--analyze-only --json` for read-only unprocessed timeline analysis.
  `--no-edit` preserves timing while mastering. `--no-render` prepares a project;
  it is **not** a finished/validated render.
- Success requires exit 0, `status == "complete"`, and
  `validation.complete == true`. Report duration, LUFS, true peak, zero stretch,
  and output paths from JSON. Do not claim audition or subjective approval from
  numerical validation. The accepted reference does not pre-approve future reads.
- On nonzero exit read `report.json` and `work/` in the output directory.
  Do not silently relax safety thresholds, truncate words, pad long silence,
  install random plugins, or rerun over an existing job. Use a new output path.
  `docs/agent-workflow.md` maps failures to interventions.

## Architecture / changes

`admaster/`: CLI, strict project preflight, audio/timing plans, independent QC.
`reaper/`: native edits, stock FX, rendering; `profiles/`: stable settings and
bounded source-dependent adjustments. `nix/`: packaging/module/checks.

Read `docs/mastering-profile.md` before changing the sound or safety policy.
Keep routine decisions deterministic; agent prompts must not duplicate DSP logic.
Edit code, profiles, tests and docs here; input projects/media and credentials stay
external. Never modify `/etc/nixos`, activate NixOS, or touch a live REAPER session.

## Verify repository changes

```sh
nix flake check                         # unit tests + real headless synthetic render
nix develop -c python -m unittest discover -s tests -v
nix run . -- --doctor --json
```

Stage newly added implementation files before flake evaluation (Git flakes omit
untracked files). For a release, also clone into a fresh directory and follow the
README quick start. Keep GitHub visibility private; never push private audio,
API keys, REAPER licenses, state caches, or host-specific paths.
