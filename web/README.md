# Sprite Sheet Splitter — Web App

A mobile-friendly, browser-based version of Sprite Sheet Splitter. Same
purpose as the Python/Tkinter desktop app in the repo root, rebuilt as a
static, dependency-free web page (HTML/CSS/vanilla JS) so it runs on
**phones, tablets, and desktops** — anywhere with a modern browser.

Everything happens on-device: the sprite sheet is decoded and sliced
entirely in the browser via `<canvas>`, and nothing is ever uploaded
anywhere.

## Features

Feature parity with the desktop app:

- **Import** — tap to choose an image, or drag & drop on desktop.
- **Rows × Columns** or **Fixed Sprite Size** slicing modes, with
  configurable start offset (X, Y) and spacing between sprites.
- **Live grid preview** overlaid on the sheet, recalculated as you type.
- **Automatic naming** — sequential (`sprite_001.png`) or grid-coordinate
  (`sprite_r0_c1.png`), with a custom prefix.
- **Skip fully transparent tiles** option.
- **One-click export** — bundles every sliced sprite into a `.zip` and
  downloads it (works identically on iOS, Android, and desktop browsers).
- **Save to Folder** — on browsers that support the File System Access API
  (e.g. desktop Chrome/Edge), you can instead write the sprites directly
  into a folder you pick, mirroring the desktop app's auto-created output
  folder. This button only appears where the browser supports it.

## No dependencies, no build step

`zip-writer.js` is a small, self-contained ZIP file writer (~150 lines)
written specifically for this app — there is no third-party library and no
network request involved in producing the `.zip`, so the app works fully
offline once the page itself is loaded (or opened from disk).

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

## Files

```
index.html             # markup
style.css              # responsive, mobile-first styling
app.js                 # app logic: grid math, canvas preview, slicing, export
zip-writer.js           # dependency-free ZIP archive writer
manifest.webmanifest    # enables "Add to Home Screen" on mobile
```
