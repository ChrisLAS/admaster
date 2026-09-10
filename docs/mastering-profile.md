# Evidence and profile policy

## What was actually approved

The source was a clean, continuous mono 24-bit 44.1 kHz take. The original project
had one track, three items, two crossfades, no active automation, bypassed track
ReaEQ/ReaComp/ReaLimit, and an active master ReaLimit. Item gains were unity and
routing was centered to the master. The original project was 95.223831 seconds;
its source was 96.351202 seconds. Its prior FLAC included a one-second render tail.

The first master used 15 pause edits plus a 2.3533% pitch-preserving speed increase.
The listener reported a robotic/generated quality. Restoring original speed and
using 20 pause edits produced the approved result. That is direct listener evidence
for **zero automatic time stretching**, not merely a conservative guess.

Approved reference measurements: 90.000000 seconds, -19.21 LUFS mono, -1.30 dBTP,
4.7 LU loudness range, 3,969,000 samples. A 320 kbps mono MP3 derived from this WAV
measured -19.21 LUFS and -1.29 dBTP. MP3 is an optional delivery conversion; the
canonical automatic output remains the WAV and editable project.

## Deterministic sound

| Stage | Approved setting |
| --- | --- |
| ReaEQ HP | 55 Hz, default 2-octave bandwidth |
| ReaEQ body bell | 440 Hz, -1.25 dB, 1.4 octaves |
| ReaEQ presence bell | 2.5 kHz, +0.7 dB, 1.5 octaves |
| Shelves | Disabled |
| ReaComp | -25 dB threshold, 2:1, 6 dB knee |
| Detector | 5 ms RMS, 90 Hz high-pass, 20 kHz low-pass |
| Attack/release | 15/120 ms; no automatic makeup/release; no pre-comp |
| Track output gain | +11.92 dB initial value, after track FX |
| Master ReaLimit | -1.3 dB threshold and ceiling, reference true-peak/performance state, 15 ms release setting |
| Other processing | No gate, denoiser, de-esser, saturation, pitch shift or stretching |
| Render | 44.1 kHz, mono, PCM 24-bit, dither; no added render tail |

True-peak mode is not an ordinary automatable ReaLimit parameter. The pinned
REAPER 7.79 does not successfully support the newer named `TRUEPEAK` setter.
The driver therefore loads the approved, sanitized **48-byte VST state** through
`TrackFX_SetNamedConfigParm(..., "vst_chunk_program", ...)`, then applies exposed
parameters. It reads the state back and checks the version and true-peak flag.
An incompatible future state version fails explicitly instead of assuming success.
`reaper/presets/realimit-reference.b64` contains only plugin settings and zeroed
UI geometry; no private audio, paths, credentials, license or project identifiers.
A default ReaLimit alone does not reproduce the reference. Independently measure
the WAV. No whole-project binary patching or GUI automation is involved.

The profile uses normalized stock-ReaComp API scales verified in REAPER 7.79:
ratio `(ratio-1)/99`, attack `ms/500`, release `ms/5000`, RMS `ms/100`, knee `dB/24`.
A particularly easy mistake is setting RMS to 5 instead of .05: that produces
500 ms, not 5 ms. ReaLimit threshold is `(60+dB)/72`, ceiling `(24+dB)/24`.
Tests and FX readback protect these mappings during updates.

## Source-dependent decisions

The CLI measures the unprocessed edited timeline with original item gains/fades,
but bypassed track/master FX and unity track/master gain. It retains existing
item boundaries and evaluates quiet interiors. Head/tail excess is removed first;
then longest eligible gaps are shortened proportionally up to available capacity.
It stops once the target is feasible instead of trimming every pause.

Default guards include a -50 dBFS sample-peak quiet threshold, gap length at least
330 ms, at least 200 ms retained quiet space, at most 65% reduction per gap,
24 new cuts/minute, and at most 12% total duration reduction. Speech's 95th-percentile
10 ms RMS must sit at least 20 dB above the cut threshold. Cuts cannot span an
existing item boundary. Typical new crossfades are 8 ms; sub-16 ms adjustments use
a shorter crossfade that fits inside the removed quiet interval.

A trimmed terminal item may recover up to 140 ms of source only when its end is
within 500 ms of that same source's end. This carries over the reference's recovered
word tail. This is bounded look-ahead, not generation or arbitrary padding. The
existing take is never reconstructed from alternate performances. `--no-edit`
disables this recovery as well as pause/edge edits.

Output gain starts at the approved +11.92 dB and is adjusted by measured loudness,
within explicit profile bounds and a limited number of renders. A separate attenuated
pre-limiter render checks that maximum 10 ms RMS reduction stays below 6 dB and
that reduction over 3 dB affects at most 2% of active windows. The approved reference
was approximately 3.68 dB maximum and 0.125% over 3 dB. Tone is not
automatically redesigned. The same parameters do not suit every voice/microphone;
unexpected noise, sibilance, plosives, dynamics or tone require listening and an
intentional profile/source adjustment.

The automated pause map is **not** a frozen copy of the reference's 20 hand-selected
cuts. It applies the learned constraints to the current timeline. Reproducing the
approved sound does not imply byte-identical renders or identical pause choices.

## Updating deliberately

Copy the full profile for experiments, preserve the standard, and render into a
new job directory. Compare equal-loudness candidates by ear, then run the complete
checks. Only promote a change after listening approval; document the reason and
measurements. `max_stretch_percent` is fixed at zero and nonzero values are rejected.
Do not relax it as an automatic fallback.

References: [REAPER ReaScript API](https://www.reaper.fm/sdk/reascript/reascripthelp.html)
and [REAPER effects guide](https://www.reaper.fm/userguide/REAPEREffectsGuide2021.pdf).
Parameter choices above come from the approved local reference, not an internet preset.
