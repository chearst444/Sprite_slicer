# Sprite Sheet Splitter — Web App

A browser-based, mobile-friendly version of Sprite Sheet Splitter: slice a
sprite sheet into individual sprite images entirely on-device, with no
install and no server. Built as a small, dependency-free static site
(HTML/CSS/vanilla JS) so it runs the same way on a phone, a tablet, or a
desktop browser.

The full app lives in [`web/`](web/) — see [`web/README.md`](web/README.md)
for features, how to run it, and how to add it to a phone's home screen.

> Looking for the original desktop app instead? That's the Python +
> Tkinter + Pillow version, developed on a separate branch
> (`claude/sprite-sheet-splitter-gqhx2f`) / [PR #1](../../pull/1).

## Quick start

```bash
open web/index.html        # macOS — or just double-click it
xdg-open web/index.html    # Linux
```

No build step, no dependencies to install — it's ready to use as-is, and
also deploys directly to any static host (GitHub Pages, Netlify, etc.).
