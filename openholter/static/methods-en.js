"use strict";
/* Methods page in English. Keep in step with METHODS_HTML (Finnish) in app.js. */
const METHODS_HTML_EN = `
  <div class="med-box" role="note">
    <b>For research and personal use only. Not a medical device.</b>
    <p>OpenHolter is an open-source research project. It is not intended to diagnose, treat, monitor or prevent any disease, and its results do not replace a doctor's assessment. Do not change your medication or treatment based on them. OpenHolter cannot detect a heart attack and does not alert you to dangerous arrhythmias.</p>
    <p><b>If you have heart symptoms, such as chest pain or pressure, shortness of breath, fainting or dizziness, contact a doctor. In an emergency, call your local emergency number (112 in Europe, 911 in the US).</b></p>
  </div>
  <p class="hint">The methods are described so that you can judge the reliability and limits of the results yourself or with your doctor.</p>
  <details id="mittaus"><summary>Measurement</summary>
    <ul>
      <li><b>Polar H10</b> heart rate strap: single-lead ECG at 130 Hz in microvolts, accelerometer at 50 Hz (±4 G, milli-G) and the strap's own RR intervals with 1/1024 s resolution (Bluetooth Heart Rate service).</li>
      <li>Connection over Bluetooth LE with Polar's <i>Polar Measurement Data</i> (PMD) protocol. The raw Bluetooth messages are stored as they are, so the analysis can later be rerun with better methods.</li>
      <li><b>Timing:</b> sample spacing comes from the strap's own clock (about 130.0x Hz). Wall-clock time is fitted to it per connection with a linear drift correction anchored by the frames that arrived fastest (Bluetooth latency is always positive).</li>
    </ul>
  </details>
  <details id="signaali"><summary>Signal quality and display</summary>
    <ul>
      <li><b>Electrode contact</b> is assessed in 10 s windows with three measures: amplitude (1st–99th percentile range, below 150 µV = no contact), high-frequency noise (median of the derivative relative to the amplitude) and baseline wander (variation of one-second medians). The result is good, fair, poor or no contact.</li>
      <li><b>Skin contact:</b> the H10 reports in its heart rate message whether it is on the skin. A strap that is off but still connected sends noise and an invented heart rate. Periods without contact are therefore shown as <i>No skin contact</i>, their heart rate and RR intervals are left out of the analysis, and automatic recording starts only with contact and ends when there has been no contact for the timeout.</li>
      <li><b>Bluetooth level</b> combines signal strength (RSSI, dBm) with the share of ECG samples received during the last 10 seconds and the longest gap.</li>
      <li><b>Display filtering:</b> baseline wander is removed with a first-order high-pass filter: zero-phase in the recording view (0.5 Hz), real-time in the Live view (about 0.4 Hz) and by subtracting a 1 s moving average in the PDF. Filtering affects only the display; stored data is never changed.</li>
    </ul>
  </details>
  <details id="lisalyonnit"><summary>Extra beats</summary>
    <ul>
      <li><b>R peaks are detected from the ECG</b> in the style of Pan–Tompkins: band-pass (about 5–15 Hz), derivative, squaring, 150 ms moving-window integration and an adaptive threshold in 8 s blocks, 250 ms refractory period. The R peak is the largest baseline-corrected deflection near the integrated peak. The strap's own RR intervals are not used, because its detector often misses wide extra beats.</li>
      <li><b>Artefacts are rejected:</b> the first and last minute of a recording (putting the strap on and taking it off), periods without contact, Bluetooth gaps, and beats whose amplitude or surrounding (±1 s) range is more than three times the recording's typical value.</li>
      <li>A beat is <b>premature</b> when its RR interval is 12–20 % shorter than the local reference; the amount required grows with the local heart-rate variability (3 × spread). An <b>SVES</b> additionally needs a sudden shortening (below 90 % of the previous interval) and an interval after it at least as long as the premature one and at least 85 % of the reference, since a supraventricular beat is usually not followed by a full pause. A <b>VES</b> needs the next interval to be at least 95 % of the reference. The pause is <i>compensatory</i> when the two intervals add up to 1.75–2.25 times the reference. <b>Couplet</b> = two premature beats in a row, <b>run</b> = at least three in a row above 100/min.</li>
      <li><b>Shape:</b> the beat is compared with the median template of the surrounding normal beats (QRS window −80…+120 ms). If the correlation is below 0.85 or the QRS is at least 40 ms wider than the template → <b>VES</b> (probably ventricular), otherwise <b>SVES</b> (probably supraventricular). At 130 Hz one sample is 7.7 ms, so the width is a coarse estimate. In addition, every beat is compared with the template: a clearly different, wide or large QRS is a <b>VES</b> even when the beat does not come early (correlation below 0.70 even at the best ±40 ms shift, neighbouring beats fitting the template).</li>
      <li>The reference is the moving median over 31 beats of the pair means of consecutive intervals ((RR<sub>i</sub> + RR<sub>i+1</sub>) / 2). A full compensatory pause does not change the pair mean, so the reference stays correct even in bigeminy. For long runs, the reference from the preceding beats is used so that a tachycardia does not drag its own reference down.</li>
      <li><b>Irregular rhythm:</b> if successive RR intervals vary strongly and without pattern for at least 30 s (median over a 31-interval window above 10 %), the episode is reported as an irregular rhythm compatible with atrial fibrillation. This is not a diagnosis. No SVES are marked during it. Bigeminy and trigeminy do not trigger it, because their pattern repeats.</li>
      <li><b>Bigeminy run:</b> at least three premature beats on every other beat.</li>
      <li>By posture, the share of extra beats is computed from the beats that occurred in each posture, and the rate per hour is relative to the time spent in that posture.</li>
      <li><b>Limitations:</b> a single-lead chest ECG does not see every shape difference, so the VES/SVES split is indicative. About a third of VES beats are still missed, especially in ventricular tachycardia. SVES detection is unreliable: frequent atrial extra beats and atrial tachycardias can be taken for an irregular rhythm and then are not marked. Irregular-rhythm detection did not work on every test database. See <a href="#/about/validointi">Validation</a>. Without ECG, the strap's RR intervals are used as a fallback.</li>
    </ul>
  </details>
  <details id="validointi"><summary>Validation: MIT-BIH and INCART</summary>
    <ul>
      <li>The beat analysis has been tested on the <b>MIT-BIH Arrhythmia Database</b> (PhysioNet): 48 half-hour Holter recordings, about 87,000 beats, each labelled by two cardiologists. It was also tested on the St Petersburg <b>INCART</b> database (75 recordings, lead II). The test follows the ANSI/AAMI EC57 standard: classes N/S/V/F/Q, a 150 ms match window, comparison starting at 5 minutes, paced records excluded from the extra-beat statistics.</li>
      <li>The signal was resampled to 130 Hz and analysed with the same code as your own recordings. Version 5 was tuned only on half of MIT-BIH (DS1). The other half (DS2) and the INCART database (75 recordings, 257 Hz) are test data that was not used for tuning.</li>
    </ul>
    <div class="table-scroll"><table class="val-table">
      <thead><tr><th>Sensitivity / precision</th><th>MIT-BIH (44)</th><th>INCART (75)</th></tr></thead>
      <tbody>
        <tr><td>Beat (QRS) detection</td><td>97.4 / 99.9 %</td><td>95.3 / 99.6 %</td></tr>
        <tr><td>VES</td><td>68.0 / 92.5 %</td><td>59.3 / 89.7 %</td></tr>
        <tr><td>VES, without atrial fibrillation</td><td>68.0 / 95.3 %</td><td>59.2 / 89.7 %</td></tr>
        <tr><td>VES, typical single + pause</td><td>79.4 %</td><td>73.7 %</td></tr>
        <tr><td>SVES</td><td>30.4 / 68.3 %</td><td>70.1 / 57.1 %</td></tr>
        <tr><td>SVES, typical single + pause</td><td>72.8 %</td><td>79.5 %</td></tr>
        <tr><td>Irregular rhythm (atrial fibrillation), beats</td><td>82.4 / 87.1 %</td><td>0 / 0 %</td></tr>
      </tbody>
    </table></div>
    <ul>
      <li><b>Sensitivity</b> = how many of the true beats were found. <b>Precision</b> (+P) = how many of the program's marks were correct.</li>
      <li><b>Interpretation:</b> beats are found reliably. A VES mark is usually correct, and version 5 finds about two out of three VES beats (v4: half), because the shape of every beat is now checked. SVES detection is still unreliable: the improvement was large on the tuning data, but on the test data (DS2, INCART) sensitivity even dropped compared with version 4, because an irregular rhythm taken for atrial fibrillation also suppresses true SVES marks. Irregular-rhythm episodes and runs are reported but are indicative only: the two atrial fibrillation recordings in INCART were not recognised.</li>
      <li><b>Limitation:</b> MIT-BIH and INCART were recorded with Holter devices using limb leads, not with a Polar H10. The result describes the algorithm, not directly the accuracy reachable with the strap.</li>
      <li>The full report, per-record results and instructions to repeat the test: <span class="mono">docs/VALIDATION.en.md</span> in the source code. Tested version: OpenHolter 0.3.0, analysis version 5.</li>
    </ul>
  </details>
  <details id="hrv"><summary>Heart rate variability (HRV)</summary>
    <ul>
      <li>Only intervals between normal beats (NN) are used. Intervals outside 300–2000 ms or deviating more than 20 % from the 11-beat moving median are rejected, which removes extra beats and their pauses.</li>
      <li><b>RMSSD</b> (root mean square of successive NN differences) and <b>SDNN</b> (standard deviation of NN intervals) are computed in 5-minute windows. These are the time-domain measures recommended by the Task Force 1996. A window is accepted if it has at least 150 beats and at least 80 % of its intervals are accepted. The value for the whole recording is the median of the windows.</li>
      <li>Frequency-domain measures (LF/HF) are not computed, as they are unreliable lying down and with extra beats.</li>
    </ul>
  </details>
  <details id="asento"><summary>Body posture</summary>
    <ul>
      <li>Posture is inferred from the direction of gravity in one-second averages of the accelerometer.</li>
      <li><b>Calibration:</b> the direction is measured lying on your back and on your left side (optionally also on your right side and front). The body's long axis is their cross product. The posture is the nearest calibrated posture by the roll angle around the long axis.</li>
      <li><b>Upright</b> when the component along the long axis exceeds 0.7 g (about 45°). <b>Turning</b> (movement) when the direction changes more than 15° per second or the spread of the acceleration magnitude exceeds 60 mG. Posture periods shorter than 30 s are merged with their neighbours.</li>
      <li>In retro-calibration the reference directions come from the still seconds of the spans you marked.</li>
    </ul>
  </details>
  <details id="oireet"><summary>Symptom marks</summary>
    <ul><li>The moment of the press is stored with the server's clock. An extra beat is looked for from 15 s before to 2 s after the mark, because the beat is felt before the button can be pressed.</li></ul>
  </details>
  <details id="ohjelmisto"><summary>Software and privacy</summary>
    <ul>
      <li>Python: FastAPI and Uvicorn (server), bleak and CoreBluetooth (Bluetooth), NumPy (computation), reportlab (PDF). In the browser: Canvas graphics and three.js r160 (3D figure, MIT licence), no other external libraries.</li>
      <li>Runs as a background service (macOS: LaunchAgent; Windows and Linux: see the README). Recordings are stored as gzip-compressed raw data in <span class="mono">~/openholter-data</span>, and analyses run in a separate low-priority process.</li>
      <li>Your data stays on this computer. The app uses no cloud services, analytics or telemetry, and the user interface loads nothing from the internet.</li>
      <li>Open source under the GNU AGPL-3.0 licence.</li>
    </ul>
  </details>`;
