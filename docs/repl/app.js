// reASITIC REPL — Pyodide bridge and UI wiring.

const $ = (id) => document.getElementById(id);
const statusEl = $("status");
const resultsEl = $("results");
const versionEl = $("version");

const ui = {
  techSelect: $("tech-select"),
  shapeSelect: $("shape-select"),
  metalSelect: $("metal-select"),
  metalBalunPrimarySelect: $("metal-balun-primary-select"),
  metalCapTopSelect: $("metal-cap-top-select"),
  metalCapBottomSelect: $("metal-cap-bottom-select"),
  metalBalunTransitionSelect: $("metal-balun-transition-select"),
  exitMetalSelect: $("exit-metal-select"),
  mmsqExitSelect: $("mmsq-exit-metal-select"),
  viaSelect: $("via-index-select"),
  name: $("p-name"),
  pname: $("p-pname"),
  sname: $("p-sname"),
  length: $("p-length"),
  wid: $("p-wid"),
  ilenSq: $("p-ilen-sq"),
  iwidSq: $("p-iwid-sq"),
  radius: $("p-radius"),
  widPoly: $("p-wid-poly"),
  ringRadius: $("p-ring-radius"),
  capLength: $("p-cap-length"),
  capWidth: $("p-cap-width"),
  wireLength: $("p-wire-length"),
  wireWidth: $("p-wire-width"),
  width: $("p-width"),
  balunW1: $("p-balun-w1"),
  balunW2: $("p-balun-w2"),
  spacing: $("p-spacing"),
  ilen: $("p-ilen"),
  iwid: $("p-iwid"),
  turns: $("p-turns"),
  sides: $("p-sides"),
  gap: $("p-gap"),
  nvx: $("p-nvx"),
  nvy: $("p-nvy"),
  xorg: $("p-xorg"),
  yorg: $("p-yorg"),
  orient: $("p-orient"),
  phase: $("p-phase"),
  viaPhase: $("p-via-phase"),
  freq: $("p-freq"),
  swF1: $("sw-f1"),
  swF2: $("sw-f2"),
  swStep: $("sw-step"),
  build: $("btn-build"),
  actions: document.querySelectorAll(".actions button"),
  canvas: $("canvas"),
  legend: $("legend"),
  dims: $("dims"),
  code: $("code"),
  run: $("btn-run"),
  clear: $("btn-clear"),
  replOut: $("repl-out"),
  outputPanel: $("output-panel"),
  outputResizer: $("output-resizer"),
  outputTabs: $("output-tabs"),
};

// Per-pane registry for the dynamic analysis tabs. Each entry is keyed by
// the tab id (e.g. "lrq-3") and holds the action name + frozen params +
// preBuilt DOM nodes + live-update flag. ``rerun(reg)`` re-invokes the
// underlying analysis using the frozen params; ``buildShape()`` walks the
// registry and calls ``rerun`` for every entry with ``liveUpdate`` set.
const ANALYSIS_TABS = new Map();
let analysisCounter = 0;

// Parse a value that may be blank ("") / "0" → return undefined ("not specified").
// Otherwise parse as float and return that. Used to send only the parameters
// the user explicitly set so bridge.py can apply ASITIC defaults.
function optFloat(el) {
  if (!el) return undefined;
  const v = el.value;
  if (v === null || v === undefined) return undefined;
  const s = String(v).trim();
  if (s === "") return undefined;
  const n = parseFloat(s);
  if (!Number.isFinite(n) || n <= 0) return undefined;
  return n;
}

function optText(el) {
  if (!el) return undefined;
  const v = el.value;
  if (v === null || v === undefined) return undefined;
  const s = String(v).trim();
  return s === "" ? undefined : s;
}

// Pyodide runs in a Web Worker so we can actually terminate runaway
// operations. ``py.<fn>(args)`` returns a Promise that resolves with the
// Python function's JS-converted result, or rejects on error / timeout.
// On timeout we kill the worker and respawn it — the in-flight Python
// call is forcibly stopped (the only way to abort synchronous Pyodide).
const OP_TIMEOUT_MS = 3000;
const BOOT_TIMEOUT_MS = 0;  // boot takes 5–30 s; never time it out
let worker = null;
let bridgeReady = false;
let nextRequestId = 1;
const pending = new Map();  // request id → {resolve, reject, timer, label}
let workerRebootInFlight = null;

function workerCall(type, payload, timeoutMs = OP_TIMEOUT_MS) {
  if (!worker) return Promise.reject(new Error("worker not booted"));
  const id = nextRequestId++;
  const label = payload && payload.fn ? payload.fn : type;
  return new Promise((resolve, reject) => {
    const timer = timeoutMs > 0
      ? setTimeout(() => {
          if (!pending.has(id)) return;
          pending.delete(id);
          reject(new Error(`${label} timed out after ${timeoutMs} ms`));
          // Hard cancel: terminate Pyodide. The reboot drains any other
          // in-flight requests with the same reason.
          rebootWorkerAfterTimeout(label);
        }, timeoutMs)
      : null;
    pending.set(id, { resolve, reject, timer, label });
    try {
      worker.postMessage({ id, type, ...(payload || {}) });
    } catch (err) {
      pending.delete(id);
      if (timer) clearTimeout(timer);
      reject(err);
    }
  });
}

// ``await py.analyze_lrq(2.4)`` ≡ ``workerCall("call", {fn: "analyze_lrq", args: [2.4]})``.
// Same signatures as the old ``pyodide.globals.get("X")(args).toJs()``
// path, only async and timeout-bounded.
const py = new Proxy({}, {
  get(_, name) {
    return (...args) => workerCall("call", { fn: name, args });
  },
});

function spawnWorker() {
  worker = new Worker("worker.js");
  worker.onmessage = (ev) => {
    const { id, ok, result, error } = ev.data;
    const req = pending.get(id);
    if (!req) return;
    pending.delete(id);
    if (req.timer) clearTimeout(req.timer);
    if (ok) req.resolve(result);
    else req.reject(new Error(error || "worker error"));
  };
  worker.onerror = (err) => {
    // Reject everything that's still in flight.
    for (const req of pending.values()) {
      if (req.timer) clearTimeout(req.timer);
      req.reject(err);
    }
    pending.clear();
  };
}

// One-at-a-time reboot. Subsequent timeouts that fire while a reboot is
// already running just await the in-flight reboot's promise.
async function rebootWorkerAfterTimeout(label) {
  if (workerRebootInFlight) return workerRebootInFlight;
  workerRebootInFlight = (async () => {
    try {
      bridgeReady = false;
      setEnabled(false);
      setStatus(`Operation \"${label}\" timed out — restarting Pyodide…`, "busy");
      if (worker) worker.terminate();
      // Reject every other in-flight call with the same reason.
      for (const req of pending.values()) {
        if (req.timer) clearTimeout(req.timer);
        req.reject(new Error("worker terminated after timeout"));
      }
      pending.clear();
      spawnWorker();
      await workerCall("boot", {}, BOOT_TIMEOUT_MS);
      await loadTechFile(ui.techSelect.value);
      bridgeReady = true;
      setEnabled(true);
      setStatus("Ready (restarted after timeout).", "ready");
    } catch (err) {
      setStatus(`Restart failed: ${err.message || err}`, "error");
    } finally {
      workerRebootInFlight = null;
    }
  })();
  return workerRebootInFlight;
}

function setStatus(msg, kind = "info") {
  statusEl.textContent = msg;
  statusEl.style.color =
    kind === "error" ? "var(--bad)" :
    kind === "ready" ? "var(--good)" :
    kind === "busy"  ? "var(--warn)" :
    "var(--muted)";
}

function showResult(text, kind = "info") {
  resultsEl.textContent = text;
  resultsEl.classList.remove("success", "error");
  if (kind === "ok") resultsEl.classList.add("success");
  if (kind === "error") resultsEl.classList.add("error");
}

function fmtFloat(v, n = 4) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  if (Math.abs(v) >= 1e4 || (Math.abs(v) > 0 && Math.abs(v) < 1e-3)) {
    return v.toExponential(n);
  }
  return v.toFixed(n);
}

function setEnabled(enabled) {
  ui.build.disabled = !enabled;
  ui.run.disabled = !enabled;
  ui.actions.forEach((b) => (b.disabled = !enabled));
}

function downloadText(filename, text, mime = "text/plain") {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function getSpec() {
  const kind = ui.shapeSelect.value;
  // Build a spec that mirrors the per-command syntax in ./run/doc:
  // mandatory args are always present, optional args are sent only when
  // the user provided a value (so bridge.py applies the ASITIC default).

  // Per-shape "primary size" args.
  let length;
  let width;
  let radius;
  if (kind === "ring") {
    length = parseFloat(ui.ringRadius.value);
    width = parseFloat(ui.wireWidth.value);
    radius = parseFloat(ui.ringRadius.value);
  } else if (kind === "wire") {
    length = parseFloat(ui.wireLength.value);
    width = parseFloat(ui.wireWidth.value);
  } else if (kind === "capacitor") {
    length = parseFloat(ui.capLength.value);
    width = parseFloat(ui.capWidth.value);
  } else if (kind === "polygon_spiral" || kind === "symmetric_polygon") {
    radius = parseFloat(ui.radius.value);
    length = radius * 2;
    width = parseFloat(ui.width.value);
  } else if (kind === "via") {
    length = 0;
    width = 0;
  } else if (kind === "balun_primary" || kind === "balun_secondary") {
    length = parseFloat(ui.length.value);
    width = parseFloat(ui.balunW1.value);
  } else {
    length = parseFloat(ui.length.value);
    width = parseFloat(ui.width.value);
  }

  // Metal: source from the field appropriate for this shape kind.
  let metal = null;
  let metal_top = null;       // CAP METAL1
  let metal_bottom = null;    // CAP METAL2
  let metal_transition = null; // BALUN METAL2
  if (kind === "capacitor") {
    metal_top = ui.metalCapTopSelect ? ui.metalCapTopSelect.value : null;
    metal_bottom = ui.metalCapBottomSelect ? ui.metalCapBottomSelect.value : null;
    metal = metal_top;
  } else if (kind === "balun_primary" || kind === "balun_secondary") {
    metal = ui.metalBalunPrimarySelect ? ui.metalBalunPrimarySelect.value : null;
    metal_transition = ui.metalBalunTransitionSelect
      ? ui.metalBalunTransitionSelect.value : null;
  } else {
    metal = ui.metalSelect ? ui.metalSelect.value : null;
  }

  // EXIT metal: SQ/SYMSQ/SYMPOLY/TRANS have an optional EXIT; SQMM has a
  // required EXIT (bottom of the stack).
  let exit_metal = null;
  if (kind === "multi_metal_square") {
    exit_metal = ui.mmsqExitSelect ? ui.mmsqExitSelect.value : null;
  } else {
    exit_metal = ui.exitMetalSelect ? (ui.exitMetalSelect.value || null) : null;
  }

  // NAME — most shapes use a single name, TRANS distinguishes PNAME/SNAME.
  let name;
  if (kind === "transformer_primary") name = ui.pname.value || "TP";
  else if (kind === "transformer_secondary") name = ui.sname.value || "TS";
  else name = ui.name.value || "L1";

  const spec = {
    kind,
    name,
    metal,
    exit_metal,
    metal_top,
    metal_bottom,
    metal_transition,
    via_index: ui.viaSelect && ui.viaSelect.value !== ""
      ? parseInt(ui.viaSelect.value, 10) : 0,
    radius: radius !== undefined ? radius : undefined,
    length,
    width,
    spacing: parseFloat(ui.spacing.value),
    turns: parseFloat(ui.turns.value),
    sides: parseInt(ui.sides.value, 10),
    gap: parseFloat(ui.gap.value),
    n_via_x: ui.nvx ? parseInt(ui.nvx.value, 10) : 1,
    n_via_y: ui.nvy ? parseInt(ui.nvy.value, 10) : 1,
    x_origin: parseFloat(ui.xorg.value),
    y_origin: parseFloat(ui.yorg.value),
    orient: parseFloat(ui.orient.value),
    phase: parseFloat(ui.phase.value),
    via_phase: ui.viaPhase ? parseFloat(ui.viaPhase.value) : 0,
  };

  // Optional rectangular / inner-bound parameters, sent only when set.
  // Square family: WID, ILEN, IWID.
  const wid = optFloat(ui.wid);
  if (wid !== undefined) spec.wid = wid;
  const ilenSq = optFloat(ui.ilenSq);
  if (ilenSq !== undefined) spec.ilen = ilenSq;
  const iwidSq = optFloat(ui.iwidSq);
  if (iwidSq !== undefined) spec.iwid = iwidSq;
  // Polygon family: WID (outer height — not in the doc for SP, only SYMPOLY).
  const widPoly = optFloat(ui.widPoly);
  if (widPoly !== undefined) spec.wid = widPoly;
  // Centre-tapped: ILEN required; IWID optional.
  if (kind === "symmetric_square" || kind === "symmetric_polygon") {
    spec.ilen = parseFloat(ui.ilen.value);
    const iwid = optFloat(ui.iwid);
    if (iwid !== undefined) spec.iwid = iwid;
  }
  // BALUN: optional W2.
  const w2 = optFloat(ui.balunW2);
  if (w2 !== undefined) spec.w2 = w2;

  return spec;
}

function applyShapeVisibility() {
  const kind = ui.shapeSelect.value;
  document.querySelectorAll("[data-only]").forEach((el) => {
    const allowed = el.dataset.only.split(/\s+/);
    el.style.display = allowed.includes(kind) ? "" : "none";
  });
}

function populateMetals(metals) {
  ui.metalSelect.innerHTML = "";
  ui.exitMetalSelect.innerHTML = '<option value="">(none — default M(metal-1))</option>';
  if (ui.mmsqExitSelect) ui.mmsqExitSelect.innerHTML = "";
  if (ui.metalBalunPrimarySelect) ui.metalBalunPrimarySelect.innerHTML = "";
  if (ui.metalBalunTransitionSelect) ui.metalBalunTransitionSelect.innerHTML = "";
  if (ui.metalCapTopSelect) ui.metalCapTopSelect.innerHTML = "";
  if (ui.metalCapBottomSelect) ui.metalCapBottomSelect.innerHTML = "";

  const valueLabelPairs = metals.map((m) => ({
    value: m.name || String(m.index),
    label: `${m.name || ("m" + m.index)}  (idx ${m.index}, t=${m.t}μm)`,
    index: m.index,
  }));
  const allSelects = [
    ui.metalSelect, ui.exitMetalSelect, ui.mmsqExitSelect,
    ui.metalBalunPrimarySelect, ui.metalBalunTransitionSelect,
    ui.metalCapTopSelect, ui.metalCapBottomSelect,
  ].filter(Boolean);
  valueLabelPairs.forEach(({ value, label }) => {
    allSelects.forEach((sel) => {
      const opt = document.createElement("option");
      opt.value = value;
      opt.textContent = label;
      sel.appendChild(opt);
    });
  });

  // Defaults — top metal for the primary trace selects, one layer down
  // (or the lowest) for transition / bottom selects.
  const top = valueLabelPairs[valueLabelPairs.length - 1];
  const second = valueLabelPairs.length >= 2
    ? valueLabelPairs[valueLabelPairs.length - 2]
    : top;
  ui.metalSelect.value = top.value;
  ui.exitMetalSelect.value = "";
  if (ui.mmsqExitSelect) ui.mmsqExitSelect.value = second.value;
  if (ui.metalBalunPrimarySelect) ui.metalBalunPrimarySelect.value = top.value;
  if (ui.metalBalunTransitionSelect) ui.metalBalunTransitionSelect.value = second.value;
  if (ui.metalCapTopSelect) ui.metalCapTopSelect.value = top.value;
  if (ui.metalCapBottomSelect) ui.metalCapBottomSelect.value = second.value;
}

function populateVias(vias) {
  if (!ui.viaSelect) return;
  ui.viaSelect.innerHTML = "";
  vias.forEach((v, i) => {
    const opt = document.createElement("option");
    opt.value = String(i);
    opt.textContent = `${v.name || ("via" + i)} (idx ${i})`;
    ui.viaSelect.appendChild(opt);
  });
  if (vias.length > 0) ui.viaSelect.value = "0";
}

async function loadTechFile(filename) {
  const resp = await fetch(filename, { cache: "no-cache" });
  if (!resp.ok) throw new Error(`Failed to fetch ${filename}: ${resp.status}`);
  const text = await resp.text();
  const info = await py.load_tech(text);
  populateMetals(info.metals);
  populateVias(info.vias || []);
  setStatus(`Loaded ${filename} — ${info.metals.length} metals, ${info.n_layers} layers, ${info.n_vias} vias.`, "ready");
}

async function bootPyodide() {
  spawnWorker();
  setStatus("Loading Pyodide + numpy + scipy + reasitic wheel (one-time, ~30 MB)…", "busy");
  await workerCall("boot", {}, BOOT_TIMEOUT_MS);
  bridgeReady = true;

  const v = await py.version_info();
  versionEl.textContent = v;

  await loadTechFile(ui.techSelect.value);

  setEnabled(true);
  applyShapeVisibility();
  // Auto-build the default geometry so the page lands with something visible.
  await buildShape();
  setStatus("Ready.", "ready");
  showResult(
    "Ready. Adjust the geometry and press “Build inductor”, then use the analysis buttons.\n" +
    "Every operation is capped at 3 s — if Python takes longer the worker is killed and Pyodide restarts.",
    "ok"
  );
}

async function buildShape() {
  if (!bridgeReady) return;
  setStatus("Building geometry…", "busy");
  try {
    const spec = getSpec();
    const payload = await py.build_shape(spec);
    Draw.render(ui.canvas, payload, ui.legend, ui.dims);
    const cmdEl = $("create-cmd");
    if (cmdEl) cmdEl.textContent = formatCreateCommand(spec);
    setStatus(
      `Built ${payload.name}: ${payload.polygons.length} polygon(s), turns=${payload.turns}.`,
      "ready"
    );
    // Each open analysis tab with live update on re-runs against the new
    // shape; the rest get marked stale so the user knows the numbers no
    // longer reflect the visible geometry.
    await refreshAnalysisTabs();
  } catch (err) {
    setStatus("Build failed.", "error");
    showResult(`Build failed:\n${err.message || err}`, "error");
  }
}

// Render the ASITIC CLI ``Create`` command that reproduces the current
// spec. Mirrors the syntax in run/doc/create/create.html:
//
//   SQ      NAME:LEN:(WID):(ILEN:(IWID)):W:S:N:METAL:(EXIT:XORG:YORG:ORIENT:PHASE)
//   SP      NAME:RADIUS:SIDES:W:S:N:METAL:(XORG:YORG:ORIENT:PHASE)
//   SYMSQ   NAME:LEN:(WID):(ILEN:(IWID)):W:S:N:METAL:(EXIT:XORG:YORG:ORIENT:PHASE)
//   SYMPOLY NAME:RAD:(WID):(ILEN:(IWID)):W:S:N:METAL:(EXIT:XORG:YORG:ORIENT:PHASE)
//   SQMM    NAME:LEN:(WID):(ILEN:(IWID)):W:S:N:METAL:EXIT:(XORG:YORG:ORIENT:PHASE)
//   TRANS   PNAME:SNAME:LEN:WID:W:S:N:METAL:(EXIT:XORG:YORG:ORIENT:PHASE)
//   BALUN   NAME:LEN:W1:(W2):S:N:METAL:METAL2:(XORG:YORG:ORIENT)
//   WIRE    NAME:LEN:WID:METAL:(XORG:YORG:ORIENT:PHASE)
//   CAP     NAME:LEN:WID:METAL1:METAL2:XORG:YORG:(ORIENT)
//   VIA     NAME:NX:(NY):VIA:(XORG:YORG:PHASE)
//
// Optional params that match their default are omitted to keep the line
// short and copy-pasteable; the doc allows leaving them off.
function formatCreateCommand(spec) {
  if (!spec) return "—";
  const num = (v) => Number.isFinite(v) ? parseFloat(v.toFixed(4)).toString() : null;
  const opt = (cond, key, val) => (cond && val !== null && val !== undefined && val !== ""
    ? `${key}=${val}` : null);
  const join = (cmd, parts) => `${cmd} ${parts.filter((p) => p).join(":")}`;
  const xyOrig = [
    opt(spec.x_origin !== 0, "XORG", num(spec.x_origin)),
    opt(spec.y_origin !== 0, "YORG", num(spec.y_origin)),
  ];
  const orientPhase = [
    opt(spec.orient !== 0, "ORIENT", num(spec.orient)),
    opt(spec.phase !== 0, "PHASE", num(spec.phase)),
  ];
  const optExit = opt(spec.exit_metal, "EXIT", spec.exit_metal);
  const optWid  = opt(spec.wid && spec.wid !== spec.length, "WID", num(spec.wid));
  const optIlenSq = opt(spec.ilen && spec.kind !== "symmetric_square" && spec.kind !== "symmetric_polygon",
                        "ILEN", num(spec.ilen));
  const optIwid = opt(spec.iwid, "IWID", num(spec.iwid));

  const k = spec.kind;
  if (k === "square_spiral") {
    return join("SQ", [
      `NAME=${spec.name}`,
      `LEN=${num(spec.length)}`, optWid,
      optIlenSq, optIwid,
      `W=${num(spec.width)}`, `S=${num(spec.spacing)}`, `N=${num(spec.turns)}`,
      `METAL=${spec.metal}`, optExit, ...xyOrig, ...orientPhase,
    ]);
  }
  if (k === "polygon_spiral") {
    return join("SP", [
      `NAME=${spec.name}`,
      `RADIUS=${num(spec.radius)}`, `SIDES=${spec.sides}`,
      `W=${num(spec.width)}`, `S=${num(spec.spacing)}`, `N=${num(spec.turns)}`,
      `METAL=${spec.metal}`, ...xyOrig, ...orientPhase,
    ]);
  }
  if (k === "symmetric_square") {
    return join("SYMSQ", [
      `NAME=${spec.name}`, `LEN=${num(spec.length)}`, optWid,
      `W=${num(spec.width)}`, `S=${num(spec.spacing)}`,
      `ILEN=${num(spec.ilen)}`, optIwid,
      `N=${num(spec.turns)}`, `METAL=${spec.metal}`, optExit,
      ...xyOrig, ...orientPhase,
    ]);
  }
  if (k === "symmetric_polygon") {
    return join("SYMPOLY", [
      `NAME=${spec.name}`, `RAD=${num(spec.radius)}`, optWid,
      `W=${num(spec.width)}`, `S=${num(spec.spacing)}`,
      `ILEN=${num(spec.ilen)}`, optIwid,
      `N=${num(spec.turns)}`, `SIDES=${spec.sides}`,
      `METAL=${spec.metal}`, optExit, ...xyOrig, ...orientPhase,
    ]);
  }
  if (k === "multi_metal_square") {
    return join("SQMM", [
      `NAME=${spec.name}`, `LEN=${num(spec.length)}`, optWid,
      `W=${num(spec.width)}`, `S=${num(spec.spacing)}`, `N=${num(spec.turns)}`,
      `METAL=${spec.metal}`, `EXIT=${spec.exit_metal || ""}`,
      ...xyOrig, ...orientPhase,
    ]);
  }
  if (k === "transformer_primary" || k === "transformer_secondary") {
    // TRANS in ASITIC is a single command that creates both coils, so
    // we surface both names even though our UI builds one coil at a time.
    const pname = (ui.pname && ui.pname.value) || "TP";
    const sname = (ui.sname && ui.sname.value) || "TS";
    return join("TRANS", [
      `PNAME=${pname}`, `SNAME=${sname}`,
      `LEN=${num(spec.length)}`,
      `W=${num(spec.width)}`, `S=${num(spec.spacing)}`, `N=${num(spec.turns)}`,
      `METAL=${spec.metal}`, optExit, ...xyOrig, ...orientPhase,
    ]);
  }
  if (k === "balun_primary" || k === "balun_secondary") {
    return join("BALUN", [
      `NAME=${spec.name}`, `LEN=${num(spec.length)}`,
      `W1=${num(spec.width)}`,
      opt(spec.w2 && spec.w2 !== spec.width, "W2", num(spec.w2)),
      `S=${num(spec.spacing)}`, `N=${num(spec.turns)}`,
      `METAL=${spec.metal}`,
      opt(spec.metal_transition, "METAL2", spec.metal_transition),
      ...xyOrig,
      opt(spec.orient !== 0, "ORIENT", num(spec.orient)),
    ]);
  }
  if (k === "wire") {
    return join("W", [
      `NAME=${spec.name}`,
      `LEN=${num(spec.length)}`, `WID=${num(spec.width)}`,
      `METAL=${spec.metal}`, ...xyOrig, ...orientPhase,
    ]);
  }
  if (k === "capacitor") {
    return join("CAP", [
      `NAME=${spec.name}`,
      `LEN=${num(spec.length)}`, `WID=${num(spec.width)}`,
      `METAL1=${spec.metal_top || spec.metal}`,
      `METAL2=${spec.metal_bottom || spec.metal}`,
      `XORG=${num(spec.x_origin)}`, `YORG=${num(spec.y_origin)}`,
      opt(spec.orient !== 0, "ORIENT", num(spec.orient)),
    ]);
  }
  if (k === "via") {
    // Lookup the via-layer's name from the populated <select> so the
    // command shows e.g. "VIA=via0" instead of a bare index.
    let viaName = `via${spec.via_index}`;
    if (ui.viaSelect && ui.viaSelect.selectedOptions[0]) {
      viaName = ui.viaSelect.selectedOptions[0].textContent.split(/\s+/)[0];
    }
    return join("V", [
      `NAME=${spec.name}`,
      `NX=${spec.n_via_x}`,
      ...(spec.n_via_y && spec.n_via_y !== spec.n_via_x
        ? [`NY=${spec.n_via_y}`] : []),
      `VIA=${viaName}`, ...xyOrig,
      opt(spec.via_phase !== 0, "PHASE", num(spec.via_phase)),
    ]);
  }
  if (k === "ring") {
    // RING is a reASITIC extension (no entry in run/doc); render in the
    // same style for consistency.
    return join("RING", [
      `NAME=${spec.name}`, `RADIUS=${num(spec.radius)}`,
      `W=${num(spec.width)}`, `GAP=${num(spec.gap)}`,
      `SIDES=${spec.sides}`, `METAL=${spec.metal}`,
      ...xyOrig, ...orientPhase,
    ]);
  }
  return `${k} (?)`;
}

function fmtLrq(d) {
  return [
    `Frequency        : ${fmtFloat(d.freq_ghz, 3)} GHz`,
    `Self inductance L: ${fmtFloat(d.L_nH, 4)} nH`,
    `R (DC)           : ${fmtFloat(d.R_dc_ohm, 4)} Ω`,
    `R (AC, ${fmtFloat(d.freq_ghz, 2)} GHz): ${fmtFloat(d.R_ac_ohm, 4)} Ω`,
    `Quality factor Q : ${fmtFloat(d.Q, 2)}`,
    "",
    `Segments         : ${d.n_segments}`,
    `Total run length : ${fmtFloat(d.total_length_um, 1)} μm`,
  ].join("\n");
}

function fmtPi(d) {
  return [
    `Pi-equivalent at ${fmtFloat(d.freq_ghz, 3)} GHz`,
    "",
    `L_series  : ${fmtFloat(d.L_nH, 4)} nH`,
    `R_series  : ${fmtFloat(d.R_series, 4)} Ω`,
    `C_p1      : ${fmtFloat(d.C_p1_fF, 3)} fF`,
    `C_p2      : ${fmtFloat(d.C_p2_fF, 3)} fF`,
    `G_p1      : ${fmtFloat(d.g_p1, 4)} S`,
    `G_p2      : ${fmtFloat(d.g_p2, 4)} S`,
  ].join("\n");
}

// L · R · Q sweep — same two-pane layout as the S-param sweep but the
// plot is a small-multiples (3 stacked panels: L, R_ac, Q) since the
// three quantities have unrelated y-axis scales. The table is wider too
// since it carries L, R_dc, R_ac, Q simultaneously.
function renderLrqSweepTable(tableBody, d) {
  tableBody.innerHTML = "";
  for (let i = 0; i < d.freqs_ghz.length; i++) {
    const tr = document.createElement("tr");
    [
      d.freqs_ghz[i].toFixed(3),
      d.L_nH[i].toFixed(4),
      d.R_dc_ohm[i].toFixed(4),
      d.R_ac_ohm[i].toFixed(4),
      d.Q[i].toFixed(3),
    ].forEach((v) => {
      const td = document.createElement("td");
      td.textContent = v;
      tr.appendChild(td);
    });
    tableBody.appendChild(tr);
  }
}

// One reusable mini-panel for the small-multiples plot — a single trace
// over the swept frequency range with its own auto-scaled y-axis.
function _drawMiniPanel(svg, NS, {x, y, w, h, fs, fmin, fmax, fspan,
                                  data, color, label}) {
  const COLOR_BORDER = "#2a323d";
  const COLOR_GRID = "#2a323d";
  const COLOR_LABEL = "#8b96a3";
  function el(tag, attrs, text) {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (text !== undefined) e.textContent = text;
    svg.appendChild(e);
    return e;
  }
  // Autoscale y from the data with a 5% padding above the max. If the
  // values are essentially constant, give the panel a finite ymin/ymax
  // span centred on the value so the line shows up.
  let ymin = Math.min(...data);
  let ymax = Math.max(...data);
  if (ymax - ymin < 1e-12) {
    const c = ymax || 1;
    ymin = c - Math.abs(c) * 0.05 - 1e-6;
    ymax = c + Math.abs(c) * 0.05 + 1e-6;
  } else {
    const pad = (ymax - ymin) * 0.08;
    ymin = Math.max(0, ymin - pad);
    ymax = ymax + pad;
  }
  const X = (f) => x + ((f - fmin) / fspan) * w;
  const Y = (v) => y + (1 - (v - ymin) / (ymax - ymin)) * h;

  // 3-tick y grid (min, mid, max).
  const yTicks = [ymin, (ymin + ymax) / 2, ymax];
  yTicks.forEach((t) => {
    const ty = Y(t);
    el("line", {
      x1: x, x2: x + w, y1: ty, y2: ty,
      stroke: COLOR_GRID, "stroke-dasharray": "2 3", opacity: "0.35",
    });
    el("text", {
      x: x - 6, y: ty + 3, "text-anchor": "end", fill: COLOR_LABEL,
    }, formatTick(t));
  });

  // Panel frame.
  el("rect", { x, y, width: w, height: h, fill: "none", stroke: COLOR_BORDER });

  // Trace.
  const pts = fs.map((f, i) => `${X(f)},${Y(data[i])}`).join(" ");
  el("polyline", {
    points: pts, fill: "none", stroke: color, "stroke-width": "1.6",
  });

  // Panel label (rotated, on the left margin).
  el("text", {
    x: x - 38, y: y + h / 2, "text-anchor": "middle", fill: color,
    transform: `rotate(-90, ${x - 38}, ${y + h / 2})`,
    style: "font-weight: 600;",
  }, label);
}

function formatTick(v) {
  if (!Number.isFinite(v)) return "";
  const a = Math.abs(v);
  if (a === 0) return "0";
  if (a >= 100) return v.toFixed(0);
  if (a >= 10)  return v.toFixed(1);
  if (a >= 1)   return v.toFixed(2);
  return v.toFixed(3);
}

function renderLrqSweepPlot(svg, d) {
  const NS = "http://www.w3.org/2000/svg";
  while (svg.firstChild) svg.removeChild(svg.firstChild);

  const W = 400, H = 360;
  const M = { top: 8, right: 16, bottom: 28, left: 56 };
  const gap = 14;
  const innerW = W - M.left - M.right;
  const innerH = H - M.top - M.bottom - 2 * gap;
  const panelH = innerH / 3;
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("preserveAspectRatio", "xMidYMid meet");

  const fs = d.freqs_ghz;
  if (!fs || fs.length < 2) return;
  const fmin = fs[0];
  const fmax = fs[fs.length - 1];
  const fspan = (fmax - fmin) || 1;

  const COLOR_LABEL = "#8b96a3";
  const COLOR_GRID = "#2a323d";

  const panels = [
    { data: d.L_nH,     color: "#5aa9ff", label: "L (nH)" },
    { data: d.R_ac_ohm, color: "#fbbf24", label: "R_ac (Ω)" },
    { data: d.Q,        color: "#4ade80", label: "Q" },
  ];
  panels.forEach((p, i) => {
    _drawMiniPanel(svg, NS, {
      x: M.left, y: M.top + i * (panelH + gap),
      w: innerW, h: panelH,
      fs, fmin, fmax, fspan,
      data: p.data, color: p.color, label: p.label,
    });
  });

  // Shared x-axis tick labels at the bottom of the last panel.
  const lastY = M.top + 2 * (panelH + gap) + panelH;
  const xTicks = 5;
  for (let i = 0; i < xTicks; i++) {
    const t = i / (xTicks - 1);
    const f = fmin + t * fspan;
    const x = M.left + t * innerW;
    // Tick line crossing all panel bottoms (just below the last panel).
    const tick = document.createElementNS(NS, "line");
    tick.setAttribute("x1", x); tick.setAttribute("x2", x);
    tick.setAttribute("y1", lastY); tick.setAttribute("y2", lastY + 4);
    tick.setAttribute("stroke", COLOR_GRID);
    svg.appendChild(tick);
    const lbl = document.createElementNS(NS, "text");
    lbl.setAttribute("x", x);
    lbl.setAttribute("y", lastY + 16);
    lbl.setAttribute("text-anchor", "middle");
    lbl.setAttribute("fill", COLOR_LABEL);
    lbl.textContent = f.toFixed(f >= 10 ? 0 : 1);
    svg.appendChild(lbl);
  }
  // X-axis title.
  const xLbl = document.createElementNS(NS, "text");
  xLbl.setAttribute("x", M.left + innerW / 2);
  xLbl.setAttribute("y", H - 4);
  xLbl.setAttribute("text-anchor", "middle");
  xLbl.setAttribute("fill", COLOR_LABEL);
  xLbl.textContent = "Frequency (GHz)";
  svg.appendChild(xLbl);
}

// Sweep results render as a real HTML table + an SVG line plot of
// |S11| / |S21| vs frequency. Both tabular and graphical views go into
// the same tab pane; the table populates the top half (scrollable) and
// the plot sits underneath.
function renderSweepTable(tableBody, d) {
  tableBody.innerHTML = "";
  for (let i = 0; i < d.freqs_ghz.length; i++) {
    const tr = document.createElement("tr");
    const cells = [
      d.freqs_ghz[i].toFixed(3),
      d.abs_S11[i].toFixed(4),
      d.abs_S21[i].toFixed(4),
      d.abs_S12[i].toFixed(4),
      d.abs_S22[i].toFixed(4),
    ];
    cells.forEach((v) => {
      const td = document.createElement("td");
      td.textContent = v;
      tr.appendChild(td);
    });
    tableBody.appendChild(tr);
  }
}

function renderSweepPlot(svg, d) {
  const NS = "http://www.w3.org/2000/svg";
  while (svg.firstChild) svg.removeChild(svg.firstChild);

  const W = 400, H = 220;
  const M = { top: 14, right: 16, bottom: 30, left: 46 };
  const innerW = W - M.left - M.right;
  const innerH = H - M.top - M.bottom;
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("preserveAspectRatio", "xMidYMid meet");

  const fs = d.freqs_ghz;
  if (!fs || fs.length < 2) return;
  const fmin = fs[0];
  const fmax = fs[fs.length - 1];
  const fspan = (fmax - fmin) || 1;

  // |Sij| is bounded by 1 for passive networks but rounding / extraction
  // can push it slightly over — let the y-axis stretch to fit.
  const ymax = Math.max(
    1.0,
    ...d.abs_S11, ...d.abs_S21, ...d.abs_S12, ...d.abs_S22,
  );

  const X = (f) => M.left + ((f - fmin) / fspan) * innerW;
  const Y = (v) => M.top + (1 - v / ymax) * innerH;

  const COLOR_BORDER = "#2a323d";
  const COLOR_GRID = "#2a323d";
  const COLOR_LABEL = "#8b96a3";
  const COLOR_S11 = "#5aa9ff";
  const COLOR_S21 = "#4ade80";
  const COLOR_WARN = "#fbbf24";

  function el(tag, attrs, text) {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (text !== undefined) e.textContent = text;
    svg.appendChild(e);
    return e;
  }

  // y-grid + ticks at 0, 0.25, 0.5, 0.75, 1.0
  [0, 0.25, 0.5, 0.75, 1.0].forEach((t) => {
    if (t > ymax) return;
    const y = Y(t);
    el("line", {
      x1: M.left, x2: W - M.right, y1: y, y2: y,
      stroke: COLOR_GRID, "stroke-dasharray": "2 3", opacity: "0.4",
    });
    el("text", {
      x: M.left - 6, y: y + 3, "text-anchor": "end", fill: COLOR_LABEL,
    }, t.toFixed(2));
  });

  // x-grid + ticks at 5 evenly spaced frequencies
  const xTicks = 5;
  for (let i = 0; i < xTicks; i++) {
    const t = i / (xTicks - 1);
    const f = fmin + t * fspan;
    const x = X(f);
    el("line", {
      x1: x, x2: x, y1: M.top, y2: H - M.bottom,
      stroke: COLOR_GRID, "stroke-dasharray": "2 3", opacity: "0.3",
    });
    el("text", {
      x, y: H - M.bottom + 14, "text-anchor": "middle", fill: COLOR_LABEL,
    }, f.toFixed(f >= 10 ? 0 : 1));
  }

  // Plot frame on top of the grid.
  el("rect", {
    x: M.left, y: M.top, width: innerW, height: innerH,
    fill: "none", stroke: COLOR_BORDER,
  });

  // Axis labels.
  el("text", {
    x: M.left + innerW / 2, y: H - 4, "text-anchor": "middle", fill: COLOR_LABEL,
  }, "Frequency (GHz)");
  el("text", {
    x: 10, y: M.top + innerH / 2, "text-anchor": "middle", fill: COLOR_LABEL,
    transform: `rotate(-90, 10, ${M.top + innerH / 2})`,
  }, "|S|");

  // Self-resonance marker (if present and inside the swept band).
  if (d.self_resonance_ghz && d.self_resonance_ghz >= fmin && d.self_resonance_ghz <= fmax) {
    const xr = X(d.self_resonance_ghz);
    el("line", {
      x1: xr, x2: xr, y1: M.top, y2: H - M.bottom,
      stroke: COLOR_WARN, "stroke-dasharray": "3 3",
    });
    el("text", {
      x: xr + 4, y: M.top + 10, fill: COLOR_WARN,
    }, `SRF ≈ ${d.self_resonance_ghz.toFixed(2)} GHz`);
  }

  // Trace polylines.
  const traces = [
    { color: COLOR_S11, data: d.abs_S11, label: "|S11|" },
    { color: COLOR_S21, data: d.abs_S21, label: "|S21|" },
  ];
  traces.forEach(({ color, data }) => {
    const pts = fs.map((f, i) => `${X(f)},${Y(data[i])}`).join(" ");
    el("polyline", {
      points: pts, fill: "none", stroke: color, "stroke-width": "1.6",
    });
  });

  // Legend in the top-right interior corner.
  traces.forEach((t, i) => {
    const lx = W - M.right - 78;
    const ly = M.top + 12 + i * 14;
    el("line", { x1: lx, y1: ly, x2: lx + 18, y2: ly, stroke: t.color, "stroke-width": "2" });
    el("text", { x: lx + 23, y: ly + 3, fill: "#d8e0e8" }, t.label);
  });
}

// Snapshot the current values of every analysis input. A tab freezes its
// params at spawn time so live-update reruns use the *original* frequency
// / sweep range, even if the user edits those inputs after spawning.
function captureAnalysisParams(action) {
  if (action === "sweep" || action === "s2p" || action === "lrq_sweep") {
    return {
      f1: parseFloat(ui.swF1.value),
      f2: parseFloat(ui.swF2.value),
      step: parseFloat(ui.swStep.value),
    };
  }
  if (action === "info") {
    return {};
  }
  return { freq: parseFloat(ui.freq.value) };
}

// Build the human-readable label shown on the tab chip.
function labelForAction(action, params) {
  switch (action) {
    case "lrq":       return `L·R·Q · ${fmtFloat(params.freq, 3)} GHz`;
    case "pi":        return `Pi · ${fmtFloat(params.freq, 3)} GHz`;
    case "sweep":     return `S-sweep · ${params.f1}–${params.f2}/${params.step} GHz`;
    case "lrq_sweep": return `L·R·Q sweep · ${params.f1}–${params.f2}/${params.step} GHz`;
    case "s2p":       return `.s2p · ${params.f1}–${params.f2}/${params.step} GHz`;
    case "spice":     return `SPICE · ${fmtFloat(params.freq, 3)} GHz`;
    case "info":      return `Geom info`;
    default:          return action;
  }
}

// Execute one analysis against the *current* shape, render into the
// tab's pane, and clear the stale marker. Sweep tabs use a table + SVG
// plot; the others use the pre-formatted <pre> renderer.
async function runAnalysisIntoTab(reg) {
  const { action, params, paneEl } = reg;
  const stale = paneEl.querySelector(".live-stale");
  const out = paneEl.querySelector(".analysis-out");
  if (out) out.classList.remove("error");
  try {
    if (action === "lrq") {
      const r = await py.analyze_lrq(params.freq);
      out.textContent = fmtLrq(r);
    } else if (action === "pi") {
      const r = await py.analyze_pi(params.freq);
      out.textContent = fmtPi(r);
    } else if (action === "sweep") {
      const r = await py.analyze_sweep(params.f1, params.f2, params.step);
      renderSweepTable(paneEl.querySelector(".sweep-table tbody"), r);
      renderSweepPlot(paneEl.querySelector(".sweep-plot"), r);
      const res = paneEl.querySelector(".sweep-resonance");
      if (res) {
        res.textContent = r.self_resonance_ghz
          ? `Self-resonance ≈ ${fmtFloat(r.self_resonance_ghz, 3)} GHz`
          : "";
      }
    } else if (action === "lrq_sweep") {
      const r = await py.analyze_lrq_sweep(params.f1, params.f2, params.step);
      renderLrqSweepTable(paneEl.querySelector(".sweep-table tbody"), r);
      renderLrqSweepPlot(paneEl.querySelector(".sweep-plot"), r);
    } else if (action === "s2p") {
      const text = await py.export_s2p(params.f1, params.f2, params.step);
      out.textContent = text;
      // Only auto-download on the initial click; re-runs from live update
      // just refresh the in-tab preview to avoid spamming downloads.
      if (!reg.hasRunOnce) downloadText("L1_sweep.s2p", text);
    } else if (action === "spice") {
      const text = await py.export_spice(params.freq);
      out.textContent = text;
      if (!reg.hasRunOnce) downloadText("L1_pi.cir", text);
    } else if (action === "info") {
      const r = await py.geom_info();
      out.textContent = JSON.stringify(r, null, 2);
    }
    reg.hasRunOnce = true;
    if (stale) stale.textContent = "";
  } catch (err) {
    if (out) {
      out.textContent = `${action} failed:\n${err.message || err}`;
      out.classList.add("error");
    } else {
      // Sweep tab: surface the error in the resonance row.
      const res = paneEl.querySelector(".sweep-resonance");
      if (res) {
        res.style.color = "var(--bad)";
        res.textContent = `${action} failed: ${err.message || err}`;
      }
    }
  }
}

function setActiveTab(id) {
  document.querySelectorAll("#output-tabs .tab").forEach((t) => {
    t.classList.toggle("active", t.dataset.tab === id);
  });
  document.querySelectorAll(".tab-pane").forEach((p) => {
    p.classList.toggle("active", p.dataset.pane === id);
  });
}

function closeAnalysisTab(id) {
  const reg = ANALYSIS_TABS.get(id);
  if (!reg) return;
  const wasActive = reg.tabEl.classList.contains("active");
  reg.tabEl.remove();
  reg.paneEl.remove();
  ANALYSIS_TABS.delete(id);
  if (wasActive) setActiveTab("results");
}

// Spawn a new analysis tab + pane and switch to it. The new tab starts
// with ``Live update`` enabled so the user can iterate on geometry and
// see numbers refresh without re-clicking the analysis button.
async function spawnAnalysisTab(action) {
  const params = captureAnalysisParams(action);
  analysisCounter += 1;
  const id = `${action}-${analysisCounter}`;
  const label = labelForAction(action, params);

  const tabBtn = document.createElement("button");
  tabBtn.className = "tab";
  tabBtn.dataset.tab = id;
  tabBtn.innerHTML = `<span class="tab-label"></span><span class="tab-close" title="Close">×</span>`;
  tabBtn.querySelector(".tab-label").textContent = label;
  ui.outputTabs.appendChild(tabBtn);

  const pane = document.createElement("div");
  pane.className = "tab-pane";
  pane.dataset.pane = id;
  const headHtml = `
    <div class="analysis-head">
      <span class="analysis-title"></span>
      <label class="live-toggle">
        <input type="checkbox" checked />
        Live update
      </label>
      <button type="button" class="live-rerun">Run now</button>
      <span class="live-stale"></span>
    </div>
  `;
  if (action === "sweep") {
    pane.innerHTML = `${headHtml}
      <div class="sweep-body">
        <div class="sweep-table-wrap">
          <table class="sweep-table">
            <thead>
              <tr>
                <th>f (GHz)</th>
                <th>|S<sub>11</sub>|</th>
                <th>|S<sub>21</sub>|</th>
                <th>|S<sub>12</sub>|</th>
                <th>|S<sub>22</sub>|</th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>
        <div class="sweep-resonance"></div>
        <svg class="sweep-plot" viewBox="0 0 400 220" preserveAspectRatio="xMidYMid meet"></svg>
      </div>`;
  } else if (action === "lrq_sweep") {
    pane.innerHTML = `${headHtml}
      <div class="sweep-body">
        <div class="sweep-table-wrap">
          <table class="sweep-table">
            <thead>
              <tr>
                <th>f (GHz)</th>
                <th>L (nH)</th>
                <th>R<sub>dc</sub> (Ω)</th>
                <th>R<sub>ac</sub> (Ω)</th>
                <th>Q</th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>
        <svg class="sweep-plot lrq-sweep-plot" viewBox="0 0 400 360" preserveAspectRatio="xMidYMid meet"></svg>
      </div>`;
  } else {
    pane.innerHTML = `${headHtml}<pre class="analysis-out"></pre>`;
  }
  pane.querySelector(".analysis-title").textContent = label;
  ui.outputPanel.appendChild(pane);

  const reg = {
    id, action, params, label,
    tabEl: tabBtn,
    paneEl: pane,
    liveUpdate: true,
    hasRunOnce: false,
  };
  ANALYSIS_TABS.set(id, reg);

  // Per-tab event wiring.
  tabBtn.addEventListener("click", (e) => {
    if (e.target.closest(".tab-close")) {
      e.stopPropagation();
      closeAnalysisTab(id);
    } else {
      setActiveTab(id);
    }
  });
  pane.querySelector(".live-toggle input").addEventListener("change", (e) => {
    reg.liveUpdate = e.target.checked;
    const stale = pane.querySelector(".live-stale");
    if (reg.liveUpdate && reg.staleSinceLastRun) {
      runAnalysisIntoTab(reg).then(() => {
        reg.staleSinceLastRun = false;
        stale.textContent = "";
      });
    }
  });
  pane.querySelector(".live-rerun").addEventListener("click", async () => {
    setStatus(`Running: ${action}…`, "busy");
    await runAnalysisIntoTab(reg);
    reg.staleSinceLastRun = false;
    setStatus("Done.", "ready");
  });

  setActiveTab(id);
  setStatus(`Running: ${action}…`, "busy");
  await runAnalysisIntoTab(reg);
  setStatus("Done.", "ready");
  return reg;
}

// Called after every successful buildShape(). Walks every analysis tab
// and, for those with live update on, re-runs against the new shape.
// Tabs with live update off get a "stale" marker so the user knows the
// numbers no longer reflect the visible geometry.
async function refreshAnalysisTabs() {
  if (!bridgeReady) return;
  for (const reg of ANALYSIS_TABS.values()) {
    if (reg.liveUpdate) {
      await runAnalysisIntoTab(reg);
      reg.staleSinceLastRun = false;
    } else {
      reg.staleSinceLastRun = true;
      const stale = reg.paneEl.querySelector(".live-stale");
      if (stale) stale.textContent = "(stale)";
    }
  }
}

// Compat wrapper for the analysis buttons in the params panel.
async function runAction(name) {
  if (!bridgeReady) return;
  try {
    await spawnAnalysisTab(name);
  } catch (err) {
    setStatus("Action failed.", "error");
    showResult(`${name} failed:\n${err.message || err}`, "error");
  }
}

async function runRepl() {
  if (!bridgeReady) return;
  setStatus("Running cell…", "busy");
  try {
    const r = await py.run_repl(ui.code.value);
    const stamp = new Date().toLocaleTimeString();
    let chunk = `>>> ${stamp}\n`;
    if (r.stdout) chunk += r.stdout;
    if (r.stderr) chunk += r.stderr;
    if (!r.stdout && !r.stderr && r.ok) chunk += "(no output)\n";
    ui.replOut.textContent = chunk + (ui.replOut.textContent ? "\n" + ui.replOut.textContent : "");
    setStatus(r.ok ? "REPL ok." : "REPL raised.", r.ok ? "ready" : "error");
    // The user may have rebuilt the shape — refresh the canvas if so.
    const payload = await py.current_shape_payload();
    if (payload) {
      Draw.render(ui.canvas, payload, ui.legend, ui.dims);
    }
  } catch (err) {
    setStatus("REPL crashed.", "error");
    ui.replOut.textContent = `${err.message || err}\n` + ui.replOut.textContent;
  }
}

function wireEvents() {
  ui.techSelect.addEventListener("change", async () => {
    setEnabled(false);
    try {
      await loadTechFile(ui.techSelect.value);
      await buildShape();
    } finally {
      setEnabled(true);
    }
  });

  ui.shapeSelect.addEventListener("change", () => {
    applyShapeVisibility();
    buildShape();
  });

  [
    ui.metalSelect, ui.exitMetalSelect, ui.mmsqExitSelect,
    ui.metalBalunPrimarySelect, ui.metalBalunTransitionSelect,
    ui.metalCapTopSelect, ui.metalCapBottomSelect,
    ui.viaSelect, ui.name, ui.pname, ui.sname,
    ui.length, ui.wid, ui.ilenSq, ui.iwidSq,
    ui.radius, ui.widPoly,
    ui.ringRadius, ui.wireLength, ui.wireWidth,
    ui.capLength, ui.capWidth,
    ui.width, ui.balunW1, ui.balunW2,
    ui.spacing, ui.ilen, ui.iwid, ui.turns, ui.sides, ui.gap,
    ui.nvx, ui.nvy,
    ui.xorg, ui.yorg, ui.orient, ui.phase, ui.viaPhase,
  ].filter(Boolean).forEach((el) => {
    el.addEventListener("change", buildShape);
  });

  ui.build.addEventListener("click", buildShape);

  ui.actions.forEach((b) =>
    b.addEventListener("click", () => runAction(b.dataset.action))
  );

  ui.run.addEventListener("click", runRepl);
  ui.clear.addEventListener("click", () => (ui.replOut.textContent = ""));
  ui.code.addEventListener("keydown", (ev) => {
    if (ev.ctrlKey && ev.key === "Enter") {
      ev.preventDefault();
      runRepl();
    }
  });

  // Delegated handler — handles both the static (Results / Python REPL)
  // tabs and any dynamic analysis tabs added later.
  ui.outputTabs.addEventListener("click", (ev) => {
    const tab = ev.target.closest(".tab");
    if (!tab) return;
    if (ev.target.closest(".tab-close")) return;  // closed in the dynamic handler
    setActiveTab(tab.dataset.tab);
  });

  // Resizable output panel: drag the left-edge handle horizontally.
  wireOutputResizer();
}

// Drag-to-resize the right-hand output panel. The grid uses a CSS var
// (--output-width) for its third column; we update it live during drag
// and persist the chosen width to localStorage so subsequent loads keep
// the user's layout.
function wireOutputResizer() {
  const STORAGE_KEY = "reasitic_repl_output_width";
  const main = document.querySelector("main");
  const root = document.documentElement;
  const stored = parseFloat(localStorage.getItem(STORAGE_KEY) || "");
  if (Number.isFinite(stored) && stored >= 220) {
    main.style.setProperty("--output-width", `${stored}px`);
  }

  let dragging = false;
  let startX = 0;
  let startW = 0;

  ui.outputResizer.addEventListener("mousedown", (ev) => {
    dragging = true;
    startX = ev.clientX;
    const css = getComputedStyle(main).getPropertyValue("--output-width").trim();
    startW = parseFloat(css) || 380;
    document.body.classList.add("dragging-resizer");
    ui.outputResizer.classList.add("dragging");
    ev.preventDefault();
  });

  document.addEventListener("mousemove", (ev) => {
    if (!dragging) return;
    // Dragging the handle left widens the output panel; right shrinks it.
    const dx = startX - ev.clientX;
    const maxW = Math.max(320, window.innerWidth - 360 - 320);
    const newW = Math.max(220, Math.min(maxW, startW + dx));
    main.style.setProperty("--output-width", `${newW}px`);
  });

  document.addEventListener("mouseup", () => {
    if (!dragging) return;
    dragging = false;
    document.body.classList.remove("dragging-resizer");
    ui.outputResizer.classList.remove("dragging");
    const finalW = getComputedStyle(main).getPropertyValue("--output-width").trim();
    const finalPx = parseFloat(finalW);
    if (Number.isFinite(finalPx)) {
      localStorage.setItem(STORAGE_KEY, String(finalPx));
    }
  });

  // Double-click to reset to the default width.
  ui.outputResizer.addEventListener("dblclick", () => {
    main.style.removeProperty("--output-width");
    localStorage.removeItem(STORAGE_KEY);
  });
}

wireEvents();
bootPyodide().catch((err) => {
  setStatus("Boot failed.", "error");
  showResult(`Boot failed:\n${err.message || err}`, "error");
});
