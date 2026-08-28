/**
 * Sprite Sheet Splitter — web app logic.
 *
 * Pure client-side: no server, no build step, no network dependency. Slices
 * a sprite sheet image into individual PNG files entirely in the browser
 * using <canvas>, then bundles them into a .zip (see zip-writer.js) for
 * one-click download. Works on desktop and mobile browsers alike.
 */
(function () {
  "use strict";

  const SUPPORTED_TYPES = ["image/png", "image/jpeg", "image/gif", "image/bmp", "image/webp"];

  // ---- DOM references -----------------------------------------------
  const els = {
    dropzone: document.getElementById("dropzone"),
    fileInput: document.getElementById("fileInput"),
    browseBtn: document.getElementById("browseBtn"),
    fileLabel: document.getElementById("fileLabel"),
    canvas: document.getElementById("previewCanvas"),
    placeholder: document.getElementById("placeholder"),
    infoBar: document.getElementById("infoBar"),
    statusBar: document.getElementById("statusBar"),

    modeGrid: document.getElementById("modeGrid"),
    modeFixed: document.getElementById("modeFixed"),
    modeAuto: document.getElementById("modeAuto"),
    modeJson: document.getElementById("modeJson"),
    gridInputs: document.getElementById("gridInputs"),
    fixedInputs: document.getElementById("fixedInputs"),
    autoInputs: document.getElementById("autoInputs"),
    jsonInputs: document.getElementById("jsonInputs"),
    rows: document.getElementById("rows"),
    cols: document.getElementById("cols"),
    spriteW: document.getElementById("spriteW"),
    spriteH: document.getElementById("spriteH"),
    offsetX: document.getElementById("offsetX"),
    offsetY: document.getElementById("offsetY"),
    spacingX: document.getElementById("spacingX"),
    spacingY: document.getElementById("spacingY"),
    marginHint: document.getElementById("marginHint"),

    detectThreshold: document.getElementById("detectThreshold"),
    detectGap: document.getElementById("detectGap"),
    detectMinSize: document.getElementById("detectMinSize"),
    detectBgColor: document.getElementById("detectBgColor"),
    detectBtn: document.getElementById("detectBtn"),
    detectStatus: document.getElementById("detectStatus"),

    jsonFileInput: document.getElementById("jsonFileInput"),
    jsonLoadBtn: document.getElementById("jsonLoadBtn"),
    jsonStatus: document.getElementById("jsonStatus"),

    prefix: document.getElementById("prefix"),
    namingSeq: document.getElementById("namingSeq"),
    namingCoords: document.getElementById("namingCoords"),
    namingHint: document.getElementById("namingHint"),
    skipBlank: document.getElementById("skipBlank"),

    exportBtn: document.getElementById("exportBtn"),
    saveFolderBtn: document.getElementById("saveFolderBtn"),
  };

  // ---- state -----------------------------------------------------------
  const state = {
    image: null, // HTMLImageElement
    fileBaseName: "sprite",
    sourceCanvas: null, // full-res offscreen canvas holding the decoded image
    detectedRects: null, // cached results for "auto"/"json" modes: [{r,c,x0,y0,x1,y1,name}]
    detecting: false,
  };

  function currentMode() {
    if (els.modeAuto.checked) return "auto";
    if (els.modeJson.checked) return "json";
    return els.modeGrid.checked ? "grid" : "fixed";
  }

  // ---- grid math (mirrors the desktop app's logic) ----------------------
  function intOr(value, fallback) {
    const n = parseInt(value, 10);
    return Number.isFinite(n) ? n : fallback;
  }

  /** Returns { rects, error }. rects: [{r,c,x0,y0,x1,y1,name}] in image pixels. */
  function computeRects() {
    if (!state.image) return { rects: [], error: null };

    const mode = currentMode();

    if (mode === "auto") {
      if (state.detectedRects === null) return { rects: [], error: null };
      if (!state.detectedRects.length) {
        return { rects: [], error: 'No sprites detected yet. Click "Detect Sprites".' };
      }
      return { rects: state.detectedRects, error: null };
    }
    if (mode === "json") {
      if (state.detectedRects === null) return { rects: [], error: null };
      if (!state.detectedRects.length) {
        return { rects: [], error: 'No sprites loaded. Click "Load JSON...".' };
      }
      return { rects: state.detectedRects, error: null };
    }

    const imgW = state.image.naturalWidth;
    const imgH = state.image.naturalHeight;
    const offsetX = intOr(els.offsetX.value, 0);
    const offsetY = intOr(els.offsetY.value, 0);
    const spacingX = intOr(els.spacingX.value, 0);
    const spacingY = intOr(els.spacingY.value, 0);

    if (offsetX < 0 || offsetY < 0 || spacingX < 0 || spacingY < 0) {
      return { rects: [], error: "Offset and spacing must be zero or positive." };
    }

    let rows, cols, cellW, cellH;

    if (mode === "grid") {
      rows = intOr(els.rows.value, 0);
      cols = intOr(els.cols.value, 0);
      if (rows <= 0 || cols <= 0) {
        return { rects: [], error: "Rows and columns must be positive integers." };
      }
      const availW = imgW - offsetX - spacingX * (cols - 1);
      const availH = imgH - offsetY - spacingY * (rows - 1);
      if (availW <= 0 || availH <= 0) {
        return { rects: [], error: "Rows/columns + spacing/offset are larger than the image." };
      }
      cellW = availW / cols;
      cellH = availH / rows;
      if (cellW < 1 || cellH < 1) {
        return { rects: [], error: "Computed sprite size is smaller than 1px. Reduce rows/columns." };
      }
    } else {
      cellW = intOr(els.spriteW.value, 0);
      cellH = intOr(els.spriteH.value, 0);
      if (cellW <= 0 || cellH <= 0) {
        return { rects: [], error: "Sprite width and height must be positive integers." };
      }
      cols = cellW + spacingX > 0 ? Math.floor((imgW - offsetX + spacingX) / (cellW + spacingX)) : 0;
      rows = cellH + spacingY > 0 ? Math.floor((imgH - offsetY + spacingY) / (cellH + spacingY)) : 0;
      if (rows <= 0 || cols <= 0) {
        return { rects: [], error: "No sprites fit with the current size/offset/spacing." };
      }
    }

    const rects = [];
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const x0f = offsetX + c * (cellW + spacingX);
        const y0f = offsetY + r * (cellH + spacingY);
        const x1f = x0f + cellW;
        const y1f = y0f + cellH;
        let x0 = Math.round(x0f);
        let y0 = Math.round(y0f);
        let x1 = Math.min(Math.round(x1f), imgW);
        let y1 = Math.min(Math.round(y1f), imgH);
        if (x1 <= x0 || y1 <= y0) continue;
        rects.push({ r, c, x0, y0, x1, y1, name: null });
      }
    }
    return { rects, error: null };
  }

  // ---- file loading ------------------------------------------------------
  function isSupportedFile(file) {
    if (SUPPORTED_TYPES.includes(file.type)) return true;
    return /\.(png|jpe?g|gif|bmp|webp|tga)$/i.test(file.name);
  }

  function loadFile(file) {
    if (!file) return;
    if (!isSupportedFile(file)) {
      setStatus(`Unsupported file type: ${file.name}`, true);
      return;
    }
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      state.image = img;
      state.fileBaseName = file.name.replace(/\.[^.]+$/, "") || "sprite";

      const off = document.createElement("canvas");
      off.width = img.naturalWidth;
      off.height = img.naturalHeight;
      off.getContext("2d").drawImage(img, 0, 0);
      state.sourceCanvas = off;

      els.fileLabel.textContent = `${file.name}  (${img.naturalWidth}x${img.naturalHeight}px)`;
      els.placeholder.style.display = "none";
      els.prefix.value = els.prefix.value || "sprite";
      setStatus(`Loaded ${file.name}`);
      URL.revokeObjectURL(url);

      // Detected/imported sprite boxes are tied to the previous image.
      state.detectedRects = null;
      els.detectStatus.textContent = "Click “Detect Sprites” to scan for content.";
      els.jsonStatus.textContent = "No JSON file loaded.";

      updatePreview();
    };
    img.onerror = () => {
      setStatus(`Could not decode image: ${file.name}`, true);
      URL.revokeObjectURL(url);
    };
    img.src = url;
  }

  // ---- preview rendering ---------------------------------------------
  function updatePreview() {
    const canvas = els.canvas;
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;

    const cssW = canvas.clientWidth || canvas.parentElement.clientWidth;
    const cssH = Math.max(280, Math.min(640, Math.round(cssW * 0.72)));
    canvas.style.height = cssH + "px";
    canvas.width = Math.round(cssW * dpr);
    canvas.height = Math.round(cssH * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cssW, cssH);

    if (!state.image) {
      els.infoBar.textContent = "";
      return;
    }

    const imgW = state.image.naturalWidth;
    const imgH = state.image.naturalHeight;
    const scale = Math.max(0.01, Math.min(cssW / imgW, cssH / imgH));
    const dispW = Math.max(1, Math.round(imgW * scale));
    const dispH = Math.max(1, Math.round(imgH * scale));
    const offX = Math.round((cssW - dispW) / 2);
    const offY = Math.round((cssH - dispH) / 2);

    // checkerboard behind transparent areas
    drawCheckerboard(ctx, offX, offY, dispW, dispH);
    ctx.drawImage(state.sourceCanvas, offX, offY, dispW, dispH);

    const { rects, error } = computeRects();

    if (error) {
      els.infoBar.textContent = "⚠ " + error;
      els.infoBar.classList.add("error");
      return;
    }
    els.infoBar.classList.remove("error");

    ctx.strokeStyle = "#00e5ff";
    ctx.lineWidth = 1;
    for (const { x0, y0, x1, y1 } of rects) {
      const rx0 = offX + x0 * scale;
      const ry0 = offY + y0 * scale;
      const rx1 = offX + x1 * scale;
      const ry1 = offY + y1 * scale;
      ctx.strokeRect(rx0 + 0.5, ry0 + 0.5, rx1 - rx0 - 1, ry1 - ry0 - 1);
    }

    if (rects.length) {
      const sw = rects[0].x1 - rects[0].x0;
      const sh = rects[0].y1 - rects[0].y0;
      const mode = currentMode();
      const sizeNote = mode === "grid" || mode === "fixed" ? `each ~${sw}x${sh}px` : "varying sizes";
      els.infoBar.textContent = `${rects.length} sprite(s) — ${sizeNote}`;
    } else if (currentMode() !== "auto" && currentMode() !== "json") {
      els.infoBar.textContent = "No sprites in current configuration.";
    } else {
      els.infoBar.textContent = "";
    }
  }

  function drawCheckerboard(ctx, x, y, w, h) {
    const size = 8;
    ctx.save();
    ctx.beginPath();
    ctx.rect(x, y, w, h);
    ctx.clip();
    for (let yy = y; yy < y + h; yy += size) {
      for (let xx = x; xx < x + w; xx += size) {
        const even = ((xx - x) / size + (yy - y) / size) % 2 === 0;
        ctx.fillStyle = even ? "#3a3a3a" : "#2b2b2b";
        ctx.fillRect(xx, yy, size, size);
      }
    }
    ctx.restore();
  }

  // ---- naming ----------------------------------------------------------
  function buildFileName(prefix, idx, totalDigits, r, c, coordsMode) {
    if (coordsMode) return `${prefix}_r${r}_c${c}.png`;
    return `${prefix}_${String(idx).padStart(totalDigits, "0")}.png`;
  }

  /** name -> unique "name.png", deduped against `used` (a Set). Mirrors the
   * desktop app: a JSON entry's own name always wins over the naming radio. */
  function uniqueNamedFile(name, used) {
    const stem = window.SpriteDetect.sanitizeFilename(name);
    let fname = `${stem}.png`;
    let n = 2;
    while (used.has(fname)) {
      fname = `${stem}_${n}.png`;
      n++;
    }
    return fname;
  }

  // ---- slicing / export --------------------------------------------------
  function isTileBlank(tileCanvas) {
    const ctx = tileCanvas.getContext("2d");
    const { data } = ctx.getImageData(0, 0, tileCanvas.width, tileCanvas.height);
    for (let i = 3; i < data.length; i += 4) {
      if (data[i] !== 0) return false;
    }
    return true;
  }

  function tileToCanvas(rect) {
    const w = rect.x1 - rect.x0;
    const h = rect.y1 - rect.y0;
    const c = document.createElement("canvas");
    c.width = w;
    c.height = h;
    c.getContext("2d").drawImage(state.sourceCanvas, rect.x0, rect.y0, w, h, 0, 0, w, h);
    return c;
  }

  function canvasToPngBytes(canvas) {
    return new Promise((resolve, reject) => {
      canvas.toBlob((blob) => {
        if (!blob) return reject(new Error("toBlob failed"));
        blob.arrayBuffer().then((buf) => resolve(new Uint8Array(buf)));
      }, "image/png");
    });
  }

  async function sliceAll() {
    const { rects, error } = computeRects();
    if (error) throw new Error(error);
    if (!rects.length) throw new Error("No sprites to export with the current settings.");

    const prefix = (els.prefix.value || "sprite").trim() || "sprite";
    const coordsMode = els.namingCoords.checked;
    const skipBlank = els.skipBlank.checked;
    const totalDigits = Math.max(3, String(rects.length).length);

    const files = [];
    const usedNames = new Set();
    let idx = 0;
    let skipped = 0;
    for (const rect of rects) {
      idx++;
      const tileCanvas = tileToCanvas(rect);
      if (skipBlank && isTileBlank(tileCanvas)) {
        skipped++;
        continue;
      }
      const name = rect.name
        ? uniqueNamedFile(rect.name, usedNames)
        : buildFileName(prefix, idx, totalDigits, rect.r, rect.c, coordsMode);
      usedNames.add(name);
      const data = await canvasToPngBytes(tileCanvas);
      files.push({ name, data });
    }
    return { files, skipped, total: rects.length };
  }

  function triggerDownload(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
  }

  async function exportZip() {
    if (!state.image) {
      setStatus("Please load a sprite sheet first.", true);
      return;
    }
    els.exportBtn.disabled = true;
    setStatus("Slicing sprites...");
    try {
      const { files, skipped, total } = await sliceAll();
      if (!files.length) {
        setStatus("Nothing to export (all tiles were blank).", true);
        return;
      }
      setStatus(`Building zip (${files.length} sprite${files.length === 1 ? "" : "s"})...`);
      const blob = window.ZipWriter.createZipBlob(files);
      const zipName = `${state.fileBaseName}_sliced.zip`;
      triggerDownload(blob, zipName);
      let msg = `Exported ${files.length} of ${total} sprite(s) as ${zipName}`;
      if (skipped) msg += ` (${skipped} blank tile(s) skipped)`;
      setStatus(msg);
    } catch (e) {
      setStatus(e.message || String(e), true);
    } finally {
      els.exportBtn.disabled = false;
    }
  }

  // ---- optional: File System Access API (Chrome/Edge desktop, some Android) --
  const fsAccessSupported = typeof window.showDirectoryPicker === "function";
  if (fsAccessSupported) {
    els.saveFolderBtn.hidden = false;
    els.saveFolderBtn.addEventListener("click", saveToFolder);
  }

  async function getUniqueSubfolder(parentHandle, baseName) {
    let name = baseName;
    let n = 1;
    // getDirectoryHandle(name, {create:false}) throws NotFoundError if absent.
    // We probe until we find a name that doesn't exist yet, mirroring the
    // desktop app's collision-safe output folder behavior.
    for (;;) {
      try {
        await parentHandle.getDirectoryHandle(name, { create: false });
        name = `${baseName}_${n}`;
        n++;
      } catch (e) {
        return parentHandle.getDirectoryHandle(name, { create: true });
      }
    }
  }

  async function saveToFolder() {
    if (!state.image) {
      setStatus("Please load a sprite sheet first.", true);
      return;
    }
    els.saveFolderBtn.disabled = true;
    try {
      const parentHandle = await window.showDirectoryPicker();
      setStatus("Slicing sprites...");
      const { files, skipped, total } = await sliceAll();
      if (!files.length) {
        setStatus("Nothing to export (all tiles were blank).", true);
        return;
      }
      const folderHandle = await getUniqueSubfolder(parentHandle, `${state.fileBaseName}_sliced`);
      for (const file of files) {
        const fileHandle = await folderHandle.getFileHandle(file.name, { create: true });
        const writable = await fileHandle.createWritable();
        await writable.write(file.data);
        await writable.close();
      }
      let msg = `Saved ${files.length} of ${total} sprite(s) to folder "${folderHandle.name}"`;
      if (skipped) msg += ` (${skipped} blank tile(s) skipped)`;
      setStatus(msg);
    } catch (e) {
      if (e.name !== "AbortError") setStatus(e.message || String(e), true);
    } finally {
      els.saveFolderBtn.disabled = false;
    }
  }

  // ---- auto-detect -------------------------------------------------------
  function parseHexColor(text) {
    text = text.trim().replace(/^#/, "");
    if (!text) return null;
    if (text.length === 3) text = text.split("").map((c) => c + c).join("");
    if (text.length !== 6 || /[^0-9a-fA-F]/.test(text)) return null;
    return [0, 2, 4].map((i) => parseInt(text.slice(i, i + 2), 16));
  }

  function runDetect() {
    if (!state.image) {
      setStatus("Please load a sprite sheet first.", true);
      return;
    }
    if (state.detecting) return;

    const threshold = Math.max(0, Math.min(255, intOr(els.detectThreshold.value, 16)));
    const gapTolerance = Math.max(0, intOr(els.detectGap.value, 2));
    const minSize = Math.max(1, intOr(els.detectMinSize.value, 4));
    const bgColor = parseHexColor(els.detectBgColor.value);

    state.detecting = true;
    els.detectBtn.disabled = true;
    els.detectStatus.textContent = "Detecting… this can take a few seconds for large images.";
    setStatus("Detecting sprites...");

    // Defer one tick so the "Detecting…" status actually paints before the
    // (synchronous, potentially heavy) scan blocks the main thread.
    setTimeout(() => {
      try {
        const w = state.sourceCanvas.width;
        const h = state.sourceCanvas.height;
        const imageData = state.sourceCanvas.getContext("2d").getImageData(0, 0, w, h);
        const rects = window.SpriteDetect.detectSpritesFromImageData(imageData, {
          threshold, gapTolerance, minSize, bgColor,
        });
        state.detectedRects = rects.map((r, i) => ({ r: 0, c: i, x0: r.x0, y0: r.y0, x1: r.x1, y1: r.y1, name: null }));
        if (rects.length) {
          els.detectStatus.textContent = `${rects.length} sprite(s) detected.`;
        } else {
          els.detectStatus.textContent =
            "No sprite content detected. Try lowering the threshold, increasing gap " +
            "tolerance, or checking the background color.";
        }
        setStatus(`Detected ${rects.length} sprite(s).`);
      } catch (e) {
        els.detectStatus.textContent = "⚠ Detection failed: " + (e.message || e);
        setStatus("Detection failed.", true);
      } finally {
        state.detecting = false;
        els.detectBtn.disabled = false;
        updatePreview();
      }
    }, 20);
  }

  // ---- JSON coordinate import --------------------------------------------
  function loadJsonFile(file) {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      let entries;
      try {
        const data = JSON.parse(reader.result);
        entries = window.SpriteDetect.parseJsonSprites(data);
      } catch (e) {
        setStatus("Could not load JSON file: " + (e.message || e), true);
        els.jsonStatus.textContent = "⚠ " + (e.message || e);
        return;
      }

      const imgW = state.image ? state.image.naturalWidth : null;
      const imgH = state.image ? state.image.naturalHeight : null;
      const rects = [];
      let skipped = 0;
      entries.forEach((e, i) => {
        if (e.w <= 0 || e.h <= 0) {
          skipped++;
          return;
        }
        const x1 = e.x + e.w;
        const y1 = e.y + e.h;
        if (imgW != null && (e.x < 0 || e.y < 0 || x1 > imgW || y1 > imgH)) {
          skipped++;
          return;
        }
        rects.push({ r: 0, c: i, x0: e.x, y0: e.y, x1, y1, name: e.name });
      });

      state.detectedRects = rects;
      els.jsonStatus.textContent =
        `${file.name} — ${rects.length} sprite(s) loaded` +
        (skipped ? `, ${skipped} skipped (out of bounds)` : "");
      setStatus(`Loaded ${rects.length} sprite(s) from ${file.name}`);
      updatePreview();
    };
    reader.onerror = () => setStatus(`Could not read file: ${file.name}`, true);
    reader.readAsText(file);
  }

  // ---- misc UI wiring ----------------------------------------------------
  function setStatus(msg, isError) {
    els.statusBar.textContent = msg;
    els.statusBar.classList.toggle("error", !!isError);
  }

  function onModeChange() {
    const mode = currentMode();
    els.gridInputs.hidden = mode !== "grid";
    els.fixedInputs.hidden = mode !== "fixed";
    els.autoInputs.hidden = mode !== "auto";
    els.jsonInputs.hidden = mode !== "json";

    // Offset & spacing only apply to the two grid-based modes; disable
    // (rather than hide) so the panel layout never reorders.
    const gridBased = mode === "grid" || mode === "fixed";
    [els.offsetX, els.offsetY, els.spacingX, els.spacingY].forEach((el) => {
      el.disabled = !gridBased;
    });
    els.marginHint.textContent = gridBased
      ? "Start = top-left offset before the first sprite. Spacing = gap between adjacent sprites."
      : "Not used in this mode — sprite bounds come from the detected content or the imported coordinates instead.";

    // Row/Col naming has no meaning for auto-detected or JSON-imported
    // sprites -- there's no grid to derive coordinates from.
    const contentBased = mode === "auto" || mode === "json";
    els.namingCoords.disabled = contentBased;
    if (contentBased && els.namingCoords.checked) {
      els.namingSeq.checked = true;
    }
    els.namingHint.textContent = contentBased
      ? "Detected/imported sprites use sequential naming, unless a JSON entry supplies its own \"name\" (which always takes priority)."
      : "";

    updatePreview();
  }

  function wireEvents() {
    els.fileInput.addEventListener("change", (e) => loadFile(e.target.files[0]));

    els.dropzone.addEventListener("click", () => els.fileInput.click());
    els.browseBtn.addEventListener("click", () => els.fileInput.click());
    els.dropzone.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") els.fileInput.click();
    });

    ["dragenter", "dragover"].forEach((evt) =>
      els.dropzone.addEventListener(evt, (e) => {
        e.preventDefault();
        els.dropzone.classList.add("dragover");
      })
    );
    ["dragleave", "drop"].forEach((evt) =>
      els.dropzone.addEventListener(evt, (e) => {
        e.preventDefault();
        els.dropzone.classList.remove("dragover");
      })
    );
    els.dropzone.addEventListener("drop", (e) => {
      const file = e.dataTransfer.files && e.dataTransfer.files[0];
      if (file) loadFile(file);
    });

    els.modeGrid.addEventListener("change", onModeChange);
    els.modeFixed.addEventListener("change", onModeChange);
    els.modeAuto.addEventListener("change", onModeChange);
    els.modeJson.addEventListener("change", onModeChange);

    [
      els.rows, els.cols, els.spriteW, els.spriteH,
      els.offsetX, els.offsetY, els.spacingX, els.spacingY,
    ].forEach((input) => input.addEventListener("input", updatePreview));

    els.namingSeq.addEventListener("change", updatePreview);
    els.namingCoords.addEventListener("change", updatePreview);

    els.detectBtn.addEventListener("click", runDetect);
    els.jsonLoadBtn.addEventListener("click", () => els.jsonFileInput.click());
    els.jsonFileInput.addEventListener("change", (e) => loadJsonFile(e.target.files[0]));

    els.exportBtn.addEventListener("click", exportZip);

    window.addEventListener("resize", debounce(updatePreview, 120));
  }

  function debounce(fn, ms) {
    let t;
    return (...args) => {
      clearTimeout(t);
      t = setTimeout(() => fn(...args), ms);
    };
  }

  wireEvents();
  onModeChange();
})();
