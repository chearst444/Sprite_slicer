# Sprite Sheet Splitter

A lightweight, standalone desktop utility that slices a sprite sheet image
into individual sprite files. Built with Python, Tkinter, and Pillow — no
browser, no server, no build step.

## Features

- **Import**: Open a sprite sheet via file browser, or drag & drop it
  straight onto the preview (PNG, JPG, BMP, GIF, TGA, WEBP).
- **Slicing configuration**:
  - *Rows x Columns* mode — specify a grid and cell size is derived
    automatically.
  - *Fixed Sprite Size* mode — specify exact pixel width/height per sprite
    and the number of rows/columns is auto-detected from the sheet size.
  - Start offset (X, Y) and spacing between sprites, for sheets with
    padding/margins/gutters.
- **Live grid preview** — an overlay is drawn directly on the sprite sheet
  so you can verify slice boundaries before exporting anything.
- **Automatic naming** — sequential (`sprite_001.png`, `sprite_002.png`, ...)
  or grid-coordinate based (`sprite_r0_c1.png`), with a custom prefix.
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
2. **Configure slicing** — choose Rows x Columns or Fixed Sprite Size, and
   set start offset / spacing if your sheet has padding or gutters between
   sprites.
3. **Check the preview** — cyan grid lines overlay the sheet live as you
   type, so you can confirm the slices line up before exporting.
4. **Set naming** — pick a prefix and naming pattern.
5. **Export** — optionally pick an output folder and/or enable "Also create
   a .zip archive", then click **Export Sprites**. You'll be asked if you'd
   like the output folder opened for you.

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
