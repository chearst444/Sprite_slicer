#!/usr/bin/env python3
"""
Sprite Sheet Splitter
======================
A lightweight, standalone desktop utility for slicing a sprite sheet image
into individual sprite files.

Run with:  python sprite_slicer.py

Dependencies: Pillow (required), tkinterdnd2 (optional, enables drag & drop)
See requirements.txt.
"""

import os
import re
import sys
import json
import shutil
import queue
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    from PIL import Image, ImageTk, ImageFilter, ImageChops
except ImportError:
    print("Pillow is required. Install it with:  pip install -r requirements.txt")
    sys.exit(1)

# Drag-and-drop support is optional. If tkinterdnd2 isn't installed the app
# still works fully via the "Browse..." button.
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False

APP_TITLE = "Sprite Sheet Splitter"
SUPPORTED_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tga", ".webp")

CANVAS_W = 760
CANVAS_H = 560

# Window width, in px, below which the controls panel stacks above the
# preview instead of sitting beside it -- this is what keeps the app usable
# on a phone/tablet-sized window (or a narrow desktop one) instead of
# cramming everything into a sliver next to the sheet preview.
BREAKPOINT_WIDTH = 820


def _int_or(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _float_or(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def sanitize_filename(name):
    """Turn an arbitrary sprite name (e.g. from a JSON atlas) into a safe
    filename stem. Atlas names are often "virtual" paths (e.g. a
    TexturePacker frame named "characters/hero_idle_0.png") rather than
    real filesystem paths, so path separators are flattened into the name
    (via underscores) rather than truncated with os.path.basename."""
    name = str(name).strip()
    name = re.sub(r"\.(png|jpg|jpeg|gif|bmp|tga|webp)$", "", name, flags=re.IGNORECASE)
    name = re.sub(r'[\\/:*?"<>|]+', "_", name)
    name = re.sub(r"\s+", "_", name).strip("._") or "sprite"
    return name


# ----------------------------------------------------------------------
# Auto-detect: connected-component analysis of the sprite sheet's actual
# content (transparency, or a flat background color), so sprites of
# varying, irregular sizes are found from their real bounding boxes
# instead of assuming a uniform grid.
# ----------------------------------------------------------------------
def reading_order_sort(rects):
    """Sort (x0,y0,x1,y1) rects into a natural top-to-bottom, left-to-right
    reading order, grouping into rows by approximate vertical position
    (rects don't need to share an exact y0 to be considered the same row)."""
    items = sorted(rects, key=lambda r: r[1])
    rows, current_row, current_y, row_tol = [], [], None, 0
    for r in items:
        x0, y0, x1, y1 = r
        h = y1 - y0
        if current_y is None:
            current_row, current_y, row_tol = [r], y0, h * 0.6
        elif y0 - current_y <= row_tol:
            current_row.append(r)
        else:
            rows.append(current_row)
            current_row, current_y, row_tol = [r], y0, h * 0.6
    if current_row:
        rows.append(current_row)
    result = []
    for row in rows:
        row.sort(key=lambda r: r[0])
        result.extend(row)
    return result


def detect_sprites(image, threshold=16, gap_tolerance=2, min_size=4, bg_color=None):
    """Scan `image` for the bounding boxes of its actual sprite content and
    return them as a reading-order list of (x0, y0, x1, y1) tuples.

    Foreground is determined from the alpha channel when the image has
    transparency, or by color distance from a background color otherwise.
    Nearby foreground blobs within `gap_tolerance` pixels are merged into a
    single sprite (handles sprites split by a thin gap, e.g. separate limbs),
    and regions smaller than `min_size` on either axis are dropped as noise.
    """
    w, h = image.size
    has_alpha = image.mode in ("RGBA", "LA") or (
        image.mode == "P" and "transparency" in image.info
    )

    if has_alpha:
        rgba = image.convert("RGBA")
        alpha = rgba.split()[-1]
        mask_img = alpha.point(lambda a: 255 if a > threshold else 0)
    else:
        rgb = image.convert("RGB")
        if bg_color is None:
            bg_color = rgb.getpixel((0, 0))
        bg_img = Image.new("RGB", (w, h), bg_color)
        diff = ImageChops.difference(rgb, bg_img).convert("L")
        mask_img = diff.point(lambda p: 255 if p > threshold else 0)

    orig_mask = bytearray(mask_img.tobytes())

    if gap_tolerance > 0:
        k = 2 * gap_tolerance + 1
        work_mask = bytearray(mask_img.filter(ImageFilter.MaxFilter(k)).tobytes())
    else:
        work_mask = orig_mask

    # Two-pass connected-component labeling (8-connectivity) via union-find,
    # run on the (possibly dilated) work_mask so nearby blobs merge --
    # but bounding boxes are gathered from the ORIGINAL mask only, so the
    # merged box still hugs the real opaque pixels.
    labels = [0] * (w * h)
    parent = [0]

    def find(x):
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb if ra < rb else ra] = ra if ra < rb else rb

    next_label = 1
    for y in range(h):
        row = y * w
        for x in range(w):
            idx = row + x
            if not work_mask[idx]:
                continue
            neighbors = []
            if x > 0 and work_mask[idx - 1]:
                neighbors.append(labels[idx - 1])
            if y > 0:
                if work_mask[idx - w]:
                    neighbors.append(labels[idx - w])
                if x > 0 and work_mask[idx - w - 1]:
                    neighbors.append(labels[idx - w - 1])
                if x < w - 1 and work_mask[idx - w + 1]:
                    neighbors.append(labels[idx - w + 1])
            if not neighbors:
                labels[idx] = next_label
                parent.append(next_label)
                next_label += 1
            else:
                m = min(neighbors)
                labels[idx] = m
                for n in neighbors:
                    if n != m:
                        union(n, m)

    bboxes = {}
    for y in range(h):
        row = y * w
        for x in range(w):
            idx = row + x
            if not orig_mask[idx]:
                continue
            lbl = labels[idx]
            if lbl == 0:
                continue
            r = find(lbl)
            b = bboxes.get(r)
            if b is None:
                bboxes[r] = [x, y, x, y]
            else:
                if x < b[0]:
                    b[0] = x
                if y < b[1]:
                    b[1] = y
                if x > b[2]:
                    b[2] = x
                if y > b[3]:
                    b[3] = y

    rects = []
    for minx, miny, maxx, maxy in bboxes.values():
        bw, bh = maxx - minx + 1, maxy - miny + 1
        if bw < min_size or bh < min_size:
            continue
        rects.append((minx, miny, maxx + 1, maxy + 1))

    return reading_order_sort(rects)


# ----------------------------------------------------------------------
# JSON coordinate import: load exact sprite bounding boxes from a metadata
# file instead of computing them, e.g. a hand-authored map or a
# TexturePacker-style atlas export.
# ----------------------------------------------------------------------
def parse_json_sprites(data):
    """Normalize a parsed JSON document into a list of
    {"name": str|None, "x": int, "y": int, "w": int, "h": int} dicts.

    Accepts three shapes:
      - a bare list of entries: [{"x":..,"y":..,"width":..,"height":..}, ...]
      - {"sprites": [...]} with the same entry shape
      - TexturePacker "frames" as a dict: {"frames": {"name.png": {"frame":
        {"x":..,"y":..,"w":..,"h":..}}, ...}}
      - TexturePacker "frames" as a list: {"frames": [{"filename":..,
        "frame": {"x":..,"y":..,"w":..,"h":..}}, ...]}
    """
    def entry(name, x, y, w, h):
        return {
            "name": str(name) if name is not None else None,
            "x": _int_or(x), "y": _int_or(y),
            "w": _int_or(w), "h": _int_or(h),
        }

    results = []

    if isinstance(data, list):
        items = data
    elif isinstance(data, dict) and "sprites" in data and isinstance(data["sprites"], list):
        items = data["sprites"]
    elif isinstance(data, dict) and "frames" in data:
        frames = data["frames"]
        if isinstance(frames, dict):
            for name, val in frames.items():
                frame = val.get("frame", val) if isinstance(val, dict) else {}
                results.append(entry(
                    name, frame.get("x"), frame.get("y"),
                    frame.get("w", frame.get("width")), frame.get("h", frame.get("height")),
                ))
            return results
        elif isinstance(frames, list):
            items = frames
        else:
            raise ValueError("'frames' must be an object or an array")
    else:
        raise ValueError(
            "Unrecognized JSON shape. Expected a list of sprites, "
            "{\"sprites\": [...]}, or a TexturePacker-style {\"frames\": ...}."
        )

    for item in items:
        if not isinstance(item, dict):
            continue
        frame = item.get("frame", item)
        name = item.get("name") or item.get("filename")
        results.append(entry(
            name, frame.get("x"), frame.get("y"),
            frame.get("w", frame.get("width")), frame.get("h", frame.get("height")),
        ))

    return results


class SpriteSlicerApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        # Small enough to fit a phone- or tablet-sized window (or a resized
        # desktop one); the responsive layout below takes over from there.
        self.root.minsize(340, 480)

        # ---- state -------------------------------------------------
        self.image_path = None          # path to source sprite sheet
        self.image = None                # PIL.Image (full resolution, original mode)
        self.preview_photo = None        # ImageTk.PhotoImage currently shown
        self.scale = 1.0                 # scale factor: displayed / original
        self.offset_canvas = (0, 0)      # top-left of image on canvas

        # slicing config vars
        self.mode = tk.StringVar(value="grid")  # "grid" | "fixed" | "auto" | "json"
        self.rows_var = tk.StringVar(value="4")
        self.cols_var = tk.StringVar(value="4")
        self.sprite_w_var = tk.StringVar(value="32")
        self.sprite_h_var = tk.StringVar(value="32")
        self.offset_x_var = tk.StringVar(value="0")
        self.offset_y_var = tk.StringVar(value="0")
        self.spacing_x_var = tk.StringVar(value="0")
        self.spacing_y_var = tk.StringVar(value="0")

        # auto-detect params
        self.detect_threshold_var = tk.StringVar(value="16")
        self.detect_gap_var = tk.StringVar(value="2")
        self.detect_minsize_var = tk.StringVar(value="4")
        self.detect_bgcolor_var = tk.StringVar(value="")
        self.detect_status_var = tk.StringVar(value="Click “Detect Sprites” to scan for content.")
        self._detecting = False

        # json import
        self.json_path_var = tk.StringVar(value="No JSON file loaded")
        self._json_error = None

        # cached results for auto/json modes (list of (r,c,x0,y0,x1,y1,name))
        self.detected_rects = None

        self.prefix_var = tk.StringVar(value="sprite")
        self.naming_var = tk.StringVar(value="sequential")  # "sequential" | "coords"
        self.skip_blank_var = tk.BooleanVar(value=True)
        self.make_zip_var = tk.BooleanVar(value=False)
        self.output_dir_var = tk.StringVar(value="")  # override; blank = auto next to source

        self.status_var = tk.StringVar(value="Open a sprite sheet to get started.")
        self.info_var = tk.StringVar(value="")

        # nudge / touch-drag support for repositioning the grid on the
        # preview directly, instead of typing into the offset fields
        self.nudge_step_var = tk.StringVar(value="1")
        self._layout_mode = None   # "wide" | "narrow", tracks which responsive layout is active
        self._drag_start = None    # (canvas_x, canvas_y, start_offset_x, start_offset_y) while dragging
        self._wrap_labels = []     # labels whose wraplength should track the controls panel width

        self._build_ui()
        self._bind_traces()
        self._apply_responsive_layout()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self):
        root = self.root
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        root.rowconfigure(1, weight=0)

        # Touch-friendlier default hit targets -- bigger tap area on every
        # button/checkbox/radio button helps a lot on a phone/tablet screen.
        style = ttk.Style(root)
        style.configure("TButton", padding=(10, 8))
        style.configure("TCheckbutton", padding=(2, 6))
        style.configure("TRadiobutton", padding=(2, 6))

        # `body` holds the controls panel and the preview panel, and is the
        # thing whose internal grid gets reconfigured by
        # _apply_responsive_layout() -- side-by-side on a wide window,
        # stacked (controls on top, preview below) on a narrow/phone one.
        self.body = ttk.Frame(root)
        self.body.grid(row=0, column=0, sticky="nsew")

        status_bar = ttk.Frame(root, relief="sunken", borderwidth=1)
        status_bar.grid(row=1, column=0, sticky="ew")
        ttk.Label(status_bar, textvariable=self.status_var, padding=(6, 3)).pack(anchor="w")

        # -------- left: controls panel (scrollable, so a short/narrow
        # window scrolls instead of clipping controls off-screen) --------
        self.controls_container = ttk.Frame(self.body)

        self.controls_canvas = tk.Canvas(self.controls_container, highlightthickness=0,
                                          bd=0, width=300, height=400)
        controls_scroll = ttk.Scrollbar(self.controls_container, orient="vertical",
                                         command=self.controls_canvas.yview)
        self.controls_canvas.configure(yscrollcommand=controls_scroll.set)
        self.controls_canvas.pack(side="left", fill="both", expand=True)
        controls_scroll.pack(side="right", fill="y")

        controls_outer = ttk.Frame(self.controls_canvas, padding=(10, 10))
        self._controls_window = self.controls_canvas.create_window(
            (0, 0), window=controls_outer, anchor="nw"
        )

        def _on_controls_inner_configure(event):
            self.controls_canvas.configure(scrollregion=self.controls_canvas.bbox("all"))
        controls_outer.bind("<Configure>", _on_controls_inner_configure)

        def _on_controls_canvas_configure(event):
            self.controls_canvas.itemconfig(self._controls_window, width=event.width)
            wrap = max(160, event.width - 24)
            for label in self._wrap_labels:
                label.configure(wraplength=wrap)
        self.controls_canvas.bind("<Configure>", _on_controls_canvas_configure)

        def _on_mousewheel(event):
            if event.num == 5 or event.delta < 0:
                self.controls_canvas.yview_scroll(1, "units")
            elif event.num == 4 or event.delta > 0:
                self.controls_canvas.yview_scroll(-1, "units")

        def _bind_mousewheel(_event=None):
            self.controls_canvas.bind_all("<MouseWheel>", _on_mousewheel)
            self.controls_canvas.bind_all("<Button-4>", _on_mousewheel)
            self.controls_canvas.bind_all("<Button-5>", _on_mousewheel)

        def _unbind_mousewheel(_event=None):
            self.controls_canvas.unbind_all("<MouseWheel>")
            self.controls_canvas.unbind_all("<Button-4>")
            self.controls_canvas.unbind_all("<Button-5>")

        self.controls_canvas.bind("<Enter>", _bind_mousewheel)
        self.controls_canvas.bind("<Leave>", _unbind_mousewheel)

        ttk.Label(controls_outer, text=APP_TITLE, font=("TkDefaultFont", 14, "bold")).pack(
            anchor="w", pady=(0, 10)
        )

        # --- import ---
        import_frame = ttk.LabelFrame(controls_outer, text="1. Sprite Sheet", padding=10)
        import_frame.pack(fill="x", pady=(0, 10))
        ttk.Button(import_frame, text="Browse for Image...", command=self.browse_file).pack(
            fill="x"
        )
        drop_hint = "Drag & drop an image onto the preview" if DND_AVAILABLE else \
            "(Install tkinterdnd2 to enable drag & drop)"
        drop_hint_label = ttk.Label(import_frame, text=drop_hint, foreground="#666", wraplength=280)
        drop_hint_label.pack(anchor="w", pady=(6, 0))
        self.file_label = ttk.Label(import_frame, text="No file loaded", foreground="#333",
                                     wraplength=280)
        self.file_label.pack(anchor="w", pady=(6, 0))
        self._wrap_labels += [drop_hint_label, self.file_label]

        # --- slicing mode ---
        mode_frame = ttk.LabelFrame(controls_outer, text="2. Slicing Method", padding=10)
        mode_frame.pack(fill="x", pady=(0, 10))

        mode_row1 = ttk.Frame(mode_frame)
        mode_row1.pack(fill="x", anchor="w")
        ttk.Radiobutton(mode_row1, text="Rows x Columns", variable=self.mode,
                         value="grid", command=self._on_mode_change).pack(side="left")
        ttk.Radiobutton(mode_row1, text="Fixed Sprite Size", variable=self.mode,
                         value="fixed", command=self._on_mode_change).pack(side="left", padx=(12, 0))
        mode_row2 = ttk.Frame(mode_frame)
        mode_row2.pack(fill="x", anchor="w", pady=(4, 0))
        ttk.Radiobutton(mode_row2, text="Auto-Detect (content-based)", variable=self.mode,
                         value="auto", command=self._on_mode_change).pack(side="left")
        mode_row3 = ttk.Frame(mode_frame)
        mode_row3.pack(fill="x", anchor="w", pady=(4, 0))
        ttk.Radiobutton(mode_row3, text="Import Coordinates (JSON)", variable=self.mode,
                         value="json", command=self._on_mode_change).pack(side="left")

        # grid inputs
        self.grid_inputs = ttk.Frame(mode_frame)
        self.grid_inputs.pack(fill="x", pady=(8, 0))
        self._labeled_entry(self.grid_inputs, "Rows:", self.rows_var, 0, 0)
        self._labeled_entry(self.grid_inputs, "Columns:", self.cols_var, 0, 2)

        # fixed-size inputs
        self.fixed_inputs = ttk.Frame(mode_frame)
        self._labeled_entry(self.fixed_inputs, "Sprite Width:", self.sprite_w_var, 0, 0)
        self._labeled_entry(self.fixed_inputs, "Sprite Height:", self.sprite_h_var, 0, 2)

        # auto-detect inputs
        self.auto_inputs = ttk.Frame(mode_frame)
        self._labeled_entry(self.auto_inputs, "Threshold:", self.detect_threshold_var, 0, 0)
        self._labeled_entry(self.auto_inputs, "Gap Tolerance:", self.detect_gap_var, 0, 2)
        self._labeled_entry(self.auto_inputs, "Min Size (px):", self.detect_minsize_var, 1, 0, pady=(6, 0))
        self._labeled_entry(self.auto_inputs, "Bg Color (hex):", self.detect_bgcolor_var, 1, 2, pady=(6, 0), entry_width=8)
        bgcolor_hint = ttk.Label(
            self.auto_inputs,
            text="Bg Color is only used for images without transparency;\n"
                 "leave blank to auto-sample from the top-left pixel.",
            foreground="#666", justify="left", wraplength=280,
        )
        bgcolor_hint.grid(row=2, column=0, columnspan=4, sticky="w", pady=(6, 0))
        self.detect_button = ttk.Button(self.auto_inputs, text="Detect Sprites", command=self.run_detect)
        self.detect_button.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        detect_status_label = ttk.Label(self.auto_inputs, textvariable=self.detect_status_var,
                                         foreground="#666", wraplength=280, justify="left")
        detect_status_label.grid(row=4, column=0, columnspan=4, sticky="w", pady=(6, 0))

        # json import inputs
        self.json_inputs = ttk.Frame(mode_frame)
        ttk.Button(self.json_inputs, text="Load JSON...", command=self.browse_json).pack(fill="x")
        json_path_label = ttk.Label(self.json_inputs, textvariable=self.json_path_var,
                                     foreground="#666", wraplength=280, justify="left")
        json_path_label.pack(anchor="w", pady=(6, 0))
        json_format_hint = ttk.Label(
            self.json_inputs,
            text="Supports a simple {\"sprites\":[{\"name\",\"x\",\"y\",\"width\",\"height\"}]} "
                 "list, or a TexturePacker-style {\"frames\": ...} atlas. Named entries keep "
                 "their JSON name as the output filename.",
            foreground="#666", justify="left", wraplength=280,
        )
        json_format_hint.pack(anchor="w", pady=(6, 0))
        self._wrap_labels += [bgcolor_hint, detect_status_label, json_path_label, json_format_hint]

        # --- margins / spacing / offset (grid & fixed modes only; the
        # section stays in place and its inputs are disabled rather than
        # hidden for auto/json modes, so toggling modes never reorders it) ---
        self.margin_frame = ttk.LabelFrame(controls_outer, text="3. Offset & Spacing", padding=10)
        self.margin_frame.pack(fill="x", pady=(0, 10))
        self.margin_entries = [
            self._labeled_entry(self.margin_frame, "Start X:", self.offset_x_var, 0, 0),
            self._labeled_entry(self.margin_frame, "Start Y:", self.offset_y_var, 0, 2),
            self._labeled_entry(self.margin_frame, "Spacing X:", self.spacing_x_var, 1, 0, pady=(6, 0)),
            self._labeled_entry(self.margin_frame, "Spacing Y:", self.spacing_y_var, 1, 2, pady=(6, 0)),
        ]
        self.margin_hint = ttk.Label(
            self.margin_frame,
            text="Start = top-left offset before the first sprite.\n"
                 "Spacing = gap between adjacent sprites.",
            foreground="#666", justify="left", wraplength=280,
        )
        self.margin_hint.grid(row=2, column=0, columnspan=4, sticky="w", pady=(8, 0))

        # Touch-friendly D-pad for nudging the grid's start offset without
        # having to type into the Start X/Y fields -- and the sheet itself
        # can also just be dragged (mouse or touch) to reposition it; see
        # the canvas bindings in _build_ui's preview section below.
        nudge_row = ttk.Frame(self.margin_frame)
        nudge_row.grid(row=3, column=0, columnspan=4, sticky="w", pady=(10, 0))
        ttk.Label(nudge_row, text="Nudge grid:").grid(row=0, column=0, sticky="w", padx=(0, 8))
        dpad = ttk.Frame(nudge_row)
        dpad.grid(row=0, column=1)

        def dpad_button(dx, dy, text):
            btn = tk.Button(dpad, text=text, width=3, height=1, font=("TkDefaultFont", 12, "bold"),
                             command=lambda: self._nudge_offset(dx, dy))
            self.margin_entries.append(btn)  # disabled together with the other offset controls
            return btn

        dpad_button(0, -1, "▲").grid(row=0, column=1, padx=2, pady=2)
        dpad_button(-1, 0, "◄").grid(row=1, column=0, padx=2, pady=2)
        dpad_button(1, 0, "►").grid(row=1, column=2, padx=2, pady=2)
        dpad_button(0, 1, "▼").grid(row=2, column=1, padx=2, pady=2)

        ttk.Label(nudge_row, text="Step (px):").grid(row=0, column=2, sticky="w", padx=(14, 4))
        step_entry = ttk.Entry(nudge_row, textvariable=self.nudge_step_var, width=5)
        step_entry.grid(row=0, column=3, sticky="w")
        self.margin_entries.append(step_entry)
        drag_hint = ttk.Label(
            self.margin_frame,
            text="Tip: you can also tap/click-drag directly on the sheet "
                 "preview to move the grid.",
            foreground="#666", justify="left", wraplength=280,
        )
        drag_hint.grid(row=4, column=0, columnspan=4, sticky="w", pady=(8, 0))
        self._wrap_labels += [self.margin_hint, drag_hint]

        # --- naming ---
        naming_frame = ttk.LabelFrame(controls_outer, text="4. Naming", padding=10)
        naming_frame.pack(fill="x", pady=(0, 10))
        self._labeled_entry(naming_frame, "Prefix:", self.prefix_var, 0, 0, entry_width=14)
        naming_row = ttk.Frame(naming_frame)
        naming_row.grid(row=1, column=0, columnspan=4, sticky="w", pady=(8, 0))
        ttk.Radiobutton(naming_row, text="Sequential (prefix_001.png)", variable=self.naming_var,
                         value="sequential", command=self._update_preview).pack(anchor="w")
        self.coords_naming_radio = ttk.Radiobutton(
            naming_row, text="Row/Col (prefix_r0_c1.png)", variable=self.naming_var,
            value="coords", command=self._update_preview)
        self.coords_naming_radio.pack(anchor="w")
        self.naming_hint = ttk.Label(
            naming_frame, foreground="#666", justify="left", wraplength=280)
        self.naming_hint.grid(row=2, column=0, columnspan=4, sticky="w", pady=(4, 0))
        ttk.Checkbutton(naming_frame, text="Skip fully transparent/blank tiles",
                         variable=self.skip_blank_var, command=self._update_preview).grid(
            row=3, column=0, columnspan=4, sticky="w", pady=(8, 0))
        self._wrap_labels.append(self.naming_hint)

        # --- output ---
        output_frame = ttk.LabelFrame(controls_outer, text="5. Export", padding=10)
        output_frame.pack(fill="x", pady=(0, 10))
        out_row = ttk.Frame(output_frame)
        out_row.pack(fill="x")
        ttk.Button(out_row, text="Choose Output Folder...", command=self.choose_output_dir).pack(
            side="left"
        )
        ttk.Button(out_row, text="Use Default", command=self.reset_output_dir).pack(
            side="left", padx=(6, 0)
        )
        self.output_label = ttk.Label(output_frame, text="Default: alongside source image",
                                       foreground="#666", wraplength=280)
        self.output_label.pack(anchor="w", pady=(6, 0))
        self._wrap_labels.append(self.output_label)
        ttk.Checkbutton(output_frame, text="Also create a .zip archive",
                         variable=self.make_zip_var).pack(anchor="w", pady=(8, 0))

        ttk.Button(output_frame, text="Export Sprites", command=self.export_sprites).pack(
            fill="x", pady=(10, 0)
        )

        self._on_mode_change()

        # -------- preview panel (right when wide, below when narrow) --------
        self.preview_outer = ttk.Frame(self.body, padding=(0, 10, 10, 10))
        self.preview_outer.rowconfigure(0, weight=1)
        self.preview_outer.columnconfigure(0, weight=1)

        canvas_frame = ttk.Frame(self.preview_outer, relief="sunken", borderwidth=1)
        canvas_frame.grid(row=0, column=0, sticky="nsew")

        self.canvas = tk.Canvas(canvas_frame, bg="#2b2b2b", width=CANVAS_W, height=CANVAS_H,
                                 highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_text(
            CANVAS_W // 2, CANVAS_H // 2,
            text="Open or drop a sprite sheet here",
            fill="#aaaaaa", font=("TkDefaultFont", 14), tags="placeholder"
        )
        self.canvas.bind("<Configure>", lambda e: self._update_preview())

        # Drag (mouse or touch, wherever the platform maps touch to mouse
        # events -- true of touchscreens under Tk on Windows/macOS/most
        # Linux desktops) directly on the sheet to reposition the grid in
        # "Rows x Columns" / "Fixed Sprite Size" mode, instead of only
        # being able to type into the Start X/Y fields.
        self.canvas.bind("<ButtonPress-1>", self._on_canvas_press)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)

        if DND_AVAILABLE:
            self.canvas.drop_target_register(DND_FILES)
            self.canvas.dnd_bind("<<Drop>>", self._on_drop)

        info_bar = ttk.Frame(self.preview_outer)
        info_bar.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        ttk.Label(info_bar, textvariable=self.info_var, foreground="#333").pack(anchor="w")

        # controls_container's own grid placement is handled by
        # _apply_responsive_layout(), which also places preview_outer.
        self.root.bind("<Configure>", self._on_root_configure)

    def _labeled_entry(self, parent, label, var, row, col, entry_width=8, pady=0):
        ttk.Label(parent, text=label).grid(row=row, column=col, sticky="w", padx=(0, 4), pady=pady)
        entry = ttk.Entry(parent, textvariable=var, width=entry_width)
        entry.grid(row=row, column=col + 1, sticky="w", padx=(0, 12), pady=pady)
        return entry

    # ------------------------------------------------------------------
    # Responsive layout: side-by-side on a wide window, stacked on a
    # narrow/phone-sized one. Re-evaluated on every resize.
    # ------------------------------------------------------------------
    def _on_root_configure(self, event):
        if event.widget is not self.root:
            return
        self._apply_responsive_layout()

    def _apply_responsive_layout(self):
        width = self.root.winfo_width()
        # winfo_width() reports 1 before the window is first drawn; treat
        # that as "wide" (the desktop-default layout) rather than narrow.
        narrow = 1 < width < BREAKPOINT_WIDTH
        mode = "narrow" if narrow else "wide"
        if mode == self._layout_mode:
            return
        self._layout_mode = mode

        self.body.columnconfigure(0, weight=1)
        self.body.columnconfigure(1, weight=0 if narrow else 1)
        self.body.rowconfigure(0, weight=0 if narrow else 1)
        self.body.rowconfigure(1, weight=1 if narrow else 0)

        if narrow:
            # Controls on top in a height-capped, scrollable strip so the
            # preview below always keeps enough room to be useful; sheet
            # preview underneath, full width.
            self.controls_canvas.configure(height=240)
            self.controls_container.grid(row=0, column=0, columnspan=2, sticky="ew")
            self.preview_outer.grid(row=1, column=0, columnspan=2, sticky="nsew")
        else:
            # grid() only changes the options passed to it -- columnspan
            # must be reset explicitly here or it would stick at 2 from a
            # previous narrow layout and center the panel instead of
            # pinning it to the left column.
            self.controls_canvas.configure(height=400)
            self.controls_container.grid(row=0, column=0, columnspan=1, sticky="ns")
            self.preview_outer.grid(row=0, column=1, columnspan=1, sticky="nsew")

    # ------------------------------------------------------------------
    # Touch/tap grid repositioning: D-pad nudge buttons, and drag-on-sheet
    # ------------------------------------------------------------------
    def _nudge_offset(self, dx, dy):
        if self.mode.get() not in ("grid", "fixed"):
            return
        step = max(1, _int_or(self.nudge_step_var.get(), 1))
        new_x = max(0, _int_or(self.offset_x_var.get(), 0) + dx * step)
        new_y = max(0, _int_or(self.offset_y_var.get(), 0) + dy * step)
        self.offset_x_var.set(str(new_x))
        self.offset_y_var.set(str(new_y))

    def _on_canvas_press(self, event):
        if self.image is None or self.mode.get() not in ("grid", "fixed"):
            return
        self._drag_start = (
            event.x, event.y,
            _int_or(self.offset_x_var.get(), 0), _int_or(self.offset_y_var.get(), 0),
        )

    def _on_canvas_drag(self, event):
        if self._drag_start is None:
            return
        start_x, start_y, start_off_x, start_off_y = self._drag_start
        scale = self.scale or 1.0
        dx_img = (event.x - start_x) / scale
        dy_img = (event.y - start_y) / scale
        img_w, img_h = self.image.size
        new_x = min(max(0, round(start_off_x + dx_img)), max(0, img_w - 1))
        new_y = min(max(0, round(start_off_y + dy_img)), max(0, img_h - 1))
        self.offset_x_var.set(str(new_x))
        self.offset_y_var.set(str(new_y))

    def _on_canvas_release(self, event):
        self._drag_start = None

    def _bind_traces(self):
        watched = [
            self.rows_var, self.cols_var, self.sprite_w_var, self.sprite_h_var,
            self.offset_x_var, self.offset_y_var, self.spacing_x_var, self.spacing_y_var,
        ]
        for v in watched:
            v.trace_add("write", lambda *a: self._update_preview())

    def _on_mode_change(self):
        mode = self.mode.get()
        self.grid_inputs.pack_forget()
        self.fixed_inputs.pack_forget()
        self.auto_inputs.pack_forget()
        self.json_inputs.pack_forget()

        if mode == "grid":
            self.grid_inputs.pack(fill="x", pady=(8, 0))
        elif mode == "fixed":
            self.fixed_inputs.pack(fill="x", pady=(8, 0))
        elif mode == "auto":
            self.auto_inputs.pack(fill="x", pady=(8, 0))
        else:  # json
            self.json_inputs.pack(fill="x", pady=(8, 0))

        # Offset & spacing only make sense for the two grid-based modes;
        # disable (rather than hide) so the panel layout never reorders.
        grid_based = mode in ("grid", "fixed")
        for entry in self.margin_entries:
            entry.configure(state="normal" if grid_based else "disabled")
        self.margin_hint.configure(
            text=("Start = top-left offset before the first sprite.\n"
                  "Spacing = gap between adjacent sprites.") if grid_based
            else "Not used in this mode — sprite bounds come from the "
                 "detected content or the imported coordinates instead."
        )

        # Row/Col naming has no meaning for auto-detected or JSON-imported
        # sprites -- there's no grid to derive coordinates from.
        if mode in ("auto", "json"):
            self.coords_naming_radio.configure(state="disabled")
            if self.naming_var.get() == "coords":
                self.naming_var.set("sequential")
            hint = ("Detected/imported sprites use sequential naming, unless a JSON "
                    "entry supplies its own \"name\" (which always takes priority).")
        else:
            self.coords_naming_radio.configure(state="normal")
            hint = ""
        self.naming_hint.configure(text=hint)

        # self.canvas doesn't exist yet on the very first call, made while
        # _build_ui is still constructing the controls panel.
        if hasattr(self, "canvas"):
            self.canvas.configure(cursor="fleur" if grid_based else "arrow")
            if not grid_based:
                self._drag_start = None

        self._update_preview()

    # ------------------------------------------------------------------
    # File loading
    # ------------------------------------------------------------------
    def browse_file(self):
        path = filedialog.askopenfilename(
            title="Select a sprite sheet",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.gif *.tga *.webp"),
                       ("All files", "*.*")],
        )
        if path:
            self.load_image(path)

    def _on_drop(self, event):
        # tkinterdnd2 wraps multi-file paths in braces; take the first file.
        raw = event.data
        path = raw.strip()
        if path.startswith("{") and path.endswith("}"):
            path = path[1:-1]
        else:
            path = path.split()[0]
        if os.path.splitext(path)[1].lower() not in SUPPORTED_EXTS:
            messagebox.showerror(APP_TITLE, f"Unsupported file type: {path}")
            return
        self.load_image(path)

    def load_image(self, path):
        try:
            img = Image.open(path)
            img.load()
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Could not open image:\n{e}")
            return

        self.image_path = path
        self.image = img
        self.file_label.config(text=f"{os.path.basename(path)}  ({img.width}x{img.height}px)")
        self.reset_output_dir()
        self.status_var.set(f"Loaded {os.path.basename(path)}")
        self.canvas.delete("placeholder")

        # Detected/imported sprite boxes are tied to the previous image.
        self.detected_rects = None
        self._json_error = None
        self.detect_status_var.set("Click “Detect Sprites” to scan for content.")
        self.json_path_var.set("No JSON file loaded")

        self._update_preview()

    # ------------------------------------------------------------------
    # Auto-detect
    # ------------------------------------------------------------------
    def _parse_hex_color(self, text):
        text = text.strip().lstrip("#")
        if not text:
            return None
        try:
            if len(text) == 3:
                text = "".join(c * 2 for c in text)
            if len(text) != 6:
                return None
            return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            return None

    def run_detect(self):
        if self.image is None:
            messagebox.showwarning(APP_TITLE, "Please load a sprite sheet first.")
            return
        if self._detecting:
            return

        threshold = max(0, min(255, _int_or(self.detect_threshold_var.get(), 16)))
        gap = max(0, _int_or(self.detect_gap_var.get(), 2))
        min_size = max(1, _int_or(self.detect_minsize_var.get(), 4))
        bg_color = self._parse_hex_color(self.detect_bgcolor_var.get())

        self._detecting = True
        self.detect_button.configure(state="disabled")
        self.detect_status_var.set("Detecting… this can take a few seconds for large images.")
        self.status_var.set("Detecting sprites...")

        image = self.image
        result_queue = queue.Queue()

        def worker():
            try:
                rects = detect_sprites(
                    image, threshold=threshold, gap_tolerance=gap,
                    min_size=min_size, bg_color=bg_color,
                )
                result_queue.put(("ok", rects))
            except Exception as e:  # pragma: no cover - defensive
                result_queue.put(("error", str(e)))

        threading.Thread(target=worker, daemon=True).start()
        self.root.after(80, lambda: self._poll_detect(result_queue))

    def _poll_detect(self, result_queue):
        try:
            status, payload = result_queue.get_nowait()
        except queue.Empty:
            self.root.after(80, lambda: self._poll_detect(result_queue))
            return

        self._detecting = False
        self.detect_button.configure(state="normal")

        if status == "error":
            self.detect_status_var.set(f"⚠ Detection failed: {payload}")
            self.status_var.set("Detection failed.")
            return

        rects = payload
        self.detected_rects = [
            (0, i, x0, y0, x1, y1, None) for i, (x0, y0, x1, y1) in enumerate(rects)
        ]
        if rects:
            self.detect_status_var.set(f"{len(rects)} sprite(s) detected.")
        else:
            self.detect_status_var.set(
                "No sprite content detected. Try lowering the threshold, "
                "increasing gap tolerance, or checking the background color."
            )
        self.status_var.set(f"Detected {len(rects)} sprite(s).")
        self._update_preview()

    # ------------------------------------------------------------------
    # JSON import
    # ------------------------------------------------------------------
    def browse_json(self):
        path = filedialog.askopenfilename(
            title="Select a sprite coordinate JSON file",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if path:
            self.load_json(path)

    def load_json(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            entries = parse_json_sprites(data)
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Could not load JSON file:\n{e}")
            return

        img_w, img_h = (self.image.size if self.image else (None, None))
        rects, skipped = [], 0
        for i, e in enumerate(entries):
            x0, y0, w, h = e["x"], e["y"], e["w"], e["h"]
            if w <= 0 or h <= 0:
                skipped += 1
                continue
            x1, y1 = x0 + w, y0 + h
            if img_w is not None:
                if x0 < 0 or y0 < 0 or x1 > img_w or y1 > img_h:
                    skipped += 1
                    continue
            rects.append((0, i, x0, y0, x1, y1, e["name"]))

        self.detected_rects = rects
        self.json_path_var.set(
            f"{os.path.basename(path)} — {len(rects)} sprite(s) loaded"
            + (f", {skipped} skipped (out of bounds)" if skipped else "")
        )
        self.status_var.set(f"Loaded {len(rects)} sprite(s) from {os.path.basename(path)}")
        self._update_preview()

    # ------------------------------------------------------------------
    # Grid computation
    # ------------------------------------------------------------------
    def compute_rects(self):
        """Return (rects, error). rects is a list of
        (row, col, x0, y0, x1, y1, name) in ORIGINAL image pixel
        coordinates; name is None unless a JSON entry supplied one."""
        if self.image is None:
            return [], None

        mode = self.mode.get()

        if mode == "auto":
            if self.detected_rects is None:
                return [], None
            if not self.detected_rects:
                return [], "No sprites detected yet. Click “Detect Sprites”."
            return self.detected_rects, None

        if mode == "json":
            if self.detected_rects is None:
                return [], None
            if not self.detected_rects:
                return [], "No sprites loaded. Click “Load JSON...”."
            return self.detected_rects, None

        img_w, img_h = self.image.size
        offset_x = _int_or(self.offset_x_var.get(), 0)
        offset_y = _int_or(self.offset_y_var.get(), 0)
        spacing_x = _int_or(self.spacing_x_var.get(), 0)
        spacing_y = _int_or(self.spacing_y_var.get(), 0)

        if offset_x < 0 or offset_y < 0 or spacing_x < 0 or spacing_y < 0:
            return [], "Offset and spacing must be zero or positive."

        if mode == "grid":
            rows = _int_or(self.rows_var.get(), 0)
            cols = _int_or(self.cols_var.get(), 0)
            if rows <= 0 or cols <= 0:
                return [], "Rows and columns must be positive integers."
            avail_w = img_w - offset_x - spacing_x * (cols - 1)
            avail_h = img_h - offset_y - spacing_y * (rows - 1)
            if avail_w <= 0 or avail_h <= 0:
                return [], "Rows/columns + spacing/offset are larger than the image."
            cell_w = avail_w / cols
            cell_h = avail_h / rows
            if cell_w < 1 or cell_h < 1:
                return [], "Computed sprite size is smaller than 1px. Reduce rows/columns."
        else:  # fixed
            cell_w = _int_or(self.sprite_w_var.get(), 0)
            cell_h = _int_or(self.sprite_h_var.get(), 0)
            if cell_w <= 0 or cell_h <= 0:
                return [], "Sprite width and height must be positive integers."
            cols = int((img_w - offset_x + spacing_x) // (cell_w + spacing_x)) if (cell_w + spacing_x) > 0 else 0
            rows = int((img_h - offset_y + spacing_y) // (cell_h + spacing_y)) if (cell_h + spacing_y) > 0 else 0
            if rows <= 0 or cols <= 0:
                return [], "No sprites fit with the current size/offset/spacing."

        rects = []
        for r in range(rows):
            for c in range(cols):
                x0 = offset_x + c * (cell_w + spacing_x)
                y0 = offset_y + r * (cell_h + spacing_y)
                x1 = x0 + cell_w
                y1 = y0 + cell_h
                rx0, ry0, rx1, ry1 = round(x0), round(y0), round(x1), round(y1)
                rx1 = min(rx1, img_w)
                ry1 = min(ry1, img_h)
                if rx1 <= rx0 or ry1 <= ry0:
                    continue
                rects.append((r, c, rx0, ry0, rx1, ry1, None))
        return rects, None

    # ------------------------------------------------------------------
    # Preview rendering
    # ------------------------------------------------------------------
    def _update_preview(self):
        if self.image is None:
            return

        canvas = self.canvas
        canvas.delete("sheet", "grid", "error", "draghint")

        cw = max(canvas.winfo_width(), 100)
        ch = max(canvas.winfo_height(), 100)
        img_w, img_h = self.image.size
        scale = min(cw / img_w, ch / img_h)
        scale = max(scale, 0.01)
        disp_w, disp_h = max(1, int(img_w * scale)), max(1, int(img_h * scale))

        display_img = self.image
        if display_img.mode not in ("RGB", "RGBA"):
            display_img = display_img.convert("RGBA")
        thumb = display_img.resize((disp_w, disp_h), Image.LANCZOS)
        self.preview_photo = ImageTk.PhotoImage(thumb)

        off_x = (cw - disp_w) // 2
        off_y = (ch - disp_h) // 2
        self.scale = scale
        self.offset_canvas = (off_x, off_y)

        canvas.create_image(off_x, off_y, anchor="nw", image=self.preview_photo, tags="sheet")

        rects, error = self.compute_rects()

        if error:
            self.info_var.set(f"⚠ {error}")
            canvas.create_text(cw // 2, ch - 16, text=error, fill="#ff6b6b", tags="error")
            return

        for (r, c, x0, y0, x1, y1, name) in rects:
            cx0, cy0 = off_x + x0 * scale, off_y + y0 * scale
            cx1, cy1 = off_x + x1 * scale, off_y + y1 * scale
            canvas.create_rectangle(cx0, cy0, cx1, cy1, outline="#00e5ff", width=1, tags="grid")

        if rects:
            sample_w = rects[0][4] - rects[0][2]
            sample_h = rects[0][5] - rects[0][3]
            uniform = self.mode.get() in ("grid", "fixed")
            size_note = f"each ~{sample_w}x{sample_h}px" if uniform else "varying sizes"
            self.info_var.set(f"{len(rects)} sprite(s) — {size_note}")
        elif self.mode.get() not in ("auto", "json"):
            self.info_var.set("No sprites in current configuration.")
        else:
            self.info_var.set("")

        if self.mode.get() in ("grid", "fixed"):
            canvas.create_text(
                cw // 2, ch - 14, text="Tap/drag the sheet to move the grid",
                fill="#dddddd", font=("TkDefaultFont", 9), tags="draghint",
            )

    # ------------------------------------------------------------------
    # Output directory handling
    # ------------------------------------------------------------------
    def reset_output_dir(self):
        self.output_dir_var.set("")
        self.output_label.config(text="Default: alongside source image")

    def choose_output_dir(self):
        path = filedialog.askdirectory(title="Choose parent folder for exported sprites")
        if path:
            self.output_dir_var.set(path)
            self.output_label.config(text=f"Parent folder: {path}")

    def _make_output_folder(self):
        prefix = self.prefix_var.get().strip() or "sprite"
        base_name = os.path.splitext(os.path.basename(self.image_path))[0] if self.image_path else prefix
        parent = self.output_dir_var.get().strip()
        if not parent:
            parent = os.path.dirname(self.image_path) or os.getcwd()

        folder_name = f"{base_name}_sliced"
        target = os.path.join(parent, folder_name)
        n = 1
        while os.path.exists(target):
            target = os.path.join(parent, f"{folder_name}_{n}")
            n += 1
        os.makedirs(target, exist_ok=True)
        return target

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------
    def export_sprites(self):
        if self.image is None:
            messagebox.showwarning(APP_TITLE, "Please load a sprite sheet first.")
            return

        rects, error = self.compute_rects()
        if error:
            messagebox.showerror(APP_TITLE, error)
            return
        if not rects:
            messagebox.showwarning(APP_TITLE, "No sprites to export with the current settings.")
            return

        try:
            out_dir = self._make_output_folder()
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Could not create output folder:\n{e}")
            return

        prefix = self.prefix_var.get().strip() or "sprite"
        naming = self.naming_var.get()
        skip_blank = self.skip_blank_var.get()

        source = self.image
        total_digits = max(3, len(str(len(rects))))
        used_names = set()

        exported = 0
        skipped = 0
        for idx, (r, c, x0, y0, x1, y1, name) in enumerate(rects, start=1):
            tile = source.crop((x0, y0, x1, y1))

            if skip_blank and tile.mode in ("RGBA", "LA"):
                alpha = tile.getchannel("A")
                if alpha.getbbox() is None:
                    skipped += 1
                    continue

            if name:
                stem = sanitize_filename(name)
                fname = f"{stem}.png"
                dedupe = 2
                while fname in used_names:
                    fname = f"{stem}_{dedupe}.png"
                    dedupe += 1
            elif naming == "coords":
                fname = f"{prefix}_r{r}_c{c}.png"
            else:
                fname = f"{prefix}_{idx:0{total_digits}d}.png"
            used_names.add(fname)

            tile.save(os.path.join(out_dir, fname))
            exported += 1

        zip_path = None
        if self.make_zip_var.get():
            try:
                archive_base = out_dir.rstrip("/\\")
                zip_path = shutil.make_archive(archive_base, "zip", root_dir=out_dir)
            except Exception as e:
                messagebox.showwarning(APP_TITLE, f"Sprites exported, but zipping failed:\n{e}")

        msg = f"Exported {exported} sprite(s) to:\n{out_dir}"
        if skipped:
            msg += f"\n({skipped} blank tile(s) skipped)"
        if zip_path:
            msg += f"\n\nZip archive created:\n{zip_path}"
        self.status_var.set(f"Exported {exported} sprite(s) to {out_dir}" + (f" (+zip)" if zip_path else ""))

        open_folder = messagebox.askyesno(APP_TITLE, msg + "\n\nOpen the output folder now?")
        if open_folder:
            self._open_folder(out_dir)

    @staticmethod
    def _open_folder(path):
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception:
            pass


def main():
    if DND_AVAILABLE:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()

    try:
        style = ttk.Style(root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
    except Exception:
        pass

    app = SpriteSlicerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
