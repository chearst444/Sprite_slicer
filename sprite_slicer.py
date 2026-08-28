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
import sys
import shutil
import tempfile
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    from PIL import Image, ImageTk
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


def _int_or(value, default=0):
    try:
        v = int(float(value))
        return v
    except (TypeError, ValueError):
        return default


class SpriteSlicerApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.minsize(1080, 700)

        # ---- state -------------------------------------------------
        self.image_path = None          # path to source sprite sheet
        self.image = None                # PIL.Image (full resolution, original mode)
        self.preview_photo = None        # ImageTk.PhotoImage currently shown
        self.scale = 1.0                 # scale factor: displayed / original
        self.offset_canvas = (0, 0)      # top-left of image on canvas

        # slicing config vars
        self.mode = tk.StringVar(value="grid")            # "grid" | "fixed"
        self.rows_var = tk.StringVar(value="4")
        self.cols_var = tk.StringVar(value="4")
        self.sprite_w_var = tk.StringVar(value="32")
        self.sprite_h_var = tk.StringVar(value="32")
        self.offset_x_var = tk.StringVar(value="0")
        self.offset_y_var = tk.StringVar(value="0")
        self.spacing_x_var = tk.StringVar(value="0")
        self.spacing_y_var = tk.StringVar(value="0")

        self.prefix_var = tk.StringVar(value="sprite")
        self.naming_var = tk.StringVar(value="sequential")  # "sequential" | "coords"
        self.skip_blank_var = tk.BooleanVar(value=True)
        self.make_zip_var = tk.BooleanVar(value=False)
        self.output_dir_var = tk.StringVar(value="")  # override; blank = auto next to source

        self.status_var = tk.StringVar(value="Open a sprite sheet to get started.")
        self.info_var = tk.StringVar(value="")

        self._build_ui()
        self._bind_traces()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self):
        root = self.root
        root.columnconfigure(0, weight=0)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        # -------- left: controls panel (scrollable) --------
        controls_outer = ttk.Frame(root, padding=(10, 10))
        controls_outer.grid(row=0, column=0, sticky="ns")

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
        ttk.Label(import_frame, text=drop_hint, foreground="#666", wraplength=280).pack(
            anchor="w", pady=(6, 0)
        )
        self.file_label = ttk.Label(import_frame, text="No file loaded", foreground="#333",
                                     wraplength=280)
        self.file_label.pack(anchor="w", pady=(6, 0))

        # --- slicing mode ---
        mode_frame = ttk.LabelFrame(controls_outer, text="2. Grid / Slicing", padding=10)
        mode_frame.pack(fill="x", pady=(0, 10))

        mode_row = ttk.Frame(mode_frame)
        mode_row.pack(fill="x")
        ttk.Radiobutton(mode_row, text="Rows x Columns", variable=self.mode,
                         value="grid", command=self._on_mode_change).pack(side="left")
        ttk.Radiobutton(mode_row, text="Fixed Sprite Size (px)", variable=self.mode,
                         value="fixed", command=self._on_mode_change).pack(side="left", padx=(12, 0))

        # grid inputs
        self.grid_inputs = ttk.Frame(mode_frame)
        self.grid_inputs.pack(fill="x", pady=(8, 0))
        self._labeled_entry(self.grid_inputs, "Rows:", self.rows_var, 0, 0)
        self._labeled_entry(self.grid_inputs, "Columns:", self.cols_var, 0, 2)

        # fixed-size inputs
        self.fixed_inputs = ttk.Frame(mode_frame)
        self._labeled_entry(self.fixed_inputs, "Sprite Width:", self.sprite_w_var, 0, 0)
        self._labeled_entry(self.fixed_inputs, "Sprite Height:", self.sprite_h_var, 0, 2)

        # --- margins / spacing / offset ---
        margin_frame = ttk.LabelFrame(controls_outer, text="3. Offset & Spacing", padding=10)
        margin_frame.pack(fill="x", pady=(0, 10))
        self._labeled_entry(margin_frame, "Start X:", self.offset_x_var, 0, 0)
        self._labeled_entry(margin_frame, "Start Y:", self.offset_y_var, 0, 2)
        self._labeled_entry(margin_frame, "Spacing X:", self.spacing_x_var, 1, 0, pady=(6, 0))
        self._labeled_entry(margin_frame, "Spacing Y:", self.spacing_y_var, 1, 2, pady=(6, 0))
        ttk.Label(
            margin_frame,
            text="Start = top-left offset before the first sprite.\n"
                 "Spacing = gap between adjacent sprites.",
            foreground="#666", justify="left"
        ).grid(row=2, column=0, columnspan=4, sticky="w", pady=(8, 0))

        # --- naming ---
        naming_frame = ttk.LabelFrame(controls_outer, text="4. Naming", padding=10)
        naming_frame.pack(fill="x", pady=(0, 10))
        self._labeled_entry(naming_frame, "Prefix:", self.prefix_var, 0, 0, entry_width=14)
        naming_row = ttk.Frame(naming_frame)
        naming_row.grid(row=1, column=0, columnspan=4, sticky="w", pady=(8, 0))
        ttk.Radiobutton(naming_row, text="Sequential (prefix_001.png)", variable=self.naming_var,
                         value="sequential", command=self._update_preview).pack(anchor="w")
        ttk.Radiobutton(naming_row, text="Row/Col (prefix_r0_c1.png)", variable=self.naming_var,
                         value="coords", command=self._update_preview).pack(anchor="w")
        ttk.Checkbutton(naming_frame, text="Skip fully transparent/blank tiles",
                         variable=self.skip_blank_var, command=self._update_preview).grid(
            row=2, column=0, columnspan=4, sticky="w", pady=(8, 0))

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
        ttk.Checkbutton(output_frame, text="Also create a .zip archive",
                         variable=self.make_zip_var).pack(anchor="w", pady=(8, 0))

        ttk.Button(output_frame, text="Export Sprites", command=self.export_sprites).pack(
            fill="x", pady=(10, 0)
        )

        self._on_mode_change()

        # -------- right: preview panel --------
        preview_outer = ttk.Frame(root, padding=(0, 10, 10, 10))
        preview_outer.grid(row=0, column=1, sticky="nsew")
        preview_outer.rowconfigure(0, weight=1)
        preview_outer.columnconfigure(0, weight=1)

        canvas_frame = ttk.Frame(preview_outer, relief="sunken", borderwidth=1)
        canvas_frame.grid(row=0, column=0, sticky="nsew")
        preview_outer.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(canvas_frame, bg="#2b2b2b", width=CANVAS_W, height=CANVAS_H,
                                 highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_text(
            CANVAS_W // 2, CANVAS_H // 2,
            text="Open or drop a sprite sheet here",
            fill="#aaaaaa", font=("TkDefaultFont", 14), tags="placeholder"
        )
        self.canvas.bind("<Configure>", lambda e: self._update_preview())

        if DND_AVAILABLE:
            self.canvas.drop_target_register(DND_FILES)
            self.canvas.dnd_bind("<<Drop>>", self._on_drop)

        info_bar = ttk.Frame(preview_outer)
        info_bar.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        ttk.Label(info_bar, textvariable=self.info_var, foreground="#333").pack(anchor="w")

        status_bar = ttk.Frame(root, relief="sunken", borderwidth=1)
        status_bar.grid(row=1, column=0, columnspan=2, sticky="ew")
        ttk.Label(status_bar, textvariable=self.status_var, padding=(6, 3)).pack(anchor="w")

    def _labeled_entry(self, parent, label, var, row, col, entry_width=8, pady=0):
        ttk.Label(parent, text=label).grid(row=row, column=col, sticky="w", padx=(0, 4), pady=pady)
        entry = ttk.Entry(parent, textvariable=var, width=entry_width)
        entry.grid(row=row, column=col + 1, sticky="w", padx=(0, 12), pady=pady)
        return entry

    def _bind_traces(self):
        watched = [
            self.rows_var, self.cols_var, self.sprite_w_var, self.sprite_h_var,
            self.offset_x_var, self.offset_y_var, self.spacing_x_var, self.spacing_y_var,
        ]
        for v in watched:
            v.trace_add("write", lambda *a: self._update_preview())

    def _on_mode_change(self):
        if self.mode.get() == "grid":
            self.fixed_inputs.pack_forget()
            self.grid_inputs.pack(fill="x", pady=(8, 0))
        else:
            self.grid_inputs.pack_forget()
            self.fixed_inputs.pack(fill="x", pady=(8, 0))
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
        self._update_preview()

    # ------------------------------------------------------------------
    # Grid computation
    # ------------------------------------------------------------------
    def compute_rects(self):
        """Return (rects, error) where rects is a list of
        (row, col, x0, y0, x1, y1) in ORIGINAL image pixel coordinates."""
        if self.image is None:
            return [], None

        img_w, img_h = self.image.size
        offset_x = _int_or(self.offset_x_var.get(), 0)
        offset_y = _int_or(self.offset_y_var.get(), 0)
        spacing_x = _int_or(self.spacing_x_var.get(), 0)
        spacing_y = _int_or(self.spacing_y_var.get(), 0)

        if offset_x < 0 or offset_y < 0 or spacing_x < 0 or spacing_y < 0:
            return [], "Offset and spacing must be zero or positive."

        if self.mode.get() == "grid":
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
        else:
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
                rects.append((r, c, rx0, ry0, rx1, ry1))
        return rects, None

    # ------------------------------------------------------------------
    # Preview rendering
    # ------------------------------------------------------------------
    def _update_preview(self):
        if self.image is None:
            return

        canvas = self.canvas
        canvas.delete("sheet", "grid", "error")

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

        for (r, c, x0, y0, x1, y1) in rects:
            cx0, cy0 = off_x + x0 * scale, off_y + y0 * scale
            cx1, cy1 = off_x + x1 * scale, off_y + y1 * scale
            canvas.create_rectangle(cx0, cy0, cx1, cy1, outline="#00e5ff", width=1, tags="grid")

        if rects:
            sample_w = rects[0][4] - rects[0][2]
            sample_h = rects[0][5] - rects[0][3]
            self.info_var.set(
                f"{len(rects)} sprite(s) — each ~{sample_w}x{sample_h}px"
            )
        else:
            self.info_var.set("No sprites in current configuration.")

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

        exported = 0
        skipped = 0
        for idx, (r, c, x0, y0, x1, y1) in enumerate(rects, start=1):
            tile = source.crop((x0, y0, x1, y1))

            if skip_blank and tile.mode in ("RGBA", "LA"):
                alpha = tile.getchannel("A")
                if alpha.getbbox() is None:
                    skipped += 1
                    continue

            if naming == "coords":
                fname = f"{prefix}_r{r}_c{c}.png"
            else:
                fname = f"{prefix}_{idx:0{total_digits}d}.png"

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
