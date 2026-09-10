# admaster

Private, Nix-packaged podcast ad mastering in REAPER. One command creates an
editable project and lossless WAV, tightens pauses at **original voice speed**,
and checks duration, loudness, true peak, media integrity, and edit boundaries.

The standard sound is extracted from an approved real ad master: gentle ReaEQ,
2:1 ReaComp, ReaLimit in the reference true-peak mode, and mono -19 LUFS delivery.
No gate, denoiser, saturation, or automatic de-esser. No time stretching.

## Quick start

On a Nix Linux host with GitHub access to this private repository:

```sh
gh repo clone ChrisLAS/admaster
cd admaster
./scripts/bootstrap --json
./bin/admaster ~/ads/example/project.rpp --duration 90
```

`bootstrap` enables `nix-command flakes` for that invocation, builds the locked
package, and checks REAPER/stock plugins on a private virtual display. It is safe
to repeat and does not edit system configuration. If necessary enable flakes for
interactive commands in your existing Nix configuration; or use `./bin/admaster`,
which passes the flags per invocation. Install Nix first via
[the official instructions](https://nixos.org/download/).

No manual Python packages, ReaPack, SWS, GUI clicking, or audio device is required.
REAPER is proprietary: use its permitted evaluation or your own license. Existing
`~/.config/REAPER/reaper-reginfo2.ini`, or an external `REAPER_LICENSE_FILE`, is linked
only into a temporary private runtime and never copied into job output or Git.
An empty-home, unregistered evaluation environment is covered by the tests.

For an interactive environment, use `nix develop` and then `admaster ...`.
On hosts without flakes enabled, use
`nix --extra-experimental-features 'nix-command flakes' develop`.
The bootstrap and `./bin/admaster` wrappers already supply these flags.

Without entering a shell (flakes enabled):

```sh
nix run . -- ~/ads/example/project.rpp --duration 90 --json
```

Input scope: **one mono track, one continuous WAV/FLAC recording**, with existing
splits, fades and item gains. Input sample rates may differ; output defaults to
44.1 kHz mono 24-bit WAV. Only stock ReaEQ/ReaComp/ReaLimit input chains are accepted.
More complex projects fail explicitly; isolate the dialogue or review them first.

## Agent use

Launch either agent from this repository:

```sh
codex
# or
opencode
```

Then: `Master ~/ads/example/project.rpp using the standard profile. Final runtime: 90 seconds.`

The root `AGENTS.md` supplies the complete operating contract. For Hermes, set the
working directory to the clone and use the same instruction, or have it execute:

```sh
nix run . -- ~/ads/example/project.rpp --duration 90 --json
```

A tiny optional instruction adapter is in [docs/hermes.md](docs/hermes.md).
All agents use the same implementation; none need to recreate mastering logic.

## Outputs and options

Default job directory: `project-admaster/` beside the input; existing directories
are never overwritten. Use `--output /new/job/directory` to choose another.

```text
project-admaster/
├── master.rpp              # editable, self-contained with relative media paths
├── master.wav              # validated mono 24-bit master
├── media/                  # copied original source, identified by checksum
├── original.rpp.backup     # unchanged input text; for restoration/audit
├── profile.toml            # exact profile used
├── report.json             # concise status + validation + provenance
└── work/                   # cut plan, FX readback, intermediate WAVs and logs
```

Move/copy the **whole job directory** to keep the derived media/project portable.
The render destination is resolved for the job’s current location. After moving a
job, rerun `admaster moved/master.rpp --no-edit --output /new/job` to generate a
new delivery, or update the destination in REAPER before a manual render. The
unchanged original backup uses the input's original relative paths; restore it
beside the original media, rather than opening it as the derived project.

| Option | Effect |
| --- | --- |
| `--duration 90` | Target 90 seconds; an existing read from 89–90 seconds keeps its runtime. Longer reads are shortened to 90 seconds using safe pause edits |
| `--exact-duration` | With `--duration`, require the requested runtime to within one sample; no one-second allowance |
| `--profile path.toml` | Complete custom profile; strict schema/safety validation |
| `--analyze-only` | Read-only analysis of unprocessed project timeline; no retained output |
| `--no-edit` | Preserve timing; apply the standard processing chain |
| `--no-render` | Prepare editable project; report `prepared`, never `complete` |
| `--validate-render master.wav --duration 90` | Independent checks of an existing WAV; nonzero on failure |
| `--doctor` | Dependency/plugin/writable-runtime check; optional project accessibility check |
| `--verbose` | REAPER diagnostic logs on stderr |
| `--json` | One JSON result on stdout; agents should inspect status and validation |

With no duration, only eligible leading/trailing silence is tightened. If a target
requires deleting speech, excessive cuts, extending the read, or speeding up the
voice, the command fails. A meter cannot prove naturalness: `auditory_review` stays
`not_performed` until a human or capable listening tool actually auditions the result.

The one-second allowance applies to all requested durations, including 60-second
and 90-second slots, and to `--no-edit` and `--validate-render`. A 59.433-second
read can therefore satisfy `--duration 60` without padding or slowing speech.
Reads more than one second short still stop for review. Longer reads target the
requested runtime; the allowance does not permit overruns or relax pause-edit guards.
JSON reports include `requested_duration`, actual `duration`,
`duration_allowance_seconds`, and `duration_shortfall_seconds`. Internal render QC
still checks the chosen plan to within one sample. Use `--exact-duration` for strict
delivery requirements. Targets round to the nearest output sample.

## Nix installation

The flake exposes `packages.<system>.admaster`/`default`, `apps.<system>.default`,
`devShells.<system>.default`, `checks`, and `nixosModules.default`.
Linux x86-64 is tested; Linux AArch64 outputs are provided and evaluated, but require
an AArch64 builder to run their checks. Dependencies are pinned in `flake.lock`.
The flake explicitly allows only its own private package and REAPER as unfree dependencies.

Private remote execution, with SSH authentication already configured:

```sh
nix run 'git+ssh://git@github.com/ChrisLAS/admaster?ref=main' -- ~/ads/project.rpp --duration 90
```

`nix run github:ChrisLAS/admaster -- ...` also works when the **Nix fetcher** has
GitHub access. `gh auth login` alone does not give the Nix daemon that access.
Prefer cloning with `gh` and running locally, or SSH; keep any Nix GitHub token in
external credential/secret configuration, never in this repository, a command
argument, a flake URL, or `flake.lock`.

In a NixOS or Home Manager flake:

```nix
inputs.admaster.url = "git+ssh://git@github.com/ChrisLAS/admaster?ref=main";
# In a module where `inputs` and `pkgs` are in scope:
environment.systemPackages = [ inputs.admaster.packages.${pkgs.stdenv.hostPlatform.system}.admaster ];
# Home Manager instead:
# home.packages = [ inputs.admaster.packages.${pkgs.stdenv.hostPlatform.system}.admaster ];
```

Or import `inputs.admaster.nixosModules.default` and set
`programs.admaster.enable = true`. This only installs the package; no audio services
or desktop settings are altered. Commit the consumer flake lock intentionally.

## Profiles

[profiles/ad-read.toml](profiles/ad-read.toml) is the canonical standard. The bounded
output-gain adjustment is source-dependent; EQ/compressor settings remain fixed.
The limiter loads a tiny sanitized reference state through REAPER’s VST-state
API and verifies true-peak mode. See
[the profile evidence and policy](docs/mastering-profile.md) before changing it.

## Checks and a synthetic practice run

```sh
nix flake check
nix develop -c python examples/generate-fixture.py /tmp/admaster-example
nix run . -- /tmp/admaster-example/source.rpp --duration 19 --json
```

Tests synthesize their own audio. No reference recording, transcript, or private
source project is tracked. See [architecture](docs/architecture.md) and
[agent failure handling](docs/agent-workflow.md).

## Troubleshooting

- **Private fetch fails:** clone with authenticated `gh`, or use authenticated SSH.
- **Output exists:** select a fresh `--output`; nothing is overwritten.
- **Timing capacity/limit:** inspect `work/plan.json` if present and `report.json`;
  choose a realistic target or make a reviewed manual pause edit in a derived project.
- **Unsupported project:** isolate one continuous mono dialogue track. Never flatten
  unknown routing or disable automation merely to get past the guard.
- **Source level/clipping/noise:** inspect the source; the clean-read profile is not
  a restoration tool. Fix the source in a new version rather than loosening validation.
- **REAPER timeout/plugin failure:** run `--doctor --verbose`, inspect the job's
  `work/*.log`, check REAPER licensing, and rerun with the locked Nix environment.
- **Loudness/gain/peak failure:** inspect gain-pass logs and the voice itself. Large
  source differences need engineering judgment, not ever-higher makeup gain.

Do not publish a candidate solely because a file exists. A finished technical job
must exit zero and report `status: complete` with `validation.complete: true`.
