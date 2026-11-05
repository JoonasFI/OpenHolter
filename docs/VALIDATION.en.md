# Validation of the beat analysis: MIT-BIH and INCART

🇫🇮 [Suomeksi](VALIDATION.md)

This page describes how OpenHolter's beat and extra-beat analysis has been tested, on which data and with what result.
The weaknesses are reported too, including the places where the new version is worse than the old one. You can rerun
the test yourself and should get a bit-for-bit identical result.

**Latest version:** analysis version 6 (`openholter/beats.py`), tested 5 November 2026, see [Analysis version 6](#analysis-version-6-latest). Analysis version 5 was tested on 3 November 2026.
The results of the previous version (analysis version 4) are [kept unchanged below](#analysis-version-4-earlier-result-unchanged).

**Raw results and per-record tables** (`docs/validation/`):

| Database | v5 | v4 |
|---|---|---|
| MIT-BIH (also DS1/DS2 separately) | [`mitdb-v5-results.json`](validation/mitdb-v5-results.json) · [`mitdb-v5-records.md`](validation/mitdb-v5-records.md) | [`mitdb-v4-results.json`](validation/mitdb-v4-results.json) · [`mitdb-v4-records.md`](validation/mitdb-v4-records.md) |
| INCART | [`incartdb-v5-results.json`](validation/incartdb-v5-results.json) · [`incartdb-v5-records.md`](validation/incartdb-v5-records.md) | [`incartdb-v4-results.json`](validation/incartdb-v4-results.json) · [`incartdb-v4-records.md`](validation/incartdb-v4-records.md) |

*The per-record tables have Finnish column headings: Tallenne = record, Kytkentä = lead, Huom. = note,
VES/SVES viite = reference count, löydetty = found, Väärä hälytys normaalista = false alarms on normal beats.*

> OpenHolter is not a medical device. The validation describes the algorithm's performance on known research
> data, not whether it is suitable for diagnosis. It is not.

## Analysis version 6 (latest)

Version 6 was made because v5's SVES detection did not generalise and QRS detection limited everything else. The v5 and
v4 sections below are unchanged.

### Results

Parameters were tuned on DS1 only and locked. All datasets were then run once, and nothing was changed afterwards.
**Only SVDB and AFDB are a clean test**: they were downloaded for this round and opened only after locking. DS2 and INCART
results were seen with v5, and the causes found there guided the design of v6, although no numbers were tuned on them.
Their improvement is therefore probably optimistic. Values are Se / +P in per cent.

| Dataset | QRS v5 → v6 | VES v5 → v6 | SVES v5 → v6 |
|---|---:|---:|---:|
| **SVDB, 78 records (clean test)** | 99.2 / 99.9 → **99.9 / 99.4** | 61.9 / 82.2 → **59.6 / 79.5** | 49.4 / 76.6 → **53.6 / 75.1** |
| DS2 (seen) | 97.9 / 99.9 → 99.9 / 99.7 | 70.6 / 93.1 → 82.6 / 91.8 | 10.9 / 43.4 → 12.7 / 48.2 |
| INCART (seen) | 95.3 / 99.6 → 99.8 / 99.0 | 59.3 / 89.7 → 78.1 / 89.9 | 70.1 / 57.1 → 87.6 / 66.3 |
| DS1 (tuning data, optimistic) | 97.3 / 99.9 → 99.8 / 99.8 | 65.8 / 92.0 → 82.2 / 90.0 | 70.4 / 83.6 → 74.1 / 82.1 |
| MIT-BIH all | 97.4 / 99.9 → 99.9 / 99.7 | 68.0 / 92.5 → 82.4 / 90.8 | 30.4 / 68.3 → 32.9 / 69.4 |

Single extra beats (both neighbours normal), sensitivity; any extra-beat mark counts as found:

| Dataset | VES all single | VES typical | SVES all single | SVES typical |
|---|---:|---:|---:|---:|
| SVDB (clean test) | 74.2 → 74.0 | 89.4 → 88.5 | 52.7 → **71.5** | 63.1 → **90.8** |
| MIT-BIH all | 76.1 → 90.9 | 79.4 → 96.0 | 61.6 → 73.3 | 72.8 → 90.0 |
| INCART (seen) | 65.7 → 85.7 | 73.7 → 92.3 | 77.1 → 95.7 | 79.5 → 98.0 |

Atrial fibrillation and irregular rhythm:

| Dataset and measure | v5 | v6 |
|---|---:|---:|
| **AFDB, 23 records, 233 h, second by second (clean test): Se / +P** | 83.3 / 95.2 | **80.9 / 99.1** |
| AFDB: non-AF time classified correctly (specificity) | 97.1 | 99.5 |
| AFDB: records where at least half of the AF was found | 21 / 23 | 18 / 23 |
| MIT-BIH all, by beat: Se / +P | 82.4 / 87.1 | 93.4 / 75.6 |
| INCART, by beat: Se / +P (2 AF records) | 0 / 0 | 27.6 / 44.7 |
| SVDB: records with an episode reported (no rhythm annotations, so correctness cannot be judged) | 25 | 13 |

Runs Se / +P: SVDB 26.6 / 45.3 → 28.0 / 41.5; DS2 2.4 / 57.1 → 5.3 / 39.1; INCART 24.1 / 33.6 → 57.2 / 51.3.
Per-record tables are in `docs/validation/{mitdb,incartdb,svdb,afdb}-v6-*` and `{svdb,afdb}-v5-*` (v5 was run on the new
datasets for comparison).

### Interpretation

- **Beat detection is now at a good level** on all datasets (Se 99.8–99.9 %). There are slightly more false detections than
  before, especially on INCART (+P 99.0 %).
- **Typical single SVES improved clearly on the clean test** (63 → 91 %), while the overall SVES figure improved only a little.
  For an ordinary user this is the most important improvement.
- **False atrial fibrillation alarms fell on the clean test** (+P 95 → 99 %, specificity 97.1 → 99.5 %). The price is slightly
  lower sensitivity, and over half of the AF is missed in five records out of 23.
- **VES did not improve on the clean test** but got slightly worse (61.9 / 82.2 → 59.6 / 79.5). The improvement elsewhere was
  large (MIT-BIH 68 → 82 %). The weaker SVDB result shows that the VES improvement does not generalise to all data.

SVES and VES counts are still indicative only. Treatment decisions must not be based on them.

### What changed

1. **QRS detector.** v5's threshold was fixed per 8 s block, so one tall beat raised it enough to hide neighbouring beats and wide
   VES. v6's threshold follows the last beats (threshold = noise level + 0.4 × (signal level − noise level); signal level is the
   median of the last 8 peaks). There is also Pan–Tompkins style search-back (when a gap exceeds 1.5 times the usual, the highest
   rejected peak is rechecked at half the threshold) and T-wave rejection (within 420 ms, under half of the previous peak).
2. **Atrial fibrillation requires the P wave to be absent.** Irregularity alone confused frequent atrial extra beats with AF.
   v6 averages the −240…−60 ms segments of nearby beats in two halves. A repeating P wave makes the halves alike. The P wave counts
   as visible when their correlation is at least 0.75 and its height at least 5 % of the QRS. An AF episode needs no visible P wave
   and irregularity above 0.05 (v5 used irregularity above 0.10 alone).
3. **Tuning and testing.** Tuned on DS1, about 40 variants tried. A wider template window was tried and not adopted. Readers for SVDB
   and AFDB and a simulator test for frequent atrial extra beats were added.

The analysis result fields are the same as in v5, so the user interface needs no changes.

### Known weaknesses

- **One fault can reject a whole run.** In record 865 (SVDB) a run of about 1,000 beats went entirely unmarked in v6, although v5 found
  it: found SVES dropped from 1,740 to 677. This one record lowered SVDB's overall SVES sensitivity by about 10.6 percentage points. The rule accepts a sequence as a
  whole. The exact trigger has not been established.
- **False AF episodes on MIT-BIH:** +P fell from 87 to 76 %; for example record 200 has 819 beats in episodes without AF. In record 222
  false SVES increased (9 → 71).
- **INCART's AF:** only part of records I49 and I50 is found (Se 28 %).
- **Records where an atrial beat is the dominant rhythm** (MIT 232, SVDB 822) go almost entirely undetected.
- **More false VES marks,** especially in noisy records (INCART I54 156 → 267, I01 273 → 337).
- **AF detection has been tested only on Holter leads.** The P-wave height in the H10's chest lead
  can differ, so the 5 % limit must be checked on real H10 data.
- **No untouched datasets remain.** SVDB and AFDB have now been seen as well. The next round needs a new test dataset.

## Summary: v5 compared with v4

Analysis version 5 was tuned **only** on the DS1 half of MIT-BIH. DS2 and INCART were run only after all parameters
had been locked, and nothing was changed after seeing their results. The DS2 and INCART columns are therefore a true
test result; the DS1 column is not.

| Measure | v4 MIT-BIH | v5 DS1 *(tuning data)* | v5 DS2 *(test)* | v5 MIT-BIH all | v4 INCART | v5 INCART *(test)* |
|---|---:|---:|---:|---:|---:|---:|
| QRS Se / +P | 97.4 / 99.9 | 97.3 / 99.9 | 97.9 / 99.9 | 97.4 / 99.9 | 95.3 / 99.6 | 95.3 / 99.6 |
| VES Se | 49.0 | 65.8 | **70.6** | **68.0** | 49.2 | **59.3** |
| VES +P | 93.1 | 92.0 | 93.1 | 92.5 | 95.2 | 89.7 |
| SVES Se | 20.4 | 70.4 | **10.9** | 30.4 | 83.3 | **70.1** |
| SVES +P | 40.0 | 83.6 | **43.4** | 68.3 | 66.5 | **57.1** |
| All extra beats Se / +P | 43.1 / 82.9 | 68.5 / 93.7 | 51.2 / 90.1 | 59.6 / 92.1 | 54.8 / 94.0 | 62.6 / 88.0 |
| Irregular rhythm (atrial fibrillation), beats Se / +P | – | 99.5 / 87.0 | 75.9 / 87.2 | 82.4 / 87.1 | – | 0 / 0 * |
| Runs (≥ 3 in a row) Se / +P | – | 44.3 / 65.9 | 2.4 / 57.1 | 13.4 / 64.6 | – | 24.1 / 33.6 |

All figures are percentages. Se = sensitivity (how many of the true ones were found), +P = positive predictivity, or precision
(how many of the marks were correct). The v4 INCART result was produced afterwards with the v4 code and the same validation
code for comparison. \* Neither of INCART's two atrial fibrillation recordings was recognised, and in 12 other recordings
the program reported an irregular-rhythm episode that is not in the reference (see below).

**Interpretation in short.**

- **VES (ventricular extra beats) improved on every database.** Sensitivity rose from 49 % to 68 % on MIT-BIH and from
  49 % to 59 % on INCART, mainly because the shape of every beat is now checked, not only of premature beats.
  The price is in precision: on INCART it fell from 95 % to 90 %, on MIT-BIH from 93.1 % to 92.5 %.
- **SVES (supraventricular extra beats): the result is mixed, and v5 is not clearly better.**
  On the tuning data (DS1) the improvement was large (Se 29 → 70 %, +P 46 → 84 %), but **it did not carry over to the test data.**
  On DS2 precision improved (36 → 43 %) but sensitivity got worse (16 → 11 %). On INCART both sensitivity
  (83 → 70 %) and precision (66 → 57 %) got worse. This is a typical sign of overfitting: a rule that looked good on DS1
  does not generalise. The reasons are broken down [below](#where-v5-is-worse-than-v4).
- **Atrial fibrillation detection** works reasonably on MIT-BIH (82 % of atrial fibrillation beats were recognised,
  87 % of what was reported was real atrial fibrillation or flutter), but failed completely on INCART.
- **Reporting of runs** (≥ 3 extra beats in a row) is new and still weak: most reference runs are missed.

The SVES figures still should not be trusted. The VES figures are indicative.

## What changed in version 5 and why

The v4 validation showed five main problems (see [the v4 results](#analysis-version-4-earlier-result-unchanged)).
Each got a change. QRS detection and artefact rejection are unchanged.

1. **(a) Irregular rhythm and atrial fibrillation.** In v4 most false SVES marks came from atrial fibrillation recordings,
   because in an irregular rhythm even normal beats look premature. v5 computes, for every beat, the irregularity of the
   rhythm over a 31-interval window: the median difference of consecutive intervals relative to the local median interval.
   Only intervals between normally shaped beats are used, and the difference is computed at lags 1, 2 and 3, taking the smallest.
   This way bigeminy (every other beat an extra beat) and trigeminy do not look irregular, because their pattern repeats.
   When the value stays above 0.10 for at least 30 seconds, the episode is reported as a finding of its own (`af_episodes`,
   "irregular rhythm, compatible with atrial fibrillation"). The episode is widened by 10 s at each end, because the moving median
   crosses the threshold only when half of the window is irregular. **No SVES marks are made during an episode.**
   VES marks are still made from the beat's shape.
2. **(b) The prematurity threshold follows local variability.** v4 always required a 20 % shorter interval. v5 computes the local
   spread of the ratio between RR interval and reference (median absolute deviation, MAD, over 31 beats; VES beats and the beats
   after them are left out so that they do not inflate the spread). The required prematurity is 3 × spread, but at least 12 % and at
   most 20 %. In a steady rhythm a beat 12 % early is enough; in a varying rhythm 20 % is required as before. In addition, for an SVES
   the interval must shorten suddenly: below 90 % of the previous interval, so that a gradual sinus acceleration does not look like an extra beat.
3. **(c) SVES does not require a full pause.** A supraventricular extra beat usually "resets" the sinus node, so the interval after
   it is only of normal length, not longer. v4 required a pause above 105 %. v5 requires the next interval to be at least as long
   as the premature interval and at least 85 % of the reference. The latter condition rejects the case where an extra detection
   (for example a T wave) splits one interval in two. A premature VES needs the next interval to be at least 95 % of the reference.
4. **(d) Runs.** Consecutive premature beats are handled as one sequence. The reference is locked at the start of the sequence and is
   the larger of the centred median and the median of the preceding beats only; otherwise a long tachycardia would drag its own
   reference down and not look premature. A sequence of at least 3 beats is reported as a run (`runs`) if its rate is above 100/min
   (the usual definition of SVT/VT). A slower "run" is more likely a change of the underlying rhythm, so only beats that are clearly
   VES by shape are marked in it. If a sequence has both VES-shaped and SVES-shaped beats, the normally shaped ones are left out,
   except when SVES-shaped beats outnumber VES-shaped ones more than two to one: then a mildly different beat is taken as an aberrant SVES.
5. **(e) VES by shape alone.** v4 checked the shape only of premature beats, so a late VES (common at a slow heart rate) was missed.
   v5 compares every beat with the median template of nearby normal beats (±40 beats, two passes). A beat is a VES even without
   prematurity if its correlation with the template is below 0.70 even at the best ±40 ms shift and the QRS is at least 40 ms wider
   or 1.5 × larger. A beat is also a VES if the correlation at the R peak is negative, below 0.80 at the best shift, and the QRS is
   wider. Both neighbouring beats must also fit the template. The shift is needed because the detector places the beat at the
   largest deflection, which in an RS-shaped complex can be either the R or the S wave; without it normal beats looked "differently
   shaped" in record 215 (about 100 false VES marks during development). The neighbour condition rejects cases where the template or
   the signal is locally off.

New fields in the analysis result (`analysis-v5.json`, `ectopy`): `af_episodes`, `af_seconds`, `runs` and `ves_morphology_only`.
In addition, every extra beat (`details`) has the fields `premature`, `run` and `in_af`.

## Avoiding overfitting: how the tuning was done

- **Split.** MIT-BIH was divided into the established training and test halves of de Chazal et al. (2004). The paced records
  102, 104, 107 and 217 belong to neither.
  DS1 (tuning): 101, 106, 108, 109, 112, 114, 115, 116, 118, 119, 122, 124, 201, 203, 205, 207, 208, 209, 215, 220, 223, 230.
  DS2 (test): 100, 103, 105, 111, 113, 117, 121, 123, 200, 202, 210, 212, 213, 214, 219, 221, 222, 228, 231, 232, 233, 234.
  INCART is test data in full.
- **What was done with DS1.** All rules and thresholds were developed by looking at DS1's errors record by record (most in 106,
  119, 124, 201, 203, 208, 209, 215 and 223). About 40 parameter variants were tried on DS1 one at a time or in small combinations.
  This is tuning, and that is why the DS1 result is optimistic.
- **Locking.** The parameters were locked (`openholter/beats.py`, section "v5 parameters"). After locking, one change was made before
  the test data was run: the 10 s widening of atrial fibrillation episodes. It came from a simulator test and was checked only on DS1.
  After that, DS2, all of MIT-BIH and INCART were run once, and the code was not changed based on the results. The only later code
  change was removing a development-time diagnostics hook, and the results were checked to be bit-for-bit identical.
- **A weakness in the split.** DS1 has only two atrial fibrillation recordings (201, 203). The threshold for atrial fibrillation
  detection therefore came from very little data, which shows in the test result.

## Detailed results (v5)

### MIT-BIH

| | DS1 *(tuning)* | DS2 *(test)* | All 44 |
|---|---:|---:|---:|
| VES reference beats | 3,109 | 2,587 | 5,696 |
| VES Se / +P | 65.8 / 92.0 | 70.6 / 93.1 | 68.0 / 92.5 |
| SVES reference beats | 760 | 1,556 | 2,316 |
| SVES Se / +P | 70.4 / 83.6 | 10.9 / 43.4 | 30.4 / 68.3 |
| Without atrial fibrillation records: VES Se / +P | 64.7 / 95.1 | 72.2 / 95.5 | 68.0 / 95.3 |
| Without atrial fibrillation records: SVES Se / +P | 83.8 / 84.3 | 7.7 / 42.7 | 33.1 / 73.3 |
| VES, typical single, Se | 80.7 | 78.4 | 79.4 (v4: 76.0) |
| SVES, typical single, Se | 76.9 | 66.7 | 72.8 (v4: **81.8**) |
| VES, all single, Se | 76.8 | 75.6 | 76.1 (v4: 56.5) |
| SVES, all single, Se | 70.3 | 50.9 | 61.6 (v4: 55.7) |

*Typical single* means the same as in v4: both neighbours are normal beats, the preceding interval is below 80 % and the next
above 105 % of the local median. In the subgroups any extra-beat mark counts as found.

**DS2's SVES figure is dominated by record 232.** It holds 1,121 of DS2's 1,556 SVES beats. The record has sick sinus syndrome,
and supraventricular beats are the prevailing rhythm almost all the time. They are not premature relative to anything, so neither
version finds them (v4 39, v5 33). Without record 232, DS2's SVES is **v4 Se 49.7 % / +P 32.3 %, v5 Se 31.5 % / +P 38.2 %.**
Counted this way too, v5's sensitivity is clearly worse.

Confusion matrix, all 44 non-paced MIT-BIH records (v5; v4 in brackets):

| Reference ↓ / OpenHolter → | VES | SVES | no mark |
|---|---:|---:|---:|
| N (normal) | 188 (121) | 150 (538) | 71,526 |
| S (SVES) | 44 (39) | 705 (472) | 1,567 |
| V (VES) | 3,874 (2,789) | 149 (156) | 1,673 |
| F (fusion) | 28 (3) | 8 (3) | 576 |
| Q | 3 (2) | 1 (0) | 11 |
| no reference beat | 52 (42) | 19 (10) | |

On MIT-BIH, 465 VES marks were made from shape alone (without prematurity). Of these, 429 were true VES beats, 24 normal,
5 fusion beats and 7 others.

### INCART

[St Petersburg INCART 12-lead Arrhythmia Database](https://physionet.org/content/incartdb/1.0.0/): 75 half-hour 12-lead
recordings from 32 patients, 257 Hz. Lead II was used, resampled 257 → 130 Hz.

| | v4 | v5 |
|---|---:|---:|
| QRS Se / +P (141,828 beats) | 95.3 / 99.6 | 95.3 / 99.6 |
| VES Se / +P (16,317 reference beats) | 49.2 / 95.2 | 59.3 / 89.7 |
| SVES Se / +P (1,599 reference beats) | 83.3 / 66.5 | 70.1 / 57.1 |
| All extra beats Se / +P | 54.8 / 94.0 | 62.6 / 88.0 |
| VES, typical single, Se | 71.3 | 73.7 |
| SVES, typical single, Se | 97.4 | 79.5 |
| Runs Se / +P (145 reference runs, 134 of them VES runs) | – | 24.1 / 33.6 |

957 (60 %) of INCART's SVES beats are in two recordings of the same patient, I33 and I34, in which about a third of the beats
are atrial extra beats. INCART's SVES figure therefore largely reflects these two recordings.

### Irregular rhythm (atrial fibrillation)

The measure compares reference beats that fall in the cardiologists' atrial fibrillation or flutter episodes (rhythm annotations
`(AFIB` and `(AFL`) with beats that fall in an episode reported by the program.

| | Reference atrial fibrillation records | Recognised beats (Se) | Reported that is correct (+P) | Episodes in records without atrial fibrillation in the reference |
|---|---:|---:|---:|---|
| MIT-BIH DS1 | 2 (201, 203) | 99.5 % | 87.0 % | 1 record (207: one 66 s episode containing no reference beats)* |
| MIT-BIH DS2 | 5 (202, 210, 219, 221, 222) | 75.9 % | 87.2 % | none |
| INCART | 2 (I49, I50) | **0 %** | **0 %** | 12 records, 38 min in total |

\* Probably at the record's ventricular flutter episode. Per-record figures are in
[`mitdb-v5-records.md`](validation/mitdb-v5-records.md).

- On MIT-BIH some of the "false" atrial fibrillation beats are other irregular atrial rhythms, for example the atrial tachycardia
  and nodal rhythm of records 201 and 222. Exactly there an SVES mark would be correct, so SVES sensitivity suffers
  (202: v4 37 → v5 12 found, 222: 126 → 59).
- In INCART's two atrial fibrillation recordings the ventricular response is unusually even. The irregularity value stayed at a
  median of 0.04 against the threshold of 0.10, so they were not recognised.
- On INCART the false episodes come from recordings with very frequent extra beats or runs (I33, I34, I42, I47 and I31).
  Frequent atrial extra beats make the rhythm genuinely irregular, and v5 takes it for atrial fibrillation. The SVES beats of
  I33 and I34 then go unmarked (v4 915, v5 659 found).

### Runs

A reference run means at least three consecutive S or V beats. A run by the program counts as found if it overlaps a reference run in time (±150 ms).

| | Reference runs (S / V / mixed) | Found Se | Program's runs that are correct (+P) |
|---|---:|---:|---:|
| MIT-BIH DS1 | 61 (20 / 32 / 9) | 44.3 % (S 85 %, V 31 %) | 65.9 % |
| MIT-BIH DS2 | 170 (153 / 16 / 1) | 2.4 % (S 0 %, V 25 %) | 57.1 % |
| INCART | 145 (9 / 134 / 2) | 24.1 % (S 33 %, V 23 %) | 33.6 % |

Most of DS2's S runs are in record 232 (see above), and the atrial tachycardias of record 222 fall into irregular-rhythm episodes.
VES runs are often missed because in ventricular tachycardia the beats resemble each other, so the local "normal template" gets mixed up,
or the run is slower than 100/min (accelerated idioventricular rhythm, e.g. record 124).

### Ablation: what the SVES suppression during atrial fibrillation does

Below is the same v5 without the SVES suppression during atrial fibrillation episodes (`AF_THR` set so high that no episodes arise).
**This is reporting, not a choice.** Choosing the version from this table would be tuning on test data, and that has not been done.

| SVES Se / +P | v5 | v5 without suppression | v4 |
|---|---:|---:|---:|
| MIT-BIH DS1 | 70.4 / 83.6 | 72.6 / 53.8 | 28.6 / 46.0 |
| MIT-BIH DS2 | 10.9 / 43.4 | 19.2 / 28.2 | 16.4 / 36.1 |
| INCART | 70.1 / 57.1 | 87.3 / 58.8 | 83.3 / 66.5 |

The suppression improves precision a lot on MIT-BIH, but on INCART it only lowers sensitivity. The other SVES changes of v5
((b), (c) and (d)) raise sensitivity on every database but lower precision on INCART (66.5 → 58.8 %). The suppression has practically
no effect on the VES results.

### Where v5 is worse than v4

- **SVES sensitivity on DS2** (16.4 → 10.9 %; without record 232, 49.7 → 31.5 %) and **on INCART** (83.3 → 70.1 %). The main cause is
  the SVES suppression during atrial fibrillation episodes in recordings with atrial tachycardia, atrial flutter or very frequent atrial
  extra beats (MIT 202, 222; INCART I33, I34).
- **SVES precision on INCART** (66.5 → 57.1 %). New false SVES marks come among others from I35 (118, ventricular couplets and fusion
  beats in tachycardia), I42 (220), I62, I67 and I06–I07.
- **VES precision on INCART** (95.2 → 89.7 %) and slightly on MIT-BIH (93.1 → 92.5 %). Normal beats marked as VES by shape alone numbered
  176 on INCART. False VES marks increased most in I01 (80 → 273), I54 (42 → 156), I04 (13 → 57), I03 (10 → 50) and I40 (6 → 34).
- **SVES, typical single** (MIT 81.8 → 72.8 %, INCART 97.4 → 79.5 %). The suddenness requirement, the handling of mixed sequences in
  the run rules, and the atrial fibrillation suppression also remove some of the "easy" SVES beats.
- **Atrial fibrillation detection did not generalise to INCART** (0 % in two atrial fibrillation recordings, false episodes in 12 recordings).

**Conclusion.** The VES changes (e) and (b) appear to generalise. The SVES changes did not generalise to the test data. Further
development should be done with a new tuning dataset, and the result confirmed on a third dataset that has not been touched before.
DS2 and INCART, now used as test data, can no longer serve as a clean test if parameters are tuned on them.

## Datasets

**[MIT-BIH Arrhythmia Database](https://physionet.org/content/mitdb/1.0.0/)** (Moody & Mark 2001), PhysioNet,
licence Open Data Commons Attribution 1.0. The standard test set for arrhythmia analysis.

- 48 half-hour two-channel Holter recordings from 47 people (Beth Israel Hospital, 1975–79).
- 360 Hz, 11 bits, about 110,000 beats, each classified independently by two cardiologists.
- Selected on purpose to contain many arrhythmias, so it is harder than an ordinary healthy person's recording.

**[St Petersburg INCART 12-lead Arrhythmia Database](https://physionet.org/content/incartdb/1.0.0/)**
(Tihonenko et al. 2008), PhysioNet, licence Open Data Commons Attribution 1.0.

- 75 half-hour excerpts of Holter recordings from 32 patients undergoing tests for coronary artery disease.
- 12 leads, 257 Hz, WFDB signal format 16. Beat annotations made automatically and corrected by hand.
- Atrial fibrillation is present in only two recordings; SVES beats are concentrated in a few recordings.

Neither dataset is distributed with OpenHolter. They are downloaded from PhysioNet, and the files are checked against PhysioNet's
`SHA256SUMS.txt` (MIT-BIH: 704 files, INCART: 230 files, all matched). In INCART's `SHA256SUMS.txt` the hash and name are separated
by a single space, so `shasum -c` does not read it directly (see [Run it yourself](#run-it-yourself)).

**[MIT-BIH Supraventricular Arrhythmia Database](https://physionet.org/content/svdb/1.0.0/)** (SVDB; Greenwald et al. 1990):
78 half-hour two-channel records, 128 Hz, first channel, same EC57 rules.
**[MIT-BIH Atrial Fibrillation Database](https://physionet.org/content/afdb/1.0.0/)** (AFDB; Moody & Mark 1983): 23 records of about
10 hours, 250 Hz, first channel. The beat annotations are unaudited, so only the rhythm is scored, second by second, against the
`(AFIB` and `(AFL` annotations, leaving out the first and last minute. Both are licensed under Open Data Commons Attribution 1.0, and
the files matched `SHA256SUMS.txt` (416 and 155 files).

## Method

The test follows **ANSI/AAMI EC57** (testing of arrhythmia algorithms) as in v4:

1. **Signal.** MIT-BIH: the first channel (MLII in 44 records, V5 in records 102 and 104). INCART: lead II. The signal is converted
   to microvolts with the header's gain and baseline and resampled to 130 Hz (the Polar H10 rate) by FFT. The analysis runs
   **exactly the same code as for real recordings**. There are no per-record settings.
2. **Reference.** The cardiologists' beat labels are grouped into the EC57 classes:
   N (N, L, R, e, j), S or SVES (A, a, J, S), V or VES (V, E), F (fusion) and Q (paced, unclassifiable).
3. **Comparison.** A detection matches a reference beat if they are at most 150 ms apart, one to one. Comparison starts at
   5 minutes (EC57). The last minute is left out because the app always ignores it (strap being taken off). Ventricular
   fibrillation and flutter episodes are excluded from the QRS statistics (EC57).
4. **Paced records** (MIT-BIH 102, 104, 107, 217) are included in the QRS statistics but not in the extra-beat statistics (EC57).
   INCART has no paced records.
5. **Computation.** Everything is computed from the total over all beats ("gross"), not as an average of records.
   Sensitivity Se = TP / (TP + FN), precision +P = TP / (TP + FP). The denominator of VES and SVES precision includes all of the
   program's VES or SVES marks, also those that hit fusion beats (as in v4).
6. **Irregular rhythm and runs** are not EC57 measures; they are defined here (see the sections above). Program runs that fall in
   ventricular flutter episodes are counted as they are (record 207).

The reader and scoring code is in [`openholter/validation.py`](../openholter/validation.py). The WFDB file formats (header, signal
formats 212 and 16, MIT annotations) are read with about 70 lines of our own code, so there is no third-party library between the
data and the result.

## Limitations

- **Different device, different lead.** MIT-BIH and INCART were recorded with Holter devices using limb leads (MLII, II). The Polar H10
  measures one lead across the chest. The QRS shape and signal quality differ, so the result describes the algorithm rather than
  directly how it works with the H10.
- **Datasets weighted towards arrhythmias.** For an ordinary healthy person with occasional single extra beats, the situation is
  closest to the "typical single" figures.
- **Small subsets.** SVES beats and atrial fibrillation are concentrated in a few records (MIT 232, 222, 202; INCART I33, I34, I49, I50).
  A single record can change the total by tens of percentage points.
- **The test data has now been used.** DS2 and INCART were untouched until v5's tuning. If their results are used for further
  development, they are no longer clean test sets.
- **The simulator test** (`tests/test_pipeline.py`) checks that the new rules work in the cases they were made for: an SVES without
  a pause, an SVT run, an atrial fibrillation episode and a late VES. It says nothing about accuracy on real data.

## Analysis version 4 (earlier result, unchanged)

Below is the result published for version 4 as it was (tested 3 November 2026, all of MIT-BIH, no DS1/DS2 split).
Raw results: [`mitdb-v4-results.json`](validation/mitdb-v4-results.json), [`mitdb-v4-records.md`](validation/mitdb-v4-records.md).

### Summary

| Measure | Result | What it means |
|---|---:|---|
| QRS detection, sensitivity (Se) | **97.4 %** | 97.4 % of all heartbeats were found |
| QRS detection, precision (+P) | **99.9 %** | 99.9 % of the detected beats were real |
| VES, precision (+P) | **93.1 %** | when the program says "VES", it is right 93 % of the time |
| VES, sensitivity (Se) | **49.0 %** | half of all VES beats are found |
| VES, typical single* | **76.0 %** | a VES followed by a pause in a normal rhythm |
| SVES, precision (+P) | **40.0 %** | most SVES marks are false alarms |
| SVES, sensitivity (Se) | **20.4 %** | |
| SVES, typical single* | **81.8 %** | |

\* *Typical single:* both neighbours normal beats, the preceding interval below 80 % and the next above 105 % of the local median.
This is exactly the pattern the method looks for. In the subgroups any extra-beat mark (VES or SVES) counts as found.

**Interpretation in short.** Beats are found reliably. When the program marks a beat as a ventricular extra beat (VES), the mark is
usually correct; without atrial fibrillation the precision is 97.3 %. The program does, however, **undercount**: about half of the
VES beats are missed, because the method only looks for a premature beat followed by a pause. SVES detection is weak and its figures
should not be trusted.

### Dataset

As above (MIT-BIH Arrhythmia Database, 48 recordings, 704 files checked against `SHA256SUMS.txt`).

### Method

As above, with these differences: only MIT-BIH, signal resampled 360 → 130 Hz, nothing tuned per record, and the algorithm was not
changed based on this test. The WFDB formats were read with about 60 lines of our own code.

### Detailed results

#### QRS detection (48 records)

| | Reference beats | Found (TP) | Missed (FN) | Extra (FP) | Se | +P |
|---|---:|---:|---:|---:|---:|---:|
| All | 87,521 | 85,240 | 2,281 | 68 | 97.4 % | 99.9 % |
| Without atrial fibrillation/flutter | 72,352 | 70,772 | 1,580 | 55 | 97.8 % | 99.9 % |

Despite beats rejected as artefacts, 97.3 % of the reference beats remain in the analysis. The weakest records are 228 (71 %),
104 (83 %, paced, V5) and 203 (85 %, multiform VES and ventricular tachycardia). They have low or highly variable QRS complexes that are
missed at 130 Hz bandwidth with a fixed threshold. Known algorithms reach over 99 % sensitivity on this dataset at the full 360 Hz,
so there is room for improvement.

#### Extra beats (44 records, non-paced)

Confusion matrix: rows are the cardiologist's class, columns OpenHolter's mark.

| Reference ↓ / OpenHolter → | VES | SVES | no mark |
|---|---:|---:|---:|
| N (normal) | 121 | 538 | 71,205 |
| S (SVES) | 39 | 472 | 1,805 |
| V (VES) | 2,789 | 156 | 2,751 |
| F (fusion) | 3 | 3 | 606 |
| Q | 2 | 0 | 13 |
| no reference beat | 42 | 10 | |

| | Se | +P | Se, typical single | Se, all single |
|---|---:|---:|---:|---:|
| VES | 49.0 % | 93.1 % | 76.0 % (2,783 beats) | 56.5 % (4,151) |
| SVES | 20.4 % | 40.0 % | 81.8 % (378) | 55.7 % (632) |
| All extra beats (V + S) | 43.1 % | 82.9 % | | |
| Without atrial fibrillation: VES | 50.1 % | **97.3 %** | | |
| Without atrial fibrillation: all | 42.5 % | **96.9 %** | | |

156 VES beats (2.7 %) were marked as SVES and 39 SVES beats as VES.

#### Why beats are missed

Beats the program did not mark as extra beats at all (VES 2,751, SVES 1,802) break down as follows:

| Reason | VES | SVES |
|---|---:|---:|
| Not premature (interval less than 20 % shorter) | 874 | 149 |
| Part of a run (couplet, triplet, tachycardia or bigeminy with fusion beats) | 676 | 1,480 |
| QRS not detected at all | 703 | 105 |
| Other (e.g. distorted reference, noise) | 366 | 21 |
| No pause after (interpolated beat) | 95 | 47 |
| Rejected as artefact | 37 | 0 |

*(Computed from the rhythm of the reference annotations with a separate analysis; indicative, not part of the EC57 report.)*

- **A prematurity-based method** does not see a VES that comes after an almost normal interval, which is common at a slow heart rate.
  The beat's shape (wide QRS) would reveal it. *(Addressed in v5 by change (e).)*
- **Runs:** record 232 has over a thousand consecutive supraventricular beats. Long runs and tachycardias do not look like single extra
  beats, and v4 did not report them.
- **Atrial fibrillation:** an irregular rhythm makes even normal beats look premature. Most of the false SVES marks come from atrial
  fibrillation records (201, 202, 203, 219, 222). v4 did not detect or report atrial fibrillation.

### Limitations

As above; in addition, v4 was tested on one dataset only. Because the algorithm had not been tuned on it, the result was not overfitted.
The v4 simulator test gave almost 100 % results because the simulated extra beats were exactly the type the method looks for, which is
why testing on real data was needed.

## Run it yourself

```bash
# 1. download MIT-BIH (77 MB) and check it
curl -LO https://physionet.org/static/published-projects/mitdb/mit-bih-arrhythmia-database-1.0.0.zip
unzip mit-bih-arrhythmia-database-1.0.0.zip
cd mit-bih-arrhythmia-database-1.0.0 && shasum -a 256 -c SHA256SUMS.txt && cd ..

# 2. download INCART (564 MB) and check it (the file has a single space between hash and name)
curl -L -o incartdb.zip https://physionet.org/static/published-projects/incartdb/st-petersburg-incart-12-lead-arrhythmia-database-1.0.0.zip
unzip incartdb.zip -d incartdb
cd incartdb/files && sed 's/ /  /' SHA256SUMS.txt | shasum -a 256 -c - && cd ../..

# 3. download SVDB (55 MB) and AFDB (461 MB) the same way (the checksum file has a single space between hash and name)
curl -LO https://physionet.org/static/published-projects/svdb/mit-bih-supraventricular-arrhythmia-database-1.0.0.zip
unzip mit-bih-supraventricular-arrhythmia-database-1.0.0.zip
curl -L -o afdb.zip https://physionet.org/static/published-projects/afdb/mit-bih-atrial-fibrillation-database-1.0.0.zip
unzip afdb.zip -d afdb

# 4. run the validation (a few minutes, AFDB holds 233 hours)
python -m openholter validate --mitdb mit-bih-arrhythmia-database-1.0.0 --incartdb incartdb/files \
  --svdb mit-bih-supraventricular-arrhythmia-database-1.0.0 --afdb afdb/files --out docs/validation
```

The command writes `docs/validation/<dataset>-v<analysis version>-results.json` and `-records.md`. The MIT-BIH JSON contains the
overall result (`summary`) and DS1 and DS2 separately (`summary_ds1`, `summary_ds2`).

If you change the analysis, rerun the validation and include the changed files in `docs/validation/` in your pull request, also when
the result gets worse. Tune only on DS1 and say what you tuned.

## References

- Moody GB, Mark RG. The impact of the MIT-BIH Arrhythmia Database. *IEEE Eng Med Biol* 20(3):45–50 (2001).
- Tihonenko V, Khaustov A, Ivanov S, Rivin A, Yakushenko E. St Petersburg INCART 12-lead Arrhythmia Database.
  PhysioNet (2008). doi:10.13026/C2V88N.
- Greenwald SD, Patil RS, Mark RG. Improved detection and classification of arrhythmias in noise-corrupted
  electrocardiograms using contextual information. *Computers in Cardiology* 17:461–464 (1990). (SVDB)
- Moody GB, Mark RG. A new method for detecting atrial fibrillation using R-R intervals.
  *Computers in Cardiology* 10:227–230 (1983). (AFDB)
- Goldberger AL et al. PhysioBank, PhysioToolkit, and PhysioNet. *Circulation* 101(23):e215–e220 (2000).
- ANSI/AAMI EC57: Testing and reporting performance results of cardiac rhythm and ST segment measurement algorithms.
- de Chazal P, O'Dwyer M, Reilly RB. Automatic classification of heartbeats using ECG morphology and heartbeat
  interval features. *IEEE Trans Biomed Eng* 51(7):1196–1206 (2004).
- Pan J, Tompkins WJ. A real-time QRS detection algorithm. *IEEE Trans Biomed Eng* 32(3):230–236 (1985).
