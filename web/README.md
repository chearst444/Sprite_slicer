# Sprite Sheet Splitter — Web App

A mobile-friendly, browser-based version of Sprite Sheet Splitter. Same
purpose as the Python/Tkinter desktop app in the repo root, rebuilt as a
static, dependency-free web page (HTML/CSS/vanilla JS) so it runs on
**phones, tablets, and desktops** — anywhere with a modern browser.

Everything happens on-device: the sprite sheet is decoded and sliced
entirely in the browser via `<canvas>`, and nothing is ever uploaded
anywhere.

## Features

Feature parity with the desktop app — four slicing methods, for uniform
grids as well as irregular, varying-size sprite sheets:

- **Import** — tap to choose an image, or drag & drop on desktop.
- **Rows × Columns** or **Fixed Sprite Size** — configurable start offset
  (X, Y) and spacing between sprites.
- **Auto-Detect** — scans the sheet's actual content (transparency, or a
  flat background color for images without an alpha channel) and finds
  each sprite's real bounding box via connected-component analysis
  (`detect.js`), so sprites of *different* sizes on the same sheet are
  sliced accurately instead of forcing a uniform grid. Tunable threshold, a
  gap-tolerance to merge sprites split by a thin gap, and a minimum-size
  filter to ignore stray noise pixels.
- **Import Coordinates (JSON)** — load exact sprite bounding boxes from a
  metadata file instead of computing them: either a simple
  `{"sprites": [{"name","x","y","width","height"}]}` list, or a
  TexturePacker-style `{"frames": ...}` atlas (hash or array form). Named
  entries keep their JSON name as the output filename.
- **Live preview** overlaid on the sheet, recalculated live for the grid
  modes and on-demand (via a "Detect Sprites" / "Load JSON..." action) for
  the content-based modes.
- **Automatic naming** — sequential (`sprite_001.png`) or grid-coordinate
  (`sprite_r0_c1.png`), with a custom prefix. A JSON entry's own `"name"`
  always takes priority when present.
- **Skip fully transparent tiles** option.
- **One-click export** — bundles every sliced sprite into a `.zip` and
  downloads it (works identically on iOS, Android, and desktop browsers).
- **Save to Folder** — on browsers that support the File System Access API
  (e.g. desktop Chrome/Edge), you can instead write the sprites directly
  into a folder you pick, mirroring the desktop app's auto-created output
  folder. This button only appears where the browser supports it.

## No dependencies, no build step

`zip-writer.js` and `detect.js` are small, self-contained modules written
specifically for this app — there is no third-party library and no network
request involved in producing the `.zip` or scanning for sprites, so the
app works fully offline once the page itself is loaded (or opened from
disk).

## Running it

Just open `index.html` in a browser — no server required:

```bash
open web/index.html        # macOS
xdg-open web/index.html    # Linux
```

Or serve it (needed for some mobile browsers to allow "Add to Home
Screen", and handy for testing on a phone over your local network):

```bash
cd web
python3 -m http.server 8000
# then visit http://<your-computer's-LAN-IP>:8000 from your phone
```

It also deploys as-is to any static host (GitHub Pages, Netlify, Vercel,
S3, etc.) — the `web/` folder is the entire deployable unit.

### Add to your phone's home screen

Once served over `http://` or `https://`, most mobile browsers offer "Add
to Home Screen" (Safari: Share → Add to Home Screen; Chrome on Android:
menu → Add to Home screen), which installs it as a standalone app icon
using `manifest.webmanifest`.

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
fall back to the prefix + naming pattern set in step 4; entries outside the
loaded image's bounds are skipped and counted in the status line.

## Files

```
index.html             # markup
style.css              # responsive, mobile-first styling
app.js                 # app logic: mode handling, canvas preview, slicing, export
detect.js               # content-based sprite detection + JSON coordinate parsing
zip-writer.js           # dependency-free ZIP archive writer
manifest.webmanifest    # enables "Add to Home Screen" on mobile
```
