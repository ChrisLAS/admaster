# Agent workflow

Routine path: read `AGENTS.md`, run bootstrap once on a new host, then invoke
`admaster project.rpp --duration 90 --json`. Parse JSON and exit status, not log prose.
No agent-specific settings or credentials are required by admaster.

`complete` means the technical checks passed; mention listening honestly. `prepared`
means a project exists but the final WAV has not been rendered/verified. `analyzed`
means the input was inspected without retained outputs. A failed job may contain
candidate WAVs; these are not deliverables.

| Failure | Next action |
| --- | --- |
| `dependency`, `reaper_protocol`, `reaper_timeout` | Bootstrap/doctor, then inspect REAPER logs and external licensing; use pinned dependencies |
| `profile` | Compare the complete TOML with the standard; do not invent extra keys |
| `missing_media`, `source_changed` | Locate the correct recording or wait for copying/syncing to finish; never substitute a different take silently |
| `unsupported_project` | Inspect the named unsupported state; derive a simple dialogue project manually if authorized |
| `source_level`, `source_clipping`, `source_silence` | Review audio; the automatic clean-read workflow cannot diagnose/repair every source |
| `timing_capacity`, `timing_limit`, `duration_too_long` | Report achievable reduction; request a revised target or reviewed manual edit; never enable stretching or cut copy silently |
| `duration_no_edit` | Exact duration conflicts with preserving timing; explain the conflict |
| `gain_limit`, `limiter_load`, `validation` | Inspect `work/gain-passes.json`, `work/validation.json`, and loudness logs; listen before changing profile limits |
| `output_exists` | Choose a fresh job path; preserve previous work |

A manual edit must remain in a derived project with the original recoverable. Use
`--no-edit` if timing has already been approved, and validate any manually rendered
WAV with `admaster --validate-render ... --duration ... --json`. A render-only check
validates file properties; it does not inspect the corresponding project or prove
that speech was preserved.

For repository changes, run `nix flake check`, inspect the diff, and repeat the
fresh-checkout workflow. New profiles or DSP changes need equal-loudness listening
approval in addition to tests. Root `AGENTS.md` is the cross-agent entry point;
this file supplies detail only when routine processing fails.
