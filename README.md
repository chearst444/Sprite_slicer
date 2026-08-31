# Sprite Sheet Splitter

A lightweight, standalone desktop utility that slices a sprite sheet image
into individual sprite files. Built with Python, Tkinter, and Pillow — no
browser, no server, no build step.

## Features

- **Import**: Open a sprite sheet via file browser, or drag & drop it
  straight onto the preview (PNG, JPG, BMP, GIF, TGA, WEBP).
- **Slicing configuration** — four methods, for uniform grids as well as
  irregular, varying-size sprite sheets:
  - *Rows x Columns* — specify a grid and cell size is derived automatically.
  - *Fixed Sprite Size* — specify exact pixel width/height per sprite, and
    the number of rows/columns is derived from the sheet size.
  - *Auto-Detect* — scans the sheet's actual content (transparency, or a
    flat background color for images without an alpha channel) and finds
    each sprite's real bounding box via connected-component analysis, so
    sprites of *different* sizes on the same sheet are sliced accurately
    instead of forcing a uniform grid. Tunable threshold, a gap-tolerance
    to merge sprites split by a thin gap (e.g. separated limbs), and a
    minimum-size filter to ignore stray noise pixels.
  - *Import Coordinates (JSON)* — load exact sprite bounding boxes from a
    metadata file instead of computing them: either a simple
    `{"sprites": [{"name","x","y","width","height"}]}` list, or a
    TexturePacker-style `{"frames": ...}` atlas (hash or array form).
    Named entries keep their JSON name as the output filename.
  - Start offset (X, Y) and spacing between sprites (grid modes only), for
    sheets with padding/margins/gutters.
- **Live preview** — an overlay is drawn directly on the sprite sheet so you
  can verify slice boundaries before exporting anything, whether from a
  uniform grid, detected content, or an imported mapping.
- **Touch-friendly grid positioning** — in *Rows x Columns* / *Fixed Sprite
  Size* mode, tap-and-drag (or click-and-drag) directly on the sheet preview
  to move the grid, or use the on-screen ▲▼◄► nudge buttons next to the
  offset fields. Both work alongside typing exact values into Start X/Y.
- **Responsive window** — the window can be resized down to phone/tablet
  proportions: below ~820px wide, the controls panel stacks above the
  preview (instead of a cramped sidebar) and scrolls independently so
  nothing is pushed off-screen.
- **Automatic naming** — sequential (`sprite_001.png`, `sprite_002.png`, ...)
  or grid-coordinate based (`sprite_r0_c1.png`), with a custom prefix. A
  JSON entry's own `"name"` always takes priority when present.
- **Skip blank tiles** — optionally skip fully transparent cells (useful for
  sheets that don't perfectly fill their grid).
- **Directory management** — a dedicated output folder (`<sheet_name>_sliced`,
  auto-incremented if it already exists) is created automatically next to
  the source image, or anywhere you choose.
- **One-click export** — saves every sprite as its own PNG, with an optional
  `.zip` archive of the whole collection for easy download/sharing.

## Setup

```bash
pip install -r requirements.txt
```

`Pillow` is required. `tkinterdnd2` is optional — it only enables drag &
drop; without it, use the "Browse..." button instead.

> Tkinter itself ships with most Python installs. On some Linux distros you
> may need to install it separately, e.g. `sudo apt install python3-tk`.

## Run

```bash
python sprite_slicer.py
```

## Usage

1. **Load a sheet** — click "Browse for Image..." or drag an image onto the
   preview panel.
2. **Choose a slicing method**:
   - *Rows x Columns* / *Fixed Sprite Size* — set start offset / spacing if
     your sheet has padding or gutters between sprites; the preview updates
     live as you type.
   - *Auto-Detect* — adjust threshold / gap tolerance / min size if needed,
     then click **Detect Sprites** (this scans the image, so it runs on
     demand rather than on every keystroke).
   - For *Rows x Columns* / *Fixed Sprite Size*, you can also drag directly
     on the sheet preview (mouse or touch) to reposition the grid, or use
     the ▲▼◄► nudge buttons instead of typing into Start X/Y.
   - *Import Coordinates (JSON)* — click **Load JSON...** and pick a
     metadata file (see below for the supported formats).
3. **Check the preview** — cyan boxes overlay the sheet so you can confirm
   the slices are correct before exporting, whether uniform, detected, or
   imported.
4. **Set naming** — pick a prefix and naming pattern.
5. **Export** — optionally pick an output folder and/or enable "Also create
   a .zip archive", then click **Export Sprites**. You'll be asked if you'd
   like the output folder opened for you.

## JSON coordinate format

For *Import Coordinates (JSON)*, either of these shapes works:

```json
{
  "sprites": [
    { "name": "hero_idle_0", "x": 0, "y": 0, "width": 32, "height": 48 },
    { "name": "hero_idle_1", "x": 32, "y": 0, "width": 32, "height": 48 }
  ]
}
```

or a TexturePacker-style atlas export:

```json
{
  "frames": {
    "hero_idle_0.png": { "frame": { "x": 0, "y": 0, "w": 32, "h": 48 } },
    "hero_idle_1.png": { "frame": { "x": 32, "y": 0, "w": 32, "h": 48 } }
  }
}
```

`width`/`height` and `w`/`h` are both accepted. Entries without a `name`
fall back to the prefix + naming pattern set in step 4; entries that fall
outside the loaded image's bounds are skipped and counted in the status line.

## Packaging as a standalone executable (optional)

To hand this off as a double-clickable app with no Python install required,
use [PyInstaller](https://pyinstaller.org/):

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "SpriteSheetSplitter" sprite_slicer.py
```

The bundled executable will be in `dist/`.

## Project structure

```
sprite_slicer.py    # the entire application
requirements.txt    # Python dependencies
README.md
```
