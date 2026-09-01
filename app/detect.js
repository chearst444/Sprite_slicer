/**
 * detect.js
 * ---------------------------------------------------------------------
 * Content-based sprite detection and JSON coordinate-map parsing.
 *
 * detectSpritesFromImageData() finds each sprite's actual bounding box via
 * connected-component analysis (8-connectivity, union-find) over a
 * foreground mask built from the alpha channel (or, for images without
 * transparency, color distance from a background color). A gap-tolerance
 * dilation pass merges blobs split by a thin gap -- e.g. a character's
 * separated limbs -- before labeling, while bounding boxes are still
 * measured from the *original*, non-dilated mask so they stay tight.
 *
 * No dependencies: works against a plain {width, height, data} object
 * shaped like a canvas ImageData (so it's usable both in the browser and
 * under Node for testing).
 */
(function (global) {
  "use strict";

  /** Sort rects into a natural top-to-bottom, left-to-right reading order,
   * grouping into rows by approximate vertical position. */
  function readingOrderSort(rects) {
    const items = rects.slice().sort((a, b) => a.y0 - b.y0);
    const rows = [];
    let currentRow = [];
    let currentY = null;
    let rowTol = 0;
    for (const r of items) {
      const h = r.y1 - r.y0;
      if (currentY === null) {
        currentRow = [r];
        currentY = r.y0;
        rowTol = h * 0.6;
      } else if (r.y0 - currentY <= rowTol) {
        currentRow.push(r);
      } else {
        rows.push(currentRow);
        currentRow = [r];
        currentY = r.y0;
        rowTol = h * 0.6;
      }
    }
    if (currentRow.length) rows.push(currentRow);
    const result = [];
    for (const row of rows) {
      row.sort((a, b) => a.x0 - b.x0);
      result.push(...row);
    }
    return result;
  }

  /** Square dilation of a 0/1 mask by k pixels, as two separable
   * prefix-sum passes (O(w*h), independent of k). */
  function dilateMask(mask, w, h, k) {
    if (k <= 0) return mask;
    const tmp = new Uint8Array(w * h);
    const prefix = new Int32Array(w + 1);
    for (let y = 0; y < h; y++) {
      const row = y * w;
      prefix[0] = 0;
      for (let x = 0; x < w; x++) prefix[x + 1] = prefix[x] + mask[row + x];
      for (let x = 0; x < w; x++) {
        const lo = Math.max(0, x - k);
        const hi = Math.min(w - 1, x + k);
        tmp[row + x] = prefix[hi + 1] - prefix[lo] > 0 ? 1 : 0;
      }
    }
    const out = new Uint8Array(w * h);
    const prefixY = new Int32Array(h + 1);
    for (let x = 0; x < w; x++) {
      prefixY[0] = 0;
      for (let y = 0; y < h; y++) prefixY[y + 1] = prefixY[y] + tmp[y * w + x];
      for (let y = 0; y < h; y++) {
        const lo = Math.max(0, y - k);
        const hi = Math.min(h - 1, y + k);
        out[y * w + x] = prefixY[hi + 1] - prefixY[lo] > 0 ? 1 : 0;
      }
    }
    return out;
  }

  /**
   * @param {{width:number,height:number,data:Uint8ClampedArray|Uint8Array}} imageData
   * @param {{threshold?:number, gapTolerance?:number, minSize?:number, bgColor?:[number,number,number]|null}} opts
   * @returns {Array<{x0:number,y0:number,x1:number,y1:number}>}
   */
  function detectSpritesFromImageData(imageData, opts) {
    opts = opts || {};
    const w = imageData.width;
    const h = imageData.height;
    const data = imageData.data;
    const threshold = opts.threshold != null ? opts.threshold : 16;
    const gapTolerance = Math.max(0, opts.gapTolerance != null ? opts.gapTolerance : 2);
    const minSize = Math.max(1, opts.minSize != null ? opts.minSize : 4);
    let bgColor = opts.bgColor || null;

    let hasAlpha = false;
    for (let i = 3; i < data.length; i += 4) {
      if (data[i] < 255) {
        hasAlpha = true;
        break;
      }
    }

    const origMask = new Uint8Array(w * h);
    if (hasAlpha) {
      for (let p = 0, i = 3; p < w * h; p++, i += 4) {
        origMask[p] = data[i] > threshold ? 1 : 0;
      }
    } else {
      if (!bgColor) bgColor = [data[0], data[1], data[2]];
      for (let p = 0, i = 0; p < w * h; p++, i += 4) {
        const dr = Math.abs(data[i] - bgColor[0]);
        const dg = Math.abs(data[i + 1] - bgColor[1]);
        const db = Math.abs(data[i + 2] - bgColor[2]);
        origMask[p] = Math.max(dr, dg, db) > threshold ? 1 : 0;
      }
    }

    const workMask = gapTolerance > 0 ? dilateMask(origMask, w, h, gapTolerance) : origMask;

    // Two-pass connected-component labeling (8-connectivity) via union-find.
    const labels = new Int32Array(w * h);
    const parent = [0];
    function find(x) {
      let root = x;
      while (parent[root] !== root) root = parent[root];
      while (parent[x] !== root) {
        const next = parent[x];
        parent[x] = root;
        x = next;
      }
      return root;
    }
    function union(a, b) {
      const ra = find(a);
      const rb = find(b);
      if (ra !== rb) parent[ra < rb ? rb : ra] = ra < rb ? ra : rb;
    }

    let nextLabel = 1;
    for (let y = 0; y < h; y++) {
      const row = y * w;
      for (let x = 0; x < w; x++) {
        const idx = row + x;
        if (!workMask[idx]) continue;
        const neighbors = [];
        if (x > 0 && workMask[idx - 1]) neighbors.push(labels[idx - 1]);
        if (y > 0) {
          if (workMask[idx - w]) neighbors.push(labels[idx - w]);
          if (x > 0 && workMask[idx - w - 1]) neighbors.push(labels[idx - w - 1]);
          if (x < w - 1 && workMask[idx - w + 1]) neighbors.push(labels[idx - w + 1]);
        }
        if (neighbors.length === 0) {
          labels[idx] = nextLabel;
          parent.push(nextLabel);
          nextLabel++;
        } else {
          const m = Math.min(...neighbors);
          labels[idx] = m;
          for (const n of neighbors) if (n !== m) union(n, m);
        }
      }
    }

    // Gather bounding boxes using only the ORIGINAL (non-dilated) mask.
    const boxes = new Map();
    for (let y = 0; y < h; y++) {
      const row = y * w;
      for (let x = 0; x < w; x++) {
        const idx = row + x;
        if (!origMask[idx]) continue;
        const lbl = labels[idx];
        if (lbl === 0) continue;
        const r = find(lbl);
        let b = boxes.get(r);
        if (!b) {
          boxes.set(r, { minx: x, miny: y, maxx: x, maxy: y });
        } else {
          if (x < b.minx) b.minx = x;
          if (y < b.miny) b.miny = y;
          if (x > b.maxx) b.maxx = x;
          if (y > b.maxy) b.maxy = y;
        }
      }
    }

    const rects = [];
    for (const b of boxes.values()) {
      const bw = b.maxx - b.minx + 1;
      const bh = b.maxy - b.miny + 1;
      if (bw < minSize || bh < minSize) continue;
      rects.push({ x0: b.minx, y0: b.miny, x1: b.maxx + 1, y1: b.maxy + 1 });
    }
    return readingOrderSort(rects);
  }

  /** Turn an arbitrary sprite name (e.g. from a JSON atlas) into a safe
   * filename stem. Atlas names are often "virtual" paths, so separators
   * are flattened into underscores rather than truncated. */
  function sanitizeFilename(name) {
    let s = String(name).trim();
    s = s.replace(/\.(png|jpe?g|gif|bmp|tga|webp)$/i, "");
    s = s.replace(/[\\/:*?"<>|]+/g, "_");
    s = s.replace(/\s+/g, "_").replace(/^[._]+|[._]+$/g, "");
    return s || "sprite";
  }

  /** Normalize a parsed JSON document into a list of
   * {name, x, y, w, h} entries. Accepts a bare list, {"sprites":[...]},
   * or a TexturePacker-style {"frames": ...} atlas (hash or array). */
  function parseJsonSprites(data) {
    function entry(name, x, y, w, h) {
      return {
        name: name != null ? String(name) : null,
        x: Math.trunc(Number(x) || 0),
        y: Math.trunc(Number(y) || 0),
        w: Math.trunc(Number(w) || 0),
        h: Math.trunc(Number(h) || 0),
      };
    }

    let items;
    if (Array.isArray(data)) {
      items = data;
    } else if (data && Array.isArray(data.sprites)) {
      items = data.sprites;
    } else if (data && data.frames != null) {
      const frames = data.frames;
      if (Array.isArray(frames)) {
        items = frames;
      } else if (typeof frames === "object") {
        const results = [];
        for (const name of Object.keys(frames)) {
          const val = frames[name];
          const frame = (val && val.frame) || val || {};
          results.push(entry(
            name, frame.x, frame.y,
            frame.w != null ? frame.w : frame.width,
            frame.h != null ? frame.h : frame.height,
          ));
        }
        return results;
      } else {
        throw new Error("'frames' must be an object or an array");
      }
    } else {
      throw new Error(
        'Unrecognized JSON shape. Expected a list of sprites, {"sprites": [...]}, ' +
        'or a TexturePacker-style {"frames": ...}.'
      );
    }

    const results = [];
    for (const item of items) {
      if (!item || typeof item !== "object") continue;
      const frame = item.frame || item;
      const name = item.name || item.filename;
      results.push(entry(
        name, frame.x, frame.y,
        frame.w != null ? frame.w : frame.width,
        frame.h != null ? frame.h : frame.height,
      ));
    }
    return results;
  }

  const api = {
    detectSpritesFromImageData,
    sanitizeFilename,
    parseJsonSprites,
    readingOrderSort,
    dilateMask,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    global.SpriteDetect = api;
  }
})(typeof window !== "undefined" ? window : globalThis);
