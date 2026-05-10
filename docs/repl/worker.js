// Pyodide runtime hosted inside a Web Worker so the main thread stays
// responsive — and, more importantly, so long-running Python calls can
// be terminated when they overrun the per-call timeout enforced by
// app.js. Each message from the main thread is a request of the form
//
//     {id, type: "boot" | "call", fn?, args?}
//
// and we always reply with
//
//     {id, ok: bool, result?, error?}
//
// matched by id. ``fn`` for ``call`` is a Python global from bridge.py.

let pyodide = null;
let ready = false;

self.onmessage = async (ev) => {
  const { id, type } = ev.data;
  try {
    if (type === "boot") {
      await boot();
      self.postMessage({ id, ok: true });
      return;
    }
    if (type === "call") {
      if (!ready) throw new Error("worker not ready");
      const result = dispatch(ev.data.fn, ev.data.args || []);
      self.postMessage({ id, ok: true, result });
      return;
    }
    throw new Error(`unknown worker message type: ${type}`);
  } catch (err) {
    self.postMessage({ id, ok: false, error: err && err.message ? err.message : String(err) });
  }
};

async function boot() {
  importScripts("https://cdn.jsdelivr.net/pyodide/v0.27.7/full/pyodide.js");
  pyodide = await loadPyodide({
    indexURL: "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/",
  });
  await pyodide.loadPackage(["numpy", "scipy", "micropip"]);
  const micropip = pyodide.pyimport("micropip");
  const wheelUrl = new URL(
    "wheels/reasitic-0.0.1-py3-none-any.whl",
    self.location.href,
  ).href;
  await micropip.install(wheelUrl);
  const bridgeSrc = await (await fetch("bridge.py", { cache: "no-cache" })).text();
  pyodide.runPython(bridgeSrc);
  ready = true;
}

// Convert each arg the way the JS bridge used to: dict/array via toPy,
// primitives passed straight through. Then convert any PyProxy result via
// toJs with ``Object.fromEntries`` so the main thread receives plain
// objects rather than Map instances.
function dispatch(fn, args) {
  const pyFn = pyodide.globals.get(fn);
  if (!pyFn) throw new Error(`no Python function: ${fn}`);
  const pyArgs = args.map((a) => {
    if (a !== null && typeof a === "object") return pyodide.toPy(a);
    return a;
  });
  let result;
  try {
    result = pyFn(...pyArgs);
  } finally {
    pyFn.destroy && pyFn.destroy();
    pyArgs.forEach((a) => a && typeof a.destroy === "function" && a.destroy());
  }
  if (result && typeof result.toJs === "function") {
    const js = result.toJs({ dict_converter: Object.fromEntries });
    result.destroy && result.destroy();
    return js;
  }
  return result;
}
