// Inductor geometry rendering on an SVG canvas.
//
// The Python side dumps shape geometry as a small JSON-friendly object:
//   {
//     name, bbox: [xmin, ymin, xmax, ymax],
//     polygons: [
//       { metal: <int>, width, thickness,
//         points: [[x, y, z], ...],
//         color: "#rrggbb",   // metal color (mapped from tech)
//         metal_name: "m3",
//       }, ...
//     ],
//     metals: [{ index, name, color }, ...],   // legend
//     ports: [{ x, y }, ...]                   // optional terminal markers
//   }
(function (global) {
  const SVG_NS = "http://www.w3.org/2000/svg";
  const PALETTE = {
    red: "#ef4444", green: "#22c55e", blue: "#60a5fa",
    yellow: "#facc15", white: "#e5e7eb", black: "#1f2937",
    purple: "#a78bfa", orange: "#fb923c", greenish: "#34d399",
    cyan: "#22d3ee", magenta: "#e879f9", grey: "#9ca3af", gray: "#9ca3af",
  };
  const FALLBACK_COLORS = ["#5aa9ff", "#22c55e", "#facc15", "#a78bfa", "#fb923c", "#34d399"];

  function colorFor(metalColor, fallbackIdx) {
    if (!metalColor) return FALLBACK_COLORS[fallbackIdx % FALLBACK_COLORS.length];
    const lower = String(metalColor).trim().toLowerCase();
    if (lower.startsWith("#")) return metalColor;
    return PALETTE[lower] || FALLBACK_COLORS[fallbackIdx % FALLBACK_COLORS.length];
  }

  function clear(svg) {
    while (svg.firstChild) svg.removeChild(svg.firstChild);
  }

  function setViewBox(svg, bbox) {
    const [x0, y0, x1, y1] = bbox;
    let dx = x1 - x0, dy = y1 - y0;
    if (dx <= 0) dx = 1;
    if (dy <= 0) dy = 1;
    const pad = Math.max(dx, dy) * 0.12 + 2;
    // SVG y grows downwards — flip with negative height to keep math-like axes.
    const minX = x0 - pad;
    const minY = -(y1 + pad);
    const w = dx + 2 * pad;
    const h = dy + 2 * pad;
    svg.setAttribute("viewBox", `${minX} ${minY} ${w} ${h}`);
  }

  function drawAxes(svg, bbox) {
    const [x0, y0, x1, y1] = bbox;
    const g = document.createElementNS(SVG_NS, "g");
    g.setAttribute("class", "axes");

    // Bounding box rectangle
    const rect = document.createElementNS(SVG_NS, "rect");
    rect.setAttribute("x", x0);
    rect.setAttribute("y", -y1);
    rect.setAttribute("width", Math.max(x1 - x0, 0.001));
    rect.setAttribute("height", Math.max(y1 - y0, 0.001));
    rect.setAttribute("class", "shape-bbox");
    g.appendChild(rect);

    // Centerlines if origin is inside the bbox
    if (x0 <= 0 && x1 >= 0) {
      const v = document.createElementNS(SVG_NS, "line");
      v.setAttribute("x1", 0); v.setAttribute("y1", -y1);
      v.setAttribute("x2", 0); v.setAttribute("y2", -y0);
      v.setAttribute("class", "axis");
      g.appendChild(v);
    }
    if (y0 <= 0 && y1 >= 0) {
      const h = document.createElementNS(SVG_NS, "line");
      h.setAttribute("x1", x0); h.setAttribute("y1", 0);
      h.setAttribute("x2", x1); h.setAttribute("y2", 0);
      h.setAttribute("class", "axis");
      g.appendChild(h);
    }

    // Scale label
    const w = x1 - x0;
    const lbl = document.createElementNS(SVG_NS, "text");
    lbl.setAttribute("x", x0);
    lbl.setAttribute("y", -y0 + Math.max(w, 1) * 0.05);
    lbl.setAttribute("class", "axis-label");
    lbl.textContent = `${w.toFixed(1)} μm × ${(y1 - y0).toFixed(1)} μm`;
    g.appendChild(lbl);

    svg.appendChild(g);
  }

  function drawPolygons(svg, payload) {
    const { polygons } = payload;
    const refStroke = Math.max(
      0.5,
      (payload.bbox[2] - payload.bbox[0]) * 0.0025
    );

    polygons.forEach((poly, idx) => {
      if (!poly.points || poly.points.length < 2) return;
      const color = colorFor(poly.color, idx);
      const w = Math.max(poly.width || refStroke, refStroke);
      const path = document.createElementNS(SVG_NS, "polyline");
      const ptStr = poly.points
        .map(([x, y]) => `${x.toFixed(3)},${(-y).toFixed(3)}`)
        .join(" ");
      path.setAttribute("points", ptStr);
      path.setAttribute("class", "shape-edge");
      path.setAttribute("stroke", color);
      path.setAttribute("stroke-width", w);
      path.setAttribute("stroke-opacity", "0.85");
      svg.appendChild(path);
    });

    // Terminal markers
    if (Array.isArray(payload.ports)) {
      payload.ports.forEach((p) => {
        const c = document.createElementNS(SVG_NS, "circle");
        c.setAttribute("cx", p.x);
        c.setAttribute("cy", -p.y);
        c.setAttribute("r", refStroke * 1.6);
        c.setAttribute("class", "shape-port");
        svg.appendChild(c);
      });
    }
  }

  function renderLegend(legendEl, payload) {
    legendEl.innerHTML = "";
    const seen = new Set();
    payload.polygons.forEach((p, i) => {
      const key = p.metal_name || ("m" + p.metal);
      if (seen.has(key)) return;
      seen.add(key);
      const span = document.createElement("span");
      span.innerHTML = `<span class="swatch" style="background:${colorFor(p.color, i)}"></span>${key}`;
      legendEl.appendChild(span);
    });
  }

  function render(svg, payload, legendEl, dimsEl) {
    clear(svg);
    setViewBox(svg, payload.bbox);
    drawAxes(svg, payload.bbox);
    drawPolygons(svg, payload);
    if (legendEl) renderLegend(legendEl, payload);
    if (dimsEl) {
      const [x0, y0, x1, y1] = payload.bbox;
      const segs = payload.polygons.reduce(
        (n, p) => n + Math.max(0, (p.points || []).length - 1),
        0
      );
      dimsEl.textContent =
        `${payload.name}  |  bbox ${(x1 - x0).toFixed(1)}×${(y1 - y0).toFixed(1)} μm  |  ` +
        `${payload.polygons.length} polygon(s), ${segs} segment(s)`;
    }
  }

  global.Draw = { render };
})(window);
