// reASITIC REPL — Pyodide bridge and UI wiring.

const $ = (id) => document.getElementById(id);
const statusEl = $("status");
const resultsEl = $("results");
const versionEl = $("version");

const ui = {
  techSelect: $("tech-select"),
  shapeSelect: $("shape-select"),
  metalSelect: $("metal-select"),
  length: $("p-length"),
  width: $("p-width"),
  spacing: $("p-spacing"),
  turns: $("p-turns"),
  sides: $("p-sides"),
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
  return {
    kind: ui.shapeSelect.value,
    name: "L1",
    metal: ui.metalSelect.value,
    length: parseFloat(ui.length.value),
    width: parseFloat(ui.width.value),
    spacing: parseFloat(ui.spacing.value),
    turns: parseFloat(ui.turns.value),
    sides: parseInt(ui.sides.value, 10),
  };
}

function applyShapeVisibility() {
  const kind = ui.shapeSelect.value;
  document.querySelectorAll("[data-only]").forEach((el) => {
    const allowed = el.dataset.only.split(/\s+/);
    el.style.display = allowed.includes(kind) ? "" : "none";
  });
  // For polygon spiral / wire, "Length" is conceptually different — relabel.
  const lengthLabel = ui.length.parentElement;
  if (kind === "polygon_spiral") {
    lengthLabel.firstChild.nodeValue = "Outer radius (μm)";
  } else if (kind === "wire") {
    lengthLabel.firstChild.nodeValue = "Length (μm)";
  } else if (kind === "symmetric_square") {
    lengthLabel.firstChild.nodeValue = "Outer length (μm)";
  } else {
    lengthLabel.firstChild.nodeValue = "Length / radius (μm)";
  }
}

function populateMetals(metals) {
  ui.metalSelect.innerHTML = "";
  metals.forEach((m) => {
    const opt = document.createElement("option");
    opt.value = m.name || String(m.index);
    opt.textContent = `${m.name || ("m" + m.index)}  (idx ${m.index}, t=${m.t}μm)`;
    ui.metalSelect.appendChild(opt);
  });
  // Default to top metal (best Q in a typical stack).
  ui.metalSelect.value = ui.metalSelect.options[ui.metalSelect.options.length - 1].value;
}

async function loadTechFile(filename) {
  const resp = await fetch(filename, { cache: "no-cache" });
  if (!resp.ok) throw new Error(`Failed to fetch ${filename}: ${resp.status}`);
  const text = await resp.text();
  const info = pyodide.globals.get("load_tech")(text).toJs({ dict_converter: Object.fromEntries });
  populateMetals(info.metals);
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

  [ui.metalSelect, ui.length, ui.width, ui.spacing, ui.turns, ui.sides].forEach((el) => {
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
