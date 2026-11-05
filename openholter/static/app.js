"use strict";
/* OpenHolter frontend. No dependencies, no external requests. */

// ------------------------------------------------------------------ utilities

const $ = (sel, el = document) => el.querySelector(sel);
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

async function api(path, opts = {}) {
  const r = await fetch(path, { ...opts, headers: { Accept: "application/json", "X-Lang": LANG, ...(opts.headers || {}) } });
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return r.json();
}

function setupCanvas(canvas) {
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
  }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, w, h };
}

const fmt = {
  clock(ms) { return new Date(ms).toLocaleTimeString(LOCALE, { hour: "2-digit", minute: "2-digit" }); },
  clockSec(ms) { return new Date(ms).toLocaleTimeString(LOCALE, { hour: "2-digit", minute: "2-digit", second: "2-digit" }); },
  dur(s) {
    if (s == null) return "–";
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
    if (s < 60) return `${Math.round(s)} s`;
    return h ? `${h} h ${String(m).padStart(2, "0")} min` : `${m} min`;
  },
  hms(s) {
    s = Math.max(0, Math.floor(s));
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    return `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  },
  pct(x, d = 0) { return x == null ? "–" : `${(x * 100).toFixed(d)}`; },
  int(x) { return x == null ? "–" : Math.round(x).toLocaleString(LOCALE); },
  // "23.19 – 06.55", with weekdays when the recording crosses midnight: "ke 23.19 – to 06.55"
  range(t0, t1, open = false) {
    const a = new Date(t0), b = new Date(t1);
    if (open) return `${fmt.clock(t0)} – ${t("nyt")}`;
    if (a.toDateString() === b.toDateString()) return `${fmt.clock(t0)} – ${fmt.clock(t1)}`;
    const wd = (d) => d.toLocaleDateString(LOCALE, { weekday: "short" });
    return `${wd(a)} ${fmt.clock(t0)} – ${wd(b)} ${fmt.clock(t1)}`;
  },
  bytes(b) { return b > 1e6 ? `${dec(b / 1e6, 1)} ${t("Mt")}` : `${Math.round(b / 1e3)} ${t("kt")}`; },
  dayTitle(ms) {
    const d = new Date(ms);
    return {
      wd: d.toLocaleDateString(LOCALE, { weekday: "long" }),
      date: d.toLocaleDateString(LOCALE, { day: "numeric", month: "numeric", year: "numeric" }),
      short: d.toLocaleDateString(LOCALE, { weekday: "short", day: "numeric", month: "numeric" }),
    };
  },
};

const QUALITY = {
  good: { label: t("Hyvä"), hint: t("Elektrodikontakti kunnossa.") },
  fair: { label: t("Kohtalainen"), hint: t("Signaalissa kohinaa. Tarkista vyön kireys.") },
  poor: { label: t("Heikko"), hint: t("Paljon häiriöitä. Kostuta elektrodit ja kiristä vyötä.") },
  none: { label: t("Ei kontaktia"), hint: t("Vyö ei ole iholla tai elektrodit ovat kuivat.") },
};

const STATE_TEXT = {
  starting: t("Käynnistyy"), scanning: t("Etsitään vyötä"), connecting: t("Yhdistetään"),
  streaming: t("Yhdistetty"), error: t("Virhe"),
};

// ------------------------------------------------------------------ live connection (global)

const Live = {
  ws: null, status: null, listeners: new Set(), retry: 500,
  connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws/live`);
    this.ws = ws;
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === "status") { this.status = msg; renderStatus(msg); }
      this.remember(msg);
      for (const fn of this.listeners) fn(msg);
    };
    ws.onopen = () => { this.retry = 500; };
    ws.onclose = () => {
      renderStatus(null);
      setTimeout(() => this.connect(), this.retry);
      this.retry = Math.min(this.retry * 2, 8000);
    };
  },
  on(fn) { this.listeners.add(fn); return () => this.listeners.delete(fn); },
  // Keep the last seconds regardless of the page, so returning to Live shows a full trace at once.
  recent: { fs: 130, ecg: [], rr: [], acc: null, posture: null, hr: null, quality: "none" },
  remember(m) {
    const r = this.recent;
    if (m.type === "backlog") Object.assign(r, { fs: m.fs || 130, ecg: m.ecg || [], rr: m.rr || [], acc: m.acc, posture: m.posture, angles: m.angles, hr: m.hr, quality: m.quality || "none" });
    else if (m.type === "ecg") {
      if (r.hr && r.hr.contact === false) return; // not worn: keep nothing
      r.fs = m.fs; r.ecg.push(...m.v);
      if (r.ecg.length > r.fs * 10) r.ecg.splice(0, r.ecg.length - Math.round(r.fs * 10));
      if (m.quality) r.quality = m.quality;
    } else if (m.type === "hr") {
      r.hr = { bpm: m.bpm, contact: m.contact };
      if (m.contact === false) { r.ecg = []; r.rr = []; } else r.rr.push(...(m.rr || []));
      const cut = Date.now() / 1000 - 95; while (r.rr.length && r.rr[0][0] < cut) r.rr.shift();
    } else if (m.type === "acc") { r.acc = m.g; r.posture = m.posture; r.angles = m.angles; }
    else if (m.type === "status" && m.state !== "streaming") { r.ecg = []; r.quality = "none"; }
  },
  snapshot() { return { type: "backlog", ...this.recent, ecg: this.recent.ecg.slice(), rr: this.recent.rr.slice() }; },
};

function batteryIcon(p) {
  const w = clamp(Math.round((p / 100) * 14), 1, 14);
  const col = p < 20 ? css("--poor") : "currentColor";
  return `<svg width="22" height="12" viewBox="0 0 22 12" fill="none"><rect x=".75" y=".75" width="18" height="10.5" rx="2.5" stroke="currentColor" stroke-width="1.2" opacity=".6"/><rect x="2.5" y="2.5" width="${w}" height="7" rx="1.2" fill="${col}"/><rect x="19.8" y="4" width="1.6" height="4" rx=".8" fill="currentColor" opacity=".6"/></svg>`;
}

// Collector errors in plain language (raw text stays in the tooltip)
function explainError(detail) {
  const d = detail || "";
  if (/turned off|not authorized|unauthori/i.test(d)) return t("Bluetooth ei käytössä: tarkista Bluetooth-lupa");
  if (/PMD service/i.test(d)) return t("Vyö ei tue EKG-striimausta (päivitä firmware)");
  if (/ECG start failed/i.test(d)) return t("EKG:n käynnistys epäonnistui");
  return t("Virhe");
}

function renderStatus(s) {
  const el = $("#status");
  if (!s) { el.innerHTML = `<span class="pill err"><span class="dot"></span>${t("Ei yhteyttä palvelimeen")}</span>`; return; }
  const cls = s.state === "streaming" ? "ok" : s.state === "error" ? "err" : "wait";
  const parts = [];
  if (s.simulated) parts.push(`<span class="pill sim">${t("Simulaattori")}</span>`);
  if (s.recording) {
    const el = (Date.now() - s.session_started_wall_ns / 1e6) / 1000;
    parts.push(`<span class="pill rec"><span class="dot"></span>${t("Tallentaa")} <span class="num" data-rec-clock>${fmt.hms(el)}</span></span>`);
  }
  const bat = s.device && s.device.battery != null && s.state === "streaming"
    ? `<span class="battery">${batteryIcon(s.device.battery)}<span class="num">${s.device.battery} %</span></span>` : "";
  const name = s.state === "streaming" && s.device && s.device.name ? s.device.name.replace("Polar ", "")
    : s.state === "error" ? explainError(s.detail) : (STATE_TEXT[s.state] || s.state);
  parts.push(`<span class="pill ${cls}" title="${esc(s.detail || "")}"><span class="dot"></span>${esc(name)}${bat ? " · " + bat : ""}</span>`);
  el.innerHTML = parts.join("");
}

setInterval(() => {
  const s = Live.status;
  if (s && s.recording) document.querySelectorAll("[data-rec-clock]").forEach((c) => (c.textContent = fmt.hms((Date.now() - s.session_started_wall_ns / 1e6) / 1000)));
}, 1000);

// ------------------------------------------------------------------ ECG paper

function drawPaper(ctx, w, h, pxPerSec, pxPerMv, x0 = 0, y0 = h / 2) {
  const minor = css("--grid-minor"), major = css("--grid-major");
  const sx = pxPerSec * 0.04, sy = pxPerMv * 0.1;
  ctx.lineWidth = 1;
  for (const [step, color, every] of [[sx, minor, 1], [sx * 5, major, 5]]) {
    if (step < 3) continue;
    ctx.strokeStyle = color;
    ctx.beginPath();
    const start = ((x0 % step) + step) % step;
    for (let x = start; x <= w; x += step) { ctx.moveTo(Math.round(x) + 0.5, 0); ctx.lineTo(Math.round(x) + 0.5, h); }
    ctx.stroke();
  }
  for (const [step, color] of [[sy, minor], [sy * 5, major]]) {
    if (step < 3) continue;
    ctx.strokeStyle = color;
    ctx.beginPath();
    for (let y = y0 % step; y <= h; y += step) { ctx.moveTo(0, Math.round(y) + 0.5); ctx.lineTo(w, Math.round(y) + 0.5); }
    ctx.stroke();
  }
}

// zero-phase first-order high-pass to remove baseline wander for display
function highpass(v, fs, fc = 0.5) {
  const n = v.length, out = new Float32Array(n);
  if (!n) return out;
  const a = Math.exp((-2 * Math.PI * fc) / fs);
  let b = v[0];
  const tmp = new Float32Array(n);
  for (let i = 0; i < n; i++) { b = a * b + (1 - a) * v[i]; tmp[i] = b; }
  b = tmp[n - 1];
  for (let i = n - 1; i >= 0; i--) { b = a * b + (1 - a) * tmp[i]; out[i] = v[i] - b; }
  return out;
}

// ------------------------------------------------------------------ live view

class Sweep {
  constructor(canvas, onBeat) {
    this.canvas = canvas; this.onBeat = onBeat;
    this.fs = 130; this.seconds = 10;
    this.reset();
  }
  reset() {
    this.n = Math.round(this.fs * this.seconds);
    this.buf = new Float32Array(this.n).fill(NaN);
    this.pos = 0; this.queue = []; this.acc = 0; this.last = null;
    this.base = null; this.amp = 400; this.sinceBeat = 1e9; this.prev = 0;
  }
  setFs(fs) { if (Math.abs(fs - this.fs) > 0.5) { this.fs = fs; this.reset(); } else this.fs = fs; }
  push(vals) { for (const v of vals) this.queue.push(v); }
  backlog(vals) { this.reset(); for (const v of vals) this._write(v, false); }
  _write(x, live) {
    // display high-pass (~0.4 Hz) + simple R-peak detector for the pulse animation
    if (this.base == null) this.base = x;
    this.base += 0.019 * (x - this.base);
    const y = x - this.base;
    this.buf[this.pos] = y;
    this.pos = (this.pos + 1) % this.n;
    const slope = y - this.prev; this.prev = y;
    this.amp = Math.max(this.amp * 0.9993, Math.abs(y));
    this.sinceBeat++;
    if (live && y > 0.5 * this.amp && slope < 0 && this.sinceBeat > this.fs * 0.3) {
      this.sinceBeat = 0; this.onBeat && this.onBeat();
    }
  }
  frame(now) {
    if (this.last == null) this.last = now;
    const dt = Math.min(0.25, (now - this.last) / 1000);
    this.last = now;
    // play out with ~0.7 s latency; speed up or slow down slightly to track the stream
    const target = this.fs * 0.7, q = this.queue.length;
    const rate = q > target * 2.5 ? 1.6 : q > target * 1.4 ? 1.08 : q < target * 0.5 ? 0.9 : 1.0;
    if (q > this.fs * 4) this.queue.splice(0, q - Math.round(target));
    this.acc += dt * this.fs * rate;
    let k = Math.floor(this.acc);
    this.acc -= k;
    k = Math.min(k, this.queue.length);
    for (let i = 0; i < k; i++) this._write(this.queue.shift(), true);
    this.draw();
  }
  draw() {
    const { ctx, w, h } = setupCanvas(this.canvas);
    ctx.clearRect(0, 0, w, h);
    const pxPerSec = w / this.seconds;
    const pxPerMv = Math.min(h / 3.2, pxPerSec * 0.4 * 2.5);
    const mid = h * 0.56;
    drawPaper(ctx, w, h, pxPerSec, pxPerMv, 0, mid);
    const gap = Math.round(this.fs * 0.25);
    const color = css("--ecg");
    ctx.lineJoin = "round"; ctx.lineCap = "round";
    // Phosphor look: the freshly written trace is bright and glows, older trace fades
    // towards the eraser. Drawn newest→oldest in chunks, each with its own alpha.
    const chunks = 36, per = Math.ceil(this.n / chunks);
    const at = (a) => {
      const i = (this.pos - 1 - a + this.n) % this.n;
      const v = this.buf[i];
      return Number.isNaN(v) ? null : [(i / this.n) * w, mid - (v / 1000) * pxPerMv, i];
    };
    for (const pass of [0, 1]) {
      ctx.strokeStyle = color;
      ctx.lineWidth = pass ? 1.8 : 6;
      for (let c = 0; c < chunks; c++) {
        const a0 = c * per, a1 = Math.min(this.n - gap, (c + 1) * per + 1);
        if (a0 >= a1) break;
        const age = (c + 0.5) / chunks; // 0 = newest
        ctx.globalAlpha = pass ? 1 - 0.72 * Math.pow(age, 0.85) : 0.24 * Math.pow(1 - age, 3);
        if (ctx.globalAlpha < 0.01) continue;
        ctx.beginPath();
        let prev = null;
        for (let a = a0; a < a1; a++) {
          const p = at(a);
          // break at missing samples and where the buffer wraps from the right edge to the left
          if (!p || (prev && p[2] > prev[2])) { prev = p; if (p) ctx.moveTo(p[0], p[1]); continue; }
          if (prev) ctx.lineTo(p[0], p[1]); else ctx.moveTo(p[0], p[1]);
          prev = p;
        }
        ctx.stroke();
      }
    }
    ctx.globalAlpha = 1;
    // pen head
    const hi = (this.pos - 1 + this.n) % this.n;
    if (!Number.isNaN(this.buf[hi])) {
      const x = (hi / this.n) * w, y = mid - (this.buf[hi] / 1000) * pxPerMv;
      const g = ctx.createRadialGradient(x, y, 0, x, y, 14);
      g.addColorStop(0, "rgba(255,255,255,.95)"); g.addColorStop(0.25, color); g.addColorStop(1, "rgba(255,84,112,0)");
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, 14, 0, Math.PI * 2); ctx.fill();
    }
    // scale bar: 1 mV / 0.2 s
    ctx.strokeStyle = "rgba(232,237,247,.55)"; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.moveTo(14, mid + pxPerMv * 0.5); ctx.lineTo(14, mid - pxPerMv * 0.5); ctx.stroke();
    ctx.fillStyle = "rgba(232,237,247,.55)"; ctx.font = "11px " + css("--mono");
    ctx.fillText("1 mV", 20, mid - pxPerMv * 0.5 + 10);
  }
  hasData() { return this.buf.some((v) => !Number.isNaN(v)); }
}

class Tacho {
  constructor(canvas) { this.canvas = canvas; this.beats = []; this.span = 90; }
  add(beats) { for (const b of beats) this.beats.push(b); this.trim(); }
  set(beats) { this.beats = beats.slice(); this.trim(); }
  trim() { const t = Date.now() / 1000 - this.span - 5; while (this.beats.length && this.beats[0][0] < t) this.beats.shift(); }
  draw() {
    const { ctx, w, h } = setupCanvas(this.canvas);
    ctx.clearRect(0, 0, w, h);
    const now = Date.now() / 1000, pad = { l: 44, r: 8, t: 10, b: 20 };
    const rr = this.beats.map((b) => b[1]);
    let lo = 500, hi = 1300;
    if (rr.length > 3) {
      const s = rr.slice().sort((a, b) => a - b);
      lo = Math.min(s[0], s[Math.floor(s.length / 2)] * 0.6); hi = Math.max(s[s.length - 1], s[Math.floor(s.length / 2)] * 1.4);
      lo = Math.floor(lo / 100) * 100; hi = Math.ceil(hi / 100) * 100;
    }
    const X = (t) => pad.l + ((t - (now - this.span)) / this.span) * (w - pad.l - pad.r);
    const Y = (v) => pad.t + (1 - (v - lo) / (hi - lo)) * (h - pad.t - pad.b);
    ctx.font = "11px " + css("--mono"); ctx.fillStyle = css("--faint"); ctx.strokeStyle = css("--line");
    ctx.lineWidth = 1;
    const step = hi - lo > 800 ? 200 : 100;
    for (let v = lo; v <= hi; v += step) {
      ctx.beginPath(); ctx.moveTo(pad.l, Math.round(Y(v)) + 0.5); ctx.lineTo(w - pad.r, Math.round(Y(v)) + 0.5); ctx.stroke();
      ctx.fillText(String(v), 6, Y(v) + 4);
    }
    for (let s = 0; s <= this.span; s += 30) ctx.fillText(s ? `−${s} s` : t("nyt"), X(now - s) - (s ? 14 : 18), h - 4);
    if (!this.beats.length) return;
    ctx.strokeStyle = "rgba(110,168,255,.35)"; ctx.lineWidth = 1.2; ctx.beginPath();
    this.beats.forEach((b, i) => (i ? ctx.lineTo(X(b[0]), Y(b[1])) : ctx.moveTo(X(b[0]), Y(b[1]))));
    ctx.stroke();
    this.beats.forEach((b, i) => {
      const win = this.beats.slice(Math.max(0, i - 6), i).map((x) => x[1]).sort((a, b) => a - b);
      const med = win.length ? win[Math.floor(win.length / 2)] : b[1];
      const early = b[1] < med * 0.8, late = b[1] > med * 1.2;
      ctx.fillStyle = early ? css("--ecg") : late ? css("--fair") : css("--hr");
      ctx.beginPath(); ctx.arc(X(b[0]), Y(b[1]), early || late ? 3.6 : 2.4, 0, Math.PI * 2); ctx.fill();
    });
  }
}

function orientationSvg(g) {
  if (!g) return `<svg viewBox="0 0 100 100"><circle cx="50" cy="50" r="44" fill="none" stroke="rgba(148,170,210,.2)"/></svg>`;
  const n = Math.hypot(...g) || 1;
  const [x, y, z] = g.map((v) => v / n);
  const px = 50 + x * 38, py = 50 - y * 38;
  const front = z >= 0;
  return `<svg viewBox="0 0 100 100">
    <defs><radialGradient id="og" cx="35%" cy="30%"><stop offset="0" stop-color="rgba(124,140,255,.25)"/><stop offset="1" stop-color="rgba(124,140,255,.02)"/></radialGradient></defs>
    <circle cx="50" cy="50" r="44" fill="url(#og)" stroke="rgba(148,170,210,.25)"/>
    <ellipse cx="50" cy="50" rx="44" ry="13" fill="none" stroke="rgba(148,170,210,.12)"/>
    <ellipse cx="50" cy="50" rx="13" ry="44" fill="none" stroke="rgba(148,170,210,.12)"/>
    <line x1="50" y1="50" x2="${px}" y2="${py}" stroke="#7c8cff" stroke-width="2" stroke-linecap="round" opacity="${front ? 1 : 0.45}"/>
    <circle cx="${px}" cy="${py}" r="${front ? 6 : 4.5}" fill="${front ? "#7c8cff" : "none"}" stroke="#7c8cff" stroke-width="2"/>
    <circle cx="50" cy="50" r="2.5" fill="rgba(232,237,247,.7)"/>
  </svg>`;
}

const LivePage = {
  mount(el) {
    el.innerHTML = `
      <div class="page-head fade-in">
        <div><h1>Live</h1><div class="sub">${t("Tarkista ennen tallennusta, että signaali näyttää puhtaalta.")}</div></div>
        <span class="spacer"></span>
        <button class="btn primary sym-btn" id="lv-sym" hidden><svg viewBox="0 0 32 32" width="18" height="18"><path fill="currentColor" d="M16 28s-11-6.6-11-15A6 6 0 0 1 16 9a6 6 0 0 1 11 4c0 8.4-11 15-11 15z"/></svg>${t("Tunsin lisälyönnin")}</button>
      </div>
      <div class="glance fade-in" id="lv-glance">
        <div class="g-tile" id="gl-q"><div class="k">${t("Kontakti")}</div><div class="v">–</div></div>
        <div class="g-tile" id="gl-bt"><div class="k">Bluetooth</div><div class="v">–</div></div>
        <div class="g-tile"><div class="k">${t("Syke")}</div><div class="v"><span class="num" id="gl-bpm">–</span> <small>bpm</small></div></div>
        <div class="g-tile"><div class="k">${t("Asento")}</div><div class="v" id="gl-pos">–</div></div>
        <div class="g-tile" id="gl-rec"><div class="k">${t("Tallennus")}</div><div class="v">–</div></div>
        <button class="btn primary big-sym" id="gl-start" hidden>● ${t("Aloita tallennus")}</button>
        <button class="btn primary sym-btn big-sym" id="gl-sym" hidden><svg viewBox="0 0 32 32" width="18" height="18"><path fill="currentColor" d="M16 28s-11-6.6-11-15A6 6 0 0 1 16 9a6 6 0 0 1 11 4c0 8.4-11 15-11 15z"/></svg>${t("Tunsin lisälyönnin")}</button>
      </div>
      <section class="card monitor fade-in">
        <div class="card-head">
          <span class="card-title">${t("EKG · viimeiset 10 s")}</span>
          <span class="meta" id="lv-fs">${t("{0} Hz · näyttösuodatin {1} Hz", 130, dec(0.4, 1))}</span>
        </div>
        <canvas id="lv-ecg"></canvas>
        <div class="monitor-empty" id="lv-empty"><div><div class="big">${t("Odotetaan signaalia")}</div><div id="lv-empty-sub">${t("Pue vyö ja kostuta elektrodit. Yhteys muodostuu automaattisesti.")}</div></div></div>
      </section>
      <div class="grid cols-3 fade-in" style="margin-top:18px">
        <section class="card">
          <div class="card-head"><span class="card-title">${t("Syke")}</span></div>
          <div class="bpm"><span class="value num" id="lv-bpm">–</span><span class="unit">bpm</span>
            <svg class="heart" id="lv-heart" viewBox="0 0 32 32"><path fill="currentColor" d="M16 28s-11-6.6-11-15A6 6 0 0 1 16 9a6 6 0 0 1 11 4c0 8.4-11 15-11 15z"/></svg>
          </div>
          <div class="substats"><div>RR<b class="num" id="lv-rr">–</b></div><div>${t("Vaihtelu 60 s")}<b class="num" id="lv-rmssd">–</b></div></div>
        </section>
        <section class="card">
          <div class="card-head"><span class="card-title">${t("Signaali")}</span>${infoLink("signaali")}</div>
          <div class="sig-row"><span class="sig-k">${t("Elektrodikontakti")}</span>
            <div class="quality q-none" id="lv-q"><div class="bars"><i></i><i></i><i></i><i></i></div><div class="label">–</div></div></div>
          <div class="hint" id="lv-q-hint">&nbsp;</div>
          <div class="sig-row" style="margin-top:12px"><span class="sig-k">Bluetooth</span>
            <div class="quality q-none" id="lv-bt"><div class="bars"><i></i><i></i><i></i><i></i></div><div class="label">–</div></div></div>
          <div class="hint" id="lv-bt-hint">&nbsp;</div>
        </section>
        <section class="card">
          <div class="card-head"><span class="card-title">${t("Tallennus")}</span></div>
          <div id="lv-rec"></div>
        </section>
      </div>
      <div class="grid live-two fade-in" style="margin-top:18px">
      <section class="card tacho">
        <div class="card-head"><span class="card-title">${t("RR-välit · 90 s")}</span>
          <span class="meta"><span style="color:var(--ecg)">●</span> ${t("etuajassa")} &nbsp; <span style="color:var(--fair)">●</span> ${t("tauko")}</span></div>
        <canvas id="lv-tacho"></canvas>
        <div class="hint" style="margin-top:8px">${t("Lisälyönti näkyy tyypillisesti lyhyenä RR-välinä, jota seuraa pitkä kompensatorinen tauko.")}</div>
      </section>
      <section class="card posture-card">
        <div class="card-head"><span class="card-title">${t("Asento")}</span>${infoLink("asento")}<span class="meta" id="lv-calmeta">${t("kalibroimaton")}</span></div>
        <div class="fig-stage" id="lv-fig"><div class="fig-fallback" id="lv-orient">${orientationSvg(null)}</div>
          <div class="fig-overlay"><div class="posture-name" id="lv-pos">–</div><div class="vals num" id="lv-g"></div></div>
          <div class="fig-hint" id="lv-fighint"></div></div>
        <button class="btn sm" id="lv-cal">${t("Kalibroi asento")}</button>
      </section>
      </div>`;
    Figure3D.create($("#lv-fig")).then((fig) => {
      if (!fig) return;
      if (!$("#lv-fig")) { fig.dispose(); return; }
      this.fig = fig;
      $("#lv-orient").remove();
      const r = Live.recent;
      this.renderAcc(r.acc, r.posture, r.angles);
    });
    $("#lv-cal").onclick = () => Calib.open();
    for (const id of ["#lv-sym", "#gl-sym"]) $(id).onclick = (e) => markSymptom(e.currentTarget);
    $("#gl-start").onclick = () => api("/api/recording/start", { method: "POST" });
    const heart = $("#lv-heart");
    this.sweep = new Sweep($("#lv-ecg"), () => { heart.classList.add("beat"); setTimeout(() => heart.classList.remove("beat"), 140); });
    this.tacho = new Tacho($("#lv-tacho"));
    this.off = Live.on((m) => this.onMsg(m));
    if (Live.status) this.onMsg(Live.status);
    this.onMsg(Live.snapshot());
    const loop = (t) => { this.sweep.frame(t); $("#lv-empty").classList.toggle("hidden", this.sweep.hasData() && !this.noContact); this.raf = requestAnimationFrame(loop); };
    this.raf = requestAnimationFrame(loop);
    this.tachoTimer = setInterval(() => { this.tacho.trim(); this.tacho.draw(); }, 1000);
    this.tacho.draw();
  },
  unmount() {
    cancelAnimationFrame(this.raf); clearInterval(this.tachoTimer); this.off && this.off();
    if (this.fig) { this.fig.dispose(); this.fig = null; }
  },
  onMsg(m) {
    if (m.type === "ecg") {
      if (this.noContact) return; // nothing measured until the strap is worn
      this.sweep.setFs(m.fs); this.sweep.push(m.v);
      if (m.quality) this.renderQuality(m.quality);
      $("#lv-fs").textContent = t("{0} Hz · näyttösuodatin {1} Hz", dec(m.fs, 2), dec(0.4, 1));
    } else if (m.type === "backlog") {
      if (m.hr && m.hr.contact === false) this.setContact(false);
      this.sweep.setFs(m.fs || 130);
      if (!this.noContact) { this.sweep.backlog(m.ecg || []); this.tacho.set(m.rr || []); }
      this.tacho.draw();
      this.renderQuality(m.quality || "none");
      if (m.hr) this.renderHr(m.hr.bpm);
      if (m.acc) this.renderAcc(m.acc, m.posture, m.angles);
      this.renderRmssd();
    } else if (m.type === "hr") {
      if ((m.contact === false) !== !!this.noContact) this.setContact(m.contact === false ? false : true);
      this.renderHr(m.bpm, m.rr);
      this.tacho.add(m.rr || []); this.tacho.draw(); this.renderRmssd();
    } else if (m.type === "acc") {
      this.renderAcc(m.g, m.posture, m.angles);
    } else if (m.type === "status") {
      this.renderRec(m);
      this.renderLink(m.link || { level: "none" });
      $("#lv-calmeta").textContent = m.calibration_id ? t("kalibroitu {0}", calLabel(m.calibration_id)) : t("kalibroimaton");
      if (m.state !== "streaming") { this.renderQuality("none"); $("#lv-bpm").textContent = "–"; $("#gl-bpm").textContent = "–"; }
      this.setContact(m.state === "streaming" ? m.contact : null);
      if (!this.noContact) $("#lv-empty-sub").textContent = m.state === "streaming" ? t("Signaali tulossa…")
        : m.state === "error" ? `${explainError(m.detail)}. ${t("macOS: Järjestelmäasetukset → Tietosuoja ja turvallisuus → Bluetooth (Python.app, tarkka polku: openholter doctor). Windows/Linux: tarkista, että Bluetooth on päällä.")}`
        : t("Pue vyö ja kostuta elektrodit. Yhteys muodostuu automaattisesti.");
    }
  },
  renderHr(bpm, rr) {
    if (this.noContact) bpm = null;
    $("#lv-bpm").textContent = bpm || "–";
    $("#lv-bpm").classList.toggle("nil", !bpm);
    $("#gl-bpm").textContent = bpm || "–";
    if (this.noContact) { $("#lv-rr").textContent = "–"; $("#lv-rmssd").textContent = "–"; return; }
    if (rr && rr.length) $("#lv-rr").innerHTML = `${Math.round(rr[rr.length - 1][1])} <span class="faint">ms</span>`;
  },
  renderRmssd() {
    if (this.noContact) { $("#lv-rmssd").textContent = "–"; return; }
    const b = this.tacho.beats.filter((x) => x[0] > Date.now() / 1000 - 60).map((x) => x[1]);
    if (b.length < 5) return;
    let s = 0; for (let i = 1; i < b.length; i++) s += (b[i] - b[i - 1]) ** 2;
    $("#lv-rmssd").innerHTML = `${Math.round(Math.sqrt(s / (b.length - 1)))} <span class="faint">ms</span>`;
  },
  renderQuality(q) {
    const el = $("#lv-q"); if (!el) return;
    el.className = `quality q-${q}`;
    $(".label", el).textContent = QUALITY[q].label;
    $("#lv-q-hint").textContent = QUALITY[q].hint;
    const gq = $("#gl-q");
    gq.className = `g-tile gq-${q}`;
    $(".v", gq).textContent = QUALITY[q].label;
  },
  // The H10 reports skin contact; without it the ECG is noise and the rate invented.
  setContact(c) {
    const was = !!this.noContact;
    this.noContact = c === false;
    if (was !== this.noContact && this.sweep) {
      // taking the strap off or putting it on: drop everything measured so far, start clean
      this.sweep.reset(); this.tacho.set([]); this.tacho.draw();
      const r = Live.recent; r.ecg = []; r.rr = [];
      if (this.noContact) this.renderAcc(null, null, null);
    }
    const mon = $(".monitor"); if (!mon) return;
    mon.classList.toggle("off-skin", this.noContact);
    const box = $("#lv-empty"), sub = $("#lv-empty-sub");
    if (this.noContact) {
      box.classList.remove("hidden");
      $(".big", box).textContent = t("Ei ihokontaktia");
      sub.textContent = t("Vyö on yhdistetty, mutta se ei ole iholla tai elektrodit ovat kuivat. Kostuta elektrodit ja pue vyö.");
      this.renderHr(null);
      this.renderQuality("none");
    } else {
      $(".big", box).textContent = t("Odotetaan signaalia");
    }
  },
  renderLink(l) {
    const el = $("#lv-bt"); if (!el) return;
    const map = { good: ["good", t("Hyvä")], fair: ["fair", t("Kohtalainen")], poor: ["poor", t("Heikko")], wait: ["fair", t("Mitataan…")], none: ["none", t("Ei yhteyttä")] };
    const [cls, label] = map[l.level] || map.none;
    el.className = `quality q-${cls}`;
    $(".label", el).textContent = label;
    const parts = [];
    if (l.rssi != null) parts.push(`${l.rssi} dBm`);
    if (l.ratio != null) parts.push(t("{0} % datasta perillä", Math.round(l.ratio * 100)));
    if (l.gap != null && l.gap >= 1.5) parts.push(t("katko {0} s", dec(l.gap, 1)));
    const advice = l.level === "poor" ? " " + t("Siirrä tietokone lähemmäs tai poista esteitä välistä.") : "";
    $("#lv-bt-hint").textContent = (parts.join(" · ") || (l.level === "none" ? t("Vyö ei ole yhdistettynä.") : "\u00a0")) + advice;
    const gt = $("#gl-bt");
    gt.className = `g-tile gq-${cls}`;
    $(".v", gt).textContent = l.rssi != null && l.level !== "none" ? `${label} · ${l.rssi}` : label;
  },
  renderAcc(g, posture, angles) {
    if (!$("#lv-pos")) return;
    if (this.noContact) { g = null; posture = null; angles = null; } // strap lying on the table: no body posture
    const label = posture ? POSTURE[posture].label : "";
    $("#lv-pos").textContent = label;
    $("#gl-pos").textContent = label || "–";
    const hint = $("#lv-fighint");
    if (this.fig) {
      if (angles) { this.fig.setGhost(false); this.fig.setPose(angles[0], angles[1]); }
      else { this.fig.setGhost(true); this.fig.setPose(0, 0); }
    } else if (g && $("#lv-orient")) {
      $("#lv-orient").innerHTML = orientationSvg(g);
    }
    hint.textContent = this.noContact ? t("Vyö ei ole päällä.") : !g ? t("Ei kiihtyvyysdataa") : angles ? "" : t("Kalibroi asento, niin hahmo kääntyy kuten sinä.");
    $("#lv-g").innerHTML = angles
      ? t("kierto {0}° · kallistus {1}°", Math.round(angles[0]), Math.round(angles[1]))
      : g ? `x ${Math.round(g[0])} · y ${Math.round(g[1])} · z ${Math.round(g[2])} mG` : "";
  },
  renderRec(s) {
    const el = $("#lv-rec"); if (!el) return;
    for (const id of ["#lv-sym", "#gl-sym"]) $(id).hidden = !s.recording;
    // phone: start button up top when nothing is recording but the strap is on
    $("#gl-start").hidden = s.recording || s.state !== "streaming" || s.contact === false;
    if (s.recording) {
      const started = s.session_started_wall_ns / 1e6;
      el.innerHTML = `
        <div class="rec-time" data-rec-clock>${fmt.hms((Date.now() - started) / 1000)}</div>
        <div class="hint">${t("Alkoi {0}", fmt.clock(started))} · ${fmt.bytes(s.session_bytes)}</div>
        <div class="btn-row" style="margin-top:12px"><button class="btn sm" id="lv-stop">■ ${t("Lopeta")}</button>
        <a class="btn sm" href="#/recording/${esc(s.session_id)}">${t("Avaa tallenne")}</a></div>`;
      $("#lv-stop").onclick = () => api("/api/recording/stop", { method: "POST" });
      $(".v", $("#gl-rec")).innerHTML = `<span class="rec-dot"></span><span class="num" data-rec-clock>${fmt.hms((Date.now() - started) / 1000)}</span>`;
    } else {
      const why = s.auto_record === false ? t("Automaattinen aloitus on pois päältä (Asetukset). Aloita tallennus tästä.")
        : s.auto_armed ? t("Alkaa automaattisesti, kun vyö puetaan.") : t("Pysäytetty käsin. Automaattinen aloitus palaa, kun vyö riisutaan.");
      el.innerHTML = `
        <div class="rec-time faint">${t("Ei käynnissä")}</div>
        <div class="hint">${why}</div>
        <div class="btn-row" style="margin-top:12px"><button class="btn primary sm" id="lv-start" ${s.state === "streaming" ? "" : "disabled"}>● ${t("Aloita tallennus")}</button></div>`;
      $("#lv-start").onclick = () => api("/api/recording/start", { method: "POST" });
      $(".v", $("#gl-rec")).innerHTML = `<span class="faint">${t("Ei käynnissä")}</span>`;
    }
  },
};

// ------------------------------------------------------------------ posture + calibration wizard

const POSTURE = {
  supine: { label: t("Selällään"), color: "--p-a" },
  left: { label: t("Vasen kylki"), color: "--p-b" },
  right: { label: t("Oikea kylki"), color: "--p-c" },
  prone: { label: t("Vatsallaan"), color: "--p-d" },
  upright: { label: t("Pystyssä"), color: "--p-up" },
  moving: { label: t("Kääntyminen"), color: "--p-move" },
  unknown: { label: t("Ei asentotietoa"), color: "--none" },
  A: { label: t("Asento {0}", "A"), color: "--p-a" }, B: { label: t("Asento {0}", "B"), color: "--p-b" },
  C: { label: t("Asento {0}", "C"), color: "--p-c" }, D: { label: t("Asento {0}", "D"), color: "--p-d" },
};
const LYING = ["supine", "left", "right", "prone"];
const POSE = { supine: [0, 0], left: [90, 0], right: [-90, 0], prone: [180, 0], upright: [0, 80] };

// three.js figure, loaded on first use; null when WebGL or the module is unavailable
const Figure3D = {
  load() { return (this._p = this._p || import("/static/figure.js").catch(() => null)); },
  async create(el, opts) {
    const m = await this.load();
    if (!m || !el.isConnected) return null;
    try { return m.createFigure(el, opts); } catch { return null; }
  },
};

function calLabel(id, dateOnly = false) {
  // ids are local timestamps: 2026-10-29_224105
  const m = /^(\d{4})-(\d{2})-(\d{2})_(\d{2})(\d{2})/.exec(id || "");
  if (!m) return id;
  return dateOnly ? t("{0}.{1}.", +m[3], +m[2]) : t("{0}.{1}. klo {2}.{3}", +m[3], +m[2], m[4], m[5]);
}

// Torso cross-section seen from the foot end; the dot is the strap on the chest.
function postureFigure(key) {
  const rot = { supine: 0, left: 90, right: -90, prone: 180 }[key] || 0;
  return `<svg viewBox="0 0 160 110" class="figure">
    <line x1="10" y1="96" x2="150" y2="96" stroke="rgba(148,170,210,.35)" stroke-width="2" stroke-linecap="round"/>
    <g transform="rotate(${rot} 80 ${rot % 180 ? 60 : 70})">
      <ellipse cx="80" cy="${rot % 180 ? 60 : 70}" rx="${rot % 180 ? 50 : 52}" ry="${rot % 180 ? 30 : 24}" fill="rgba(124,140,255,.16)" stroke="#7c8cff" stroke-width="2"/>
      <circle cx="80" cy="${(rot % 180 ? 60 : 70) - (rot % 180 ? 30 : 24)}" r="6" fill="#ff5470"/>
    </g>
    <text x="80" y="108" text-anchor="middle" font-size="9" fill="rgba(148,170,210,.7)">${t("jalkopäästä katsottuna · ● vyö")}</text>
  </svg>`;
}

const CALIB_STEPS = [
  { key: "supine", required: true, text: t("Käänny selällesi. Kädet vartalon vierelle, makaa vaakatasossa.") },
  { key: "left", required: true, text: t("Käänny vasemmalle kyljelle, vasen olkapää alaspäin.") },
  { key: "right", required: false, text: t("Käänny oikealle kyljelle. Valinnainen, tarkentaa rajoja.") },
  { key: "prone", required: false, text: t("Käänny vatsallesi. Valinnainen.") },
];
const CAPTURE_S = 15, PREP_S = 3;

const Calib = {
  open(onDone) {
    this.results = {}; this.step = 0; this.onDone = onDone;
    const el = document.createElement("div");
    el.className = "modal";
    el.innerHTML = `<div class="sheet fade-in" role="dialog" aria-label="${t("Asennon kalibrointi")}">
      <div class="sheet-head"><b>${t("Asennon kalibrointi")}</b><div class="dots" id="cb-dots"></div><button class="x" id="cb-x" aria-label="${t("Sulje")}">✕</button></div>
      <div id="cb-body"></div></div>`;
    document.body.appendChild(el);
    this.el = el;
    this.fig = null;
    this.figEl = document.createElement("div");
    this.figEl.className = "fig-stage cb-fig";
    el.querySelector(".sheet").appendChild(this.figEl); // in the DOM (and in view) for WebGL sizing; moved into the step below
    Figure3D.create(this.figEl, { interactive: true }).then((f) => {
      if (!f) { this.figEl.remove(); return; }
      if (!this.el) { f.dispose(); return; }
      this.fig = f;
      const st = CALIB_STEPS[Math.min(this.step, CALIB_STEPS.length - 1)];
      f.setPose(...POSE[st.key], true);
      this.render();
    });
    $("#cb-x").onclick = () => this.close();
    el.addEventListener("click", (e) => { if (e.target === el && !this.busy) this.close(); });
    this.render();
  },
  close() {
    if (Live.status && Live.status.simulated) api("/api/sim/posture", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ posture: null }) }).catch(() => {});
    if (this.fig) { this.fig.dispose(); this.fig = null; }
    if (this.figEl) { this.figEl.remove(); this.figEl = null; }
    this.el && this.el.remove(); this.el = null; this.busy = false;
    if (this.onDone) { const f = this.onDone; this.onDone = null; f(); }
  },
  dots() {
    $("#cb-dots").innerHTML = CALIB_STEPS.map((s, i) => `<i class="${i < this.step ? "done" : i === this.step ? "on" : ""}${this.results[s.key] && this.results[s.key].ok ? " ok" : ""}"></i>`).join("");
  },
  render() {
    if (!this.el) return;
    this.dots();
    if (this.step >= CALIB_STEPS.length) return this.summary();
    const st = CALIB_STEPS[this.step], res = this.results[st.key];
    const streaming = Live.status && Live.status.state === "streaming";
    $("#cb-body").innerHTML = `
      <div class="cb-step">
        ${this.fig ? '<div id="cb-figslot"></div>' : postureFigure(st.key)}
        <h2>${POSTURE[st.key].label}${st.required ? "" : ` <span class="opt">${t("valinnainen")}</span>`}</h2>
        <p class="hint">${st.text}</p>
        <div class="cb-run" id="cb-run">
          ${res ? (res.ok
            ? `<div class="cb-ok">✓ ${t("Mitattu")} · ${Math.round(res.magnitude)} mG · ${t("vaihtelu")} ${dec(res.spread_deg, 1)}°</div>`
            : `<div class="cb-fail">✕ ${esc(res.reason || t("Mittaus epäonnistui"))}</div>`) : ""}
        </div>
        <div class="btn-row cb-actions">
          ${res && res.ok
            ? `<button class="btn" id="cb-redo">${t("Mittaa uudelleen")}</button><button class="btn primary" id="cb-next">${t("Seuraava")} →</button>`
            : `<button class="btn primary big" id="cb-go" ${streaming ? "" : "disabled"}>${res ? t("Yritä uudelleen") : t("Aloita ({0} s)", CAPTURE_S)}</button>
               ${st.required ? "" : `<button class="btn" id="cb-skip">${t("Ohita")}</button>`}`}
        </div>
        ${streaming ? `<p class="hint faint">${t("Kun painat Aloita, sinulla on {0} s aikaa asettua. Mittauksen lopussa kuuluu merkkiääni ja puhelin värähtää.", PREP_S)}</p>`
          : `<p class="hint" style="color:var(--fair)">${t("Vyö ei ole yhdistettynä.")}</p>`}
        ${Live.status && Live.status.simulated ? `<p class="hint faint">${t("Simulaattori asettaa asennon automaattisesti.")}</p>` : ""}
      </div>`;
    if (this.fig) { $("#cb-figslot").replaceWith(this.figEl); this.fig.setPose(...POSE[st.key]); }
    const go = $("#cb-go"); if (go) go.onclick = () => this.capture(st.key);
    const redo = $("#cb-redo"); if (redo) redo.onclick = () => this.capture(st.key);
    const next = $("#cb-next"); if (next) next.onclick = () => { this.step++; this.render(); };
    const skip = $("#cb-skip"); if (skip) skip.onclick = () => { delete this.results[st.key]; this.step++; this.render(); };
  },
  ring(frac, label, sub) {
    const r = 54, c = 2 * Math.PI * r;
    return `<div class="ring"><svg viewBox="0 0 128 128"><circle cx="64" cy="64" r="${r}" class="track"/>
      <circle cx="64" cy="64" r="${r}" class="bar" stroke-dasharray="${c}" stroke-dashoffset="${c * (1 - frac)}"/></svg>
      <div class="ring-label"><b class="num">${label}</b><span>${sub}</span></div></div>`;
  },
  async capture(key) {
    this.busy = true;
    this.audio = this.audio || (window.AudioContext ? new AudioContext() : null);
    if (Live.status && Live.status.simulated) {
      await api("/api/sim/posture", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ posture: key }) });
    }
    $(".cb-actions").innerHTML = "";
    const run = $("#cb-run");
    for (let i = PREP_S; i > 0; i--) { run.innerHTML = this.ring(0, i, t("asetu paikallesi")); await sleep(1000); if (!this.el) return; }
    const t0 = performance.now();
    const req = api(`/api/calibration/capture?posture=${key}&seconds=${CAPTURE_S}`, { method: "POST" }).catch((e) => ({ ok: false, reason: e.message }));
    const tick = setInterval(() => {
      const f = Math.min(1, (performance.now() - t0) / (CAPTURE_S * 1000));
      if ($("#cb-run")) $("#cb-run").innerHTML = this.ring(f, Math.ceil(CAPTURE_S * (1 - f)), t("pysy paikallasi"));
    }, 100);
    const res = await req;
    clearInterval(tick);
    this.beep(res.ok); if (navigator.vibrate) navigator.vibrate(res.ok ? 200 : [100, 80, 100]);
    this.results[key] = res;
    this.busy = false;
    this.render();
  },
  beep(ok) {
    const a = this.audio; if (!a) return;
    const o = a.createOscillator(), g = a.createGain();
    o.frequency.value = ok ? 880 : 330; g.gain.value = 0.08;
    o.connect(g); g.connect(a.destination); o.start(); o.stop(a.currentTime + (ok ? 0.18 : 0.35));
  },
  async summary() {
    const refs = {}, measurements = {};
    for (const [k, r] of Object.entries(this.results)) if (r && r.ok) { refs[k] = r.g; measurements[k] = r; }
    if (!refs.supine || !refs.left) { this.step = refs.supine ? 1 : 0; return this.render(); }
    $("#cb-body").innerHTML = `<div class="cb-step"><p class="hint">${t("Tallennetaan…")}</p></div>`;
    let cal;
    try {
      const r = await fetch("/api/calibrations", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refs, measurements }) });
      cal = await r.json();
      if (!r.ok) throw new Error(cal.detail || r.status);
    } catch (e) {
      $("#cb-body").innerHTML = `<div class="cb-step"><div class="cb-fail">${t("Tallennus epäonnistui: {0}", esc(e.message))}</div><div class="btn-row cb-actions"><button class="btn" id="cb-back">${t("Takaisin")}</button></div></div>`;
      $("#cb-back").onclick = () => { this.step = 0; this.render(); };
      return;
    }
    const q = cal.quality || { angles: {}, warnings: [] };
    $("#cb-body").innerHTML = `<div class="cb-step">
      <div class="cb-ok big">✓ ${t("Kalibrointi tallennettu")}</div>
      <table class="mini"><tr><th>${t("Asento")}</th><th>${t("Kulma selällään-asennosta")}</th></tr>
        ${LYING.map((k) => `<tr><td><i class="sw" style="background:var(${POSTURE[k].color})"></i>${POSTURE[k].label}</td><td class="num">${q.angles[k] != null ? Math.round(q.angles[k]) + "°" : "–"}${refs[k] ? "" : ` <span class="faint">${t("arvioitu")}</span>`}</td></tr>`).join("")}
      </table>
      ${q.warnings.length ? `<div class="warn">${q.warnings.map(esc).join("<br>")}</div>` : `<p class="hint">${t("Kulmat näyttävät järkeviltä. Kalibrointi on käytössä seuraavasta tallenteesta alkaen.")}</p>`}
      <div class="btn-row cb-actions"><button class="btn primary" id="cb-done">${t("Valmis")}</button></div></div>`;
    $("#cb-done").onclick = () => this.close();
  },
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Modal confirmation; resolves true/false. `danger` styles the confirm button red.
function confirmDialog({ title, body, confirm = "OK", cancel = t("Peru"), danger = false }) {
  return new Promise((resolve) => {
    const el = document.createElement("div");
    el.className = "modal";
    el.innerHTML = `<div class="sheet fade-in confirm" role="alertdialog" aria-label="${esc(title)}">
      <div class="cb-step" style="text-align:left"><h2 style="font-size:20px">${esc(title)}</h2><div class="hint">${body}</div>
      <div class="btn-row" style="justify-content:flex-end;margin-top:18px">
        <button class="btn" data-a="0">${esc(cancel)}</button><button class="btn ${danger ? "danger" : "primary"}" data-a="1">${esc(confirm)}</button></div></div></div>`;
    document.body.appendChild(el);
    const done = (v) => { el.remove(); document.removeEventListener("keydown", key); resolve(v); };
    const key = (e) => { if (e.key === "Escape") done(false); };
    document.addEventListener("keydown", key);
    el.addEventListener("click", (e) => { if (e.target === el) done(false); });
    el.querySelectorAll("[data-a]").forEach((b) => (b.onclick = () => done(b.dataset.a === "1")));
    el.querySelector('[data-a="0"]').focus();
  });
}

function toast(html, action) {
  document.querySelectorAll(".toast").forEach((t) => t.remove());
  const el = document.createElement("div");
  el.className = "toast fade-in";
  el.innerHTML = `<span>${html}</span>${action ? `<button class="btn sm">${esc(action.label)}</button>` : ""}`;
  document.body.appendChild(el);
  if (action) el.querySelector("button").onclick = async () => { el.remove(); await action.run(); };
  setTimeout(() => el.isConnected && el.remove(), 10000);
}

async function markSymptom(btn) {
  btn.classList.add("pressed"); setTimeout(() => btn.classList.remove("pressed"), 400);
  if (navigator.vibrate) navigator.vibrate(60);
  const r = await fetch("/api/events", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) { toast(esc(j.detail || t("Merkintä epäonnistui"))); return; }
  toast(t("Merkitty klo {0}. Näet sen tallenteen aikajanalla.", fmt.clockSec(j.event.wall_ns / 1e6)));
}

async function deleteRecording(id, label) {
  const ok = await confirmDialog({
    title: t("Poistetaanko tallenne?"),
    body: `<b>${esc(label)}</b><br><br>${t("Tallenne siirtyy roskakoriin ja poistuu lopullisesti 30 päivän kuluttua. Sen voi palauttaa siihen asti kohdasta Asetukset → Roskakori.")}`,
    confirm: t("Poista"), danger: true,
  });
  if (!ok) return false;
  const r = await fetch(`/api/sessions/${encodeURIComponent(id)}`, { method: "DELETE" });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) { toast(esc(j.detail || t("Poisto epäonnistui"))); return false; }
  toast(t("Tallenne siirretty roskakoriin."), {
    label: t("Kumoa"),
    run: async () => {
      const rr = await fetch(`/api/trash/${encodeURIComponent(j.trashed)}/restore`, { method: "POST" });
      if (rr.ok) { toast(t("Tallenne palautettu.")); route(); } else toast(t("Palautus epäonnistui."));
    },
  });
  return true;
}

// ------------------------------------------------------------------ trends

const TREND_METRICS = {
  share: { label: t("Lisälyönnit"), unit: t("% lyönneistä"), get: (p) => (p.ectopy_share != null ? p.ectopy_share * 100 : null), digits: 2 },
  posture: { label: t("Asennoittain"), unit: t("% lyönneistä"), digits: 2 },
  perhour: { label: t("Lisälyönnit / h"), unit: "/ h", get: (p) => p.ectopy_per_hour, digits: 0 },
  rmssd: { label: "RMSSD", unit: "ms", get: (p) => p.rmssd, digits: 0 },
  hr: { label: t("Keskisyke"), unit: "bpm", get: (p) => p.hr_mean, digits: 0 },
};

const Trend = {
  metric: "share",
  mount(el, points) {
    this.el = el; this.points = points;
    try { this.metric = localStorage.getItem("openholter.trend") || "share"; } catch {}
    if (!TREND_METRICS[this.metric]) this.metric = "share";
    if (points.length < 1) {
      el.innerHTML = `<div class="card-head"><span class="card-title">${t("Trendit")}</span></div><p class="hint">${t("Trendi näkyy, kun ensimmäinen tallenne on analysoitu.")}</p>`;
      return;
    }
    el.innerHTML = `
      <div class="card-head"><span class="card-title">${t("Trendit")}</span><span class="meta" id="tr-sum"></span></div>
      <div class="seg" id="tr-seg">${Object.entries(TREND_METRICS).map(([k, m]) => `<button data-m="${k}" class="${k === this.metric ? "on" : ""}">${m.label}</button>`).join("")}</div>
      <canvas id="tr-cv"></canvas>
      <div class="legend" id="tr-legend"></div>`;
    el.querySelectorAll("#tr-seg button").forEach((b) => (b.onclick = () => {
      this.metric = b.dataset.m;
      try { localStorage.setItem("openholter.trend", this.metric); } catch {}
      el.querySelectorAll("#tr-seg button").forEach((x) => x.classList.toggle("on", x === b));
      this.draw();
    }));
    const cv = $("#tr-cv");
    cv.addEventListener("mousemove", (e) => this.hover(e));
    cv.addEventListener("mouseleave", () => { $("#tooltip").style.display = "none"; });
    cv.addEventListener("click", (e) => { const p = this.nearest(e); if (p) location.hash = `#/recording/${p.id}`; });
    this.onResize = () => this.draw();
    window.addEventListener("resize", this.onResize);
    this.draw();
  },
  unmount() { if (this.onResize) window.removeEventListener("resize", this.onResize); },
  series() {
    if (this.metric === "posture") {
      return LYING.map((k) => ({ key: k, color: css(POSTURE[k].color), label: POSTURE[k].label,
        vals: this.points.map((p) => (p.ectopy_by_posture && p.ectopy_by_posture[k] ? p.ectopy_by_posture[k].share * 100 : null)) }))
        .filter((s) => s.vals.some((v) => v != null));
    }
    const m = TREND_METRICS[this.metric];
    return [{ key: this.metric, color: css(this.metric === "rmssd" || this.metric === "hr" ? "--hr" : "--ecg"), label: m.label, vals: this.points.map(m.get) }];
  },
  draw() {
    const cv = $("#tr-cv"); if (!cv) return;
    const { ctx, w, h } = setupCanvas(cv);
    ctx.clearRect(0, 0, w, h);
    const m = TREND_METRICS[this.metric], ser = this.series();
    const pad = { l: 44, r: 14, t: 12, b: 26 };
    const xs = this.points.map((p) => p.start_wall_ns / 1e6);
    const x0 = Math.min(...xs), x1 = Math.max(...xs);
    const span = Math.max(x1 - x0, 86400e3);
    const X = (t) => pad.l + (xs.length === 1 ? 0.5 : (t - x0) / span) * (w - pad.l - pad.r);
    const all = ser.flatMap((s) => s.vals).filter((v) => v != null);
    const hiRaw = all.length ? Math.max(...all) : 1;
    const nice = (v) => { const p = 10 ** Math.floor(Math.log10(v || 1)); return Math.ceil(v / p * 1.15) * p; };
    const lo = 0, hi = this.metric === "hr" ? Math.ceil(Math.max(...all, 60) / 10) * 10 + 5 : nice(hiRaw);
    const yLo = this.metric === "hr" ? Math.floor(Math.min(...all, 50) / 10) * 10 - 5 : lo;
    const Y = (v) => pad.t + (1 - (v - yLo) / (hi - yLo)) * (h - pad.t - pad.b);
    this.X = X; this.Y = Y;
    // grid + axes
    ctx.font = "11px " + css("--mono"); ctx.fillStyle = css("--faint"); ctx.strokeStyle = css("--line"); ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const v = yLo + ((hi - yLo) * i) / 4, y = Math.round(Y(v)) + 0.5;
      ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(w - pad.r, y); ctx.stroke();
      ctx.fillText(dec(v, m.digits && hi < 10 ? 1 : 0), 4, y + 4);
    }
    const labels = new Set();
    this.points.forEach((p, i) => {
      const d = new Date(xs[i]), key = d.toDateString();
      if (labels.has(key)) return; labels.add(key);
      const s = d.toLocaleDateString(LOCALE, { day: "numeric", month: "numeric" });
      ctx.fillText(s, Math.min(w - pad.r - 30, Math.max(pad.l - 10, X(xs[i]) - 14)), h - 8);
    });
    // series
    for (const s of ser) {
      ctx.strokeStyle = s.color; ctx.lineWidth = 2; ctx.lineJoin = "round"; ctx.globalAlpha = 0.85;
      ctx.beginPath(); let pen = false;
      s.vals.forEach((v, i) => { if (v == null) { pen = false; return; } const x = X(xs[i]), y = Y(v); pen ? ctx.lineTo(x, y) : ctx.moveTo(x, y); pen = true; });
      ctx.stroke(); ctx.globalAlpha = 1;
      s.vals.forEach((v, i) => {
        if (v == null) return;
        ctx.fillStyle = s.color; ctx.beginPath(); ctx.arc(X(xs[i]), Y(v), 4.5, 0, Math.PI * 2); ctx.fill();
        ctx.strokeStyle = css("--panel-solid"); ctx.lineWidth = 2; ctx.stroke();
      });
    }
    // symptom markers under the dots
    this.points.forEach((p, i) => {
      if (!p.symptoms) return;
      ctx.fillStyle = css("--sym"); ctx.font = "10px " + css("--font");
      ctx.fillText(`♥${p.symptoms}`, X(xs[i]) - 9, h - pad.b + 2);
    });
    // summary + legend
    const main = ser[0];
    const last = main ? [...main.vals].reverse().find((v) => v != null) : null;
    const vals = main ? main.vals.filter((v) => v != null) : [];
    const avg = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
    const f = (v) => (v == null ? "–" : dec(v, m.digits));
    $("#tr-sum").textContent = this.metric === "posture" ? t("{0} tallennetta", this.points.length) : t("viimeisin {0} {1} · keskiarvo {2} · {3} tallennetta", f(last), m.unit, f(avg), this.points.length);
    $("#tr-legend").innerHTML = this.metric === "posture"
      ? ser.map((s) => `<span><i style="background:${s.color}"></i>${s.label}</span>`).join("") + `<span class="faint">${t("lisälyöntien osuus lyönneistä kussakin asennossa")}</span>`
      : `<span class="faint">${m.unit}. ${t("Klikkaa pistettä avataksesi tallenteen.")}</span>`;
  },
  nearest(e) {
    const cv = $("#tr-cv"), r = cv.getBoundingClientRect(), x = e.clientX - r.left;
    let best = null, bd = 1e9;
    this.points.forEach((p) => { const d = Math.abs(this.X(p.start_wall_ns / 1e6) - x); if (d < bd) { bd = d; best = p; } });
    return bd < 30 ? best : null;
  },
  hover(e) {
    const p = this.nearest(e), tip = $("#tooltip");
    if (!p) { tip.style.display = "none"; return; }
    const m = TREND_METRICS[this.metric], ser = this.series(), i = this.points.indexOf(p);
    const d = new Date(p.start_wall_ns / 1e6);
    const rows = ser.map((s) => `${this.metric === "posture" ? `<i class="sw" style="background:${s.color}"></i>${s.label} ` : ""}<b>${s.vals[i] == null ? "–" : dec(s.vals[i], m.digits)}</b> ${m.unit}`);
    tip.innerHTML = `<span class="t">${d.toLocaleDateString(LOCALE, { weekday: "short", day: "numeric", month: "numeric" })} ${fmt.clock(d.getTime())} · ${fmt.dur(p.duration_s)}</span><br>${rows.join("<br>")}${p.symptoms ? `<br><span style="color:var(--sym)">♥</span> ${t("{0} oiremerkintää", p.symptoms)}` : ""}`;
    tip.style.display = "block";
    tip.style.left = `${Math.min(e.clientX + 14, window.innerWidth - 220)}px`;
    tip.style.top = `${e.clientY + 14}px`;
  },
};

// ------------------------------------------------------------------ recordings list

function sparkSvg(vals, w = 300, h = 54) {
  const pts = (vals || []).map((v, i) => [i, v]).filter((p) => p[1] != null);
  if (pts.length < 2) return `<svg viewBox="0 0 ${w} ${h}"></svg>`;
  const ys = pts.map((p) => p[1]);
  const lo = Math.min(...ys) - 3, hi = Math.max(...ys) + 3, n = vals.length - 1;
  const X = (i) => (i / n) * w, Y = (v) => h - 4 - ((v - lo) / (hi - lo)) * (h - 8);
  const d = pts.map((p, i) => `${i ? "L" : "M"}${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join("");
  const area = `${d}L${X(pts[pts.length - 1][0]).toFixed(1)},${h}L${X(pts[0][0]).toFixed(1)},${h}Z`;
  const id = "sg" + Math.random().toString(36).slice(2, 8);
  return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
    <defs><linearGradient id="${id}" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="rgba(110,168,255,.35)"/><stop offset="1" stop-color="rgba(110,168,255,0)"/></linearGradient></defs>
    <path d="${area}" fill="url(#${id})"/><path d="${d}" fill="none" stroke="#6ea8ff" stroke-width="1.6" vector-effect="non-scaling-stroke"/></svg>`;
}

function qualityChip(score) {
  if (score == null) return "";
  const c = score > 0.9 ? "--good" : score > 0.7 ? "--fair" : "--poor";
  return `<span class="chip"><span class="sw" style="background:var(${c})"></span>${t("Laatu")} <b>${fmt.pct(score)} %</b></span>`;
}

function analysisChip(an) {
  const at = an.scheduled_at ? an.scheduled_at.replace(":", ".") : "";
  const txt = { pending: t("Analyysi klo {0}", at), queued: t("Analyysi jonossa"), running: t("Analysoidaan {0} %", Math.round((an.progress || 0) * 100)),
    done: t("Analysoitu"), stale: t("Analysoi uudelleen"), error: t("Analyysivirhe") }[an.state];
  if (!txt) return "";
  const c = an.state === "done" ? "--good" : an.state === "error" ? "--poor" : "--fair";
  return `<span class="chip"><span class="sw" style="background:var(${c})"></span>${txt}</span>`;
}

const RecordingsPage = {
  async mount(el) {
    el.innerHTML = `<div class="page-head fade-in"><div><h1>${t("Tallenteet")}</h1><div class="sub">${t("Uusin ensin.")}</div></div></div>
      <section class="card trend fade-in" id="tr"></section>
      <div id="nl" class="grid nights"></div>`;
    api("/api/trends").then((pts) => { if ($("#tr")) Trend.mount($("#tr"), pts); }).catch(() => { if ($("#tr")) $("#tr").remove(); });
    let list;
    try { list = await api("/api/sessions"); } catch (e) { if ($("#nl")) $("#nl").innerHTML = `<div class="hint">${t("Lataus epäonnistui: {0}", esc(e.message))}</div>`; return; }
    if (!$("#nl")) return; // navigated away while loading
    if (!list.length) {
      $("#nl").outerHTML = `<div class="card empty-state"><div class="big">${t("Ei vielä tallenteita")}</div>${t("Tallennus alkaa automaattisesti, kun puet vyön.")}</div>`;
      return;
    }
    $("#nl").innerHTML = list.map(({ meta: m, summary: s, analysis: an }, i) => {
      const t0 = m.started_wall_ns / 1e6;
      const t1 = m.ended_wall_ns ? m.ended_wall_ns / 1e6 : Date.now();
      const day = fmt.dayTitle(t0);
      const live = m.state === "recording";
      return `<a class="card night fade-in" style="animation-delay:${i * 40}ms" href="#/recording/${esc(m.id)}">
        <div><div class="wd">${esc(day.wd)}</div><div class="date">${esc(day.date)}</div>
        <div class="time">${fmt.range(t0, t1, live)} · ${fmt.dur((t1 - t0) / 1000)}</div></div>
        ${s ? sparkSvg(s.hr_spark) : `<div class="hint" style="height:54px;display:grid;place-items:center">${t("Yhteenveto lasketaan, kun tallenne päättyy.")}</div>`}
        <div class="chips">
          ${live ? `<span class="chip live"><span class="sw" style="background:var(--ecg)"></span>${t("Tallentaa nyt")}</span>` : ""}
          ${s && s.hr_mean ? `<span class="chip">${t("Syke")} <b>${Math.round(s.hr_mean)}</b> (${s.hr_min}–${s.hr_max})</span>` : ""}
          ${s ? qualityChip(s.quality_score) : ""}
          ${s && s.disconnects ? `<span class="chip">${t("Katkoja")} <b>${s.disconnects}</b></span>` : ""}
          ${an && an.hrv_rmssd != null ? `<span class="chip">RMSSD <b>${Math.round(an.hrv_rmssd)}</b> ms</span>` : ""}
          ${an ? analysisChip(an) : ""}
          ${m.device && /SIM/.test(m.device.name || "") ? `<span class="chip">${t("simuloitu")}</span>` : ""}
        </div></a>`;
    }).join("");
  },
  unmount() { Trend.unmount(); },
};

// ------------------------------------------------------------------ recording view

function postureClasses(p) {
  if (p.calibrated) return p.classes;
  // Uncalibrated: split the roll angle into four 90° sectors, centred on the most common angle.
  const hist = new Array(36).fill(0);
  p.roll.forEach((r, i) => { if (r != null && !p.upright[i]) hist[Math.floor(((r + 360) % 360) / 10)]++; });
  const peak = hist.indexOf(Math.max(...hist)) * 10 + 5;
  return p.roll.map((r, i) => (r == null ? null : p.upright[i] ? "upright" : "ABCD"[Math.floor((((r - peak + 45) % 360) + 360) % 360 / 90)]));
}

function postureLegend(p, classes) {
  if (p.calibrated) {
    const sec = p.seconds, lying = LYING.reduce((a, k) => a + sec[k], 0) || 1;
    return [...LYING, "upright", "moving"].filter((k) => sec[k] > 0).map((k) =>
      `<span><i style="background:var(${POSTURE[k].color})"></i>${POSTURE[k].label} <span class="faint">${fmt.dur(sec[k])}${LYING.includes(k) ? ` · ${Math.round((sec[k] / lying) * 100)} %` : ""}</span></span>`).join("");
  }
  const counts = {}; let total = 0;
  classes.forEach((c) => { if (c) { counts[c] = (counts[c] || 0) + 1; total++; } });
  return ["A", "B", "C", "D", "upright"].map((k) =>
    `<span><i style="background:var(${POSTURE[k].color})"></i>${POSTURE[k].label} <span class="faint">${Math.round(((counts[k] || 0) / (total || 1)) * 100)} %</span></span>`).join("");
}

const CAL_HOW = { chosen: t("valittu tälle tallenteelle"), auto: t("uusin ennen tallennetta"), later: t("lähin (tehty tallenteen jälkeen)") };

function calSource(src) {
  if (!src || src === "live") return t("Live-kalibrointi");
  if (src.startsWith("session:")) return t("merkitty tallenteesta {0}", calLabel(src.slice(8), true));
  return src;
}

class RecordingView {
  constructor(el, id, startAt = null) { this.el = el; this.id = id; this.startAt = startAt; this.cache = new Map(); this.span = 10; this.t = 0; }

  async mount() {
    this.el.innerHTML = `<div class="hint">${t("Ladataan…")}</div>`;
    const W = Math.max(400, Math.min(2400, Math.round(this.el.clientWidth - 120)));
    try { this.d = await api(`/api/sessions/${encodeURIComponent(this.id)}?points=${W}`); }
    catch (e) { this.el.innerHTML = `<a class="back" href="#/recordings">← ${t("Tallenteet")}</a><div class="hint">${t("Tallennetta ei voitu ladata ({0}).", esc(e.message))}</div>`; return; }
    const d = this.d, m = d.meta, s = d.summary;
    this.t0 = m.started_wall_ns / 1e6;
    this.dur = d.duration;
    this.classes = postureClasses(d.posture);
    const ar = d.analysis && d.analysis.result;
    const ectRes = ar && (ar.ectopy || ar.ectopy_rr);
    this.ectopics = ectRes ? ectRes.events.slice().sort((a, b) => a - b) : [];
    this.ectKinds = new Map((ectRes && ectRes.details || []).map((x) => [x.t, x]));
    this.ectFromEcg = !!(ectRes && ectRes.method === "ecg"); // ECG times are exact R peaks
    this.refined = new Map(); // RR-estimate time -> R peak found in the ECG (strap-RR fallback only)
    this.symptoms = (m.events || []).filter((e) => e.kind === "symptom" && e.wall_ns)
      .map((e) => ({ id: e.id, t: (e.wall_ns - m.started_wall_ns) / 1e9, note: e.note || "" }));
    this.marks = this.marks || [];
    const day = fmt.dayTitle(this.t0);
    const live = m.state === "recording";
    const gapTotal = d.gaps.reduce((a, g) => a + g[1] - g[0], 0);

    this.el.innerHTML = `
      <a class="back" href="#/recordings">← ${t("Tallenteet")}</a>
      <div class="page-head fade-in"><div>
        <h1 style="text-transform:capitalize">${esc(day.wd)} ${esc(day.date)}</h1>
        <div class="sub">${live ? fmt.clock(this.t0) + " – " + t("käynnissä") : fmt.range(this.t0, this.t0 + this.dur * 1000)} · ${esc(m.device?.name || "")}${m.end_reason ? ` · ${t("päättyi: {0}", esc(endReason(m.end_reason)))}` : ""}</div>
      </div><span class="spacer"></span>
        <button class="btn sm" id="nv-pdf" ${live ? `disabled title="${t("Raportin voi tehdä, kun tallennus on päättynyt")}"` : ""}>
          <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v11m0 0-4-4m4 4 4-4M5 19h14"/></svg>${t("PDF-raportti")}</button>
        <button class="btn sm ghost-danger" id="nv-del" ${live ? `disabled title="${t("Lopeta tallennus ennen poistamista")}"` : ""}>
          <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/></svg>${t("Poista")}</button>
      </div>
      <div class="grid stats fade-in">
        ${stat(t("Kesto"), fmt.dur(this.dur).replace(" min", "<small>min</small>").replace(" h", "<small>h</small>"), `${fmt.clock(this.t0)}–${fmt.clock(this.t0 + this.dur * 1000)}`)}
        ${stat(t("Tallennettu"), s ? `${fmt.pct(s.coverage, 1)}<small>%</small>` : "–", gapTotal > 1 ? t("katkoja {0}", fmt.dur(gapTotal)) : t("ei katkoja"))}
        ${stat(t("Signaalin laatu"), s ? `${fmt.pct(s.quality_score)}<small>%</small>` : "–", s ? t("heikkoa {0} %", fmt.pct((s.quality_windows.poor + s.quality_windows.none) / Math.max(1, Object.values(s.quality_windows).reduce((a, b) => a + b, 0)), 1)) : t("lasketaan lopuksi"))}
        ${stat(t("Keskisyke"), s && s.hr_mean ? `${Math.round(s.hr_mean)}<small>bpm</small>` : "–", s && s.hr_min ? t("vaihteluväli {0}–{1}", s.hr_min, s.hr_max) : "")}
        ${(() => {
          const e = d.analysis && d.analysis.result && d.analysis.result.ectopy;
          return e && e.method === "ecg" ? stat(t("Lyöntejä"), fmt.int(e.beats), t("EKG:n R-piikit")) : stat(t("Lyöntejä"), s ? `${fmt.int(s.rr_count)}` : "–", t("vyön RR-välit"));
        })()}
        ${stat(t("Yhteyskatkot"), String(Math.max(0, m.connections.length - 1)), t("{0} yhteysjaksoa", m.connections.length))}
      </div>

      <section class="card timeline fade-in">
        <div class="card-head"><span class="card-title">${t("Aikajana")}</span><span class="meta" id="nv-cursor"></span></div>
        <div class="track posture"><span class="lbl">${t("Asento")}</span><canvas id="nv-posture"></canvas></div>
        <div class="track hr"><span class="lbl">${t("Syke")}</span><canvas id="nv-hr"></canvas></div>
        <div class="track overview"><span class="lbl">${t("EKG")}</span><canvas id="nv-ov"></canvas></div>
        <div class="track axis"><canvas id="nv-axis"></canvas></div>
        <div class="legend">
          ${postureLegend(d.posture, this.classes)}
          <span><i style="background:repeating-linear-gradient(45deg,rgba(148,163,184,.35) 0 2px,transparent 2px 4px)"></i>${t("Ei dataa")}</span>
          <span><i style="background:var(--fair)"></i>${t("EKG: häiriö")}</span>
          <span><i style="background:var(--none)"></i>${t("EKG: ei kontaktia")}</span>
          ${d.posture.calibrated ? "" : `<span class="faint">${t("Kalibroimaton: asennot ovat ryhmiä A–D. Kalibroi Live-näkymässä tai merkitse asentoja alla.")}</span>`}
        </div>
        ${(d.posture.warnings || []).map((w) => `<div class="warn" style="margin:12px 20px 0">${esc(w)}</div>`).join("")}
      </section>

      <section class="card fade-in symcard" id="nv-sym"></section>

      <section class="card fade-in calcard" id="nv-cal"></section>

      <section class="card detail fade-in">
        <div class="card-head">
          <span class="card-title">${t("EKG")}</span>
          <span class="num" id="nv-dt" style="font-weight:600"></span>
          <span class="meta" id="nv-dmeta"></span>
        </div>
        <canvas id="nv-detail"></canvas>
        <div class="foot">
          <button class="btn sm" id="nv-prev" title="${t("Taaksepäin")} (←)">‹</button>
          <button class="btn sm" id="nv-next" title="${t("Eteenpäin")} (→)">›</button>
          <div class="seg" id="nv-spans">${[5, 10, 30, 60, 300, 900, 1800, 3600].map((v) => `<button data-span="${v}">${v < 60 ? v + " s" : v < 3600 ? v / 60 + " min" : v / 3600 + " h"}</button>`).join("")}</div>
          <div class="ect-nav" id="nv-enav" ${this.ectopics.length ? "" : "hidden"}>
            <button class="btn sm" id="nv-eprev" title="${t("Edellinen lisälyönti")}">‹</button>
            <span class="ect-count"><i></i><span id="nv-ecount">${t("Lisälyönnit {0}", this.ectopics.length)}</span></span>
            <button class="btn sm" id="nv-enext" title="${t("Seuraava lisälyönti")}">›</button>
          </div>
          <span class="hint">${t("Vedä siirtääksesi, klikkaa aikajanaa hypätäksesi.")}</span>
        </div>
      </section>

      <section class="card fade-in" id="nv-an"></section>`;
    this.renderSymptoms();
    this.renderCal();
    this.renderAnalysis(d.analysis);
    $("#nv-pdf").onclick = async (e) => {
      const b = e.currentTarget, label = b.innerHTML;
      b.disabled = true; b.textContent = t("Luodaan PDF…");
      try {
        const r = await fetch(`/api/sessions/${encodeURIComponent(this.id)}/report.pdf?lang=${LANG}`, { headers: { "X-Lang": LANG } });
        if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.status);
        const blob = await r.blob();
        const name = (r.headers.get("content-disposition") || "").match(/filename="?([^";]+)/);
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob); a.download = name ? name[1] : "openholter-ekg.pdf";
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 60000);
      } catch (err) { toast(t("PDF:n luonti epäonnistui: {0}", esc(err.message))); }
      b.disabled = false; b.innerHTML = label;
    };
    $("#nv-del").onclick = async () => {
      const label = `${day.wd} ${day.date}, ${fmt.range(this.t0, this.t0 + this.dur * 1000)} (${fmt.dur(this.dur)})`;
      if (await deleteRecording(this.id, label)) location.hash = "#/recordings";
    };

    // start the detail window at the first 10 s that contain good data, 30 min in
    // #/recording/<id>/<seconds> opens at that moment (centred); otherwise 30 min in
    this.t = this.startAt != null && isFinite(this.startAt)
      ? clamp(this.startAt - this.span / 2, 0, Math.max(0, this.dur - this.span))
      : Math.min(Math.max(0, this.dur - this.span), 1800);
    this.startAt = null;
    this.drawTimeline();
    this.ovData = await this.fetchEcg(0, this.dur, $("#nv-ov").clientWidth);
    this.drawOverview();
    this.bind();
    this.setSpan(10);
  }

  unmount() {
    window.removeEventListener("keydown", this.onKey); window.removeEventListener("resize", this.onResize);
    clearTimeout(this._poll); this.dead = true;
  }

  // ---------------------------------------------------------------- calibration card

  renderCal() {
    const p = this.d.posture, cals = this.d.calibrations || [];
    const cur = p.calibrated ? p.calibration : null;
    const chosen = cur && cur.how === "chosen" ? cur.id : "";
    const marking = !!this.marking;
    const have = new Set(this.marks.map((x) => x.posture));
    $("#nv-cal").innerHTML = `
      <div class="card-head"><span class="card-title">${t("Asennon kalibrointi")}</span>
        <span class="meta">${cur ? `${esc(calLabel(cur.id))} · ${esc(calSource(cur.source))} · ${esc(CAL_HOW[cur.how] || "")}` : t("ei kalibrointia")}</span></div>
      <div class="btn-row">
        <select id="nv-calsel" ${cals.length ? "" : "disabled"}>
          <option value="">${t("Automaattinen (uusin ennen tallennetta)")}</option>
          ${cals.map((c) => `<option value="${esc(c.id)}" ${c.id === chosen ? "selected" : ""}>${esc(calLabel(c.id))} · ${esc(calSource(c.source))}</option>`).join("")}
        </select>
        <button class="btn sm ${marking ? "primary" : ""}" id="nv-mark">${marking ? t("Lopeta merkintä") : t("Merkitse asentoja tästä tallenteesta")}</button>
      </div>
      ${marking ? `
        <p class="hint" style="margin:12px 0 8px">${t("Vedä <b>Asento</b>-raidalla jakso, jonka aikana tiedät olleesi tietyssä asennossa. Selällään ja vasen kylki tarvitaan, muut tarkentavat.")}</p>
        <div class="chips">${this.marks.map((x, i) => `<span class="chip"><i class="sw" style="background:var(${POSTURE[x.posture].color})"></i>${POSTURE[x.posture].label} <b class="num">${fmt.clock(this.t0 + x.start * 1000)}–${fmt.clock(this.t0 + x.end * 1000)}</b><button class="chip-x" data-rm="${i}" aria-label="${t("Poista")}">✕</button></span>`).join("") || `<span class="faint">${t("Ei merkintöjä vielä.")}</span>`}</div>
        <div class="btn-row" style="margin-top:12px"><button class="btn primary sm" id="nv-mkcal" ${have.has("supine") && have.has("left") ? "" : "disabled"}>${t("Luo kalibrointi merkinnöistä")}</button>
          <span class="hint" id="nv-markerr"></span></div>` : ""}`;
    $("#nv-calsel").onchange = async (e) => {
      await api(`/api/sessions/${encodeURIComponent(this.id)}/calibration`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ calibration_id: e.target.value || null }) });
      this.reload();
    };
    $("#nv-mark").onclick = () => { this.marking = !this.marking; this.renderCal(); this.drawTimeline(); };
    this.el.querySelectorAll("[data-rm]").forEach((b) => (b.onclick = () => { this.marks.splice(+b.dataset.rm, 1); this.renderCal(); this.drawTimeline(); }));
    const mk = $("#nv-mkcal");
    if (mk) mk.onclick = async () => {
      const r = await fetch(`/api/sessions/${encodeURIComponent(this.id)}/calibration-from-segments`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ segments: this.marks }) });
      const j = await r.json();
      if (!r.ok) { $("#nv-markerr").textContent = j.detail || t("Epäonnistui"); return; }
      this.marking = false; this.marks = [];
      this.reload();
    };
  }

  async reload() {
    const y = window.scrollY;
    this.cache.clear();
    this.unmount(); // drop window listeners; mount() binds fresh ones
    this.dead = false;
    await this.mount();
    window.scrollTo(0, y);
  }

  askPosture(ev, a, b) {
    const pop = document.createElement("div");
    pop.className = "popover";
    pop.innerHTML = `<div class="hint" style="margin-bottom:6px">${t("{0}–{1} oli:", fmt.clock(this.t0 + a * 1000), fmt.clock(this.t0 + b * 1000))}</div>` +
      LYING.map((k) => `<button class="btn sm" data-p="${k}"><i class="sw" style="background:var(${POSTURE[k].color})"></i>${POSTURE[k].label}</button>`).join("") +
      `<button class="btn sm" data-p="">${t("Peru")}</button>`;
    pop.style.left = `${Math.min(ev.clientX, window.innerWidth - 220)}px`;
    pop.style.top = `${ev.clientY + 12}px`;
    document.body.appendChild(pop);
    const done = (k) => { pop.remove(); this.pending = null; if (k) this.marks.push({ posture: k, start: a, end: b }); this.renderCal(); this.drawTimeline(); };
    pop.querySelectorAll("[data-p]").forEach((x) => (x.onclick = () => done(x.dataset.p)));
    setTimeout(() => document.addEventListener("pointerdown", function out(e) { if (!pop.contains(e.target)) { document.removeEventListener("pointerdown", out); if (pop.isConnected) done(""); } }), 0);
  }

  // ---------------------------------------------------------------- analysis card

  renderAnalysis(a) {
    if (this.dead) return;
    const st = a.status, res = a.result;
    const at = st.scheduled_at ? t("klo {0}", st.scheduled_at.replace(":", LANG === "fi" ? "." : ":")) : t("painikkeesta");
    const state = {
      recording: ["", t("Analysoidaan, kun tallenne on päättynyt.")],
      pending: ["", st.deferred === "recording" ? t("Ajetaan automaattisesti, kun käynnissä oleva tallennus päättyy.") : t("Odottaa päivittäistä analyysia ({0}).", at)],
      queued: ["wait", t("Jonossa…")],
      running: ["wait", t("Analysoidaan… {0} %", Math.round((st.progress || 0) * 100))],
      done: ["ok", `${t("Analysoitu")} ${res && res.created_at ? fmt.clock(Date.parse(res.created_at)) : ""}${res && res.created_at ? " · " + new Date(Date.parse(res.created_at)).toLocaleDateString(LOCALE, { day: "numeric", month: "numeric" }) : ""}`],
      stale: ["warn", t("Kalibrointi on muuttunut analyysin jälkeen. Analysoi uudelleen.")],
      error: ["err", t("Virhe: {0}", st.error || "")],
    }[st.state] || ["", st.state];
    const busy = st.state === "queued" || st.state === "running";
    const canRun = st.state !== "recording" && !busy;
    $("#nv-an").innerHTML = `
      <div class="card-head"><span class="card-title">${t("Analyysi")}</span>
        <span class="status-chip ${state[0]}">${esc(state[1])}</span>
        <span class="spacer"></span>
        <button class="btn sm ${st.state === "pending" || st.state === "stale" ? "primary" : ""}" id="nv-run" ${canRun ? "" : "disabled"}>${res ? t("Analysoi uudelleen") : t("Analysoi nyt")}</button></div>
      ${busy ? `<div class="progress"><i style="width:${Math.round((st.progress || 0.03) * 100)}%"></i></div>` : ""}
      ${res ? this.resultHtml(res) : `<p class="hint">${t("Analyysi tunnistaa lisälyönnit EKG:stä (VES/SVES) ja laskee ne asennoittain, sekä sykkeen ja sykevälivaihtelun.")}</p>`}`;
    $("#nv-run").onclick = async () => {
      await api(`/api/sessions/${encodeURIComponent(this.id)}/analyze`, { method: "POST" });
      this.pollAnalysis(true);
    };
    if (res && res.hrv) this.drawHrv(res);
    if (busy) this.pollAnalysis(false);
  }

  pollAnalysis(now) {
    clearTimeout(this._poll);
    this._poll = setTimeout(async () => {
      if (this.dead) return;
      const a = await api(`/api/sessions/${encodeURIComponent(this.id)}/analysis`);
      const wasBusy = this._busy;
      this._busy = a.status.state === "queued" || a.status.state === "running";
      if (wasBusy && !this._busy && a.status.state === "done") { this.reload(); return; }
      this.renderAnalysis(a);
    }, now ? 300 : 1200);
    this._busy = true;
  }

  resultHtml(r) {
    const p = r.posture || {}, hrv = r.hrv || {}, hp = r.hr_by_posture || {}, hb = hrv.by_posture || {};
    const ect = r.ectopy || r.ectopy_rr || {}, eb = ect.by_posture || {};
    const fromEcg = ect.method === "ecg";
    // small shares stay visible: 0,01 % rather than 0,0 %
    const pct = (x) => {
      if (x == null) return "–";
      const v = x * 100;
      if (v === 0) return "0 %";
      return `${dec(v, v < 0.1 ? 2 : 1)} %`;
    };
    const rate = (x) => (x == null ? "–" : x === 0 ? "0" : dec(x, x < 10 ? 1 : 0));
    const sec = p.seconds || {};
    const lying = LYING.reduce((a, k) => a + (sec[k] || 0), 0) || 1;
    // every class that has time or ectopics, so the rows add up to the total
    const rows = p.calibrated ? [...LYING, "upright", "moving", "unknown"].filter((k) => (sec[k] || 0) > 0 || (eb[k] && eb[k].count)) : [];
    const sumRows = rows.reduce((a, k) => a + (eb[k] ? eb[k].count : 0), 0);
    const bar = rows.filter((k) => LYING.includes(k)).map((k) => `<i style="width:${((sec[k] / lying) * 100).toFixed(2)}%;background:var(${POSTURE[k].color})" title="${POSTURE[k].label}"></i>`).join("");
    return `
      <div class="grid an-grid">
        <div class="an-wide ect-sum">
          <div><div class="an-k">${t("Lisälyönnit")} ${fromEcg ? `(${t("EKG")})` : `(${t("RR-arvio")})`} ${infoLink("lisalyonnit")}</div><div class="an-big"><span class="num">${ect.count != null ? fmt.int(ect.count) : "–"}</span><small>${t("kpl")}</small></div></div>
          ${fromEcg ? `<div><div class="an-k">VES / SVES</div><div class="an-big"><span class="num">${ect.ves} / ${ect.sves}</span></div></div>
          <div><div class="an-k">${t("Pareja")}</div><div class="an-big"><span class="num">${ect.couplets || 0}</span></div></div>` : ""}
          <div><div class="an-k">${t("Osuus lyönneistä")}</div><div class="an-big"><span class="num">${pct(ect.share)}</span></div></div>
          <div><div class="an-k">${t("Bigeminiajaksot")}</div><div class="an-big"><span class="num">${ect.bigeminy_runs ?? "–"}</span></div></div>
          ${fromEcg && ect.runs ? `<div><div class="an-k">${t("Sarjat (≥3)")}</div><div class="an-big"><span class="num">${ect.runs.length}</span></div></div>` : ""}
          ${fromEcg && ect.af_seconds != null ? `<div title="${t("Sopii eteisvärinään. Ei diagnoosi.")}"><div class="an-k">${t("Epäsäännöllinen rytmi")}</div><div class="an-big"><span class="num">${ect.af_seconds ? fmt.dur(ect.af_seconds) : "0"}</span></div></div>` : ""}
          <div class="hint" style="flex:1;min-width:240px">${fromEcg
            ? t("R-piikit EKG:stä: ennenaikainen lyönti, jota seuraa tauko. VES = leveä tai erimuotoinen QRS (todennäköisesti kammioperäinen), SVES = normaalimuotoinen. Selaa kohdat EKG-näkymän ‹ › -painikkeilla.")
            : t("Ennenaikainen lyönti + kompensatorinen tauko vyön RR-väleistä. Analysoi uudelleen, niin tunnistus tehdään EKG:stä.")}</div>
        </div>
        <div>
          <div class="an-k">${t("Asennoittain")} ${infoLink("asento")}</div>
          ${p.calibrated ? `<div class="stack">${bar}</div>
          <table class="mini">
            <tr><th>${t("Asento")}</th><th>${t("Aika")}</th><th>${t("Osuus")}</th><th>${t("Lisälyönnit")}</th><th>/ h</th><th>${t("% lyönneistä")}</th><th>${t("Syke")}</th><th>RMSSD</th></tr>
            ${rows.map((k) => `<tr><td><i class="sw" style="background:var(${POSTURE[k].color})"></i>${POSTURE[k].label}</td>
              <td class="num">${sec[k] ? fmt.dur(sec[k]) : "–"}</td><td class="num">${LYING.includes(k) ? Math.round((sec[k] / lying) * 100) + " %" : "–"}</td>
              <td class="num"><b>${eb[k] ? eb[k].count : 0}</b></td><td class="num">${eb[k] && eb[k].per_hour != null ? rate(eb[k].per_hour) : "–"}</td>
              <td class="num"><span class="ect-bar" style="--w:${eb[k] && eb[k].share ? Math.min(100, Math.max(4, eb[k].share * 1000)) : 0}%"></span>${eb[k] && eb[k].share != null ? pct(eb[k].share) : "–"}</td>
              <td class="num">${hp[k] ? Math.round(hp[k].mean) : "–"}</td><td class="num">${hb[k] ? Math.round(hb[k].rmssd_median) + " ms" : "–"}</td></tr>`).join("")}
          </table>
          <div class="hint">${t("Yhteensä <b>{0}</b> lisälyöntiä · {1} asennonvaihtoa · kääntymistä {2}", sumRows, p.transitions, fmt.dur(sec.moving || 0))}</div>`
          : `<p class="hint">${t("Ei kalibrointia, joten asentoja ei voitu nimetä. Kalibroi tai merkitse asentoja yllä, niin analyysi ajetaan uudelleen.")}</p>`}
        </div>
        <div>
          <div class="an-k">${t("Sykevälivaihtelu (RMSSD, 5 min)")} ${infoLink("hrv")}</div>
          <div class="an-big"><span class="num">${hrv.rmssd_median != null ? Math.round(hrv.rmssd_median) : "–"}</span><small>${t("ms mediaani")}</small>
            <span class="an-sub">SDNN ${hrv.sdnn_median != null ? Math.round(hrv.sdnn_median) : "–"} ms · ${t("hylätty {0} % väleistä", hrv.rejected_share != null ? dec(hrv.rejected_share * 100, 1) : "–")}</span></div>
          <canvas id="nv-hrv"></canvas>
          <div class="hint">${t("Lisälyönnit ja niiden tauot on poistettu suodattimella (±20 % paikallisesta mediaanista).")}</div>
        </div>
      </div>`;
  }

  drawHrv(r) {
    const cv = $("#nv-hrv"); if (!cv) return;
    const { ctx, w, h } = setupCanvas(cv);
    ctx.clearRect(0, 0, w, h);
    const win = (r.hrv.windows || []).filter((x) => x.rmssd != null);
    if (!win.length) return;
    const hi = Math.ceil(Math.max(...win.map((x) => x.rmssd)) / 20) * 20 + 10;
    const X = (t) => (t / this.dur) * (w - 36) + 32, Y = (v) => h - 14 - (v / hi) * (h - 24);
    ctx.font = "10px " + css("--mono"); ctx.fillStyle = css("--faint"); ctx.strokeStyle = css("--line");
    for (let v = 0; v <= hi; v += hi > 80 ? 40 : 20) { ctx.beginPath(); ctx.moveTo(32, Math.round(Y(v)) + 0.5); ctx.lineTo(w, Math.round(Y(v)) + 0.5); ctx.stroke(); ctx.fillText(String(v), 2, Y(v) + 3); }
    ctx.strokeStyle = "rgba(110,168,255,.35)"; ctx.lineWidth = 1.2; ctx.beginPath();
    win.forEach((x, i) => (i ? ctx.lineTo(X(x.t + 150), Y(x.rmssd)) : ctx.moveTo(X(x.t + 150), Y(x.rmssd)))); ctx.stroke();
    for (const x of win) {
      ctx.fillStyle = css(x.posture && POSTURE[x.posture] ? POSTURE[x.posture].color : "--hr");
      ctx.beginPath(); ctx.arc(X(x.t + 150), Y(x.rmssd), 3.2, 0, Math.PI * 2); ctx.fill();
    }
    if (r.hrv.rmssd_median != null) {
      ctx.setLineDash([4, 4]); ctx.strokeStyle = "rgba(232,237,247,.4)"; ctx.beginPath();
      ctx.moveTo(32, Y(r.hrv.rmssd_median)); ctx.lineTo(w, Y(r.hrv.rmssd_median)); ctx.stroke(); ctx.setLineDash([]);
    }
  }

  X(t, w) { return (t / this.dur) * w; }

  drawSymptoms(ctx, w, h, flag = false) {
    ctx.save();
    ctx.strokeStyle = css("--sym"); ctx.fillStyle = css("--sym"); ctx.lineWidth = 1.5;
    for (const s of this.symptoms || []) {
      const x = Math.round(this.X(s.t, w)) + 0.5;
      ctx.globalAlpha = 0.9;
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
      if (flag) { ctx.beginPath(); ctx.moveTo(x - 5, 0); ctx.lineTo(x + 5, 0); ctx.lineTo(x, 7); ctx.closePath(); ctx.fill(); }
    }
    ctx.restore();
  }

  renderSymptoms() {
    const el = $("#nv-sym"); if (!el) return;
    const res = this.d.analysis && this.d.analysis.result;
    const er = res && (res.ectopy || res.ectopy_rr);
    const ev = er ? er.events : null;
    const rows = this.symptoms.map((s) => {
      // the beat is felt, then the button is pressed: look 15 s back and 2 s forward
      let found = null;
      if (ev) for (const x of ev) if (x >= s.t - 15 && x <= s.t + 2 && (found == null || Math.abs(s.t - x) < Math.abs(s.t - found))) found = x;
      const ci = Math.floor((s.t / this.dur) * this.classes.length);
      const c = this.classes[Math.max(0, Math.min(this.classes.length - 1, ci))];
      return { ...s, found, posture: c };
    });
    const hits = rows.filter((r) => r.found != null).length;
    el.innerHTML = `
      <div class="card-head"><span class="card-title">${t("Oiremerkinnät")}</span>${infoLink("oireet")}
        <span class="meta">${rows.length ? (ev ? t("{0}/{1} merkinnässä lisälyönti 15 s sisällä", hits, rows.length) : t("analysoimatta")) : ""}</span></div>
      ${rows.length ? `<table class="mini">
        <tr><th>${t("Aika")}</th><th>${t("Asento")}</th><th>${t("Lisälyönti")}</th><th></th></tr>
        ${rows.map((r) => `<tr><td class="num"><b>${fmt.clockSec(this.t0 + r.t * 1000)}</b></td>
          <td>${r.posture ? `<i class="sw" style="background:var(${POSTURE[r.posture].color})"></i>${POSTURE[r.posture].label}` : "–"}</td>
          <td class="hint">${!ev ? t("analysoidaan myöhemmin") : r.found != null
            ? `<span style="color:var(--sym)">●</span> ${r.found <= r.t ? t("lisälyönti {0} s ennen", dec(Math.abs(r.t - r.found), 1)) : t("lisälyönti {0} s jälkeen", dec(Math.abs(r.t - r.found), 1))}`
            : t("ei lisälyöntiä lähellä")}</td>
          <td style="text-align:right;white-space:nowrap"><button class="btn sm" data-show="${r.t}">${t("Näytä EKG")}</button>
            <button class="btn sm ghost-danger" data-del="${esc(r.id)}" title="${t("Poista merkintä")}">✕</button></td></tr>`).join("")}
      </table>
      <div class="hint">${t("Merkinnät näkyvät aikajanalla pystyviivoina. Lisälyönti etsitään 15 s ennen merkintää ja 2 s sen jälkeen.")}</div>`
      : `<p class="hint">${t("Ei merkintöjä. Paina tallennuksen aikana Live-näkymän <b>Tunsin lisälyönnin</b> -painiketta, niin näet täällä, mitä EKG:ssä tapahtui sillä hetkellä.")}</p>`}`;
    el.querySelectorAll("[data-show]").forEach((b) => (b.onclick = () => {
      if (this.span > 30) this.setSpan(10);
      this.goto(+b.dataset.show - this.span * 0.7);
      $("#nv-detail").scrollIntoView({ behavior: "smooth", block: "center" });
    }));
    el.querySelectorAll("[data-del]").forEach((b) => (b.onclick = async () => {
      if (!(await confirmDialog({ title: t("Poistetaanko merkintä?"), body: t("Oiremerkintä poistetaan tästä tallenteesta."), confirm: t("Poista"), danger: true }))) return;
      const r = await fetch(`/api/sessions/${encodeURIComponent(this.id)}/events/${encodeURIComponent(b.dataset.del)}`, { method: "DELETE" });
      if (r.ok) this.reload(); else toast(t("Poisto epäonnistui."));
    }));
  }

  drawGaps(ctx, w, h) {
    ctx.save();
    ctx.fillStyle = css("--gap");
    for (const [a, b] of this.d.gaps) {
      const x0 = this.X(a, w), x1 = Math.max(x0 + 1, this.X(b, w));
      ctx.fillRect(x0, 0, x1 - x0, h);
      ctx.strokeStyle = "rgba(148,163,184,.28)"; ctx.lineWidth = 1;
      ctx.beginPath();
      for (let x = x0 - h; x < x1; x += 4) { ctx.moveTo(Math.max(x0, x), Math.max(0, x0 - x) + 0); ctx.lineTo(Math.min(x1, x + h), Math.min(h, x1 - x)); }
      ctx.stroke();
    }
    ctx.restore();
  }

  drawTimeline() {
    // posture strip
    let { ctx, w, h } = setupCanvas($("#nv-posture"));
    ctx.clearRect(0, 0, w, h);
    const n = this.classes.length;
    this.classes.forEach((c, i) => {
      if (c == null) return;
      ctx.fillStyle = css(POSTURE[c].color);
      const x0 = (i / n) * w, x1 = ((i + 1) / n) * w;
      ctx.fillRect(x0, 3, x1 - x0 + 0.6, h - 6);
    });
    this.drawGaps(ctx, w, h);
    this.drawSymptoms(ctx, w, h, true);
    // user-marked calibration segments (and the one being dragged)
    for (const mk of [...(this.marks || []), ...(this.pending ? [this.pending] : [])]) {
      const x0 = this.X(Math.min(mk.start, mk.end), w), x1 = this.X(Math.max(mk.start, mk.end), w);
      ctx.fillStyle = "rgba(255,255,255,.22)"; ctx.fillRect(x0, 0, Math.max(2, x1 - x0), h);
      ctx.strokeStyle = mk.posture ? css(POSTURE[mk.posture].color) : "#fff"; ctx.lineWidth = 2;
      ctx.strokeRect(x0 + 1, 1, Math.max(2, x1 - x0 - 2), h - 2);
    }
    $("#nv-posture").style.cursor = this.marking ? "col-resize" : "";

    // heart rate
    ({ ctx, w, h } = setupCanvas($("#nv-hr")));
    ctx.clearRect(0, 0, w, h);
    const hr = this.d.hr, N = hr.mean.length;
    const vals = hr.mean.filter((v) => v != null);
    const lo = Math.floor((Math.min(...vals, 50) - 5) / 10) * 10, hi = Math.ceil((Math.max(...vals, 70) + 8) / 10) * 10;
    const Y = (v) => 6 + (1 - (v - lo) / (hi - lo)) * (h - 12);
    this.hrY = Y;
    ctx.font = "11px " + css("--mono"); ctx.fillStyle = css("--faint"); ctx.strokeStyle = css("--line"); ctx.lineWidth = 1;
    for (let v = lo; v <= hi; v += 10) {
      ctx.beginPath(); ctx.moveTo(0, Math.round(Y(v)) + 0.5); ctx.lineTo(w, Math.round(Y(v)) + 0.5); ctx.stroke();
    }
    ctx.fillText(`${hi}`, 4, Y(hi) + 12); ctx.fillText(`${lo}`, 4, Y(lo) - 4);
    const xb = (i) => ((i + 0.5) / N) * w;
    // min/max band (clipped to a 25-75 style envelope by smoothing extremes)
    ctx.fillStyle = css("--hr-band");
    let open = false;
    const flushBand = (from, to) => {
      ctx.beginPath();
      for (let i = from; i <= to; i++) ctx.lineTo(xb(i), Y(Math.min(hr.max[i], hr.mean[i] + 12)));
      for (let i = to; i >= from; i--) ctx.lineTo(xb(i), Y(Math.max(hr.min[i], hr.mean[i] - 12)));
      ctx.closePath(); ctx.fill();
    };
    let start = -1;
    for (let i = 0; i <= N; i++) {
      const ok = i < N && hr.mean[i] != null;
      if (ok && start < 0) start = i;
      if (!ok && start >= 0) { flushBand(start, i - 1); start = -1; }
    }
    const grad = ctx.createLinearGradient(0, 0, 0, h);
    grad.addColorStop(0, "#ff7a90"); grad.addColorStop(0.5, css("--hr")); grad.addColorStop(1, "#7c8cff");
    ctx.strokeStyle = grad; ctx.lineWidth = 1.8; ctx.lineJoin = "round";
    ctx.beginPath(); open = false;
    for (let i = 0; i < N; i++) {
      const v = hr.mean[i];
      if (v == null) { open = false; continue; }
      if (open) ctx.lineTo(xb(i), Y(v)); else { ctx.moveTo(xb(i), Y(v)); open = true; }
    }
    ctx.stroke();
    this.drawGaps(ctx, w, h);
    this.drawSymptoms(ctx, w, h);

    // axis
    ({ ctx, w, h } = setupCanvas($("#nv-axis")));
    ctx.clearRect(0, 0, w, h);
    ctx.font = "11px " + css("--mono"); ctx.fillStyle = css("--muted"); ctx.strokeStyle = css("--line-hi");
    const first = new Date(this.t0); first.setMinutes(0, 0, 0); first.setHours(first.getHours() + 1);
    const stepH = this.dur > 6 * 3600 && w < 700 ? 2 : 1;
    for (let tm = first.getTime(); tm < this.t0 + this.dur * 1000; tm += 3600e3 * stepH) {
      const x = this.X((tm - this.t0) / 1000, w);
      ctx.beginPath(); ctx.moveTo(Math.round(x) + 0.5, 0); ctx.lineTo(Math.round(x) + 0.5, 5); ctx.stroke();
      const lbl = fmt.clock(tm);
      ctx.fillText(lbl, clamp(x - 16, 0, w - 34), 17);
    }
  }

  drawOverview() {
    const cv = $("#nv-ov");
    const { ctx, w, h } = setupCanvas(cv);
    ctx.clearRect(0, 0, w, h);
    const o = this.ovData;
    if (o && o.mode === "envelope") {
      const n = o.min.length, mid = h / 2;
      // robust scale: 98th percentile of bucket ranges
      // Height = amplitude range per bucket relative to the recording's typical range, so
      // artefacts (tall, amber) and electrode-off periods (flat, grey) stand out.
      const ranges = o.max.map((v, i) => (v == null ? null : v - o.min[i]));
      const sorted = ranges.filter((r) => r != null).sort((a, b) => a - b);
      const med = Math.max(200, sorted[sorted.length >> 1] || 1);
      const groups = { "--ecg": [], "--fair": [], "--none": [] };
      const classify = (o.end - o.start) / n >= 2; // buckets shorter than a couple of beats aren't comparable
      for (let i = 0; i < n; i++) {
        const r = ranges[i]; if (r == null) continue;
        const rel = r / med;
        const half = clamp(rel * 0.36, 0.04, 0.5) * h;
        groups[!classify ? "--ecg" : rel > 2.2 ? "--fair" : rel < 0.25 ? "--none" : "--ecg"].push([((i + 0.5) / n) * w, half]);
      }
      ctx.lineWidth = Math.max(1, w / n + 0.3);
      for (const [color, pts] of Object.entries(groups)) {
        ctx.strokeStyle = css(color); ctx.globalAlpha = color === "--ecg" ? 0.62 : 0.95;
        ctx.beginPath();
        for (const [x, half] of pts) { ctx.moveTo(x, mid - half); ctx.lineTo(x, mid + half); }
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
    }
    this.drawGaps(ctx, w, h);
    this.drawSymptoms(ctx, w, h);
    this.drawEctopics(ctx, w, h);
    // brush
    const x0 = this.X(this.t, w), x1 = Math.max(x0 + 3, this.X(this.t + this.span, w));
    ctx.fillStyle = "rgba(255,255,255,.10)"; ctx.fillRect(x0, 0, x1 - x0, h);
    ctx.strokeStyle = "rgba(255,255,255,.85)"; ctx.lineWidth = 1.5; ctx.strokeRect(x0 + 0.75, 0.75, x1 - x0 - 1.5, h - 1.5);
  }

  async fetchEcg(a, b, points) {
    const key = `${a.toFixed(2)}|${b.toFixed(2)}|${points}`;
    if (this.cache.has(key)) return this.cache.get(key);
    const d = await api(`/api/sessions/${encodeURIComponent(this.id)}/ecg?start=${a}&end=${b}&points=${Math.round(points)}`);
    this.cache.set(key, d);
    if (this.cache.size > 60) this.cache.delete(this.cache.keys().next().value);
    return d;
  }

  setSpan(span) {
    const center = this.t + this.span / 2;
    this.span = span;
    this.t = clamp(center - span / 2, 0, Math.max(0, this.dur - span));
    this.el.querySelectorAll("#nv-spans button").forEach((b) => b.classList.toggle("on", +b.dataset.span === span));
    this.loadDetail();
  }

  // index of the ectopic beat at the centre of the window (or -1)
  currentEctopic() {
    const c = this.t + this.span / 2;
    return this.ectopics.findIndex((e) => Math.abs(this.markTime(e) - c) < Math.min(1.5, this.span / 4));
  }

  jumpEctopic(dir) {
    const e = this.ectopics;
    if (!e.length) return;
    if (this.span > 30) this.setSpan(10);
    const c = this.t + this.span / 2;
    let k;
    if (dir > 0) { k = e.findIndex((x) => this.markTime(x) > c + 0.5); if (k < 0) k = 0; }
    else { k = -1; for (let i = e.length - 1; i >= 0; i--) if (this.markTime(e[i]) < c - 0.5) { k = i; break; } if (k < 0) k = e.length - 1; }
    this.goto(this.markTime(e[k]) - this.span / 2);
  }

  markTime(e) { return this.refined.has(e) ? this.refined.get(e) : e; }

  updateEctopicCount() {
    const el = $("#nv-ecount"); if (!el) return;
    const k = this.currentEctopic();
    el.textContent = k >= 0 ? t("Lisälyönti {0}/{1}", k + 1, this.ectopics.length) : t("Lisälyönnit {0}", this.ectopics.length);
  }

  // The RR estimate is timed from the strap's HR notification (≈1 s off): snap it to the
  // premature R peak in the ECG, i.e. the candidate peak with the shortest preceding interval.
  refineEctopics(t, v, fs) {
    if (!t.length) return;
    const amp = Math.max(...v.map(Math.abs));
    const peaks = [];
    let last = -1e9;
    for (let i = 1; i < v.length - 1; i++) {
      const a = Math.abs(v[i]);
      if (a > 0.5 * amp && a >= Math.abs(v[i - 1]) && a >= Math.abs(v[i + 1])) {
        if (t[i] - last > 0.25) { peaks.push(t[i]); last = t[i]; }
        else if (a > Math.abs(v[t.indexOf(last)] || 0)) { peaks[peaks.length - 1] = t[i]; last = t[i]; }
      }
    }
    for (const e of this.ectopics) {
      if (this.refined.has(e) || e < t[0] + 2 || e > t[t.length - 1] - 1) continue;
      let best = null, bestRr = 1e9;
      for (let i = 1; i < peaks.length; i++) {
        if (peaks[i] < e - 2 || peaks[i] > e + 1.5) continue;
        const rr = peaks[i] - peaks[i - 1];
        if (rr < bestRr) { bestRr = rr; best = peaks[i]; }
      }
      if (best != null) this.refined.set(e, best);
    }
  }

  drawEctopics(ctx, w, h) {
    ctx.save(); ctx.fillStyle = css("--ecg");
    for (const e of this.ectopics || []) {
      const x = this.X(e, w);
      ctx.beginPath(); ctx.moveTo(x - 3.5, 0); ctx.lineTo(x + 3.5, 0); ctx.lineTo(x, 6); ctx.closePath(); ctx.fill();
    }
    ctx.restore();
  }

  goto(t) { this.t = clamp(t, 0, Math.max(0, this.dur - this.span)); this.drawOverview(); this.drawDetail(); this.loadDetail(); }

  loadDetail() {
    clearTimeout(this._dl);
    this.drawOverview();
    this.drawDetail();
    this._dl = setTimeout(async () => {
      const w = $("#nv-detail").clientWidth;
      // fetch with margin so small drags redraw instantly
      const a = Math.max(0, this.t - this.span * 0.5), b = Math.min(this.dur, this.t + this.span * 1.5);
      const seq = (this._seq = (this._seq || 0) + 1);
      const data = await this.fetchEcg(Math.round(a * 10) / 10, Math.round(b * 10) / 10, w * 4);
      if (seq !== this._seq) return; // a newer request superseded this one
      this.detail = data;
      this.drawDetail();
    }, 60);
  }

  drawDetail() {
    const cv = $("#nv-detail");
    const { ctx, w, h } = setupCanvas(cv);
    ctx.clearRect(0, 0, w, h);
    const pxPerSec = w / this.span;
    const pxPerMv = Math.min(h / 3.4, Math.max(40, pxPerSec * 0.4 * 2.5));
    const mid = h * 0.55;
    drawPaper(ctx, w, h, pxPerSec, pxPerMv, -this.t * pxPerSec, mid);
    const start = this.t, end = this.t + this.span;
    const tStart = this.t0 + start * 1000;
    $("#nv-dt").textContent = `${fmt.clockSec(tStart)} – ${fmt.clockSec(tStart + this.span * 1000)}`;
    this.updateEctopicCount();
    const d = this.detail;
    // gaps
    ctx.fillStyle = css("--gap");
    for (const [a, b] of this.d.gaps) if (b > start && a < end) ctx.fillRect((a - start) * pxPerSec, 0, (b - a) * pxPerSec, h);
    for (const sy of this.symptoms || []) {
      if (sy.t < start || sy.t > end) continue;
      const x = Math.round((sy.t - start) * pxPerSec) + 0.5;
      ctx.save(); ctx.strokeStyle = css("--sym"); ctx.setLineDash([5, 4]); ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.moveTo(x, 18); ctx.lineTo(x, h); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle = css("--sym"); ctx.font = "600 11px " + css("--font"); ctx.fillText("♥ " + t("tunsin"), x + 5, 14); ctx.restore();
    }
    if (!d) return;
    const color = css("--ecg");
    if (d.mode === "raw") {
      $("#nv-dmeta").textContent = t("täysi tarkkuus · {0} Hz · 25 mm/s-ruudukko", dec(d.fs, 2));
      const v = highpass(d.v, d.fs, 0.5);
      ctx.lineJoin = "round"; ctx.lineCap = "round";
      for (const pass of [0, 1]) {
        ctx.beginPath(); ctx.strokeStyle = color; ctx.lineWidth = pass ? 1.6 : 5; ctx.globalAlpha = pass ? 1 : 0.14;
        let pen = false, prevT = null;
        for (let i = 0; i < d.t.length; i++) {
          const t = d.t[i];
          if (t < start - 1 || t > end + 1) { pen = false; continue; }
          if (prevT != null && t - prevT > 0.5) pen = false;
          prevT = t;
          const x = (t - start) * pxPerSec, y = mid - (v[i] / 1000) * pxPerMv;
          if (pen) ctx.lineTo(x, y); else { ctx.moveTo(x, y); pen = true; }
        }
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
      if (!this.ectFromEcg) this.refineEctopics(d.t, v, d.fs);
      let lastLabelEnd = -1e9; // labels of close beats (couplets) would overlap: show the first only
      for (const e of this.ectopics) {
        const tm = this.markTime(e);
        if (tm < start || tm > end) continue;
        const x = Math.round((tm - start) * pxPerSec) + 0.5;
        ctx.save();
        ctx.fillStyle = "rgba(255,84,112,.10)"; ctx.fillRect(x - 0.12 * pxPerSec, 0, 0.24 * pxPerSec, h);
        ctx.fillStyle = color; ctx.beginPath(); ctx.moveTo(x - 6, 4); ctx.lineTo(x + 6, 4); ctx.lineTo(x, 13); ctx.closePath(); ctx.fill();
        const info = this.ectKinds.get(e);
        const lbl = info ? { ves: "VES", sves: "SVES" }[info.kind] || t("lisälyönti") : this.refined.has(e) ? t("lisälyönti") : t("lisälyönti") + " (≈)";
        ctx.font = "600 11px " + css("--font");
        const text = info && info.run ? `${lbl} · ${t("sarja")}` : info && info.couplet ? `${lbl} · ${t("pari")}` : lbl;
        if (x + 8 > lastLabelEnd + 6) { ctx.fillText(text, x + 8, 13); lastLabelEnd = x + 8 + ctx.measureText(text).width; }
        ctx.restore();
      }
      // sample dots when zoomed in far enough to show the 7.7 ms resolution
      if (pxPerSec / d.fs > 5) {
        ctx.fillStyle = color;
        for (let i = 0; i < d.t.length; i++) {
          const x = (d.t[i] - start) * pxPerSec; if (x < -2 || x > w + 2) continue;
          ctx.beginPath(); ctx.arc(x, mid - (v[i] / 1000) * pxPerMv, 1.6, 0, Math.PI * 2); ctx.fill();
        }
      }
    } else {
      const inView = this.ectopics.filter((e) => e >= start && e <= end).length;
      $("#nv-dmeta").textContent = `${t("harvennettu (min/max)")}${this.ectopics.length ? ` · ${t("{0} lisälyöntiä tällä välillä", inView)}` : ""} · ${t("tuplaklikkaa tarkentaaksesi")}`;
      const n = d.min.length, bw = (d.end - d.start) / n;
      const cs = d.min.map((v, i) => (v == null ? null : (v + d.max[i]) / 2));
      // local baseline: moving median of bucket centres
      const base = cs.map((_, i) => { const win = cs.slice(Math.max(0, i - 40), i + 40).filter((x) => x != null).sort((a, b) => a - b); return win.length ? win[win.length >> 1] : 0; });
      ctx.strokeStyle = color; ctx.globalAlpha = this.ectopics.length ? 0.4 : 0.85; ctx.lineWidth = Math.max(1, (bw * pxPerSec));
      ctx.beginPath();
      for (let i = 0; i < n; i++) {
        if (d.min[i] == null) continue;
        const t = d.start + (i + 0.5) * bw; if (t < start || t > end) continue;
        const x = (t - start) * pxPerSec;
        ctx.moveTo(x, mid - ((d.max[i] - base[i]) / 1000) * pxPerMv);
        ctx.lineTo(x, mid - ((d.min[i] - base[i]) / 1000) * pxPerMv + 0.5);
      }
      ctx.stroke(); ctx.globalAlpha = 1;
      // compressed view: every ectopic beat as a thin line, clusters show up as dense bands
      ctx.save();
      // per-bucket count along the bottom (1 min buckets, or 10 s when zoomed to ≤ 5 min)
      if (this.ectopics.length) {
        const bucket = this.span > 300 ? 60 : 10, nbk = Math.ceil(this.span / bucket);
        const counts = new Array(nbk).fill(0);
        for (const e of this.ectopics) if (e >= start && e < end) counts[Math.floor((e - start) / bucket)]++;
        const top = Math.max(3, ...counts), bh = 34;
        ctx.fillStyle = "rgba(7,11,18,.55)"; ctx.fillRect(0, h - bh - 6, w, bh + 6);
        ctx.fillStyle = color;
        counts.forEach((c, i) => {
          if (!c) return;
          const hh = Math.max(2, (c / top) * bh), x0 = (i * bucket) * pxPerSec;
          ctx.fillRect(x0 + 0.5, h - 3 - hh, Math.max(1, bucket * pxPerSec - 1), hh);
        });
        ctx.font = "10px " + css("--mono"); ctx.fillStyle = "rgba(232,237,247,.6)";
        ctx.fillText(`max ${top} / ${bucket === 60 ? "min" : "10 s"}`, 6, h - bh - 10);
      }
      for (const e of this.ectopics) {
        if (e < start || e > end) continue;
        const x = Math.round((e - start) * pxPerSec) + 0.5;
        const info = this.ectKinds.get(e);
        ctx.strokeStyle = info && info.kind === "sves" ? css("--fair") : color;
        ctx.globalAlpha = 0.8; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(x, 12); ctx.lineTo(x, h - 46); ctx.stroke();
        ctx.globalAlpha = 1; ctx.fillStyle = ctx.strokeStyle;
        ctx.beginPath(); ctx.moveTo(x - 3.5, 3); ctx.lineTo(x + 3.5, 3); ctx.lineTo(x, 10); ctx.closePath(); ctx.fill();
      }
      ctx.restore();
    }
    ctx.strokeStyle = "rgba(232,237,247,.55)"; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.moveTo(14, mid + pxPerMv * 0.5); ctx.lineTo(14, mid - pxPerMv * 0.5); ctx.stroke();
    ctx.fillStyle = "rgba(232,237,247,.55)"; ctx.font = "11px " + css("--mono"); ctx.fillText("1 mV", 20, mid - pxPerMv * 0.5 + 10);
  }

  bind() {
    const tip = $("#tooltip");
    const tracks = ["#nv-posture", "#nv-hr", "#nv-ov"].map((s) => $(s));
    const tAt = (cv, ev) => clamp(((ev.clientX - cv.getBoundingClientRect().left) / cv.clientWidth) * this.dur, 0, this.dur);

    for (const cv of tracks) {
      cv.addEventListener("mousemove", (ev) => {
        const tm = tAt(cv, ev);
        const i = Math.floor((tm / this.dur) * this.d.hr.mean.length);
        const hr = this.d.hr.mean[i];
        const c = this.classes[Math.floor((tm / this.dur) * this.classes.length)];
        const inGap = this.d.gaps.some(([a, b]) => tm >= a && tm <= b);
        tip.innerHTML = `<span class="t">${fmt.clockSec(this.t0 + tm * 1000)}</span><br>${inGap ? t("ei dataa") : `${t("Syke")} <b>${hr != null ? Math.round(hr) : "–"}</b> bpm · ${c ? POSTURE[c].label : "–"}`}`;
        tip.style.display = "block";
        tip.style.left = `${Math.min(ev.clientX + 14, window.innerWidth - 180)}px`;
        tip.style.top = `${ev.clientY + 14}px`;
        $("#nv-cursor").textContent = fmt.clockSec(this.t0 + tm * 1000);
      });
      cv.addEventListener("mouseleave", () => { tip.style.display = "none"; $("#nv-cursor").textContent = ""; });
      cv.addEventListener("click", (ev) => { if (!(this.marking && cv.id === "nv-posture")) this.goto(tAt(cv, ev) - this.span / 2); });
    }
    // marking calibration segments by dragging on the posture strip
    const ps = $("#nv-posture");
    ps.addEventListener("pointerdown", (ev) => {
      if (!this.marking) return;
      ps.setPointerCapture(ev.pointerId);
      const t = tAt(ps, ev);
      this.pending = { start: t, end: t };
    });
    ps.addEventListener("pointermove", (ev) => { if (this.marking && this.pending && ev.buttons) { this.pending.end = tAt(ps, ev); this.drawTimeline(); } });
    ps.addEventListener("pointerup", (ev) => {
      if (!this.marking || !this.pending) return;
      const a = Math.min(this.pending.start, this.pending.end), b = Math.max(this.pending.start, this.pending.end);
      if (b - a < 20) { this.pending = null; this.drawTimeline(); return; } // ignore clicks / tiny drags
      this.askPosture(ev, Math.round(a), Math.round(b));
    });
    const ov = $("#nv-ov");
    let brushing = false;
    ov.addEventListener("mousedown", (ev) => { brushing = true; this.goto(tAt(ov, ev) - this.span / 2); });
    window.addEventListener("mouseup", () => { brushing = false; });
    ov.addEventListener("mousemove", (ev) => { if (brushing) this.goto(tAt(ov, ev) - this.span / 2); });

    const det = $("#nv-detail");
    let drag = null;
    det.addEventListener("pointerdown", (ev) => { drag = { x: ev.clientX, t: this.t }; det.setPointerCapture(ev.pointerId); det.classList.add("dragging"); });
    det.addEventListener("pointermove", (ev) => {
      if (!drag) return;
      const dt = ((drag.x - ev.clientX) / det.clientWidth) * this.span;
      this.t = clamp(drag.t + dt, 0, Math.max(0, this.dur - this.span));
      this.drawDetail(); this.drawOverview();
    });
    det.addEventListener("pointerup", () => { if (drag) { drag = null; det.classList.remove("dragging"); this.loadDetail(); } });
    // double-click: zoom to 10 s around that moment (handy after spotting a cluster at 30 min / 1 h)
    det.addEventListener("dblclick", (ev) => {
      const tm = this.t + ((ev.clientX - det.getBoundingClientRect().left) / det.clientWidth) * this.span;
      this.span = 10;
      this.el.querySelectorAll("#nv-spans button").forEach((b) => b.classList.toggle("on", +b.dataset.span === 10));
      this.goto(tm - 5);
    });
    det.addEventListener("wheel", (ev) => {
      if (Math.abs(ev.deltaX) > Math.abs(ev.deltaY)) {
        ev.preventDefault();
        this.t = clamp(this.t + (ev.deltaX / det.clientWidth) * this.span, 0, Math.max(0, this.dur - this.span));
        this.drawDetail(); this.drawOverview(); this.loadDetail();
      }
    }, { passive: false });
    $("#nv-prev").onclick = () => this.goto(this.t - this.span * 0.8);
    if (this.ectopics.length) {
      $("#nv-eprev").onclick = () => this.jumpEctopic(-1);
      $("#nv-enext").onclick = () => this.jumpEctopic(1);
    }
    $("#nv-next").onclick = () => this.goto(this.t + this.span * 0.8);
    this.el.querySelectorAll("#nv-spans button").forEach((b) => (b.onclick = () => this.setSpan(+b.dataset.span)));
    this.onKey = (ev) => {
      if (ev.key === "ArrowLeft") this.goto(this.t - this.span * 0.8);
      if (ev.key === "ArrowRight") this.goto(this.t + this.span * 0.8);
    };
    window.addEventListener("keydown", this.onKey);
    this.onResize = () => { if (!$("#nv-posture")) return; this.drawTimeline(); this.drawOverview(); this.drawDetail(); };
    window.addEventListener("resize", this.onResize);
  }
}

function stat(k, v, s) { return `<div class="card stat"><div class="k">${k}</div><div class="v">${v}</div><div class="s">${s || "&nbsp;"}</div></div>`; }

function endReason(r) {
  if (r === "manual stop") return t("pysäytetty käsin");
  if (/strap not seen/.test(r)) return t("vyö poistettu");
  if (/no skin contact/.test(r)) return t("vyö riisuttu");
  if (/interrupted/.test(r)) return t("sovellus pysähtyi");
  return r;
}

// ------------------------------------------------------------------ methods (settings page)

const METHODS_HTML = `
  <div class="med-box" role="note">
    <b>Vain tutkimus- ja omaan käyttöön. Ei lääkinnällinen laite.</b>
    <p>OpenHolter on avoimen lähdekoodin tutkimusprojekti. Sitä ei ole tarkoitettu sairauksien diagnosointiin, hoitoon, seurantaan tai ehkäisyyn, eivätkä sen tulokset korvaa lääkärin arviota. Älä muuta lääkitystäsi tai hoitoasi niiden perusteella. OpenHolter ei tunnista sydäninfarktia eikä hälytä vaarallisista rytmihäiriöistä.</p>
    <p><b>Jos sinulla on sydänoireita, kuten rintakipua tai puristusta, hengenahdistusta, pyörtymistä tai huimausta, ota yhteys lääkäriin. Hätätilanteessa soita 112.</b></p>
  </div>
  <p class="hint">Menetelmät on kuvattu, jotta tulosten luotettavuuden ja rajoitukset voi arvioida itse tai lääkärin kanssa.</p>
  <details id="mittaus"><summary>Mittaus</summary>
    <ul>
      <li><b>Polar H10</b> -sykevyö: yksikytkentäinen EKG 130 Hz:llä mikrovoltteina, kiihtyvyysanturi 50 Hz:llä (±4 G, milli-G) ja vyön itse laskemat RR-välit 1/1024 s:n tarkkuudella (Bluetoothin Heart Rate -palvelu).</li>
      <li>Yhteys Bluetooth LE:llä Polarin <i>Polar Measurement Data</i> (PMD) -protokollalla. Raa'at Bluetooth-viestit tallennetaan sellaisinaan, joten analyysin voi myöhemmin ajaa uudelleen paremmilla menetelmillä.</li>
      <li><b>Ajoitus:</b> näytteiden välit otetaan vyön omasta kellosta (noin 130,0x Hz). Kellonaika sovitetaan siihen yhteysjaksoittain lineaarisella ajelmakorjauksella, jota ankkuroivat nopeimmin perille tulleet kehykset (Bluetoothin viive on aina positiivinen).</li>
    </ul>
  </details>
  <details id="signaali"><summary>Signaalin laatu ja näyttö</summary>
    <ul>
      <li><b>Elektrodikontakti</b> arvioidaan 10 s:n ikkunoissa kolmella mittarilla: amplitudi (1.–99. persentiilin väli, alle 150 µV = ei kontaktia), korkeataajuinen kohina (derivaatan mediaani suhteessa amplitudiin) ja perustason vaellus (sekunnin mediaanien vaihtelu). Tuloksena on luokka hyvä, kohtalainen, heikko tai ei kontaktia.</li>
      <li><b>Ihokontakti:</b> H10 ilmoittaa sykeviestissään, onko se iholla. Riisuttu mutta yhdistetty vyö lähettää kohinaa ja keksityn sykkeen. Siksi kontaktittomat jaksot näytetään tilassa <i>Ei ihokontaktia</i>, niiden syke ja RR-välit jätetään pois analyysistä, ja automaattinen tallennus alkaa vasta kontaktista ja päättyy, kun kontaktia ei ole ollut aikakatkaisun aikaa.</li>
      <li><b>Bluetooth-taso</b> yhdistää signaalin voimakkuuden (RSSI, dBm) ja perille tulleiden EKG-näytteiden osuuden viimeisten 10 sekunnin aikana sekä pisimmän katkon.</li>
      <li><b>Näytön suodatus:</b> perustason vaellus poistetaan 1. asteen ylipäästösuodattimella: tallenteen näkymässä nollavaiheisena (0,5 Hz), live-näkymässä reaaliaikaisena (noin 0,4 Hz) ja PDF:ssä 1 s:n liukuvan keskiarvon vähennyksellä. Suodatus koskee vain esitystä, eikä tallennettua dataa muuteta.</li>
    </ul>
  </details>
  <details id="lisalyonnit"><summary>Lisälyönnit</summary>
    <ul>
      <li><b>R-piikit tunnistetaan EKG:stä</b> Pan–Tompkins-tyyppisesti: kaistanpäästö (noin 5–15 Hz), derivaatta, neliöinti, 150 ms:n liukuva integrointi ja viimeisiä lyöntejä seuraava kynnys, 200 ms:n refraktaariaika. Pitkältä väliltä haetaan puuttuva lyönti matalammalla kynnyksellä, ja T-aallot hylätään. R-piikki on suurin perustasokorjattu poikkeama integroidun huipun lähellä. Vyön omia RR-välejä ei käytetä, koska vyön oma tunnistus jättää leveät lisälyönnit usein huomaamatta.</li>
      <li><b>Häiriöt hylätään:</b> tallenteen ensimmäinen ja viimeinen minuutti (vyön pukeminen ja riisuminen), kontaktittomat jaksot, Bluetooth-katkot sekä lyönnit, joiden amplitudi tai ympäristön (±1 s) vaihteluväli on yli kolminkertainen tallenteen tavalliseen nähden.</li>
      <li>Lyönti on <b>ennenaikainen</b>, kun sen RR-väli on 12–20 % paikallista viitearvoa lyhyempi. Vaadittu määrä kasvaa paikallisen sykevaihtelun mukaan (3 × hajonta). <b>SVES</b> vaatii lisäksi äkillisen lyhenemisen (alle 90 % edellisestä välistä) ja sen, että seuraava väli on vähintään yhtä pitkä kuin ennenaikainen väli ja vähintään 85 % viitteestä. Eteisperäistä lyöntiä ei yleensä seuraa täysi tauko. <b>VES</b>:ltä vaaditaan, että seuraava väli on vähintään 95 % viitteestä. Tauko on <i>kompensatorinen</i>, kun välien summa on 1,75–2,25 kertaa viite. <b>Pari</b> = kaksi ennenaikaista peräkkäin, <b>sarja</b> = vähintään kolme peräkkäin yli 100/min.</li>
      <li><b>Muoto:</b> lyöntiä verrataan ympäröivien normaalien lyöntien mediaanimalliin (QRS-ikkuna −80…+120 ms). Jos korrelaatio on alle 0,85 tai QRS on vähintään 40 ms mallia leveämpi → <b>VES</b> (todennäköisesti kammioperäinen), muuten <b>SVES</b> (todennäköisesti eteisperäinen). 130 Hz:llä yksi näyte on 7,7 ms, joten leveys on karkea arvio. Lisäksi jokaista lyöntiä verrataan malliin: selvästi poikkeava, leveä tai suuri QRS on <b>VES</b>, vaikka lyönti ei tulisi etuajassa (korrelaatio alle 0,70 parhaallakin ±40 ms:n siirrolla, naapurilyönnit malliin sopivia).</li>
      <li>Viitearvo on peräkkäisten välien parikeskiarvon ((RR<sub>i</sub> + RR<sub>i+1</sub>) / 2) liukuva mediaani 31 lyönnin yli. Täysi kompensatorinen tauko ei muuta parikeskiarvoa, joten viite pysyy oikeana myös bigeminiassa. Pitkissä sarjoissa käytetään edeltävien lyöntien viitearvoa, jottei takykardia vedä omaa viitettään alas.</li>
      <li><b>Epäsäännöllinen rytmi:</b> jos sykevälit vaihtelevat kuviottomasti (31 välin ikkunan mediaani yli 5 %) eikä ennen QRS:ää näy toistuvaa P-aaltoa vähintään 30 s:n aikana, jakso raportoidaan epäsäännöllisenä rytminä, joka sopii eteisvärinään. Tämä ei ole diagnoosi. Jakson aikana SVES-merkintöjä ei tehdä. Bigeminia ja trigeminia eivät laukaise tätä, koska niissä kuvio toistuu.</li>
      <li><b>Bigeminiajakso:</b> vähintään kolme ennenaikaista lyöntiä joka toisena lyöntinä.</li>
      <li>Asennoittain lisälyöntien osuus lasketaan kussakin asennossa tapahtuneista lyönneistä, ja määrä tunnissa suhteutetaan asennossa vietettyyn aikaan.</li>
      <li><b>Rajoitukset:</b> yksikytkentäinen rintakehä-EKG ei näe kaikkia muotoeroja, joten VES/SVES-jako on suuntaa antava. Osa VES-lyönneistä jää löytymättä, ja osa merkinnöistä on vääriä: tulos vaihtelee paljon aineistoittain. SVES-kokonaismäärä on epäluotettava, ja yksi virhe voi hylätä koko sarjan. Eteisvärinää jää löytymättä, varsinkin kun kammiovaste on tasainen. P-aallon raja on tarkistettu vain Holter-kytkennöillä, ei H10:llä. Katso <a href="#/about/validointi">Validointi</a>. Jos EKG:tä ei ole, käytetään varalla vyön RR-välejä.</li>
    </ul>
  </details>
  <details id="validointi"><summary>Validointi: MIT-BIH, INCART, SVDB ja AFDB</summary>
    <ul>
      <li>Lyöntianalyysi on testattu <b>MIT-BIH Arrhythmia Database</b> -aineistolla (PhysioNet): 48 puolen tunnin Holter-nauhoitusta, noin 87 000 lyöntiä, joista jokaisen on luokitellut kaksi kardiologia. Lisäksi testattiin St Petersburg <b>INCART</b> -tietokannalla (75 tallennetta, kytkentä II), <b>SVDB</b>:llä (MIT-BIH Supraventricular, 78 tallennetta) ja <b>AFDB</b>:llä (MIT-BIH Atrial Fibrillation, 23 tallennetta, 233 tuntia). Testi noudattaa ANSI/AAMI EC57 -standardia: luokat N/S/V/F/Q, 150 ms:n osumaikkuna, vertailu 5 minuutin kohdalta alkaen, tahdistetut tallenteet pois lisälyöntitilastoista.</li>
      <li>Signaali näytteistettiin 130 Hz:iin, ja analyysi ajettiin samalla koodilla kuin omille tallenteille. Versio 6 säädettiin vain MIT-BIH:n puoliskolla DS1. <b>SVDB ja AFDB ovat puhdas testi:</b> ne avattiin vasta parametrien lukitsemisen jälkeen. MIT-BIH ja INCART oli nähty edellisen version yhteydessä, joten niiden luvut ovat todennäköisesti optimistisia.</li>
    </ul>
    <div class="table-scroll"><table class="val-table">
      <thead><tr><th>Herkkyys / osuvuus</th><th>SVDB, puhdas testi (78)</th><th>MIT-BIH (44)</th><th>INCART (75)</th></tr></thead>
      <tbody>
        <tr><td>Lyöntien (QRS) tunnistus</td><td>99,9 / 99,4 %</td><td>99,9 / 99,7 %</td><td>99,8 / 99,0 %</td></tr>
        <tr><td>VES</td><td>59,6 / 79,5 %</td><td>82,4 / 90,8 %</td><td>78,1 / 89,9 %</td></tr>
        <tr><td>VES, ilman eteisvärinätallenteita</td><td>59,6 / 79,5 %</td><td>80,8 / 95,2 %</td><td>78,0 / 89,9 %</td></tr>
        <tr><td>VES, tyypillinen yksittäinen + tauko</td><td>88,5 %</td><td>96,0 %</td><td>92,3 %</td></tr>
        <tr><td>SVES</td><td>53,6 / 75,1 %</td><td>32,9 / 69,4 %</td><td>87,6 / 66,3 %</td></tr>
        <tr><td>SVES, tyypillinen yksittäinen + tauko</td><td>90,8 %</td><td>90,0 %</td><td>98,0 %</td></tr>
        <tr><td>Epäsäännöllinen rytmi (eteisvärinä), lyönnit</td><td>–</td><td>93,4 / 75,6 %</td><td>27,6 / 44,7 %</td></tr>
      </tbody>
    </table></div>
    <ul>
      <li><b>Herkkyys</b> = kuinka suuri osa oikeista lyönneistä löytyi. <b>Osuvuus</b> = kuinka suuri osa ohjelman merkinnöistä oli oikeita.</li>
      <li><b>Eteisvärinä, puhdas testi</b> (AFDB, sekunneittain): herkkyys 80,9 %, osuvuus 99,1 %.</li>
      <li><b>Tulkinta:</b> lyönnit löytyvät luotettavasti, ja tyypilliset yksittäiset lisälyönnit löytyvät noin 9 tapauksessa 10:stä. VES- ja SVES-kokonaismäärät ovat suuntaa antavia: puhtaassa testissä VES-lyönneistä löytyi noin 60 % ja SVES-lyönneistä 54 %, ja VES ei parantunut edellisestä versiosta. Eteisvärinähälytys on puhtaassa testissä yleensä oikea, mutta osa eteisvärinästä jää löytymättä.</li>
      <li><b>Rajoitus:</b> Aineistot on nauhoitettu Holter-laitteilla, ei Polar H10:llä. Tulos kertoo algoritmista, ei suoraan vyön kanssa saavutettavasta tarkkuudesta.</li>
      <li>Koko raportti, tallennekohtaiset tulokset ja ohje testin toistamiseen: <span class="mono">docs/VALIDATION.md</span> projektin lähdekoodissa. Testattu versio: OpenHolter 0.3.0, analyysiversio 6.</li>
    </ul>
  </details>
  <details id="hrv"><summary>Sykevälivaihtelu (HRV)</summary>
    <ul>
      <li>Laskenta käyttää vain normaalien lyöntien välejä (NN). Hylätään välit, jotka ovat 300–2000 ms:n ulkopuolella tai poikkeavat yli 20 % 11 lyönnin liukuvasta mediaanista. Näin lisälyönnit ja niiden tauot jäävät pois.</li>
      <li><b>RMSSD</b> (peräkkäisten NN-välien erotusten neliöllinen keskiarvo) ja <b>SDNN</b> (NN-välien keskihajonta) lasketaan 5 minuutin ikkunoissa. Nämä ovat Task Force 1996 -suosituksen aikatason mittarit. Ikkuna hyväksytään, jos siinä on vähintään 150 lyöntiä ja vähintään 80 % väleistä on hyväksyttyjä. Koko tallenteen arvo on ikkunoiden mediaani.</li>
      <li>Taajuustason mittareita (LF/HF) ei lasketa, koska ne ovat makuuasennossa ja lisälyöntien kanssa epäluotettavia.</li>
    </ul>
  </details>
  <details id="asento"><summary>Kehon asento</summary>
    <ul>
      <li>Asento päätellään painovoimavektorin suunnasta kiihtyvyysanturin sekuntikeskiarvoista.</li>
      <li><b>Kalibrointi:</b> mitataan suunta selällään ja vasemmalla kyljellä (valinnaisesti myös oikealla kyljellä ja vatsallaan). Kehon pituusakseli on näiden ristitulo. Asento määräytyy pituusakselin ympäri lasketun kiertokulman mukaan lähimmästä kalibroidusta asennosta.</li>
      <li><b>Pystyssä</b>, kun pituusakselin suuntainen komponentti on yli 0,7 g (noin 45°). <b>Kääntyminen</b> (liike), kun suunta muuttuu yli 15° sekunnissa tai kiihtyvyyden suuruuden hajonta on yli 60 mG. Alle 30 s:n asentojaksot yhdistetään viereisiin.</li>
      <li>Jälkikalibroinnissa vertailusuunnat lasketaan käyttäjän merkitsemien jaksojen liikkumattomista sekunneista.</li>
    </ul>
  </details>
  <details id="oireet"><summary>Oiremerkinnät</summary>
    <ul><li>Painalluksen hetki tallennetaan palvelimen kellolla. Lisälyönti etsitään aikaväliltä 15 s ennen merkintää – 2 s sen jälkeen, koska lyönti tunnetaan ennen kuin painiketta ehtii painaa.</li></ul>
  </details>
  <details id="ohjelmisto"><summary>Ohjelmisto ja tietosuoja</summary>
    <ul>
      <li>Python: FastAPI ja Uvicorn (palvelin), bleak ja CoreBluetooth (Bluetooth), NumPy (laskenta), reportlab (PDF). Selaimessa Canvas-grafiikka ja three.js r160 (3D-hahmo, MIT-lisenssi), ei muita ulkoisia kirjastoja.</li>
      <li>Ajetaan taustapalveluna (macOS: LaunchAgent; Windows ja Linux: katso README). Tallenteet ovat gzip-pakattuina raakadatana kansiossa <span class="mono">~/openholter-data</span>, ja analyysit ajetaan erillisessä matalan prioriteetin prosessissa.</li>
      <li>Data pysyy tällä tietokoneella. Sovellus ei käytä pilvipalveluja, analytiikkaa eikä telemetriaa, ja käyttöliittymä ei lataa mitään internetistä.</li>
      <li>Avointa lähdekoodia GNU AGPL-3.0 -lisenssillä.</li>
    </ul>
  </details>`;

// ⓘ next to a figure: opens the matching section of the methods page
const infoLink = (sec, label = t("Miten tämä lasketaan?")) =>
  `<a class="info" href="#/about/${sec}" title="${label}" aria-label="${label}"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="8" cy="8" r="6.4"/><path d="M8 7.2v4M8 4.7v.1" stroke-linecap="round"/></svg></a>`;

const AboutPage = {
  async mount(el, sec) {
    let s = {};
    try { s = await api("/api/settings"); } catch {}
    el.innerHTML = `
      <div class="page-head fade-in"><div><h1>${t("Menetelmät ja tekniikka")}</h1>
        <div class="sub">OpenHolter ${esc(s.version || "")}${s.build && s.build !== "dev" ? ` · build ${esc(fmtBuild(s.build))}` : ""} · ${t("EKG-tallennin Polar H10 -sykevyölle")}</div></div></div>
      <section class="card methods about-page fade-in">${LANG === "fi" ? METHODS_HTML : (typeof METHODS_HTML_EN !== "undefined" ? METHODS_HTML_EN : METHODS_HTML)}</section>`;
    const all = el.querySelectorAll(".methods details");
    all.forEach((d) => (d.open = !sec)); // whole page open, or just the section that was asked for
    const target = sec && el.querySelector(`#${CSS.escape(sec)}`);
    if (target) {
      target.open = true;
      target.classList.add("flash");
      requestAnimationFrame(() => target.scrollIntoView({ behavior: "smooth", block: "start" }));
    }
  },
  unmount() {},
};

// ------------------------------------------------------------------ settings

function rssiBars(rssi) {
  const lvl = rssi == null ? 0 : rssi > -60 ? 4 : rssi > -70 ? 3 : rssi > -80 ? 2 : 1;
  return `<span class="rssi" title="${rssi ?? "?"} dBm">${[1, 2, 3, 4].map((i) => `<i class="${i <= lvl ? "on" : ""}"></i>`).join("")}</span>`;
}

const SettingsPage = {
  async mount(el) {
    this.el = el;
    el.innerHTML = `<div class="page-head fade-in"><div><h1>${t("Asetukset")}</h1><div class="sub">${t("Muutokset tallentuvat heti.")}</div></div></div><div id="st"></div>`;
    await this.load();
    this.timer = setInterval(() => this.refreshDevices(), 5000);
  },
  unmount() { clearInterval(this.timer); },
  async load() {
    try { this.s = await api("/api/settings"); } catch (e) { if ($("#st")) $("#st").innerHTML = `<div class="hint">${t("Lataus epäonnistui: {0}", esc(e.message))}</div>`; return; }
    if (!$("#st")) return;
    this.render();
  },
  async refreshDevices() {
    try { this.s = await api("/api/settings"); } catch { return; }
    if ($("#st-dev")) $("#st-dev").innerHTML = this.deviceHtml();
    this.bindDevice();
  },
  async save(patch, el) {
    const msg = el && el.closest(".field") ? $(".saved", el.closest(".field")) : null;
    try {
      const r = await fetch("/api/settings", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) });
      const j = await r.json();
      if (!r.ok) throw new Error(j.detail || r.status);
      this.s = j;
      if (msg) { msg.className = "saved ok"; msg.textContent = "✓ " + t("Tallennettu"); setTimeout(() => { if (msg.isConnected) msg.textContent = ""; }, 1800); }
      return true;
    } catch (e) {
      if (msg) { msg.className = "saved err"; msg.textContent = e.message; }
      return false;
    }
  },
  deviceHtml() {
    const s = this.s, c = s.config, d = s.device;
    const locked = c.device_address;
    const conn = d ? `
      <div class="dev-now">
        <div class="dev-icon ok">${batteryIcon(d.battery ?? 0)}</div>
        <div><div class="dev-name">${esc(d.name || "Polar H10")}</div>
          <div class="hint">${t("Yhdistetty")} · ${t("akku")} ${d.battery ?? "–"} % · ${esc(d.model || "")}${d.firmware ? " · firmware " + esc(d.firmware) : ""}</div>
          <div class="hint faint mono">${esc(d.address || "")}</div></div>
      </div>` : `
      <div class="dev-now"><div class="dev-icon"><span class="pill wait"><span class="dot"></span></span></div>
        <div><div class="dev-name">${t("Ei yhteyttä")}</div><div class="hint">${esc(STATE_TEXT[s.state] || s.state)}. ${t("Vyö herää, kun elektrodit ovat kosteat ja vyö on iholla.")}</div></div></div>`;
    const rows = s.seen.map((x) => {
      const isLocked = locked && locked.toLowerCase() === x.address.toLowerCase();
      const isConn = d && d.address === x.address;
      return `<tr><td>${rssiBars(x.rssi)}</td><td><b>${esc(x.name)}</b><div class="faint mono small">${esc(x.address)}</div></td>
        <td class="hint">${isConn ? t("yhdistetty") : x.ago < 15 ? t("kuuluu nyt") : t("{0} min sitten", Math.round(x.ago / 60) || "<1")}</td>
        <td style="text-align:right">${isLocked ? `<span class="status-chip ok">${t("Lukittu")} ✓</span>` : `<button class="btn sm" data-lock="${esc(x.address)}">${t("Lukitse")}</button>`}</td></tr>`;
    }).join("");
    return `${conn}
      <div class="lockline">${locked
        ? `<span>🔒 ${t("Lukittu vyöhön <b class=\"mono\">{0}</b>. Muihin vöihin ei yhdistetä.", esc(locked))}</span><button class="btn sm" id="st-unlock">${t("Poista lukitus")}</button>`
        : `<span>${t("Ei lukittu: yhdistetään ensimmäiseen laitteeseen, jonka nimi alkaa <b>{0}</b>. Lukitse oma vyösi, jos lähistöllä voi olla muita.", esc(c.device_name_prefix))}</span>`}</div>
      <div class="an-k" style="margin-top:16px">${t("Lähistöllä kuullut Polar-laitteet")}</div>
      ${rows ? `<table class="mini devs">${rows}</table>` : `<p class="hint">${t("Ei vielä yhtään. Lista päivittyy, kun sovellus etsii vyötä. Yhteyden aikana etsintä on tauolla.")}</p>`}`;
  },
  bindDevice() {
    this.el.querySelectorAll("[data-lock]").forEach((b) => (b.onclick = async () => { b.disabled = true; await this.save({ device_address: b.dataset.lock }); this.render(); }));
    const u = $("#st-unlock"); if (u) u.onclick = async () => { await this.save({ device_address: null }); this.render(); };
  },
  render() {
    const s = this.s, c = s.config, ro = s.readonly, disk = s.disk;
    const seg = (key, opts) => `<div class="seg" data-key="${key}">${opts.map(([v, l]) => `<button data-v="${v}" class="${String(c[key]) === String(v) ? "on" : ""}">${l}</button>`).join("")}</div>`;
    $("#st").innerHTML = `
      <div class="grid settings fade-in">
        <section class="card span2">
          <div class="card-head"><span class="card-title">${t("Kieli")} · Language</span></div>
          <div class="field"><div class="row"><div class="seg" id="st-lang">${Object.entries(LANGS).map(([k, l]) => `<button data-lang="${k}" class="${k === LANG ? "on" : ""}">${l}</button>`).join("")}</div></div>
            <div class="hint">${t("Valinta tallentuu tähän selaimeen. PDF-raportit tehdään valitulla kielellä.")}</div></div>
        </section>

        <section class="card span2">
          <div class="card-head"><span class="card-title">${t("Sykevyö")}</span></div>
          <div id="st-dev">${this.deviceHtml()}</div>
          <p class="hint" style="margin-top:14px">${t("Vyötä ei tarvitse parittaa käyttöjärjestelmän Bluetooth-asetuksissa, sillä sovellus hoitaa yhteyden itse. Sulje Polar Beat ja Flow puhelimesta ennen tallennusta, muuten ne voivat varata yhteyden.")}</p>
        </section>

        <section class="card">
          <div class="card-head"><span class="card-title">${t("Tallennus")}</span></div>
          <div class="field"><label>${t("Tallenne päättyy, kun vyötä ei ole nähty")}</label>
            <div class="row"><input type="number" min="1" max="180" step="1" data-key="session_timeout_min" value="${c.session_timeout_min}"><span class="unit">min</span><span class="saved"></span></div></div>
          <div class="field"><label>${t("Yhdistä uudelleen, jos dataa ei tule")}</label>
            <div class="row"><input type="number" min="5" max="120" step="1" data-key="data_timeout_s" value="${c.data_timeout_s}"><span class="unit">s</span><span class="saved"></span></div></div>
          <div class="field"><label>${t("Automaattinen aloitus")}</label>
            <div class="row"><label class="switch"><input type="checkbox" id="st-auto" ${c.auto_record ? "checked" : ""}><span class="slider"></span></label>
              <span class="switch-text">${c.auto_record ? t("Tallennus alkaa, kun vyö puetaan") : t("Tallennus aloitetaan käsin Live-näkymästä")}</span><span class="saved"></span></div>
            <div class="hint">${t("Päällä: tallennus alkaa itsestään, kun vyöllä on ollut ihokontakti 10 s, ja päättyy, kun vyö on ollut riisuttuna aikakatkaisun ajan.")}</div></div>
          <div class="field"><label>${t("Estä tietokoneen lepotila")}</label>
            <div class="row">${seg("prevent_sleep", [["always", t("Aina")], ["recording", t("Tallennettaessa")], ["never", t("Ei")]])}<span class="saved"></span></div>
            <div class="hint">${t("\"Aina\" on suositus, jotta puettu vyö havaitaan myös silloin, kun tietokone on ollut pitkään käyttämättä. Näyttö saa silti sammua.")}</div></div>
          <div class="field"><label>${t("Kiihtyvyysanturi")}</label>
            <div class="row">${seg("acc_sample_rate", [[25, "25"], [50, "50"], [100, "100"], [200, "200 Hz"]])}<span class="saved"></span></div>
            <div class="row" style="margin-top:8px">${seg("acc_range_g", [[2, "±2"], [4, "±4"], [8, "±8 G"]])}<span class="saved"></span></div>
            <div class="hint">${t("EKG: {0} Hz (H10:n ainoa taajuus). Muutos tulee voimaan uudella yhteydellä.", ro.ecg_sample_rate)}</div></div>
        </section>

        <section class="card">
          <div class="card-head"><span class="card-title">${t("Analyysi")}</span></div>
          <div class="field"><label>${t("Päivittäinen analyysi")}</label>
            <div class="row"><input type="time" data-key="analysis_time" value="${c.analysis_time || ""}" ${c.analysis_time ? "" : "disabled"}>
              <label class="check"><input type="checkbox" id="st-manual" ${c.analysis_time ? "" : "checked"}> ${t("vain käsin")}</label><span class="saved"></span></div>
            <div class="hint">${t("Päättyneet tallenteet analysoidaan kerran päivässä tähän aikaan, ei koskaan tallennuksen aikana. Tallenteen voi aina analysoida myös sen omasta näkymästä.")}</div></div>
          <div class="field"><label>${t("Kaikki tallenteet")}</label>
            <div class="row"><button class="btn sm" id="st-reall">${t("Analysoi kaikki tallenteet uudelleen")}</button><span class="saved" id="st-reall-msg"></span></div>
            <div class="hint">${t("Hyödyllinen, jos kalibrointia tai analyysiä on muutettu. Raakadataan ei kosketa.")}</div></div>
        </section>

        <section class="card span2">
          <div class="card-head"><span class="card-title">${t("Asennon kalibroinnit")}</span><span class="spacer"></span><button class="btn sm primary" id="st-cal">${t("Kalibroi nyt")}</button></div>
          ${s.calibrations.length ? `<table class="mini">
            <tr><th>${t("Tehty")}</th><th>${t("Lähde")}</th><th>${POSTURE.left.label}</th><th>${POSTURE.right.label}</th><th>${POSTURE.prone.label}</th><th></th></tr>
            ${s.calibrations.map((k, i) => `<tr><td><b>${esc(calLabel(k.id))}</b>${i === 0 ? ` <span class="status-chip ok">${t("uusin")}</span>` : ""}</td><td class="hint">${esc(calSource(k.source))}</td>
              ${["left", "right", "prone"].map((p) => `<td class="num">${Math.round(k.quality.angles[p])}°${k.refs[p] ? "" : ` <span class="faint">${t("arvio")}</span>`}</td>`).join("")}
              <td>${k.quality.warnings.length ? `<span class="status-chip warn" title="${esc(k.quality.warnings.join(" "))}">${t("huomio")}</span>` : ""}</td></tr>`).join("")}
          </table>
          <div class="hint">${t("Uusi tallenne käyttää uusinta kalibrointia, joka on tehty ennen sen loppua. Tallenteen näkymästä voi valita toisen tai merkitä asennot jälkikäteen.")}</div>`
          : `<p class="hint">${t("Ei kalibrointeja. Asennot näytetään nimeämättöminä ryhminä A–D, kunnes kalibroit.")}</p>`}
        </section>

        <section class="card">
          <div class="card-head"><span class="card-title">${t("Data")}</span></div>
          <dl class="kv">
            <dt>${t("Sijainti")}</dt><dd class="mono">${esc(disk.path)}</dd>
            <dt>${t("Tallenteita")}</dt><dd class="num">${disk.sessions}</dd>
            <dt>${t("Koko")}</dt><dd class="num">${fmt.bytes(disk.bytes)}</dd>
            <dt>${t("Vapaata")}</dt><dd class="num">${(disk.free_bytes / 1e9).toFixed(0)} ${t("Gt")} <span class="faint">≈ ${t("{0} vuotta 8 tunnin tallenteita", Math.floor(disk.free_bytes / 2e6 / 8 / 365))}</span></dd>
          </dl>
          <div class="hint">${t("Raakadata säilyy aina. Analyysit ja välimuistit (<span class=\"mono\">cache/</span>) voi poistaa, ja ne lasketaan uudelleen.")}</div>
        </section>

        <section class="card">
          <div class="card-head"><span class="card-title">${t("Tietoturva")}</span></div>
          <dl class="kv">
            <dt>${t("Salasana")}</dt><dd>${ro.auth_enabled ? `<span class="status-chip ok">${t("käytössä")}</span> ${t("käyttäjä")} <b>${esc(ro.auth_username)}</b>` : `<span class="status-chip warn">${t("pois päältä")}</span>`}</dd>
            <dt>${t("Osoite")}</dt><dd class="mono">http://${esc(location.hostname)}:${ro.port}</dd>
          </dl>
          <div class="hint">${t("Salasana asetetaan palvelinkoneella, jotta se ei kulje selaimen kautta:")}</div>
          <pre class="cmd">cd ~/openholter && .venv/bin/python -m openholter set-password</pre>
          <div class="hint">${t("Näkyy vain kotiverkossa. Älä tee reitittimeen porttiohjausta. Ei pilvipalveluita, analytiikkaa eikä telemetriaa.")}</div>
        </section>

        <section class="card span2" id="st-trash"><div class="card-head"><span class="card-title">${t("Roskakori")}</span></div><p class="hint">${t("Ladataan…")}</p></section>

        <a class="card span2 about-link" href="#/about">
          <span class="info-ico"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="8" cy="8" r="6.4"/><path d="M8 7.2v4M8 4.7v.1" stroke-linecap="round"/></svg></span>
          <span><b>${t("Menetelmät ja tekniikka")}</b><span class="hint">${t("Miten lisälyönnit, HRV, asento ja signaalin laatu lasketaan. Validointi, käytetyt kirjastot ja tietosuoja.")}</span></span>
          <span class="arrow">→</span>
        </a>
      </div>`;
    this.bindDevice();
    this.el.querySelectorAll("#st-lang [data-lang]").forEach((b) => (b.onclick = () => { if (b.dataset.lang !== LANG) setLang(b.dataset.lang); }));
    this.el.querySelectorAll("input[data-key]").forEach((inp) => (inp.onchange = () => {
      const v = inp.type === "number" ? Number(inp.value) : inp.value;
      this.save({ [inp.dataset.key]: v }, inp);
    }));
    this.el.querySelectorAll(".seg[data-key]").forEach((sg) => sg.querySelectorAll("button").forEach((b) => (b.onclick = async () => {
      const key = sg.dataset.key, raw = b.dataset.v;
      const v = typeof c[key] === "number" ? Number(raw) : raw;
      if (await this.save({ [key]: v }, sg)) sg.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
    })));
    $("#st-auto").onchange = async (e) => {
      const on = e.target.checked;
      if (await this.save({ auto_record: on }, e.target)) {
        $(".switch-text", e.target.closest(".row")).textContent = on ? t("Tallennus alkaa, kun vyö puetaan") : t("Tallennus aloitetaan käsin Live-näkymästä");
      } else e.target.checked = !on;
    };
    $("#st-manual").onchange = async (e) => {
      const t = $('input[data-key="analysis_time"]');
      if (e.target.checked) { await this.save({ analysis_time: "" }, t); t.disabled = true; }
      else { t.disabled = false; t.value = t.value || "12:00"; await this.save({ analysis_time: t.value }, t); }
    };
    $("#st-reall").onclick = async () => {
      const r = await api("/api/analyze-all", { method: "POST" });
      $("#st-reall-msg").className = "saved ok"; $("#st-reall-msg").textContent = "✓ " + t("{0} tallennetta jonossa", r.queued);
    };
    $("#st-cal").onclick = () => Calib.open(() => this.load());
    this.renderTrash();
  },
  async renderTrash() {
    const el = $("#st-trash"); if (!el) return;
    let items;
    try { items = await api("/api/trash"); } catch { return; }
    if (!$("#st-trash")) return;
    const total = items.reduce((a, x) => a + x.bytes, 0);
    el.innerHTML = `
      <div class="card-head"><span class="card-title">${t("Roskakori")}</span>
        <span class="meta">${items.length ? `${items.length === 1 ? t("1 tallenne") : t("{0} tallennetta", items.length)} · ${fmt.bytes(total)}` : t("tyhjä")}</span><span class="spacer"></span>
        ${items.length ? `<button class="btn sm ghost-danger" id="tr-empty">${t("Tyhjennä")}</button>` : ""}</div>
      ${items.length ? `<table class="mini">
        <tr><th>${t("Tallenne")}</th><th>${t("Poistettu")}</th><th>${t("Poistuu lopullisesti")}</th><th>${t("Koko")}</th><th></th></tr>
        ${items.map((x) => {
          const t0 = x.started_wall_ns ? x.started_wall_ns / 1e6 : null, t1 = x.ended_wall_ns ? x.ended_wall_ns / 1e6 : null;
          const day = t0 ? new Date(t0).toLocaleDateString(LOCALE, { day: "numeric", month: "numeric" }) : "";
          const label = t0 ? `${day} ${t1 ? fmt.range(t0, t1) : fmt.clock(t0)}` : x.session_id;
          return `<tr><td><b>${esc(label)}</b></td><td class="hint">${esc(new Date(Date.parse(x.deleted_at)).toLocaleDateString(LOCALE, { day: "numeric", month: "numeric" }))}</td>
            <td class="hint">${x.purge_in_days < 1 ? t("alle vuorokauden päästä") : t("{0} pv päästä", Math.floor(x.purge_in_days))}</td><td class="num">${fmt.bytes(x.bytes)}</td>
            <td style="text-align:right;white-space:nowrap"><button class="btn sm" data-restore="${esc(x.name)}">${t("Palauta")}</button>
              <button class="btn sm ghost-danger" data-purge="${esc(x.name)}" data-label="${esc(label)}">${t("Poista pysyvästi")}</button></td></tr>`;
        }).join("")}</table>
        <div class="hint">${t("Poistetut tallenteet säilyvät täällä 30 päivää, jonka jälkeen ne poistetaan automaattisesti.")}</div>`
      : `<p class="hint">${t("Poistetut tallenteet säilyvät täällä 30 päivää ennen lopullista poistoa.")}</p>`}`;
    el.querySelectorAll("[data-restore]").forEach((b) => (b.onclick = async () => {
      const r = await fetch(`/api/trash/${encodeURIComponent(b.dataset.restore)}/restore`, { method: "POST" });
      const j = await r.json().catch(() => ({}));
      toast(r.ok ? t("Tallenne palautettu.") : esc(j.detail || t("Palautus epäonnistui.")));
      this.load();
    }));
    el.querySelectorAll("[data-purge]").forEach((b) => (b.onclick = async () => {
      const ok = await confirmDialog({ title: t("Poistetaanko pysyvästi?"), body: `<b>${esc(b.dataset.label)}</b><br><br>${t("EKG-data poistetaan tietokoneelta lopullisesti. Tätä ei voi perua.")}`, confirm: t("Poista pysyvästi"), danger: true });
      if (!ok) return;
      await fetch(`/api/trash/${encodeURIComponent(b.dataset.purge)}`, { method: "DELETE" });
      toast(t("Poistettu pysyvästi.")); this.load();
    }));
    const empty = $("#tr-empty");
    if (empty) empty.onclick = async () => {
      const ok = await confirmDialog({ title: t("Tyhjennetäänkö roskakori?"), body: `${items.length === 1 ? t("1 tallenne") : t("{0} tallennetta", items.length)} (${fmt.bytes(total)}) ${t("poistetaan tietokoneelta lopullisesti. Tätä ei voi perua.")}`, confirm: t("Tyhjennä"), danger: true });
      if (!ok) return;
      await fetch("/api/trash", { method: "DELETE" });
      toast(t("Roskakori tyhjennetty.")); this.load();
    };
  },
};

// ------------------------------------------------------------------ router

let current = null;
async function route() {
  const hash = location.hash || "#/live";
  const view = $("#view");
  if (current && current.unmount) current.unmount();
  window.scrollTo(0, 0);
  const [, page, arg, arg2] = hash.split("/");
  const alias = { nights: "recordings", night: "recording" };
  if (alias[page]) { location.replace(`#/${alias[page]}${arg ? "/" + arg : ""}`); return; }
  document.querySelectorAll("[data-nav]").forEach((a) => a.classList.toggle("active", a.dataset.nav === (page === "recording" ? "recordings" : page)));
  if (page === "recordings") { current = RecordingsPage; await RecordingsPage.mount(view); }
  else if (page === "settings") { current = SettingsPage; await SettingsPage.mount(view); }
  else if (page === "about") { current = AboutPage; await AboutPage.mount(view, arg); }
  else if (page === "recording" && arg) { current = new RecordingView(view, decodeURIComponent(arg), arg2 != null ? Number(arg2) : null); await current.mount(); }
  else if (page === "calibrate") { // bookmarkable: opens the calibration wizard on top of Live
    current = LivePage; LivePage.mount(view);
    Calib.open(() => { if (location.hash === "#/calibrate") location.replace("#/live"); });
  }
  else { current = LivePage; LivePage.mount(view); }
}

// "20261030.0940" -> "30.10.2026 09.40" / "30/10/2026 09:40"
function fmtBuild(b) {
  const m = /^(\d{4})(\d{2})(\d{2})\.(\d{2})(\d{2})$/.exec(b || "");
  return m ? t("{0}.{1}.{2} {3}.{4}", +m[3], +m[2], m[1], m[4], m[5]) : b;
}

api("/api/status").then((s) => {
  const el = document.getElementById("app-version");
  if (el) el.textContent = `OpenHolter ${s.version}${s.build && s.build !== "dev" ? ` · build ${fmtBuild(s.build)}` : " · " + t("kehitysversio")}`;
}).catch(() => {});

window.addEventListener("hashchange", route);
translateStatic();
{
  const sw = document.getElementById("lang-switch");
  if (sw) {
    sw.innerHTML = Object.keys(LANGS).map((k) => `<button data-lang="${k}" class="${k === LANG ? "on" : ""}" title="${LANGS[k]}" lang="${k}" aria-pressed="${k === LANG}">${k.toUpperCase()}</button>`).join("");
    sw.querySelectorAll("button").forEach((b) => (b.onclick = () => { if (b.dataset.lang !== LANG) setLang(b.dataset.lang); }));
  }
}
Live.connect();
route();
