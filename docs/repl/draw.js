// Inductor geometry rendering on an SVG canvas.
//
// Ground truth: in the original ASITIC, each segment of a spiral side is a
// 4-corner *quadrilateral* (offset ±w/2 perpendicular to the centerline) that
// the X11 backend draws via XFillPolygon. We mirror that here: the JS payload
// gives us a centerline polyline + width per polygon, and for each segment we
// emit one filled SVG polygon shaped like the fat trace. Adjacent rectangles
// overlap at corners, which produces the natural mitered look you see in the
// ASITIC GUI.
//
// Payload from bridge.py:
//   {
//     name, bbox: [xmin, ymin, xmax, ymax],
//     polygons: [
//       { metal, metal_name, color, width, thickness,
//         points: [[x, y, z], ...]   // centerline polyline
//       }, ...
//     ],
//     ports: [{ x, y }, ...]
//   }
(function (global) {
  const SVG_NS = "http://www.w3.org/2000/svg";

  // Mapping of ASITIC tech-file color names → CSS colors.
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

  // Lighten/darken a hex color for stroke and fill differentiation.
  function shade(hex, amount) {
    const m = /^#([0-9a-f]{6})$/i.exec(hex);
    if (!m) return hex;
    const n = parseInt(m[1], 16);
    let r = (n >> 16) & 0xff;
    let g = (n >> 8) & 0xff;
    let b = n & 0xff;
    if (amount > 0) {
      r = Math.round(r + (255 - r) * amount);
      g = Math.round(g + (255 - g) * amount);
      b = Math.round(b + (255 - b) * amount);
    } else {
      const k = 1 + amount;
      r = Math.round(r * k); g = Math.round(g * k); b = Math.round(b * k);
    }
    return "#" + [r, g, b].map((v) => Math.max(0, Math.min(255, v)).toString(16).padStart(2, "0")).join("");
  }

  function clear(svg) {
    while (svg.firstChild) svg.removeChild(svg.firstChild);
  }

  function setViewBox(svg, bbox) {
    const [x0, y0, x1, y1] = bbox;
    let dx = x1 - x0, dy = y1 - y0;
    if (dx <= 0) dx = 1;
    if (dy <= 0) dy = 1;
    const span = Math.max(dx, dy);
    const pad = span * 0.12 + 2;
    // SVG y grows downwards — we render world Y mathematically (positive up)
    // by negating Y when emitting points; the viewBox below mirrors that.
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

    // Bounding-box rectangle
    const rect = document.createElementNS(SVG_NS, "rect");
    rect.setAttribute("x", x0);
    rect.setAttribute("y", -y1);
    rect.setAttribute("width", Math.max(x1 - x0, 0.001));
    rect.setAttribute("height", Math.max(y1 - y0, 0.001));
    rect.setAttribute("class", "shape-bbox");
    g.appendChild(rect);

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

    const w = x1 - x0;
    const lbl = document.createElementNS(SVG_NS, "text");
    lbl.setAttribute("x", x0);
    lbl.setAttribute("y", -y0 + Math.max(w, 1) * 0.06);
    lbl.setAttribute("class", "axis-label");
    lbl.textContent = `${w.toFixed(1)} μm × ${(y1 - y0).toFixed(1)} μm`;
    g.appendChild(lbl);

    svg.appendChild(g);
  }

  function drawPolygons(svg, payload) {
    const { polygons } = payload;

    // Group polygons by metal so we can layer them in tech-stack order
    // (lower metal beneath higher metal). With one metal layer this is a
    // no-op; with transformer / multi-metal shapes it matters.
    const layered = [...polygons]
      .map((p, idx) => ({ p, idx }))
      .sort((a, b) => (a.p.metal | 0) - (b.p.metal | 0));

    layered.forEach(({ p, idx }) => {
      const fill = colorFor(p.color, idx);
      const segPolys = Array.isArray(p.segment_polys) ? p.segment_polys : [];
      if (segPolys.length === 0) return;

      const group = document.createElementNS(SVG_NS, "g");
      group.setAttribute("data-metal", p.metal);
      group.setAttribute("data-metal-name", p.metal_name || "");

      // ASITIC's CIF emits one filled 4-corner ``P`` polygon per spiral
      // side (offsets ±W/2 perpendicular to the centerline). We mirror
      // that here — bridge.py hands us the corner lists, and we draw
      // each as an SVG <polygon>. Adjacent rectangles overlap at the
      // corner squares (one overlap per bend), which tiles the corner
      // cleanly and matches the visual produced by ASITIC's
      // ``XFillPolygon`` sequence. We deliberately *omit* a stroke so
      // the overlap regions don't show seams between adjacent fills.
      segPolys.forEach((corners) => {
        if (!corners || corners.length < 3) return;
        const poly = document.createElementNS(SVG_NS, "polygon");
        const pts = corners
          .map(([x, y]) => `${x.toFixed(3)},${(-y).toFixed(3)}`)
          .join(" ");
        poly.setAttribute("points", pts);
        poly.setAttribute("fill", fill);
        poly.setAttribute("stroke", "none");
        group.appendChild(poly);
      });

      // A faint outline around the union of all segments lets the eye
      // pick out the shape; we draw it after the fills using the
      // centerline polyline as a stroked path with miter joins, which
      // matches the XDrawSegments overlay the C GUI puts on top of the
      // filled metal.
      if (p.points && p.points.length >= 2) {
        const path = document.createElementNS(SVG_NS, "path");
        const cmds = [];
        for (let i = 0; i < p.points.length; i++) {
          const [x, y] = p.points[i];
          cmds.push(`${i === 0 ? "M" : "L"} ${x.toFixed(3)} ${(-y).toFixed(3)}`);
        }
        const a = p.points[0], b = p.points[p.points.length - 1];
        if (Math.hypot(a[0] - b[0], a[1] - b[1]) < 1e-6) cmds.push("Z");
        path.setAttribute("d", cmds.join(" "));
        path.setAttribute("fill", "none");
        path.setAttribute("stroke", shade(fill, -0.55));
        path.setAttribute("stroke-opacity", "0.55");
        path.setAttribute("stroke-width", Math.max((p.width || 1) * 0.05, 0.25));
        path.setAttribute("stroke-linecap", "butt");
        path.setAttribute("stroke-linejoin", "miter");
        group.appendChild(path);
      }

      svg.appendChild(group);
    });

    // Terminal markers: small filled circles at the entry / exit ports of
    // the spiral so users can see where the actual port leads attach.
    if (Array.isArray(payload.ports) && payload.ports.length) {
      const span = payload.bbox[2] - payload.bbox[0];
      const r = Math.max(span * 0.012, 1.0);
      payload.ports.forEach((p) => {
        const c = document.createElementNS(SVG_NS, "circle");
        c.setAttribute("cx", p.x);
        c.setAttribute("cy", -p.y);
        c.setAttribute("r", r);
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
        `${payload.polygons.length} polygon(s), ${segs} fat-trace segment(s)`;
    }
  }

  global.Draw = { render };
})(window);
