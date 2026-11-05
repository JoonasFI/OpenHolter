# Changelog

🇫🇮 [Suomeksi](CHANGELOG.fi.md)

OpenHolter has two version numbers: the **app version** (below) and the **analysis version**, which changes when beat analysis results can change.
Recordings are always analysed from the raw data, so a new analysis version also applies to old recordings.

Figures are sensitivity / precision. Weakened results are listed as carefully as improved ones. Full method and per-record tables: [docs/VALIDATION.en.md](docs/VALIDATION.en.md).

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
