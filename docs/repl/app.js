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
  tabs: document.querySelectorAll(".tab"),
};

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

let pyodide = null;
let bridgeReady = false;

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
  const info = pyodide.globals.get("load_tech")(text).toJs({ dict_converter: Object.fromEntries });
  populateMetals(info.metals);
  populateVias(info.vias || []);
  setStatus(`Loaded ${filename} — ${info.metals.length} metals, ${info.n_layers} layers, ${info.n_vias} vias.`, "ready");
}

async function bootPyodide() {
  setStatus("Loading Pyodide runtime…", "busy");
  pyodide = await loadPyodide({
    indexURL: "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/",
  });

  setStatus("Loading numpy + scipy (~25 MB)…", "busy");
  await pyodide.loadPackage(["numpy", "scipy", "micropip"]);

  setStatus("Installing reASITIC wheel…", "busy");
  const micropip = pyodide.pyimport("micropip");
  const wheelUrl = new URL("wheels/reasitic-0.0.1-py3-none-any.whl", window.location.href).href;
  await micropip.install(wheelUrl);

  setStatus("Wiring REPL bridge…", "busy");
  const bridgeSrc = await (await fetch("bridge.py", { cache: "no-cache" })).text();
  pyodide.runPython(bridgeSrc);

  bridgeReady = true;
  const v = pyodide.globals.get("version_info")();
  versionEl.textContent = v;

  await loadTechFile(ui.techSelect.value);

  setEnabled(true);
  applyShapeVisibility();
  // Auto-build the default geometry so the page lands with something visible.
  await buildShape();
  setStatus("Ready.", "ready");
  showResult(
    "Ready. Adjust the geometry and press “Build inductor”, then use the analysis buttons.\n" +
    "Switch to the Python REPL tab to script against the live `shape` and `tech` objects.",
    "ok"
  );
}

async function buildShape() {
  if (!bridgeReady) return;
  setStatus("Building geometry…", "busy");
  try {
    const spec = getSpec();
    const payload = pyodide.globals
      .get("build_shape")(pyodide.toPy(spec))
      .toJs({ dict_converter: Object.fromEntries });
    Draw.render(ui.canvas, payload, ui.legend, ui.dims);
    setStatus(
      `Built ${payload.name}: ${payload.polygons.length} polygon(s), turns=${payload.turns}.`,
      "ready"
    );
  } catch (err) {
    setStatus("Build failed.", "error");
    showResult(`Build failed:\n${err.message || err}`, "error");
  }
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

function fmtSweep(d) {
  const rows = ["       f (GHz)     |S11|     |S21|     |S12|     |S22|"];
  for (let i = 0; i < d.freqs_ghz.length; i++) {
    rows.push(
      [
        d.freqs_ghz[i].toFixed(3).padStart(14),
        d.abs_S11[i].toFixed(4).padStart(9),
        d.abs_S21[i].toFixed(4).padStart(9),
        d.abs_S12[i].toFixed(4).padStart(9),
        d.abs_S22[i].toFixed(4).padStart(9),
      ].join("")
    );
  }
  if (d.self_resonance_ghz) {
    rows.push("");
    rows.push(`Self-resonance ≈ ${fmtFloat(d.self_resonance_ghz, 3)} GHz`);
  }
  return rows.join("\n");
}

async function runAction(name) {
  if (!bridgeReady) return;
  setStatus(`Running: ${name}…`, "busy");
  try {
    const f = parseFloat(ui.freq.value);
    if (name === "lrq") {
      const r = pyodide.globals.get("analyze_lrq")(f).toJs({ dict_converter: Object.fromEntries });
      showResult(fmtLrq(r), "ok");
    } else if (name === "pi") {
      const r = pyodide.globals.get("analyze_pi")(f).toJs({ dict_converter: Object.fromEntries });
      showResult(fmtPi(r), "ok");
    } else if (name === "sweep") {
      const f1 = parseFloat(ui.swF1.value);
      const f2 = parseFloat(ui.swF2.value);
      const stp = parseFloat(ui.swStep.value);
      const r = pyodide.globals.get("analyze_sweep")(f1, f2, stp)
        .toJs({ dict_converter: Object.fromEntries });
      showResult(fmtSweep(r), "ok");
    } else if (name === "s2p") {
      const f1 = parseFloat(ui.swF1.value);
      const f2 = parseFloat(ui.swF2.value);
      const stp = parseFloat(ui.swStep.value);
      const text = pyodide.globals.get("export_s2p")(f1, f2, stp);
      downloadText("L1_sweep.s2p", text);
      showResult(text, "ok");
    } else if (name === "spice") {
      const text = pyodide.globals.get("export_spice")(f);
      downloadText("L1_pi.cir", text);
      showResult(text, "ok");
    } else if (name === "info") {
      const r = pyodide.globals.get("geom_info")().toJs({ dict_converter: Object.fromEntries });
      showResult(JSON.stringify(r, null, 2), "ok");
    }
    setStatus("Done.", "ready");
  } catch (err) {
    setStatus("Action failed.", "error");
    showResult(`${name} failed:\n${err.message || err}`, "error");
  }
}

async function runRepl() {
  if (!bridgeReady) return;
  setStatus("Running cell…", "busy");
  try {
    const r = pyodide.globals
      .get("run_repl")(ui.code.value)
      .toJs({ dict_converter: Object.fromEntries });
    const stamp = new Date().toLocaleTimeString();
    let chunk = `>>> ${stamp}\n`;
    if (r.stdout) chunk += r.stdout;
    if (r.stderr) chunk += r.stderr;
    if (!r.stdout && !r.stderr && r.ok) chunk += "(no output)\n";
    ui.replOut.textContent = chunk + (ui.replOut.textContent ? "\n" + ui.replOut.textContent : "");
    setStatus(r.ok ? "REPL ok." : "REPL raised.", r.ok ? "ready" : "error");
    // The user may have rebuilt the shape — refresh the canvas if so.
    const payload = pyodide.globals.get("current_shape_payload")();
    if (payload && payload.toJs) {
      Draw.render(
        ui.canvas,
        payload.toJs({ dict_converter: Object.fromEntries }),
        ui.legend,
        ui.dims
      );
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

  ui.tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      ui.tabs.forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      document.querySelectorAll(".tab-pane").forEach((p) => p.classList.remove("active"));
      document.querySelector(`.tab-pane[data-pane="${tab.dataset.tab}"]`).classList.add("active");
    });
  });
}

wireEvents();
bootPyodide().catch((err) => {
  setStatus("Boot failed.", "error");
  showResult(`Boot failed:\n${err.message || err}`, "error");
});
