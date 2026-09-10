# Architecture

The CLI is a small Python pipeline; REAPER performs the actual audio edits, FX,
and rendering. FFmpeg and NumPy/SoundFile independently validate the output.
Everything is supplied by a pinned Nix closure. There is no network/API requirement
after dependencies are built, and no Codex/OpenCode/Hermes-specific runtime.

1. **Preflight:** parse balanced RPP chunks read-only, reject unsupported features,
   check source existence, layout, rates and source bounds. No arbitrary project is
   silently reduced to one track. Limit input duration/size to bound resource use.
2. **Preserve:** exclusively create a new job directory. Copy media with hashes and
   save the unchanged original project text. Rewrite only source FILE paths in the
   derived copy. ReaScript owns all other changes; the source project is never opened
   by the automation process.
3. **Prepare:** isolated REAPER bypasses track/master FX and gains, retains item
   gains/fades, optionally recovers a short terminal tail, and renders the dry timeline.
4. **Plan:** calculate sample-accurate edge trims and low-level gap edits. Fail if
   conservative capacity is insufficient. Original voice speed is an invariant.
5. **Apply:** native splits/deletes/ripple position changes, crossfades, profile FX,
   explicit sample rate/channel format and exact render bounds. Read plugin state back.
6. **Render/adjust:** invoke REAPER `-renderproject`, measure output loudness, make
   bounded output-gain corrections, and rerender. Every attempt is retained in `work/`.
7. **Verify:** decode all samples, measure integrated LUFS/true peak, check format,
   duration, clipping, suspicious silence and every edit boundary. Render a diagnostic with the limiter bypassed at -24 dB, measure limiter activity,
   restore the saved master settings, and check source hashes.
   A JSON report declares either `complete`, `prepared`, `analyzed`, or `failed`.

REAPER runs under Xvfb with `-newinst -cfgfile` and a temporary resource directory.
Render destinations are resolved per job: REAPER 7.79 batch rendering did not
reliably honor a relative destination. Media references remain relative.
The derived project resets hardware monitoring to outputs 1/2 rather than carrying
an old host’s interface-channel assignment. Original projects and global device
preferences are unchanged.
The process never attaches to an active instance and does not require PipeWire,
JACK, an audio interface or a desktop session. A process-group timeout terminates
only the owned REAPER/Xvfb process tree. Licensing is external and not redistributed.

`--analyze-only` uses a temporary copied job and cleans it after read-only timeline
analysis. `--no-render` still needs a temporary dry render for reliable timing
analysis; it omits the final mastered render and never claims validation completed.

Errors are nonzero with a stable short code and `needs_intervention` in JSON.
After output creation, `report.json` records failures and the working directory
retains diagnostics. Argument/preflight failures before output creation do not
leave a job directory. Existing output directories are never reused implicitly.

MP3 encoding is deliberately outside the mastering loop: codec delay/padding and
lossy peaks need separate validation. Keep WAV as the timing authority, and account
for gapless metadata when verifying a derived MP3's decoded duration.

No numerical check can guarantee word intelligibility or subjective naturalness.
Always distinguish technical validation from actual listening approval.
