# Changelog

🇫🇮 [Suomeksi](CHANGELOG.fi.md)

OpenHolter has two version numbers: the **app version** (below) and the **analysis version**, which changes when beat analysis results can change.
Recordings are always analysed from the raw data, so a new analysis version also applies to old recordings.

Figures are sensitivity / precision. Weakened results are listed as carefully as improved ones. Full method and per-record tables: [docs/VALIDATION.en.md](docs/VALIDATION.en.md).

## 0.5.3: tidier log

- While resting, the state stays "resting" instead of flipping to "searching" and back every five seconds (needless log lines and flicker in the interface).
- macOS's momentary "Bluetooth device is turned off" is logged as a short warning instead of a full traceback. Scanning resumes in 5 seconds as before.

## 0.5.2: an unworn strap is let go

- Fixed: the computer kept the link to an unworn strap open, and the strap went on streaming ECG for hours, which drained its battery overnight. Now the strap is let go after 2 minutes without skin contact when nothing is being recorded, and it is not reconnected for 3 minutes so it can fall asleep. When the strap is put on, the connection and automatic recording start as before (with up to about 3 minutes' delay if that happens during the rest). A recording started by hand always keeps the link open. Settings `release_unworn_s` and `rest_after_release_s`.

## 0.5.1: Windows fixes

Thanks to koskrik, who tested OpenHolter on Windows 11 and reported the bug with a fix ([#1](https://github.com/JoonasFI/OpenHolter/issues/1)).

- Fixed: `openholter run` crashed on Windows right at start (`NotImplementedError`), because asyncio's signal handling works only on macOS and Linux. Windows now uses a plain signal handler, so Ctrl+C stops the program cleanly.
- Fixed: the background process for the analysis and the PDF report would have crashed on Windows, because `os.nice` exists only on Unix.
- `openholter doctor` no longer shows a CoreBluetooth error on Windows and Linux. Only macOS asks for Bluetooth permission.

## 0.5.0: the viewer

The analysis version is still 6: extra-beat counts and classes do not change.

- ECG playback in the recording view: play and pause (also with the space bar), speeds 1×, 2×, 5×, 10× and 30×, and an optional stop at every extra beat and symptom mark.
- A dashed centre line in the ECG view with the exact time above it, to a tenth of a second.
- PDF report strips now include runs (at most 6, longest first) and couplets (at most 4, spread through the recording).
- A posture circle at the bottom of the ECG view: its arrow shows which way the chest faces, seen from the foot end, and turns smoothly.
- "Slow at findings" playback option: 1× from one second before to one second after each finding, with a smooth slow-down and speed-up.
- **New viewer** (`#/viewer`): the whole recording on one screen of about 15 inches. Numbered findings with filters and go-to-number,
  details at the centre line (heart rate, RR, beat class, prematurity), 3D posture, whole-night posture, heart-rate and RR tracks (RR as
  dots or a density map), a zoom ladder whole night → 10 min → 2 min → ECG, beat classes and RR intervals on the ECG, calipers, gain
  5/10/20 mm/mV, an analysis summary row, beat shapes (beats grouped by QRS shape), eye-saver mode, an auto-hiding top bar and
  keyboard shortcuts.
- The analysis saves the time of every beat to a file of its own. For recordings analysed earlier, the beats are found once, the
  first time the recording is opened in the viewer.
- The beat-shape limits were set on the author's own H10 recordings (one night and four short recordings). The grouping is for display
  only and changes no counts or classes.

## 0.4.2: the beat detector recovers from artefact spikes

- **Serious bug fixed (0.4.0 and 0.4.1):** artefact spikes while the strap was being put on could raise the beat detector's threshold for good, so that no beats were found in the rest of the recording. It was found on a real H10 recording: zero beats in a 7,000-beat recording. The raw data was not affected.
- The levels are now re-estimated when no beat has come for 3 seconds and a QRS-like peak shows in the last seconds.
- Validation: AFDB sensitivity 80.9 → 80.7 %. Other published figures round to the same values. The analysis version is still 6, so if you ran 0.4.0 or 0.4.1, delete `sessions/*/cache/analysis-v6.json` to have your recordings analysed again.

## 0.4.1: faster analysis of long gaps

- Fixed: the beat detector in 0.4.0 slowed down sharply on long stretches without beats, for example when the strap was off. It now searches back at most 5 seconds.
- Results did not change: all validation results for MIT-BIH, INCART, SVDB and AFDB are identical to 0.4.0. Only the app version and run times differ, so the published result files were not regenerated. AFDB analysis time fell from 747 s to 197 s.

## 0.4.0: analysis version 6

The clean test means data that was opened only after the parameters were locked: SVDB (78 recordings) and AFDB (23 recordings, 233 hours).

**Improved**

| | Dataset | Version 5 | Version 6 |
|---|---|---:|---:|
| Beat (QRS) sensitivity | MIT-BIH | 97.4 % | **99.9 %** |
| Beat (QRS) sensitivity | SVDB, clean test | 99.2 % | **99.9 %** |
| Typical single SVES, sensitivity | SVDB, clean test | 63.1 % | **90.8 %** |
| Atrial fibrillation, precision | AFDB, clean test | 95.2 % | **99.1 %** |
| Overall VES, sensitivity | MIT-BIH (seen data, probably optimistic) | 68.0 % | **82.4 %** |

**Did not improve or got worse**

| | Dataset | Version 5 | Version 6 |
|---|---|---:|---:|
| Overall VES | SVDB, clean test | 61.9 / 82.2 % | 59.6 / 79.5 % |
| Beat (QRS) precision | SVDB, clean test | 99.9 % | 99.4 % |
| Atrial fibrillation, sensitivity | AFDB, clean test | 83.3 % | 80.9 % |
| Recordings with at least half of the AF found | AFDB, clean test | 21 / 23 | 18 / 23 |
| Atrial fibrillation, precision | MIT-BIH, per beat | 87.1 % | 75.6 % |

Overall SVES improved only a little on the clean test (49.4 / 76.6 → 53.6 / 75.1 %), so overall VES and SVES counts remain indicative.

**Changed**

- New QRS detector: the threshold follows the latest beats, with search-back over long gaps and T-wave rejection.
- Atrial fibrillation episodes now require that no repeating P wave is seen, as well as an irregular rhythm.
- Validation readers and command-line options for SVDB and AFDB.

**Good to know**

- The detection limits have only been tested on Holter recordings, not yet on real H10 data.
- SVDB and AFDB have now been seen, so the next round needs a new clean test dataset.
- The result files in `docs/validation/` were generated just before this version number was set, so they say `openholter_version` 0.3.0. They are identified by `analysis_version` 6.

## 0.3.0: first public version, analysis version 5

- Recording from the Polar H10: ECG 130 Hz, accelerometer 50 Hz and RR intervals, with automatic start and stop.
- Beat analysis: VES and SVES, couplets, runs and bigeminy, irregular rhythm episodes, posture and HRV.
- Web interface, trends, symptom markers, posture calibration, trash and settings.
- PDF report with the full ECG.
- Finnish and English in the interface and the PDF.
- Open validation against MIT-BIH and INCART following ANSI/AAMI EC57.
